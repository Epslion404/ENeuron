#include "xaxidma.h"
#include "xaxidma_hw.h"
#include "xil_cache.h"
#include "xil_io.h"
#include "xil_printf.h"
#include "xil_types.h"
#include "xparameters.h"
#include "xstatus.h"
#include "sleep.h"
#include "xtime_l.h"
#include "b3_fixed_vector_generated.h"

#ifndef B3_BENCHMARK_SAMPLE_COUNT
#define B3_BENCHMARK_SAMPLE_COUNT 1U
#endif
#ifndef B3_BENCHMARK_UNIQUE_INPUT_COUNT
#define B3_BENCHMARK_UNIQUE_INPUT_COUNT 1U
#endif

#define TX_BUFFER_BASE 0x01006000U
#define RX_BUFFER_BASE 0x01007000U
#define MONITOR_MM2S_BASE 0x40410000U
#define MONITOR_S2MM_BASE 0x40420000U
#define MAX_FRAME_BYTES 4096U
// 当前最大响应为 19 word（76 字节）；只对头部 256 字节做填充/缓存维护，
// 避免每帧对 4 KiB 缓冲区做全量写回与无效化。
#define RX_GUARD_BYTES 256U
#define POLL_INTERVAL_US 1U
#define TRANSFER_TIMEOUT_US 1000000U
#define RESET_POLL_BUDGET 500U
#define MAGIC 0x32424E45U
#define HEADER_WORDS 8U
#define MODEL_WORDS B3_MODEL_WORD_COUNT
#define MASK_WORDS B3_MASK_WORD_COUNT
#define MODEL_ID 3U
#define MASK_EPOCH 1U
#define GROUP_MASK_GRANULARITY "group_4way"
#define STRICT_2OF4_CANDIDATE 0U
#define STRICT_2OF4_CANDIDATE_TEXT "false"
#define NPU_STATUS_BASE 0x40430000U

#if defined(B3_SPEED_BENCHMARK) || defined(B3_PL_DISTRIBUTION_REPLAY)
#define SPEED_BENCH_BASE 0x01009000U
#define SPEED_BENCH_MAGIC 0x42335350U
#define SPEED_BENCH_SAMPLES B3_BENCHMARK_SAMPLE_COUNT
#define SPEED_BENCH_RUNNING 1U
#define SPEED_BENCH_PASS 2U
#define SPEED_BENCH_FAIL 3U
#define SPEED_FAILURE_NONE 0U
#define SPEED_FAILURE_SETUP_FENCE 1U
#define SPEED_FAILURE_WARMUP_SAMPLE 2U
#define SPEED_FAILURE_MASK 3U
#define SPEED_FAILURE_SAMPLE_FENCE 4U
#define SPEED_FAILURE_SAMPLE 5U
#define SPEED_FAILURE_INDEX_NONE 0xFFFFFFFFU
#define B3_PRINT(...) ((void)0)
#else
#define B3_PRINT(...) xil_printf(__VA_ARGS__)
#endif

#if defined(B3_ACCURACY_BENCHMARK)
#define ACCURACY_BENCH_BASE 0x01010000U
#define ACCURACY_BENCH_MAGIC 0x42334143U
#define ACCURACY_BENCH_RUNNING 1U
#define ACCURACY_BENCH_PASS 2U
#define ACCURACY_BENCH_FAIL 3U
#define ACCURACY_BENCH_SAMPLE_BYTES 56U
#endif

#ifndef B3_LIVE_MASK_BATCH_K
#define B3_LIVE_MASK_BATCH_K 1U
#endif

static u32 speed_ps_us;
static u32 speed_dma_us;
static u32 last_sample_ps_us;
static u32 last_sample_dma_us;
static u32 last_sample_result_us;
static u32 last_sample_total_us;
static u32 last_mask_compute_us;
static u32 last_mask_submit_us;
static u32 last_result_crc;

static void memory_barrier(void);

#if defined(B3_SPEED_BENCHMARK)
struct speed_bench_sample {
    u32 sequence;
    u32 sample_id;
    u32 mask_epoch;
    u32 input_crc;
    u32 status;
    u32 ps_us;
    u32 dma_us;
    u32 result_us;
    u32 total_us;
    u32 npu_cycles;
    u32 execute_groups;
    u32 skip_groups;
    u32 protocol_errors;
    u32 result_crc;
    u32 mask_split_us; // [15:0] mask_compute_us, [31:16] mask_submit_us
};

struct speed_bench_record {
    u32 magic;
    u32 status;
    u32 mode_id;
    u32 sample_count;
    u32 setup_us;
    u32 mask_us;
    u32 fence_us;
    u32 total_min_us;
    u32 total_max_us;
    u32 total_sum_lo;
    u32 total_sum_hi;
    u32 dma_min_us;
    u32 dma_max_us;
    u32 dma_sum_lo;
    u32 dma_sum_hi;
    u32 ps_min_us;
    u32 ps_max_us;
    u32 ps_sum_lo;
    u32 ps_sum_hi;
    u32 result_failures;
    u32 failure_stage;
    u32 failure_sample_index;
    u32 failure_check_mask;
    u32 failure_response_words;
    u32 failure_response_sequence;
    u32 mask_compute_us;
    u32 mask_submit_us;
    struct speed_bench_sample samples[SPEED_BENCH_SAMPLES];
};

static volatile struct speed_bench_record *const speed_bench =
    (volatile struct speed_bench_record *)SPEED_BENCH_BASE;
static u32 speed_bench_active;

static u32 benchmark_mode_id(void)
{
#if defined(B3_LIVE_ENEURON)
    return 3U;
#elif defined(B3_STATIC_MIXED) || defined(B3_CALIBRATED_STATIC)
    return 2U;
#elif defined(B3_FULL_OPEN)
    return 1U;
#else
    return 0U;
#endif
}

#if defined(B3_ACCURACY_BENCHMARK)
struct accuracy_bench_sample {
    u32 mask_epoch;
    u32 input_crc;
    u32 status;
    u32 result_crc;
    s32 logits[10];
};

struct accuracy_bench_record {
    u32 magic;
    u32 status;
    u32 mode_id;
    u32 sample_count;
    u32 result_failures;
    u32 failure_stage;
    u32 failure_sample_index;
    struct accuracy_bench_sample samples[B3_BENCHMARK_SAMPLE_COUNT];
};

_Static_assert(sizeof(struct accuracy_bench_sample) == ACCURACY_BENCH_SAMPLE_BYTES,
               "accuracy sample layout must remain 56 bytes");
_Static_assert(sizeof(struct accuracy_bench_record) <= 24576U,
               "accuracy benchmark record must fit the 24 KiB scratch region");

static volatile struct accuracy_bench_record *const accuracy_bench =
    (volatile struct accuracy_bench_record *)ACCURACY_BENCH_BASE;

static void accuracy_bench_record_failure(u32 stage, u32 sample_index)
{
    ++accuracy_bench->result_failures;
    accuracy_bench->status = ACCURACY_BENCH_FAIL;
    accuracy_bench->failure_stage = stage;
    accuracy_bench->failure_sample_index = sample_index;
    memory_barrier();
}
#endif

static u32 npu_counter(u32 offset)
{
    return Xil_In32(NPU_STATUS_BASE + offset);
}

static void speed_bench_record_failure(u32 stage, u32 sample_index)
{
    speed_bench->failure_stage = stage;
    speed_bench->failure_sample_index = sample_index;
    memory_barrier();
}
#endif

static u32 xtime_delta_us(XTime start, XTime stop)
{
    XTime counts_per_us = COUNTS_PER_SECOND / 1000000U;
    if (counts_per_us == 0U) {
        counts_per_us = 1U;
    }
    return (u32)((stop - start) / counts_per_us);
}

