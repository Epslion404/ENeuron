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

#define TX_BUFFER_BASE 0x01006000U
#define RX_BUFFER_BASE 0x01007000U
#define MONITOR_MM2S_BASE 0x40410000U
#define MONITOR_S2MM_BASE 0x40420000U
#define MAX_FRAME_BYTES 4096U
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

static u32 speed_ps_us;
static u32 speed_dma_us;

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
#else
#define APPLICATION_MODE "b2_packet_smoke"
#define SAMPLE_MASK_EPOCH MASK_EPOCH
#define SEND_MASK_COMMANDS 1
#endif

#if defined(B3_BYPASS) || defined(B3_FULL_OPEN) || defined(B3_DENSE) || defined(B3_STATIC_MIXED) || defined(B3_LIVE_ENEURON) || defined(B3_EPOCH_OVERLAP)
#define B3_NUMERIC_CHECK 1
#if defined(B3_STATIC_MIXED)
static const s32 *const expected_logits = B3_STATIC_MIXED_LOGITS;
#elif defined(B3_LIVE_ENEURON)
static const s32 *const expected_logits = B3_LIVE_ENEURON_LOGITS;
#else
static const s32 *const expected_logits = B3_DENSE_LOGITS;
#endif

static s32 expected_logit(u32 index)
{
    return expected_logits[index];
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
    xil_printf("B2_PACKET_FAIL reason=%s sequence=%u tx_sr=0x%08x rx_sr=0x%08x\r\n",
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

static u32 static_mixed_mask_word(u32 index)
{
    /* 每 bit 控制一个四权重组；该组级候选由黄金 manifest 提供。 */
    return B3_STATIC_MIXED_MASK_WORDS[index];
}

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
    for (lane = 0U; lane < 4U; ++lane) {
        acc += (s32)decode_int8_byte(word, lane) * activations[start + lane];
    }
    return acc;
}

static void apply_live_meta_mask(u32 *bits, u32 group_base, u32 mask)
{
    u32 local;
    for (local = 0U; local < 4U; ++local) {
        if ((mask >> local) & 1U) {
            bits[group_base + local] = 1U;
        }
    }
}

static void compute_live_group4way_mask(void)
{
    s32 pixels[64];
    s32 hidden[32];
    u32 bits[592];
    u32 beat;
    u32 nibble;
    u32 hidden_index;
    u32 output_index;
    u32 meta;
    u32 group;
    u32 word_index;
    u32 bit_index;

    for (beat = 0U; beat < 8U; ++beat) {
        for (nibble = 0U; nibble < 8U; ++nibble) {
            pixels[beat * 8U + nibble] = (s32)((B3_SAMPLE_INPUT_BEATS[beat] >> (4U * nibble)) & 0xFU);
        }
    }
    for (bit_index = 0U; bit_index < 592U; ++bit_index) {
        bits[bit_index] = 0U;
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
            apply_live_meta_mask(bits, hidden_index * 16U + meta * 4U, live_top2_mask(evidence));
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
            apply_live_meta_mask(bits, 512U + output_index * 8U + meta * 4U, live_top2_mask(evidence));
        }
    }

    for (word_index = 0U; word_index < 19U; ++word_index) {
        live_mask_words[word_index] = 0U;
    }
    for (bit_index = 0U; bit_index < 592U; ++bit_index) {
        if (bits[bit_index] != 0U) {
            live_mask_words[bit_index / 32U] |= 1U << (bit_index & 31U);
        }
    }
    live_mask_ready = 1U;
}

static u32 live_mask_word(u32 index)
{
    return live_mask_words[index];
}
#endif

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

static u32 build_sample_frame(volatile u32 *frame, u32 sample_id,
                              u32 model_id, u32 epoch)
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
        frame[8U + index] = B3_SAMPLE_INPUT_BEATS[index];
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

    // probe 在每个 TLAST 后自动停用；每个 DMA 帧都必须重新打开旁路。
    monitor_reset(MONITOR_MM2S_BASE);
    if (expect_response != 0U) {
        monitor_reset(MONITOR_S2MM_BASE);
    }

    if (expect_response != 0U) {
        for (index = 0U; index < rx_capacity / 4U; ++index) {
            rx[index] = 0xA5A5A5A5U;
        }
        Xil_DCacheFlushRange(RX_BUFFER_BASE, rx_capacity);
        Xil_DCacheInvalidateRange(RX_BUFFER_BASE, rx_capacity);
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
    usleep(10U);
    status = wait_dma(1U, expect_response != 0U ? 1U : 0U);
    if (status != XST_SUCCESS) {
        return XST_FAILURE;
    }
    if (expect_response != 0U) {
        Xil_DCacheInvalidateRange(RX_BUFFER_BASE, rx_capacity);
        memory_barrier();
        if (rx[0] != MAGIC) {
            return XST_FAILURE;
        }
        *response_words = 8U + (rx[2] / 4U) + 1U;
        if (*response_words > rx_capacity / 4U) {
            return XST_FAILURE;
        }
    }
    return XST_SUCCESS;
}

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