#if defined(B3_BYPASS)
#define APPLICATION_MODE "b3_bypass"
#define SAMPLE_MASK_EPOCH 0U
#define SEND_MASK_COMMANDS 0
#elif defined(B3_STATIC_MIXED)
#define APPLICATION_MODE "b3_static_mixed"
#define SAMPLE_MASK_EPOCH MASK_EPOCH
#define SEND_MASK_COMMANDS 1
#elif defined(B3_CALIBRATED_STATIC)
#define APPLICATION_MODE "b3_calibrated_static"
#define SAMPLE_MASK_EPOCH MASK_EPOCH
#define SEND_MASK_COMMANDS 1
#elif defined(B3_LIVE_ENEURON)
#define APPLICATION_MODE "b3_live_eneuron"
#define SAMPLE_MASK_EPOCH MASK_EPOCH
#define SEND_MASK_COMMANDS 1
#elif defined(B3_FULL_OPEN)
#define APPLICATION_MODE "b3_full_open"
#define SAMPLE_MASK_EPOCH MASK_EPOCH
#define SEND_MASK_COMMANDS 1
#elif defined(B3_DENSE)
#define APPLICATION_MODE "b3_dense"
#define SAMPLE_MASK_EPOCH MASK_EPOCH
#define SEND_MASK_COMMANDS 1
#elif defined(B3_EPOCH_OVERLAP)
#define APPLICATION_MODE "b3_epoch_overlap"
#define SAMPLE_MASK_EPOCH MASK_EPOCH
#define SEND_MASK_COMMANDS 1
#elif defined(B3_PL_DISTRIBUTION_REPLAY)
#define APPLICATION_MODE "b3_distribution_replay"
#define SAMPLE_MASK_EPOCH MASK_EPOCH
#define SEND_MASK_COMMANDS 1
#else
#define APPLICATION_MODE "b2_packet_smoke"
#define SAMPLE_MASK_EPOCH MASK_EPOCH
#define SEND_MASK_COMMANDS 1
#endif

#if defined(B3_BYPASS) || defined(B3_FULL_OPEN) || defined(B3_DENSE) || defined(B3_STATIC_MIXED) || defined(B3_CALIBRATED_STATIC) || defined(B3_LIVE_ENEURON) || defined(B3_EPOCH_OVERLAP) || defined(B3_PL_DISTRIBUTION_REPLAY)
#define B3_NUMERIC_CHECK 1
static s32 last_result_logits[10];
#if !defined(B3_SPEED_BENCHMARK)
#if defined(B3_STATIC_MIXED)
static const s32 *const expected_logits = B3_STATIC_MIXED_LOGITS;
#elif defined(B3_CALIBRATED_STATIC)
/* 校准模式只用于 speed benchmark；该分支仅为非 speed 编译提供定义。 */
static const s32 *const expected_logits = B3_DENSE_LOGITS;
#elif defined(B3_LIVE_ENEURON)
static const s32 *const expected_logits = B3_LIVE_ENEURON_LOGITS;
#else
static const s32 *const expected_logits = B3_DENSE_LOGITS;
#endif
#endif

static s32 expected_logit(u32 sample_index, u32 index)
{
#if defined(B3_SPEED_BENCHMARK)
    #if defined(B3_STATIC_MIXED)
    return B3_STATIC_EXPECTED_LOGITS[sample_index][index];
    #elif defined(B3_CALIBRATED_STATIC)
    return B3_CALIBRATED_STATIC_EXPECTED_LOGITS[sample_index][index];
    #elif defined(B3_LIVE_ENEURON)
    return B3_LIVE_EXPECTED_LOGITS[sample_index][index];
    #else
    return B3_DENSE_EXPECTED_LOGITS[sample_index][index];
    #endif
#else
    return expected_logits[index];
#endif
}
#endif

#if defined(XPAR_AXIDMA_0_DEVICE_ID)
#define DMA_DEVICE_ID XPAR_AXIDMA_0_DEVICE_ID
#elif defined(XPAR_AXI_DMA_0_DEVICE_ID)
#define DMA_DEVICE_ID XPAR_AXI_DMA_0_DEVICE_ID
#else
#error "AXI DMA device ID is missing from generated xparameters.h"
#endif

enum {
    OP_MODEL_BEGIN = 1U,
    OP_MODEL_DATA = 2U,
    OP_MODEL_COMMIT = 3U,
    OP_MASK_BEGIN = 4U,
    OP_MASK_DATA = 5U,
    OP_MASK_COMMIT = 6U,
    OP_SAMPLE_FENCE = 10U,
    TYPE_COMMAND = 1U,
    TYPE_SAMPLE = 2U,
    TYPE_RESPONSE = 3U,
    TYPE_RESULT = 4U
};

static XAxiDma dma;
static UINTPTR dma_base;
static u32 sequence = 1U;

static void memory_barrier(void)
{
    __asm__ volatile("dmb sy" ::: "memory");
}

static u32 crc32_word(u32 crc, u32 data)
{
    u32 byte_index;
    u32 bit_index;
    for (byte_index = 0U; byte_index < 4U; ++byte_index) {
        u32 value = (data >> (byte_index * 8U)) & 0xFFU;
        crc ^= value;
        for (bit_index = 0U; bit_index < 8U; ++bit_index) {
            crc = (crc >> 1U) ^ (0xEDB88320U & (0U - (crc & 1U)));
        }
    }
    return crc;
}

static u32 read_reg(u32 channel_offset, u32 register_offset)
{
    return XAxiDma_ReadReg(dma_base + channel_offset, register_offset);
}

static int dma_reset_and_wait(void)
{
    u32 poll;
    XAxiDma_Reset(&dma);
    for (poll = 0U; poll < RESET_POLL_BUDGET; ++poll) {
        if (XAxiDma_ResetIsDone(&dma)) {
            XAxiDma_IntrDisable(&dma, XAXIDMA_IRQ_ALL_MASK,
                                XAXIDMA_DEVICE_TO_DMA);
            XAxiDma_IntrDisable(&dma, XAXIDMA_IRQ_ALL_MASK,
                                XAXIDMA_DMA_TO_DEVICE);
            return XST_SUCCESS;
        }
        usleep(POLL_INTERVAL_US);
    }
    return XST_FAILURE;
}

static void monitor_reset(UINTPTR base)
{
    Xil_Out32(base, 1U);
    Xil_Out32(base, 0U);
    memory_barrier();
}

static int wait_dma(u32 wait_tx, u32 wait_rx)
{
    u32 elapsed = 0U;
    while (elapsed < TRANSFER_TIMEOUT_US) {
        u32 tx_sr = read_reg(XAXIDMA_TX_OFFSET, XAXIDMA_SR_OFFSET);
        u32 rx_sr = read_reg(XAXIDMA_RX_OFFSET, XAXIDMA_SR_OFFSET);
        if ((tx_sr | rx_sr) & XAXIDMA_ERR_ALL_MASK) {
            return XST_FAILURE;
        }
        if ((!wait_tx || !XAxiDma_Busy(&dma, XAXIDMA_DMA_TO_DEVICE)) &&
            (!wait_rx || !XAxiDma_Busy(&dma, XAXIDMA_DEVICE_TO_DMA))) {
            return XST_SUCCESS;
        }
        usleep(POLL_INTERVAL_US);
        ++elapsed;
    }
    return XST_FAILURE;
}

static int fail(const char *reason)
{
    (void)reason;
    B3_PRINT("B2_PACKET_FAIL reason=%s sequence=%u tx_sr=0x%08x rx_sr=0x%08x\r\n",
               reason, sequence,
               read_reg(XAXIDMA_TX_OFFSET, XAXIDMA_SR_OFFSET),
               read_reg(XAXIDMA_RX_OFFSET, XAXIDMA_SR_OFFSET));
    return XST_FAILURE;
}

static void set_command_fields(u32 words[4], u32 opcode, u32 epoch,
                               u32 low_word)
{
    // command_word = {opcode, 4'd0, epoch, 56'd0, low_word}；
    // AXI DMA 按 little-endian 发送 4 个 32-bit beat。
    words[0] = low_word;
    words[1] = 0U;
    words[2] = (epoch & 0xFFU) << 24U;
    words[3] = (opcode << 28U) | ((epoch >> 8U) & 0x00FFFFFFU);
}

static u32 model_word_for_index(u32 index)
{
#ifdef B3_NUMERIC_CHECK
    return b3_model_word_for_index(index);
#else
    // 其余 word 保持零，三个非零 bias 用于确认板上确实完成了模型装载。
    if (index == 624U) return 3U;
    if (index == 625U) return 0xFFFFFFFBU;
    if (index == 633U) return 0xFFFFFFFFU;
    return 0U;
#endif
}

#if defined(B3_STATIC_MIXED) || defined(B3_CALIBRATED_STATIC)
static u32 static_mixed_mask_word(u32 index)
{
    /* 每 bit 控制一个四权重组；static 由黄金 manifest、calibrated 由校准集提供。 */
#if defined(B3_CALIBRATED_STATIC)
    return B3_CALIBRATED_STATIC_MASK_WORDS[index];
#else
    return B3_STATIC_MIXED_MASK_WORDS[index];
#endif
}
#endif

static int send_command(u32 opcode, u32 epoch, u32 low_word);
static int submit_frame(u32 tx_bytes, u32 rx_capacity, u32 expect_response,
                        u32 *response_words);
static int send_sample_frame_only(u32 sample_id, u32 epoch, u32 sample_index);
static int receive_result_frame_only(u32 sample_index);
static int wait_distribution_replay(void);
static int send_fence_and_check(u32 expected_epoch);
static u32 finish_frame(volatile u32 *frame, u32 word_count);
static u32 build_sample_frame(volatile u32 *frame, u32 sample_id,
                              u32 model_id, u32 epoch, u32 sample_index);
static u32 build_command_batch_frame(volatile u32 *frame,
                                     const u32 (*commands)[4],
                                     u32 command_count, u32 epoch,
                                     u32 model_id);

#if defined(B3_LIVE_ENEURON)
static u32 live_mask_words[19];
static u32 live_mask_ready;

static s8 decode_int8_byte(u32 word, u32 byte_index)
{
    return (s8)((word >> (8U * byte_index)) & 0xFFU);
}

static u32 quantize_live_evidence(s32 contribution)
{
    u32 magnitude = (contribution < 0) ? (u32)(-contribution) : (u32)contribution;
    u32 level = (magnitude + 15U) / 16U;
    return (level > 3U) ? 3U : level;
}

static u32 live_top2_mask(const u32 evidence[4])
{
    u32 order[4] = {0U, 1U, 2U, 3U};
    u32 first;
    u32 second;
    u32 tmp;
    for (first = 0U; first < 3U; ++first) {
        for (second = first + 1U; second < 4U; ++second) {
            u32 left = evidence[order[first]];
            u32 right = evidence[order[second]];
            if (right > left || (right == left && order[second] < order[first])) {
                tmp = order[first];
                order[first] = order[second];
                order[second] = tmp;
            }
        }
    }
    return (1U << order[0]) | (1U << order[1]);
}

static s32 group_mac(u32 word, const s32 *activations, u32 start)
{
    s32 acc = 0;
    u32 lane;
    if (word == 0U) {
        return 0;
    }
    for (lane = 0U; lane < 4U; ++lane) {
        acc += (s32)decode_int8_byte(word, lane) * activations[start + lane];
    }
    return acc;
}

static void apply_live_meta_mask(u32 group_base, u32 mask)
{
    u32 local;
    for (local = 0U; local < 4U; ++local) {
        if ((mask >> local) & 1U) {
            u32 bit_index = group_base + local;
            live_mask_words[bit_index / 32U] |= 1U << (bit_index & 31U);
        }
    }
}

static void compute_live_group4way_mask(u32 sample_index)
{
    s32 pixels[64];
    s32 hidden[32];
    u32 beat;
    u32 nibble;
    u32 hidden_index;
    u32 output_index;
    u32 meta;
    u32 group;
    u32 word_index;

    for (beat = 0U; beat < 8U; ++beat) {
        for (nibble = 0U; nibble < 8U; ++nibble) {
            pixels[beat * 8U + nibble] = (s32)((B3_SAMPLE_INPUT_BEATS[sample_index][beat] >> (4U * nibble)) & 0xFU);
        }
    }
    for (word_index = 0U; word_index < 19U; ++word_index) {
        live_mask_words[word_index] = 0U;
    }

    for (hidden_index = 0U; hidden_index < 32U; ++hidden_index) {
        s32 acc = (s32)model_word_for_index(512U + hidden_index);
        s32 l0_contributions[16];
        u32 evidence[4];
        for (group = 0U; group < 16U; ++group) {
            l0_contributions[group] = group_mac(
                model_word_for_index(16U * hidden_index + group),
                pixels,
                group * 4U);
            acc += l0_contributions[group];
        }
        if (acc < 0) {
            hidden[hidden_index] = 0;
        } else if (acc > 127) {
            hidden[hidden_index] = 127;
        } else {
            hidden[hidden_index] = acc;
        }
        for (meta = 0U; meta < 4U; ++meta) {
            for (group = 0U; group < 4U; ++group) {
                u32 group_index = meta * 4U + group;
                evidence[group] = quantize_live_evidence(l0_contributions[group_index]);
            }
            apply_live_meta_mask(hidden_index * 16U + meta * 4U, live_top2_mask(evidence));
        }
    }

    for (output_index = 0U; output_index < 10U; ++output_index) {
        u32 evidence[4];
        for (meta = 0U; meta < 2U; ++meta) {
            for (group = 0U; group < 4U; ++group) {
                u32 group_index = meta * 4U + group;
                s32 contribution = group_mac(
                    model_word_for_index(544U + 8U * output_index + group_index),
                    hidden,
                    group_index * 4U);
                evidence[group] = quantize_live_evidence(contribution);
            }
            apply_live_meta_mask(512U + output_index * 8U + meta * 4U, live_top2_mask(evidence));
        }
    }
    live_mask_ready = 1U;
}

static u32 live_mask_word(u32 index)
{
    return live_mask_words[index];
}
#endif

#if defined(B3_STATIC_MIXED) || defined(B3_CALIBRATED_STATIC)
static int validate_static_mixed_mask(void)
{
    u32 group;
    u32 ones = 0U;
    for (group = 0U; group < 592U; ++group) {
        if ((static_mixed_mask_word(group / 32U) >> (group & 31U)) & 1U) {
            ++ones;
        }
        if ((group & 3U) == 3U) {
            if (ones != 2U) {
                return XST_FAILURE;
            }
            ones = 0U;
        }
    }
    return ones == 0U ? XST_SUCCESS : XST_FAILURE;
}
#endif

static int send_mask_for_epoch(u32 epoch)
{
    u32 index;
    u32 command_words[21][4];
    volatile u32 *const tx = (volatile u32 *)TX_BUFFER_BASE;
    u32 frame_bytes;

#if defined(B3_STATIC_MIXED) || defined(B3_CALIBRATED_STATIC)
    if (validate_static_mixed_mask() != XST_SUCCESS) {
        return XST_FAILURE;
    }
#elif defined(B3_LIVE_ENEURON)
    if (live_mask_ready == 0U) {
        return XST_FAILURE;
    }
#endif
    set_command_fields(command_words[0], OP_MASK_BEGIN, epoch, 0U);
    for (index = 0U; index < MASK_WORDS; ++index) {
        u32 mask_word;
#if defined(B3_STATIC_MIXED) || defined(B3_CALIBRATED_STATIC)
        mask_word = static_mixed_mask_word(index);
#elif defined(B3_LIVE_ENEURON)
        mask_word = live_mask_word(index);
#else
        mask_word = B3_FULL_OPEN_MASK_WORDS[index];
#endif
        set_command_fields(command_words[index + 1U], OP_MASK_DATA, epoch, mask_word);
    }
    set_command_fields(command_words[20], OP_MASK_COMMIT, epoch, 0U);
    frame_bytes = build_command_batch_frame(tx, command_words, 21U, epoch, MODEL_ID);
    if (frame_bytes == 0U || submit_frame(frame_bytes, 0U, 0U, 0) != XST_SUCCESS) {
        return fail("mask_batch_dma");
    }
    ++sequence;
    return XST_SUCCESS;
}

static u32 finish_frame(volatile u32 *frame, u32 word_count)
{
    u32 index;
    u32 crc = 0xFFFFFFFFU;
    for (index = 0U; index < word_count; ++index) {
        crc = crc32_word(crc, frame[index]);
    }
    frame[word_count] = ~crc;
    return (word_count + 1U) * 4U;
}