static int send_fence_and_check(void)
{
    volatile u32 *const tx = (volatile u32 *)TX_BUFFER_BASE;
    volatile u32 *const rx = (volatile u32 *)RX_BUFFER_BASE;
    u32 frame_bytes;
    u32 response_words = 0U;
    u32 request_sequence = sequence;
    frame_bytes = build_command_frame(tx, OP_SAMPLE_FENCE, 0U, 0x00000F00U, MODEL_ID);
    if (submit_frame(frame_bytes, MAX_FRAME_BYTES, 1U, &response_words) != XST_SUCCESS) {
        return fail("fence_dma");
    }
    Xil_DCacheInvalidateRange(RX_BUFFER_BASE, MAX_FRAME_BYTES);
    if (response_words != 13U || rx[1] != 0x08000301U || rx[2] != 16U ||
        rx[3] != request_sequence || rx[5] != MODEL_ID || rx[6] != 0U ||
        rx[8] != 0U || rx[9] != 0U || rx[10] != 0x0F000000U ||
        rx[11] != 0xD0A00000U) {
        return fail("fence_response");
    }
    xil_printf("B2_PACKET_FENCE_PASS sequence=%u response_words=%u\r\n",
               request_sequence, response_words);
    ++sequence;
    return XST_SUCCESS;
}

static int send_sample_and_check(void)
{
    volatile u32 *const tx = (volatile u32 *)TX_BUFFER_BASE;
    volatile u32 *const rx = (volatile u32 *)RX_BUFFER_BASE;
    u32 frame_bytes;
    u32 response_words = 0U;
    u32 request_sequence = sequence;
    u32 sample_id = 0x12345678U;
    XTime t_ps0;
    XTime t_dma0;
    XTime t_dma1;
    XTime_GetTime(&t_ps0);
    frame_bytes = build_sample_frame(tx, sample_id, MODEL_ID, SAMPLE_MASK_EPOCH);
    XTime_GetTime(&t_dma0);
    speed_ps_us += xtime_delta_us(t_ps0, t_dma0);
    if (submit_frame(frame_bytes, MAX_FRAME_BYTES, 1U, &response_words) != XST_SUCCESS) {
        return fail("sample_dma");
    }
    XTime_GetTime(&t_dma1);
    speed_dma_us = xtime_delta_us(t_dma0, t_dma1);
    xil_printf("B3_SPEED_SPLIT ps_us=%u dma_us=%u\r\n", speed_ps_us, speed_dma_us);
    Xil_DCacheInvalidateRange(RX_BUFFER_BASE, MAX_FRAME_BYTES);
    if (response_words != 19U || rx[1] != 0x08000401U || rx[2] != 40U ||
        rx[3] != request_sequence || rx[4] != sample_id ||
        rx[5] != MODEL_ID || rx[6] != SAMPLE_MASK_EPOCH) {
        return fail("result_response");
    }
#ifdef B3_NUMERIC_CHECK
    {
        u32 index;
        u32 crc = 0xFFFFFFFFU;
        s32 result_logits[10];
        for (index = 0U; index < 18U; ++index) {
            crc = crc32_word(crc, rx[index]);
        }
        if (rx[18] != ~crc) {
            return fail("b3_result_crc");
        }
        for (index = 0U; index < 10U; ++index) {
            result_logits[index] = (s32)rx[8U + index];
            if (result_logits[index] != expected_logit(index)) {
                xil_printf("B3_LOGIT_FAIL index=%u expected=%d actual=%d\r\n",
                           index, expected_logit(index),
                           result_logits[index]);
                return fail("b3_logit_mismatch");
            }
        }
        #if defined(B3_BYPASS)
        xil_printf("B3_BYPASS_PASS sequence=%u sample_id=0x%08x response_words=%u mask_words=0 logits=165,-18,14,0,0,0,0,0,0,153\r\n",
                   request_sequence, sample_id, response_words);
        #elif defined(B3_STATIC_MIXED)
        xil_printf("B3_STATIC_MIXED_PASS sequence=%u sample_id=0x%08x response_words=%u mask_words=%u logits=74,-18,14,0,0,0,0,0,0,114 group_reads=296 group_skips=296 granularity=%s strict_2of4_candidate=%u\r\n",
                   request_sequence, sample_id, response_words, MASK_WORDS,
                   GROUP_MASK_GRANULARITY, STRICT_2OF4_CANDIDATE);
        #elif defined(B3_LIVE_ENEURON)
        xil_printf("B3_LIVE_ENEURON_PASS sequence=%u sample_id=0x%08x response_words=%u mask_words=%u logits=165,-18,14,0,0,0,0,0,0,153 group_reads=296 group_skips=296 granularity=%s strict_2of4_candidate=%u decision_source=live_eneuron_s2\r\n",
                   request_sequence, sample_id, response_words, MASK_WORDS,
                   GROUP_MASK_GRANULARITY, STRICT_2OF4_CANDIDATE);
        #elif defined(B3_FULL_OPEN)
        xil_printf("B3_FULL_OPEN_PASS sequence=%u sample_id=0x%08x response_words=%u mask_words=%u logits=165,-18,14,0,0,0,0,0,0,153\r\n",
                   request_sequence, sample_id, response_words, MASK_WORDS);
        #elif defined(B3_EPOCH_OVERLAP)
        xil_printf("B3_EPOCH_OVERLAP_PASS sequence=%u sample_id=0x%08x response_words=%u mask_words=%u logits=165,-18,14,0,0,0,0,0,0,153 result_epoch=%u\r\n",
                   request_sequence, sample_id, response_words, MASK_WORDS, SAMPLE_MASK_EPOCH);
        #else
        xil_printf("B3_DENSE_PASS sequence=%u sample_id=0x%08x response_words=%u mask_words=%u logits=165,-18,14,0,0,0,0,0,0,153\r\n",
                   request_sequence, sample_id, response_words, MASK_WORDS);
        #endif
    }
#else
    if (rx[8] != 3U || rx[9] != 0xFFFFFFFBU || rx[17] != 0xFFFFFFFFU) {
        return fail("result_response");
    }
    xil_printf("B2_PACKET_RESULT_PASS sequence=%u sample_id=0x%08x response_words=%u\r\n",
               request_sequence, sample_id, response_words);
#endif
    ++sequence;
    return XST_SUCCESS;
}