static u32 build_command_frame(volatile u32 *frame, u32 opcode, u32 epoch,
                               u32 low_word, u32 model_id)
{
    u32 command[4];
    u32 index;
    frame[0] = MAGIC;
    frame[1] = 0x08000101U;
    frame[2] = 16U;
    frame[3] = sequence;
    frame[4] = 0U;
    frame[5] = model_id;
    frame[6] = epoch;
    frame[7] = 0U;
    set_command_fields(command, opcode, epoch, low_word);
    for (index = 0U; index < 4U; ++index) {
        frame[8U + index] = command[index];
    }
    return finish_frame(frame, 12U);
}

/* 一次 DMA 将整组 mask 命令交给 PL ingress，保留逐 command 的原子语义。 */
static u32 build_command_batch_frame(volatile u32 *frame,
                                     const u32 (*commands)[4],
                                     u32 command_count, u32 epoch,
                                     u32 model_id)
{
    u32 index;
    u32 word_index;

    if (command_count == 0U || command_count > 253U) {
        return 0U;
    }
    frame[0] = MAGIC;
    frame[1] = 0x08000101U;
    frame[2] = command_count * 16U;
    frame[3] = sequence;
    frame[4] = 0U;
    frame[5] = model_id;
    frame[6] = epoch;
    frame[7] = 0U;
    for (index = 0U; index < command_count; ++index) {
        for (word_index = 0U; word_index < 4U; ++word_index) {
            frame[8U + index * 4U + word_index] = commands[index][word_index];
        }
    }
    return finish_frame(frame, 8U + command_count * 4U);
}

static u32 build_sample_frame(volatile u32 *frame, u32 sample_id,
                              u32 model_id, u32 epoch, u32 sample_index)
{
    u32 index;
    frame[0] = MAGIC;
    frame[1] = 0x08000201U;
    frame[2] = 32U;
    frame[3] = sequence;
    frame[4] = sample_id;
    frame[5] = model_id;
    frame[6] = epoch;
    frame[7] = 0U;
    for (index = 0U; index < 8U; ++index) {
#ifdef B3_NUMERIC_CHECK
        frame[8U + index] = B3_SAMPLE_INPUT_BEATS[sample_index][index];
#else
        frame[8U + index] = 0U;
#endif
    }
    return finish_frame(frame, 16U);
}

static int submit_frame(u32 tx_bytes, u32 rx_capacity, u32 expect_response,
                        u32 *response_words)
{
    volatile u32 *const rx = (volatile u32 *)RX_BUFFER_BASE;
    u32 status;
    u32 index;
    u32 guard_bytes = rx_capacity < RX_GUARD_BYTES ? rx_capacity : RX_GUARD_BYTES;

    // probe 在每个 TLAST 后自动停用；每个 DMA 帧都必须重新打开旁路。
    monitor_reset(MONITOR_MM2S_BASE);
    if (expect_response != 0U) {
        monitor_reset(MONITOR_S2MM_BASE);
    }

    if (expect_response != 0U) {
        for (index = 0U; index < guard_bytes / 4U; ++index) {
            rx[index] = 0xA5A5A5A5U;
        }
        Xil_DCacheFlushRange(RX_BUFFER_BASE, guard_bytes);
        status = XAxiDma_SimpleTransfer(&dma, RX_BUFFER_BASE, rx_capacity,
                                        XAXIDMA_DEVICE_TO_DMA);
        if (status != XST_SUCCESS) {
            return XST_FAILURE;
        }
    }
    Xil_DCacheFlushRange(TX_BUFFER_BASE, tx_bytes);
    memory_barrier();
    status = XAxiDma_SimpleTransfer(&dma, TX_BUFFER_BASE, tx_bytes,
                                    XAXIDMA_DMA_TO_DEVICE);
    if (status != XST_SUCCESS) {
        return XST_FAILURE;
    }
    // BTT 写入后 DMA 的 idle 位可能仍保留上一帧状态；留一小段时间让
    // MM2S 真正进入运行态，避免连续短帧在旧 idle 状态下重叠提交。
    usleep(2U);
    status = wait_dma(1U, expect_response != 0U ? 1U : 0U);
    if (status != XST_SUCCESS) {
        return XST_FAILURE;
    }
    if (expect_response != 0U) {
        Xil_DCacheInvalidateRange(RX_BUFFER_BASE, guard_bytes);
        memory_barrier();
        if (rx[0] != MAGIC) {
            return XST_FAILURE;
        }
        *response_words = 8U + (rx[2] / 4U) + 1U;
        if (*response_words > guard_bytes / 4U) {
            return XST_FAILURE;
        }
    }
    return XST_SUCCESS;
}

#if defined(B3_PL_DISTRIBUTION_REPLAY)
static int send_sample_frame_only(u32 sample_id, u32 epoch, u32 sample_index)
{
    volatile u32 *const tx = (volatile u32 *)TX_BUFFER_BASE;
    u32 frame_bytes = build_sample_frame(tx, sample_id, MODEL_ID, epoch, sample_index);
    if (submit_frame(frame_bytes, 0U, 0U, 0) != XST_SUCCESS) {
        return fail("distribution_sample_dma");
    }
    ++sequence;
    return XST_SUCCESS;
}

static int receive_result_frame_only(u32 sample_index)
{
    volatile u32 *const rx = (volatile u32 *)RX_BUFFER_BASE;
    u32 status;
    u32 index;
    u32 crc;
    const u32 guard_bytes = RX_GUARD_BYTES;
    const u32 expected_sample_id = B3_SAMPLE_IDS[sample_index];

    monitor_reset(MONITOR_S2MM_BASE);
    for (index = 0U; index < guard_bytes / 4U; ++index) {
        rx[index] = 0xA5A5A5A5U;
    }
    Xil_DCacheFlushRange(RX_BUFFER_BASE, guard_bytes);
    status = XAxiDma_SimpleTransfer(&dma, RX_BUFFER_BASE, MAX_FRAME_BYTES,
                                    XAXIDMA_DEVICE_TO_DMA);
    if (status != XST_SUCCESS || wait_dma(0U, 1U) != XST_SUCCESS) {
        return fail("distribution_result_dma");
    }
    Xil_DCacheInvalidateRange(RX_BUFFER_BASE, guard_bytes);
    memory_barrier();
    if (rx[0] != MAGIC || rx[1] != 0x08000401U || rx[2] != 40U ||
        rx[4] != expected_sample_id || rx[5] != MODEL_ID || rx[6] != SAMPLE_MASK_EPOCH ||
        rx[7] != 0U) {
        return fail("distribution_result_metadata");
    }
    crc = 0xFFFFFFFFU;
    for (index = 0U; index < 18U; ++index) {
        crc = crc32_word(crc, rx[index]);
    }
    if (rx[18] != ~crc) {
        return fail("distribution_result_crc");
    }
    for (index = 0U; index < 10U; ++index) {
        if ((s32)rx[8U + index] != B3_DENSE_EXPECTED_LOGITS[sample_index][index]) {
            return fail("distribution_result_logit");
        }
    }
    last_result_crc = rx[18];
    return XST_SUCCESS;
}

static int wait_distribution_replay(void)
{
    u32 elapsed_us;
    for (elapsed_us = 0U; elapsed_us < 10000000U; elapsed_us += 10U) {
        u32 replay_status = Xil_In32(NPU_STATUS_BASE + 0x64U);
        u32 capture_count = Xil_In32(NPU_STATUS_BASE + 0x70U);
        u32 completed_count = Xil_In32(NPU_STATUS_BASE + 0x68U);
        u32 protocol_errors = Xil_In32(NPU_STATUS_BASE + 0x60U);
        if (replay_status == 5U || protocol_errors != 0U) {
            return fail("distribution_replay_status");
        }
        if (replay_status == 4U && capture_count == B3_BENCHMARK_SAMPLE_COUNT &&
            completed_count == 10000U) {
            return XST_SUCCESS;
        }
        usleep(10U);
    }
    return fail("distribution_replay_timeout");
}