int main(void)
{
    XAxiDma_Config *config;
    u32 index;

    Xil_DCacheDisable();
    xil_printf("B2_PACKET_BEGIN\r\n");
    xil_printf("APPLICATION_MODE=%s\r\n", APPLICATION_MODE);
    xil_printf("PROTOCOL=ENB2_PACKET_NPU_V1\r\n");
    xil_printf("TARGET=xc7z020clg484-2\r\n");
    xil_printf("TX_BUFFER=0x%08x RX_BUFFER=0x%08x\r\n",
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
            xil_printf("B2_PACKET_MODEL_PROGRESS words=%u\r\n", index + 1U);
        }
    }
    if (send_command(OP_MODEL_COMMIT, 0U, 0U) != XST_SUCCESS) return XST_FAILURE;
#if SEND_MASK_COMMANDS
#if defined(B3_STATIC_MIXED)
    if (validate_static_mixed_mask() != XST_SUCCESS) {
        return fail("static_mask_legality");
    }
    xil_printf("B3_STATIC_MASK_VALID groups=592 active_groups=296 skipped_groups=296 granularity=%s strict_2of4_candidate=%s\r\n",
               GROUP_MASK_GRANULARITY, STRICT_2OF4_CANDIDATE_TEXT);
#endif
#if defined(B3_LIVE_ENEURON)
    {
        XTime t0;
        XTime t1;
        XTime_GetTime(&t0);
        compute_live_group4way_mask();
        XTime_GetTime(&t1);
        speed_ps_us += xtime_delta_us(t0, t1);
    }
    if (live_mask_ready == 0U) {
        return fail("live_mask_compute");
    }
    xil_printf("B3_LIVE_MASK_VALID groups=592 active_groups=296 skipped_groups=296 granularity=%s strict_2of4_candidate=%s decision_source=live_eneuron_s2 gain=1 score=S2\r\n",
               GROUP_MASK_GRANULARITY, STRICT_2OF4_CANDIDATE_TEXT);