static int run_distribution_replay(void)
{
    u32 sample_index;
    const u32 final_sample_index = (10000U - 1U) % B3_BENCHMARK_SAMPLE_COUNT;

    if (send_fence_and_check(0U) != XST_SUCCESS ||
        send_sample_frame_only(B3_SAMPLE_IDS[0], SAMPLE_MASK_EPOCH, 0U) != XST_SUCCESS) {
        return XST_FAILURE;
    }
    for (sample_index = 1U; sample_index < B3_BENCHMARK_SAMPLE_COUNT; ++sample_index) {
        if (send_fence_and_check(SAMPLE_MASK_EPOCH) != XST_SUCCESS ||
            send_sample_frame_only(B3_SAMPLE_IDS[sample_index], SAMPLE_MASK_EPOCH,
                                   sample_index) != XST_SUCCESS) {
            return XST_FAILURE;
        }
    }
    if (wait_distribution_replay() != XST_SUCCESS ||
        receive_result_frame_only(final_sample_index) != XST_SUCCESS) {
        return XST_FAILURE;
    }
    return XST_SUCCESS;
}
#endif

static int send_command(u32 opcode, u32 epoch, u32 low_word)
{
    volatile u32 *const tx = (volatile u32 *)TX_BUFFER_BASE;
    u32 frame_bytes = build_command_frame(tx, opcode, epoch, low_word, MODEL_ID);
    int status = submit_frame(frame_bytes, 0U, 0U, 0);
    if (status != XST_SUCCESS) {
        return fail("command_dma");
    }
    ++sequence;
    return XST_SUCCESS;
}

static int send_fence_and_check(u32 expected_epoch)
{
    volatile u32 *const tx = (volatile u32 *)TX_BUFFER_BASE;
    volatile u32 *const rx = (volatile u32 *)RX_BUFFER_BASE;
    u32 frame_bytes;
    u32 response_words = 0U;
    u32 request_sequence = sequence;
    frame_bytes = build_command_frame(tx, OP_SAMPLE_FENCE, 0U, 0x00000F00U, MODEL_ID);
    if (submit_frame(frame_bytes, MAX_FRAME_BYTES, 1U, &response_words) != XST_SUCCESS) {
#if defined(B3_SPEED_BENCHMARK)
        if (speed_bench_active != 0U) {
            speed_bench->failure_check_mask = 0U;
            speed_bench->failure_response_words = response_words;
            speed_bench->failure_response_sequence = 0U;
        }
#endif
        return fail("fence_dma");
    }
    // 响应缓存已由 submit_frame 按 RX_GUARD_BYTES 失效，这里不再重复全量 invalidate。
    // fence response 的 active epoch 位于 128-bit payload 的中间两个 16-bit lane；
    // DMA 以 little-endian 32-bit beat 回写，因此不能把 rx[9] 固定视为 0。
    u32 expected_epoch_word1 = (expected_epoch & 0xFFFFU) << 16U;
    u32 expected_epoch_word2 = 0x0F000000U | ((expected_epoch >> 16U) & 0xFFFFU);
    if (response_words != 13U || rx[1] != 0x08000301U || rx[2] != 16U ||
        rx[3] != request_sequence || rx[5] != MODEL_ID || rx[6] != 0U ||
        rx[8] != 0U || rx[9] != expected_epoch_word1 || rx[10] != expected_epoch_word2 ||
        rx[11] != 0xD0A00000U) {
#if defined(B3_SPEED_BENCHMARK)
        if (speed_bench_active != 0U) {
            u32 check_mask = 0U;
            if (response_words != 13U) check_mask |= 1U;
            if (rx[1] != 0x08000301U) check_mask |= 2U;
            if (rx[2] != 16U) check_mask |= 4U;
            if (rx[3] != request_sequence) check_mask |= 8U;
            if (rx[5] != MODEL_ID) check_mask |= 16U;
            if (rx[6] != 0U) check_mask |= 32U;
            if (rx[8] != 0U) check_mask |= 64U;
            if (rx[9] != expected_epoch_word1) check_mask |= 128U;
            if (rx[10] != expected_epoch_word2) check_mask |= 256U;
            if (rx[11] != 0xD0A00000U) check_mask |= 512U;
            speed_bench->failure_check_mask = check_mask;
            speed_bench->failure_response_words = response_words;
            speed_bench->failure_response_sequence = rx[3];
        }
#endif
        return fail("fence_response");
    }
    B3_PRINT("B2_PACKET_FENCE_PASS sequence=%u response_words=%u\r\n",
               request_sequence, response_words);
    ++sequence;
    return XST_SUCCESS;
}

static int send_sample_and_check(u32 sample_id, u32 epoch, u32 sample_index)
{
    volatile u32 *const tx = (volatile u32 *)TX_BUFFER_BASE;
    volatile u32 *const rx = (volatile u32 *)RX_BUFFER_BASE;
    u32 frame_bytes;
    u32 response_words = 0U;
    u32 request_sequence = sequence;
    XTime t_ps0;
    XTime t_dma0;
    XTime t_dma1;
    XTime t_result1;
    XTime_GetTime(&t_ps0);
    frame_bytes = build_sample_frame(tx, sample_id, MODEL_ID, epoch, sample_index);
    XTime_GetTime(&t_dma0);
    last_sample_ps_us = xtime_delta_us(t_ps0, t_dma0);
    speed_ps_us += last_sample_ps_us;
    if (submit_frame(frame_bytes, MAX_FRAME_BYTES, 1U, &response_words) != XST_SUCCESS) {
        return fail("sample_dma");
    }
    XTime_GetTime(&t_dma1);
    last_sample_dma_us = xtime_delta_us(t_dma0, t_dma1);
    speed_dma_us = last_sample_dma_us;
    // 响应缓存已由 submit_frame 按 RX_GUARD_BYTES 失效，这里不再重复全量 invalidate。
    if (response_words != 19U || rx[1] != 0x08000401U || rx[2] != 40U ||
        rx[3] != request_sequence || rx[4] != sample_id ||
        rx[5] != MODEL_ID || rx[6] != epoch) {
        return fail("result_response");
    }
#ifdef B3_NUMERIC_CHECK
    {
        u32 index;
        u32 crc = 0xFFFFFFFFU;
        for (index = 0U; index < 18U; ++index) {
            crc = crc32_word(crc, rx[index]);
        }
        if (rx[18] != ~crc) {
            return fail("b3_result_crc");
        }
        for (index = 0U; index < 10U; ++index) {
            last_result_logits[index] = (s32)rx[8U + index];
            if (last_result_logits[index] != expected_logit(sample_index, index)) {
                B3_PRINT("B3_LOGIT_FAIL index=%u expected=%d actual=%d\r\n",
                           index, expected_logit(sample_index, index),
                           last_result_logits[index]);
                return fail("b3_logit_mismatch");
            }
        }
        last_result_crc = rx[18];
        #if defined(B3_BYPASS)
        B3_PRINT("B3_BYPASS_PASS sequence=%u sample_id=0x%08x response_words=%u mask_words=0 logits=%d,%d,%d,%d,%d,%d,%d,%d,%d,%d\r\n",
                   request_sequence, sample_id, response_words,
                   last_result_logits[0], last_result_logits[1], last_result_logits[2],
                   last_result_logits[3], last_result_logits[4], last_result_logits[5],
                   last_result_logits[6], last_result_logits[7], last_result_logits[8],
                   last_result_logits[9]);
        #elif defined(B3_STATIC_MIXED)
        B3_PRINT("B3_STATIC_MIXED_PASS sequence=%u sample_id=0x%08x response_words=%u mask_words=%u logits=%d,%d,%d,%d,%d,%d,%d,%d,%d,%d group_reads=296 group_skips=296 granularity=%s strict_2of4_candidate=%u\r\n",
                   request_sequence, sample_id, response_words, MASK_WORDS,
                   last_result_logits[0], last_result_logits[1], last_result_logits[2],
                   last_result_logits[3], last_result_logits[4], last_result_logits[5],
                   last_result_logits[6], last_result_logits[7], last_result_logits[8],
                   last_result_logits[9],
                   GROUP_MASK_GRANULARITY, STRICT_2OF4_CANDIDATE);
        #elif defined(B3_LIVE_ENEURON)
        B3_PRINT("B3_LIVE_ENEURON_PASS sequence=%u sample_id=0x%08x response_words=%u mask_words=%u logits=%d,%d,%d,%d,%d,%d,%d,%d,%d,%d group_reads=296 group_skips=296 granularity=%s strict_2of4_candidate=%u decision_source=live_eneuron_s2\r\n",
                   request_sequence, sample_id, response_words, MASK_WORDS,
                   last_result_logits[0], last_result_logits[1], last_result_logits[2],
                   last_result_logits[3], last_result_logits[4], last_result_logits[5],
                   last_result_logits[6], last_result_logits[7], last_result_logits[8],
                   last_result_logits[9],
                   GROUP_MASK_GRANULARITY, STRICT_2OF4_CANDIDATE);
        #elif defined(B3_FULL_OPEN)
        B3_PRINT("B3_FULL_OPEN_PASS sequence=%u sample_id=0x%08x response_words=%u mask_words=%u logits=%d,%d,%d,%d,%d,%d,%d,%d,%d,%d\r\n",
                   request_sequence, sample_id, response_words, MASK_WORDS,
                   last_result_logits[0], last_result_logits[1], last_result_logits[2],
                   last_result_logits[3], last_result_logits[4], last_result_logits[5],
                   last_result_logits[6], last_result_logits[7], last_result_logits[8],
                   last_result_logits[9]);
        #elif defined(B3_EPOCH_OVERLAP)
        B3_PRINT("B3_EPOCH_OVERLAP_PASS sequence=%u sample_id=0x%08x response_words=%u mask_words=%u logits=%d,%d,%d,%d,%d,%d,%d,%d,%d,%d result_epoch=%u\r\n",
                   request_sequence, sample_id, response_words, MASK_WORDS,
                   last_result_logits[0], last_result_logits[1], last_result_logits[2],
                   last_result_logits[3], last_result_logits[4], last_result_logits[5],
                   last_result_logits[6], last_result_logits[7], last_result_logits[8],
                   last_result_logits[9], SAMPLE_MASK_EPOCH);
        #else
        B3_PRINT("B3_DENSE_PASS sequence=%u sample_id=0x%08x response_words=%u mask_words=%u logits=%d,%d,%d,%d,%d,%d,%d,%d,%d,%d\r\n",
                   request_sequence, sample_id, response_words, MASK_WORDS,
                   last_result_logits[0], last_result_logits[1], last_result_logits[2],
                   last_result_logits[3], last_result_logits[4], last_result_logits[5],
                   last_result_logits[6], last_result_logits[7], last_result_logits[8],
                   last_result_logits[9]);
        #endif
    }
#else
    if (rx[8] != 3U || rx[9] != 0xFFFFFFFBU || rx[17] != 0xFFFFFFFFU) {
        return fail("result_response");
    }
    B3_PRINT("B2_PACKET_RESULT_PASS sequence=%u sample_id=0x%08x response_words=%u\r\n",
               request_sequence, sample_id, response_words);
#endif
    XTime_GetTime(&t_result1);
    last_sample_result_us = xtime_delta_us(t_dma1, t_result1);
    last_sample_total_us = xtime_delta_us(t_ps0, t_result1);
    B3_PRINT("B3_SPEED_SPLIT ps_us=%u dma_us=%u result_us=%u total_us=%u\r\n",
             last_sample_ps_us, last_sample_dma_us,
             last_sample_result_us, last_sample_total_us);
    ++sequence;
    return XST_SUCCESS;
}