#endif
    if (send_command(OP_MASK_BEGIN, MASK_EPOCH, 0U) != XST_SUCCESS) return XST_FAILURE;
    for (index = 0U; index < MASK_WORDS; ++index) {
        u32 mask_word;
#if defined(B3_STATIC_MIXED)
        mask_word = static_mixed_mask_word(index);
#elif defined(B3_LIVE_ENEURON)
        mask_word = live_mask_word(index);
#else
        mask_word = B3_FULL_OPEN_MASK_WORDS[index];
#endif
        if (send_command(OP_MASK_DATA, MASK_EPOCH, mask_word) != XST_SUCCESS) return XST_FAILURE;
    }
    if (send_command(OP_MASK_COMMIT, MASK_EPOCH, 0U) != XST_SUCCESS) return XST_FAILURE;
#if defined(B3_EPOCH_OVERLAP)
    xil_printf("B3_11_PENDING_HOLD expected_active=0 expected_pending=1\r\n");
    sleep(8U);
#endif
#endif
    if (send_fence_and_check() != XST_SUCCESS) return XST_FAILURE;
    if (send_sample_and_check() != XST_SUCCESS) return XST_FAILURE;

#ifdef B3_NUMERIC_CHECK
    xil_printf("B2_PACKET_PASS model_words=%u mask_words=%u\r\n",
               MODEL_WORDS, SEND_MASK_COMMANDS ? MASK_WORDS : 0U);
    #if defined(B3_BYPASS)
    xil_printf("B3_BYPASS_PASS model_words=%u mask_words=0\r\n", MODEL_WORDS);
    #elif defined(B3_STATIC_MIXED)
    xil_printf("B3_STATIC_MIXED_PASS model_words=%u mask_words=%u group_reads=296 group_skips=296 granularity=%s strict_2of4_candidate=%u\r\n",
               MODEL_WORDS, MASK_WORDS, GROUP_MASK_GRANULARITY,
               STRICT_2OF4_CANDIDATE);
    #elif defined(B3_LIVE_ENEURON)
    xil_printf("B3_LIVE_ENEURON_PASS model_words=%u mask_words=%u group_reads=296 group_skips=296 granularity=%s strict_2of4_candidate=%u decision_source=live_eneuron_s2\r\n",
               MODEL_WORDS, MASK_WORDS, GROUP_MASK_GRANULARITY,
               STRICT_2OF4_CANDIDATE);
    #elif defined(B3_FULL_OPEN)
    xil_printf("B3_FULL_OPEN_PASS model_words=%u mask_words=%u\r\n", MODEL_WORDS, MASK_WORDS);
    #elif defined(B3_EPOCH_OVERLAP)
    xil_printf("B3_EPOCH_OVERLAP_PASS model_words=%u mask_words=%u\r\n", MODEL_WORDS, MASK_WORDS);
    #else
    xil_printf("B3_DENSE_PASS model_words=%u mask_words=%u\r\n", MODEL_WORDS, MASK_WORDS);
    #endif
#else
    xil_printf("B2_PACKET_PASS model_words=%u mask_words=%u\r\n",
               MODEL_WORDS, MASK_WORDS);
#endif
    while (1) {
        sleep(1U);
#ifdef B3_NUMERIC_CHECK
        #if defined(B3_BYPASS)
        xil_printf("B3_BYPASS_PASS model_words=%u mask_words=0\r\n", MODEL_WORDS);
        #elif defined(B3_STATIC_MIXED)
        xil_printf("B3_STATIC_MIXED_PASS model_words=%u mask_words=%u group_reads=296 group_skips=296 granularity=%s strict_2of4_candidate=%u\r\n",
                   MODEL_WORDS, MASK_WORDS, GROUP_MASK_GRANULARITY,
                   STRICT_2OF4_CANDIDATE);
        #elif defined(B3_LIVE_ENEURON)
        xil_printf("B3_LIVE_ENEURON_PASS model_words=%u mask_words=%u group_reads=296 group_skips=296 granularity=%s strict_2of4_candidate=%u decision_source=live_eneuron_s2\r\n",
                   MODEL_WORDS, MASK_WORDS, GROUP_MASK_GRANULARITY,
                   STRICT_2OF4_CANDIDATE);
        #elif defined(B3_FULL_OPEN)
        xil_printf("B3_FULL_OPEN_PASS model_words=%u mask_words=%u\r\n", MODEL_WORDS, MASK_WORDS);
        #elif defined(B3_EPOCH_OVERLAP)
        xil_printf("B3_EPOCH_OVERLAP_PASS model_words=%u mask_words=%u\r\n", MODEL_WORDS, MASK_WORDS);
        #else
        xil_printf("B3_DENSE_PASS model_words=%u mask_words=%u\r\n", MODEL_WORDS, MASK_WORDS);
        #endif
#else
        xil_printf("B2_PACKET_PASS model_words=%u mask_words=%u\r\n",
                   MODEL_WORDS, MASK_WORDS);
#endif
    }
}