#if defined(B3_SPEED_BENCHMARK)
static void benchmark_add_u32(volatile u32 *low, volatile u32 *high, u32 value)
{
    u32 previous = *low;
    *low += value;
    if (*low < previous) {
        ++(*high);
    }
}

static int run_speed_benchmark(void)
{
    XTime setup_start;
    XTime setup_stop;
    u32 baseline_execute;
    u32 baseline_skip;
    u32 sample_index;
    u32 active_epoch;

    speed_bench->magic = SPEED_BENCH_MAGIC;
    speed_bench->status = SPEED_BENCH_RUNNING;
    speed_bench->mode_id = benchmark_mode_id();
    speed_bench->sample_count = 0U;
    speed_bench->result_failures = 0U;
    speed_bench->total_min_us = 0xFFFFFFFFU;
    speed_bench->dma_min_us = 0xFFFFFFFFU;
    speed_bench->ps_min_us = 0xFFFFFFFFU;
    speed_bench->setup_us = 0U;
    speed_bench->mask_us = 0U;
    speed_bench->mask_compute_us = 0U;
    speed_bench->mask_submit_us = 0U;
    speed_bench->fence_us = 0U;
    speed_bench->total_max_us = 0U;
    speed_bench->dma_max_us = 0U;
    speed_bench->ps_max_us = 0U;
    speed_bench->total_sum_lo = 0U;
    speed_bench->total_sum_hi = 0U;
    speed_bench->dma_sum_lo = 0U;
    speed_bench->dma_sum_hi = 0U;
    speed_bench->ps_sum_lo = 0U;
    speed_bench->ps_sum_hi = 0U;
    speed_bench->failure_stage = SPEED_FAILURE_NONE;
    speed_bench->failure_sample_index = SPEED_FAILURE_INDEX_NONE;
    speed_bench->failure_check_mask = 0U;
    speed_bench->failure_response_words = 0U;
    speed_bench->failure_response_sequence = 0U;
#if defined(B3_ACCURACY_BENCHMARK)
    accuracy_bench->magic = ACCURACY_BENCH_MAGIC;
    accuracy_bench->status = ACCURACY_BENCH_RUNNING;
    accuracy_bench->mode_id = benchmark_mode_id();
    accuracy_bench->sample_count = 0U;
    accuracy_bench->result_failures = 0U;
    accuracy_bench->failure_stage = SPEED_FAILURE_NONE;
    accuracy_bench->failure_sample_index = SPEED_FAILURE_INDEX_NONE;
#endif
#if defined(B3_LIVE_ENEURON)
    if (B3_BENCHMARK_UNIQUE_INPUT_COUNT > 1U && B3_LIVE_MASK_BATCH_K != 1U) {
        speed_bench_record_failure(SPEED_FAILURE_MASK, SPEED_FAILURE_INDEX_NONE);
#if defined(B3_ACCURACY_BENCHMARK)
        accuracy_bench_record_failure(SPEED_FAILURE_MASK, SPEED_FAILURE_INDEX_NONE);
#endif
        speed_bench->status = SPEED_BENCH_FAIL;
        memory_barrier();
        return XST_FAILURE;
    }
#endif
    speed_bench_active = 1U;
    for (sample_index = 0U; sample_index < SPEED_BENCH_SAMPLES; ++sample_index) {
        speed_bench->samples[sample_index].sequence = 0U;
        speed_bench->samples[sample_index].sample_id = 0U;
        speed_bench->samples[sample_index].mask_epoch = 0U;
        speed_bench->samples[sample_index].input_crc = 0U;
        speed_bench->samples[sample_index].status = 0U;
        speed_bench->samples[sample_index].ps_us = 0U;
        speed_bench->samples[sample_index].dma_us = 0U;
        speed_bench->samples[sample_index].result_us = 0U;
        speed_bench->samples[sample_index].total_us = 0U;
        speed_bench->samples[sample_index].npu_cycles = 0U;
        speed_bench->samples[sample_index].execute_groups = 0U;
        speed_bench->samples[sample_index].skip_groups = 0U;
        speed_bench->samples[sample_index].protocol_errors = 0U;
        speed_bench->samples[sample_index].result_crc = 0U;
        speed_bench->samples[sample_index].mask_split_us = 0U;
#if defined(B3_ACCURACY_BENCHMARK)
        accuracy_bench->samples[sample_index].mask_epoch = 0U;
        accuracy_bench->samples[sample_index].input_crc = 0U;
        accuracy_bench->samples[sample_index].status = 0U;
        accuracy_bench->samples[sample_index].result_crc = 0U;
        for (u32 logit_index = 0U; logit_index < 10U; ++logit_index) {
            accuracy_bench->samples[sample_index].logits[logit_index] = 0;
        }
#endif
    }
    memory_barrier();

    XTime_GetTime(&setup_start);
    // mask 在首个样本 beat 被接受时才从 published 变为 active；首个 fence 仍应回显 0。
    if (send_fence_and_check(0U) != XST_SUCCESS) {
        speed_bench_record_failure(SPEED_FAILURE_SETUP_FENCE, SPEED_FAILURE_INDEX_NONE);
#if defined(B3_ACCURACY_BENCHMARK)
        accuracy_bench_record_failure(SPEED_FAILURE_SETUP_FENCE, SPEED_FAILURE_INDEX_NONE);
#endif
        speed_bench->status = SPEED_BENCH_FAIL;
        memory_barrier();
        return XST_FAILURE;
    }
    if (send_sample_and_check(B3_SAMPLE_IDS[0], SAMPLE_MASK_EPOCH, 0U) != XST_SUCCESS) {
        speed_bench_record_failure(SPEED_FAILURE_WARMUP_SAMPLE, 0U);
#if defined(B3_ACCURACY_BENCHMARK)
        accuracy_bench_record_failure(SPEED_FAILURE_WARMUP_SAMPLE, 0U);
#endif
        speed_bench->status = SPEED_BENCH_FAIL;
        memory_barrier();
        return XST_FAILURE;
    }
    active_epoch = SAMPLE_MASK_EPOCH;
    XTime_GetTime(&setup_stop);
    speed_bench->setup_us = xtime_delta_us(setup_start, setup_stop);

    baseline_execute = npu_counter(0x48U);
    baseline_skip = npu_counter(0x4CU);
    for (sample_index = 0U; sample_index < SPEED_BENCH_SAMPLES; ++sample_index) {
        volatile struct speed_bench_sample *sample =
            &speed_bench->samples[sample_index];
        u32 sample_sequence = sequence;
        u32 sample_epoch = active_epoch;
        XTime sample_start;
        XTime sample_stop;
#if defined(B3_LIVE_ENEURON)
        XTime mask_start;
        XTime mask_compute_stop;
        XTime mask_stop;
#endif
        XTime fence_start;
        XTime fence_stop;

        XTime_GetTime(&sample_start);
#if defined(B3_LIVE_ENEURON)
        if ((sample_index % B3_LIVE_MASK_BATCH_K) == 0U) {
            // 每个批次只更新一次 mask；批次内复用同一 active epoch。
            sample_epoch = MASK_EPOCH + (sample_index / B3_LIVE_MASK_BATCH_K) + 1U;
            XTime_GetTime(&mask_start);
            compute_live_group4way_mask(sample_index);
            XTime_GetTime(&mask_compute_stop);
            if (live_mask_ready == 0U || send_mask_for_epoch(sample_epoch) != XST_SUCCESS) {
                speed_bench_record_failure(SPEED_FAILURE_MASK, sample_index);
                ++speed_bench->result_failures;
#if defined(B3_ACCURACY_BENCHMARK)
                accuracy_bench_record_failure(SPEED_FAILURE_MASK, sample_index);
#endif
                speed_bench->status = SPEED_BENCH_FAIL;
                memory_barrier();
                return XST_FAILURE;
            }
            XTime_GetTime(&mask_stop);
            last_mask_compute_us = xtime_delta_us(mask_start, mask_compute_stop);
            last_mask_submit_us = xtime_delta_us(mask_compute_stop, mask_stop);
            speed_bench->mask_compute_us += last_mask_compute_us;
            speed_bench->mask_submit_us += last_mask_submit_us;
            speed_bench->mask_us += xtime_delta_us(mask_start, mask_stop);
        } else {
            sample_epoch = active_epoch;
            last_mask_compute_us = 0U;
            last_mask_submit_us = 0U;
        }
#endif

        // fence 是每个样本的协议边界，不能与 mask 更新一起摊销。
        XTime_GetTime(&fence_start);
        if (send_fence_and_check(active_epoch) != XST_SUCCESS) {
            speed_bench_record_failure(SPEED_FAILURE_SAMPLE_FENCE, sample_index);
            ++speed_bench->result_failures;
#if defined(B3_ACCURACY_BENCHMARK)
            accuracy_bench_record_failure(SPEED_FAILURE_SAMPLE_FENCE, sample_index);
#endif
            speed_bench->status = SPEED_BENCH_FAIL;
            memory_barrier();
            return XST_FAILURE;
        }
        XTime_GetTime(&fence_stop);
        speed_bench->fence_us += xtime_delta_us(fence_start, fence_stop);

        if (send_sample_and_check(B3_SAMPLE_IDS[sample_index], sample_epoch, sample_index) != XST_SUCCESS) {
            speed_bench_record_failure(SPEED_FAILURE_SAMPLE, sample_index);
            ++speed_bench->result_failures;
#if defined(B3_ACCURACY_BENCHMARK)
            accuracy_bench_record_failure(SPEED_FAILURE_SAMPLE, sample_index);
#endif
            speed_bench->status = SPEED_BENCH_FAIL;
            memory_barrier();
            return XST_FAILURE;
        }
        XTime_GetTime(&sample_stop);
        sample->sequence = sample_sequence;
        sample->sample_id = B3_SAMPLE_IDS[sample_index];
        sample->mask_epoch = sample_epoch;
        sample->input_crc = B3_SAMPLE_INPUT_CRC[sample_index];
        sample->status = SPEED_BENCH_PASS;
        sample->ps_us = last_sample_ps_us;
        sample->dma_us = last_sample_dma_us;
        sample->result_us = last_sample_result_us;
        sample->total_us = last_sample_total_us;
        sample->total_us = xtime_delta_us(sample_start, sample_stop);
        sample->npu_cycles = npu_counter(0x5CU);
        sample->execute_groups = npu_counter(0x48U) - baseline_execute;
        sample->skip_groups = npu_counter(0x4CU) - baseline_skip;
        sample->protocol_errors = npu_counter(0x60U);
        sample->result_crc = last_result_crc;
        sample->mask_split_us =
            (last_mask_compute_us > 0xFFFFU ? 0xFFFFU : last_mask_compute_us) |
            ((last_mask_submit_us > 0xFFFFU ? 0xFFFFU : last_mask_submit_us) << 16U);
#if defined(B3_ACCURACY_BENCHMARK)
        accuracy_bench->samples[sample_index].mask_epoch = sample_epoch;
        accuracy_bench->samples[sample_index].input_crc = B3_SAMPLE_INPUT_CRC[sample_index];
        accuracy_bench->samples[sample_index].status = ACCURACY_BENCH_PASS;
        accuracy_bench->samples[sample_index].result_crc = last_result_crc;
        for (u32 logit_index = 0U; logit_index < 10U; ++logit_index) {
            accuracy_bench->samples[sample_index].logits[logit_index] = last_result_logits[logit_index];
        }
        accuracy_bench->sample_count = sample_index + 1U;
#endif
        baseline_execute = npu_counter(0x48U);
        baseline_skip = npu_counter(0x4CU);
        active_epoch = sample_epoch;

        if (sample_index == 0U || sample->total_us < speed_bench->total_min_us) {
            speed_bench->total_min_us = sample->total_us;
        }
        if (sample_index == 0U || sample->total_us > speed_bench->total_max_us) {
            speed_bench->total_max_us = sample->total_us;
        }
        if (sample_index == 0U || sample->dma_us < speed_bench->dma_min_us) {
            speed_bench->dma_min_us = sample->dma_us;
        }
        if (sample_index == 0U || sample->dma_us > speed_bench->dma_max_us) {
            speed_bench->dma_max_us = sample->dma_us;
        }
        if (sample_index == 0U || sample->ps_us < speed_bench->ps_min_us) {
            speed_bench->ps_min_us = sample->ps_us;
        }
        if (sample_index == 0U || sample->ps_us > speed_bench->ps_max_us) {
            speed_bench->ps_max_us = sample->ps_us;
        }
        benchmark_add_u32(&speed_bench->total_sum_lo,
                          &speed_bench->total_sum_hi, sample->total_us);
        benchmark_add_u32(&speed_bench->dma_sum_lo,
                          &speed_bench->dma_sum_hi, sample->dma_us);
        benchmark_add_u32(&speed_bench->ps_sum_lo,
                          &speed_bench->ps_sum_hi, sample->ps_us);
        speed_bench->sample_count = sample_index + 1U;
        memory_barrier();
    }
    speed_bench->status = SPEED_BENCH_PASS;
#if defined(B3_ACCURACY_BENCHMARK)
    accuracy_bench->status = ACCURACY_BENCH_PASS;
    memory_barrier();
#endif
    memory_barrier();
    return XST_SUCCESS;
}
#endif

int main(void)
{
    XAxiDma_Config *config;
    u32 index;

    Xil_DCacheDisable();
    B3_PRINT("B2_PACKET_BEGIN\r\n");
    B3_PRINT("APPLICATION_MODE=%s\r\n", APPLICATION_MODE);
    B3_PRINT("PROTOCOL=ENB2_PACKET_NPU_V1\r\n");
    B3_PRINT("TARGET=xc7z020clg484-2\r\n");
    B3_PRINT("TX_BUFFER=0x%08x RX_BUFFER=0x%08x\r\n",
               TX_BUFFER_BASE, RX_BUFFER_BASE);

    config = XAxiDma_LookupConfig(DMA_DEVICE_ID);
    if (config == NULL || XAxiDma_CfgInitialize(&dma, config) != XST_SUCCESS) {
        return fail("dma_init");
    }
    dma_base = config->BaseAddr;
    if (XAxiDma_HasSg(&dma) || dma_reset_and_wait() != XST_SUCCESS) {
        return fail("dma_reset");
    }
    // 两个 AXI-Stream probe 默认 inactive；先清零计数并显式打开旁路。
    monitor_reset(MONITOR_MM2S_BASE);
    monitor_reset(MONITOR_S2MM_BASE);

    if (send_command(OP_MODEL_BEGIN, 0U, 0U) != XST_SUCCESS) return XST_FAILURE;
    for (index = 0U; index < MODEL_WORDS; ++index) {
        if (send_command(OP_MODEL_DATA, 0U, model_word_for_index(index)) != XST_SUCCESS) return XST_FAILURE;
        if ((index & 127U) == 127U) {
            B3_PRINT("B2_PACKET_MODEL_PROGRESS words=%u\r\n", index + 1U);
        }
    }
    if (send_command(OP_MODEL_COMMIT, 0U, 0U) != XST_SUCCESS) return XST_FAILURE;
#if SEND_MASK_COMMANDS
#if defined(B3_STATIC_MIXED)
    B3_PRINT("B3_STATIC_MASK_VALID groups=592 active_groups=296 skipped_groups=296 granularity=%s strict_2of4_candidate=%s\r\n",
               GROUP_MASK_GRANULARITY, STRICT_2OF4_CANDIDATE_TEXT);
#endif
#if defined(B3_LIVE_ENEURON)
    {
        XTime t0;
        XTime t1;
        XTime_GetTime(&t0);
        compute_live_group4way_mask(0U);
        XTime_GetTime(&t1);
        speed_ps_us += xtime_delta_us(t0, t1);
    }
    if (live_mask_ready == 0U) {
        return fail("live_mask_compute");
    }
    B3_PRINT("B3_LIVE_MASK_VALID groups=592 active_groups=296 skipped_groups=296 granularity=%s strict_2of4_candidate=%s decision_source=live_eneuron_s2 gain=1 score=S2\r\n",
               GROUP_MASK_GRANULARITY, STRICT_2OF4_CANDIDATE_TEXT);
#endif
    if (send_mask_for_epoch(MASK_EPOCH) != XST_SUCCESS) return XST_FAILURE;
#if defined(B3_EPOCH_OVERLAP)
    B3_PRINT("B3_11_PENDING_HOLD expected_active=0 expected_pending=1\r\n");
    sleep(8U);
#endif
#endif
#if defined(B3_PL_DISTRIBUTION_REPLAY)
    if (run_distribution_replay() != XST_SUCCESS) return XST_FAILURE;
#elif defined(B3_SPEED_BENCHMARK)
    if (run_speed_benchmark() != XST_SUCCESS) return XST_FAILURE;
#else
    if (send_fence_and_check(0U) != XST_SUCCESS) return XST_FAILURE;
    if (send_sample_and_check(B3_SAMPLE_IDS[0], SAMPLE_MASK_EPOCH, 0U) != XST_SUCCESS) return XST_FAILURE;
#endif

#ifdef B3_NUMERIC_CHECK
    B3_PRINT("B2_PACKET_PASS model_words=%u mask_words=%u\r\n",
               MODEL_WORDS, SEND_MASK_COMMANDS ? MASK_WORDS : 0U);
    #if defined(B3_BYPASS)
    B3_PRINT("B3_BYPASS_PASS model_words=%u mask_words=0\r\n", MODEL_WORDS);
    #elif defined(B3_STATIC_MIXED)
    B3_PRINT("B3_STATIC_MIXED_PASS model_words=%u mask_words=%u group_reads=296 group_skips=296 granularity=%s strict_2of4_candidate=%u\r\n",
               MODEL_WORDS, MASK_WORDS, GROUP_MASK_GRANULARITY,
               STRICT_2OF4_CANDIDATE);
    #elif defined(B3_LIVE_ENEURON)
    B3_PRINT("B3_LIVE_ENEURON_PASS model_words=%u mask_words=%u group_reads=296 group_skips=296 granularity=%s strict_2of4_candidate=%u decision_source=live_eneuron_s2\r\n",
               MODEL_WORDS, MASK_WORDS, GROUP_MASK_GRANULARITY,
               STRICT_2OF4_CANDIDATE);
    #elif defined(B3_FULL_OPEN)
    B3_PRINT("B3_FULL_OPEN_PASS model_words=%u mask_words=%u\r\n", MODEL_WORDS, MASK_WORDS);
    #elif defined(B3_EPOCH_OVERLAP)
    B3_PRINT("B3_EPOCH_OVERLAP_PASS model_words=%u mask_words=%u\r\n", MODEL_WORDS, MASK_WORDS);
    #else
    B3_PRINT("B3_DENSE_PASS model_words=%u mask_words=%u\r\n", MODEL_WORDS, MASK_WORDS);
    #endif
#else
    B3_PRINT("B2_PACKET_PASS model_words=%u mask_words=%u\r\n",
               MODEL_WORDS, MASK_WORDS);
#endif
    while (1) {
        sleep(1U);
#ifdef B3_NUMERIC_CHECK
        #if defined(B3_BYPASS)
        B3_PRINT("B3_BYPASS_PASS model_words=%u mask_words=0\r\n", MODEL_WORDS);
        #elif defined(B3_STATIC_MIXED)
        B3_PRINT("B3_STATIC_MIXED_PASS model_words=%u mask_words=%u group_reads=296 group_skips=296 granularity=%s strict_2of4_candidate=%u\r\n",
                   MODEL_WORDS, MASK_WORDS, GROUP_MASK_GRANULARITY,
                   STRICT_2OF4_CANDIDATE);
        #elif defined(B3_LIVE_ENEURON)
        B3_PRINT("B3_LIVE_ENEURON_PASS model_words=%u mask_words=%u group_reads=296 group_skips=296 granularity=%s strict_2of4_candidate=%u decision_source=live_eneuron_s2\r\n",
                   MODEL_WORDS, MASK_WORDS, GROUP_MASK_GRANULARITY,
                   STRICT_2OF4_CANDIDATE);
        #elif defined(B3_FULL_OPEN)
        B3_PRINT("B3_FULL_OPEN_PASS model_words=%u mask_words=%u\r\n", MODEL_WORDS, MASK_WORDS);
        #elif defined(B3_EPOCH_OVERLAP)
        B3_PRINT("B3_EPOCH_OVERLAP_PASS model_words=%u mask_words=%u\r\n", MODEL_WORDS, MASK_WORDS);
        #else
        B3_PRINT("B3_DENSE_PASS model_words=%u mask_words=%u\r\n", MODEL_WORDS, MASK_WORDS);
        #endif
#else
        B3_PRINT("B2_PACKET_PASS model_words=%u mask_words=%u\r\n",
                   MODEL_WORDS, MASK_WORDS);
#endif
    }
}
