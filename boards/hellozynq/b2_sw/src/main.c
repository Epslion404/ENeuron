#include "xaxidma.h"
#include "xaxidma_hw.h"
#include "xil_cache.h"
#include "xil_io.h"
#include "xil_printf.h"
#include "xil_types.h"
#include "xparameters.h"
#include "xstatus.h"
#include "sleep.h"

#define TX_BUFFER_BASE 0x01006000U
#define RX_BUFFER_BASE 0x01007000U
#define STATUS_BASE 0x01008000U
#define MAX_FRAME_BYTES 4096U
#define BUFFER_ALIGNMENT 64U
#define POLL_INTERVAL_US 1U
#define TRANSFER_TIMEOUT_US 1000000U
#define RESET_POLL_BUDGET 500U
#define STATUS_LEDGER_BASE 0x01008080U
#define MONITOR_STATUS_BASE 0x01008400U
#define FRAME_COUNT 8U
#define FRAME_LENGTHS {0U, 1U, 4U, 16U, 64U, 512U, 1472U, 4096U}
#define PRESSURE_FRAME_COUNT 10000U
#define PRESSURE_LENGTHS {1U, 4U, 16U, 64U, 512U, 1472U, 4096U}

#if defined(XPAR_AXIS_STREAM_PROBE_MM2S_BASEADDR)
#define MONITOR_MM2S_BASE XPAR_AXIS_STREAM_PROBE_MM2S_BASEADDR
#elif defined(XPAR_AXI_STREAM_MONITOR_MM2S_BASEADDR)
#define MONITOR_MM2S_BASE XPAR_AXI_STREAM_MONITOR_MM2S_BASEADDR
#elif defined(XPAR_AXIS_STREAM_PROBE_0_BASEADDR)
#define MONITOR_MM2S_BASE XPAR_AXIS_STREAM_PROBE_0_BASEADDR
#elif defined(XPAR_AXI_STREAM_MONITOR_0_BASEADDR)
#define MONITOR_MM2S_BASE XPAR_AXI_STREAM_MONITOR_0_BASEADDR
#else
/* module-reference 自定义外设不一定进入 HSI 的 xparameters.h；地址由 B2 BD 合同冻结。 */
#define MONITOR_MM2S_BASE 0x40410000U
#endif

#if defined(XPAR_AXIS_STREAM_PROBE_S2MM_BASEADDR)
#define MONITOR_S2MM_BASE XPAR_AXIS_STREAM_PROBE_S2MM_BASEADDR
#elif defined(XPAR_AXI_STREAM_MONITOR_S2MM_BASEADDR)
#define MONITOR_S2MM_BASE XPAR_AXI_STREAM_MONITOR_S2MM_BASEADDR
#elif defined(XPAR_AXIS_STREAM_PROBE_1_BASEADDR)
#define MONITOR_S2MM_BASE XPAR_AXIS_STREAM_PROBE_1_BASEADDR
#elif defined(XPAR_AXI_STREAM_MONITOR_1_BASEADDR)
#define MONITOR_S2MM_BASE XPAR_AXI_STREAM_MONITOR_1_BASEADDR
#else
#define MONITOR_S2MM_BASE 0x40420000U
#endif

#define MONITOR_CONTROL_OFFSET 0x00U
#define MONITOR_SAMPLE_OFFSET 0x20U
#define MONITOR_TOTAL_DATA_BEATS_OFFSET 0x50U
#define MONITOR_TOTAL_TLASTS_OFFSET 0x80U
#define MONITOR_TOTAL_DATA_BYTES_OFFSET 0x88U
#define MONITOR_TOTAL_BUSY_CYCLES_OFFSET 0x90U
#define MONITOR_TOTAL_STALL_CYCLES_OFFSET 0x98U
#define MONITOR_TOTAL_STARVE_CYCLES_OFFSET 0xA0U

#if defined(XPAR_AXIDMA_0_DEVICE_ID)
#define DMA_DEVICE_ID XPAR_AXIDMA_0_DEVICE_ID
#elif defined(XPAR_AXI_DMA_0_DEVICE_ID)
#define DMA_DEVICE_ID XPAR_AXI_DMA_0_DEVICE_ID
#else
#error "AXI DMA device ID is missing from generated xparameters.h"
#endif

struct dma_snapshot {
    u32 magic;
    u32 status;
    u32 sequence;
    u32 length_bytes;
    u32 tx_address;
    u32 rx_address;
    u32 cache_flush_tx;
    u32 cache_invalidate_rx;
    u32 tx_cr;
    u32 tx_sr;
    u32 tx_btt;
    u32 rx_cr;
    u32 rx_sr;
    u32 rx_btt;
    u32 crc32;
    u32 frames_total;
    u32 frames_passed;
    u32 frames_rejected;
    u32 frames_failed;
    u32 pressure_status;
    u32 pressure_total;
    u32 pressure_passed;
    u32 pressure_failed;
    u32 pressure_crc32;
    u32 pressure_last_sequence;
};

struct frame_ledger {
    u32 sequence;
    u32 length_bytes;
    u32 status;
    u32 crc32;
    u32 elapsed_us;
    u32 cache_invalidate;
    u32 mm2s_beats;
    u32 s2mm_beats;
    u32 mm2s_tlast_lo;
    u32 mm2s_tlast_hi;
    u32 s2mm_tlast_lo;
    u32 s2mm_tlast_hi;
    u32 mm2s_bytes_lo;
    u32 mm2s_bytes_hi;
    u32 s2mm_bytes_lo;
    u32 s2mm_bytes_hi;
};

typedef struct monitor_snapshot {
    u32 total_beats;
    u32 total_tlasts_lo;
    u32 total_tlasts_hi;
    u32 total_data_bytes_lo;
    u32 total_data_bytes_hi;
    u32 total_busy_cycles_lo;
    u32 total_busy_cycles_hi;
    u32 total_stall_cycles_lo;
    u32 total_stall_cycles_hi;
    u32 total_starve_cycles_lo;
    u32 total_starve_cycles_hi;
} monitor_snapshot;

struct monitor_status {
    monitor_snapshot mm2s;
    monitor_snapshot s2mm;
};

static volatile struct dma_snapshot *const snapshot =
    (volatile struct dma_snapshot *)STATUS_BASE;
static volatile struct frame_ledger *const ledger =
    (volatile struct frame_ledger *)STATUS_LEDGER_BASE;
static volatile struct monitor_status *const monitor_status =
    (volatile struct monitor_status *)MONITOR_STATUS_BASE;

static XAxiDma dma;
static UINTPTR dma_base;
static int pressure_mode;

enum {
    SNAPSHOT_RUNNING = 1U,
    SNAPSHOT_PASS = 2U,
    SNAPSHOT_FAIL = 3U,
    RESULT_STATUS_REJECTED = 4U
};

static void memory_barrier(void)
{
    __asm__ volatile("dmb sy" ::: "memory");
}

static u32 crc32(const u8 *data, u32 length)
{
    u32 crc = 0xFFFFFFFFU;
    u32 index;
    u32 bit;

    for (index = 0U; index < length; ++index) {
        crc ^= data[index];
        for (bit = 0U; bit < 8U; ++bit) {
            crc = (crc >> 1U) ^ (0xEDB88320U & (0U - (crc & 1U)));
        }
    }
    return ~crc;
}

static u32 read_reg(u32 channel_offset, u32 register_offset)
{
    return XAxiDma_ReadReg(dma_base + channel_offset, register_offset);
}

static void capture_registers(void)
{
    snapshot->tx_cr = read_reg(XAXIDMA_TX_OFFSET, XAXIDMA_CR_OFFSET);
    snapshot->tx_sr = read_reg(XAXIDMA_TX_OFFSET, XAXIDMA_SR_OFFSET);
    snapshot->tx_btt = read_reg(XAXIDMA_TX_OFFSET, XAXIDMA_BUFFLEN_OFFSET);
    snapshot->rx_cr = read_reg(XAXIDMA_RX_OFFSET, XAXIDMA_CR_OFFSET);
    snapshot->rx_sr = read_reg(XAXIDMA_RX_OFFSET, XAXIDMA_SR_OFFSET);
    snapshot->rx_btt = read_reg(XAXIDMA_RX_OFFSET, XAXIDMA_BUFFLEN_OFFSET);
}

static void monitor_reset(UINTPTR base)
{
    Xil_Out32(base + MONITOR_CONTROL_OFFSET, 1U);
    Xil_Out32(base + MONITOR_CONTROL_OFFSET, 0U);
    memory_barrier();
}

static void monitor_capture(UINTPTR base, volatile monitor_snapshot *result)
{
    (void)Xil_In32(base + MONITOR_SAMPLE_OFFSET);
    result->total_beats = Xil_In32(base + MONITOR_TOTAL_DATA_BEATS_OFFSET);
    result->total_tlasts_lo = Xil_In32(base + MONITOR_TOTAL_TLASTS_OFFSET);
    result->total_tlasts_hi = Xil_In32(base + MONITOR_TOTAL_TLASTS_OFFSET + 4U);
    result->total_data_bytes_lo = Xil_In32(base + MONITOR_TOTAL_DATA_BYTES_OFFSET);
    result->total_data_bytes_hi = Xil_In32(base + MONITOR_TOTAL_DATA_BYTES_OFFSET + 4U);
    result->total_busy_cycles_lo = Xil_In32(base + MONITOR_TOTAL_BUSY_CYCLES_OFFSET);
    result->total_busy_cycles_hi = Xil_In32(base + MONITOR_TOTAL_BUSY_CYCLES_OFFSET + 4U);
    result->total_stall_cycles_lo = Xil_In32(base + MONITOR_TOTAL_STALL_CYCLES_OFFSET);
    result->total_stall_cycles_hi = Xil_In32(base + MONITOR_TOTAL_STALL_CYCLES_OFFSET + 4U);
    result->total_starve_cycles_lo = Xil_In32(base + MONITOR_TOTAL_STARVE_CYCLES_OFFSET);
    result->total_starve_cycles_hi = Xil_In32(base + MONITOR_TOTAL_STARVE_CYCLES_OFFSET + 4U);
    memory_barrier();
}

static int reset_and_wait(void)
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
    capture_registers();
    return XST_FAILURE;
}

static int fail(const char *reason)
{
    capture_registers();
    snapshot->status = SNAPSHOT_FAIL;
    memory_barrier();
    xil_printf("B2_DMA_FAIL reason=%s sequence=%u tx_sr=0x%08x rx_sr=0x%08x\r\n",
               reason, snapshot->sequence, snapshot->tx_sr, snapshot->rx_sr);
    return XST_FAILURE;
}

static void record_ledger(u32 slot, u32 sequence, u32 length, u32 status,
                          u32 crc, u32 elapsed, u32 cache_invalidate,
                          const volatile monitor_snapshot *mm2s,
                          const volatile monitor_snapshot *s2mm)
{
    if (slot >= FRAME_COUNT) {
        return;
    }
    ledger[slot].sequence = sequence;
    ledger[slot].length_bytes = length;
    ledger[slot].status = status;
    ledger[slot].crc32 = crc;
    ledger[slot].elapsed_us = elapsed;
    ledger[slot].cache_invalidate = cache_invalidate;
    ledger[slot].mm2s_beats = mm2s->total_beats;
    ledger[slot].s2mm_beats = s2mm->total_beats;
    ledger[slot].mm2s_tlast_lo = mm2s->total_tlasts_lo;
    ledger[slot].mm2s_tlast_hi = mm2s->total_tlasts_hi;
    ledger[slot].s2mm_tlast_lo = s2mm->total_tlasts_lo;
    ledger[slot].s2mm_tlast_hi = s2mm->total_tlasts_hi;
    ledger[slot].mm2s_bytes_lo = mm2s->total_data_bytes_lo;
    ledger[slot].mm2s_bytes_hi = mm2s->total_data_bytes_hi;
    ledger[slot].s2mm_bytes_lo = s2mm->total_data_bytes_lo;
    ledger[slot].s2mm_bytes_hi = s2mm->total_data_bytes_hi;
    memory_barrier();
}

static int run_one_frame(u32 sequence, u32 length, u32 slot)
{
    volatile u8 *const tx = (volatile u8 *)TX_BUFFER_BASE;
    volatile u8 *const rx = (volatile u8 *)RX_BUFFER_BASE;
    u32 index;
    u32 elapsed = 0U;
    u32 status;
    u32 expected_crc;
    volatile monitor_snapshot *const mm2s = &monitor_status->mm2s;
    volatile monitor_snapshot *const s2mm = &monitor_status->s2mm;

    snapshot->sequence = sequence;
    snapshot->length_bytes = length;
    snapshot->tx_address = TX_BUFFER_BASE;
    snapshot->rx_address = RX_BUFFER_BASE;
    snapshot->cache_flush_tx = 0U;
    snapshot->cache_invalidate_rx = 0U;
    monitor_reset(MONITOR_MM2S_BASE);
    monitor_reset(MONITOR_S2MM_BASE);

    if (length == 0U) {
        snapshot->cache_flush_tx = 0U;
        snapshot->cache_invalidate_rx = 0U;
        monitor_capture(MONITOR_MM2S_BASE, mm2s);
        monitor_capture(MONITOR_S2MM_BASE, s2mm);
        record_ledger(slot, sequence, length, RESULT_STATUS_REJECTED, 0U,
                      0U, 0U, mm2s, s2mm);
        if (!pressure_mode) {
            ++snapshot->frames_rejected;
        }
        memory_barrier();
        xil_printf("B2_DMA_REJECT sequence=%u length=0 reason=zero_length\r\n",
                   sequence);
        return XST_SUCCESS;
    }

    for (index = 0U; index < length; ++index) {
        tx[index] = (u8)(sequence + index * 3U + 0x11U);
        rx[index] = 0U;
    }
    Xil_DCacheFlushRange(TX_BUFFER_BASE, length);
    snapshot->cache_flush_tx = 1U;
    Xil_DCacheInvalidateRange(RX_BUFFER_BASE, length);
    snapshot->cache_invalidate_rx = 1U;

    /* 合同要求先让 S2MM 接收端拥有 RX，再提交 MM2S 发送端。 */
    status = XAxiDma_SimpleTransfer(&dma, RX_BUFFER_BASE, length,
                                    XAXIDMA_DEVICE_TO_DMA);
    if (status != XST_SUCCESS) {
        return fail("submit_s2mm");
    }
    status = XAxiDma_SimpleTransfer(&dma, TX_BUFFER_BASE, length,
                                    XAXIDMA_DMA_TO_DEVICE);
    if (status != XST_SUCCESS) {
        return fail("submit_mm2s");
    }

    while (elapsed < TRANSFER_TIMEOUT_US) {
        u32 tx_sr = read_reg(XAXIDMA_TX_OFFSET, XAXIDMA_SR_OFFSET);
        u32 rx_sr = read_reg(XAXIDMA_RX_OFFSET, XAXIDMA_SR_OFFSET);
        if ((tx_sr | rx_sr) & XAXIDMA_ERR_ALL_MASK) {
            return fail("dma_error");
        }
        if (!XAxiDma_Busy(&dma, XAXIDMA_DEVICE_TO_DMA) &&
            !XAxiDma_Busy(&dma, XAXIDMA_DMA_TO_DEVICE)) {
            break;
        }
        usleep(POLL_INTERVAL_US);
        ++elapsed;
    }
    if (elapsed == TRANSFER_TIMEOUT_US) {
        return fail("timeout");
    }

    monitor_capture(MONITOR_MM2S_BASE, mm2s);
    monitor_capture(MONITOR_S2MM_BASE, s2mm);

    Xil_DCacheInvalidateRange(RX_BUFFER_BASE, length);
    snapshot->cache_invalidate_rx = 2U;
    for (index = 0U; index < length; ++index) {
        u8 expected = (u8)(sequence + index * 3U + 0x11U);
        if (rx[index] != expected) {
            return fail("payload_mismatch");
        }
    }

    expected_crc = crc32((const u8 *)rx, length);
    snapshot->crc32 = expected_crc;
    record_ledger(slot, sequence, length, SNAPSHOT_PASS, expected_crc, elapsed,
                  snapshot->cache_invalidate_rx, mm2s, s2mm);
    if (pressure_mode) {
        ++snapshot->pressure_passed;
        snapshot->pressure_crc32 ^= expected_crc;
        snapshot->pressure_last_sequence = sequence;
    } else {
        ++snapshot->frames_passed;
    }
    capture_registers();
    snapshot->status = SNAPSHOT_PASS;
    memory_barrier();
    if (!pressure_mode) {
        xil_printf("B2_DMA_PASS sequence=%u length=%u crc32=0x%08x elapsed_us=%u\r\n",
                   sequence, length, expected_crc, elapsed);
    }
    return XST_SUCCESS;
}

static int run_pressure(void)
{
    static const u32 pressure_lengths[7] = PRESSURE_LENGTHS;
    u32 index;

    snapshot->pressure_status = SNAPSHOT_RUNNING;
    snapshot->pressure_total = PRESSURE_FRAME_COUNT;
    snapshot->pressure_passed = 0U;
    snapshot->pressure_failed = 0U;
    snapshot->pressure_crc32 = 0U;
    snapshot->pressure_last_sequence = 0U;
    memory_barrier();

    pressure_mode = 1;
    for (index = 0U; index < PRESSURE_FRAME_COUNT; ++index) {
        u32 sequence = FRAME_COUNT + 1U + index;
        u32 length = pressure_lengths[index % 7U];
        if (run_one_frame(sequence, length, FRAME_COUNT) != XST_SUCCESS) {
            ++snapshot->pressure_failed;
            pressure_mode = 0;
            snapshot->pressure_status = SNAPSHOT_FAIL;
            memory_barrier();
            return XST_FAILURE;
        }
    }
    pressure_mode = 0;
    snapshot->pressure_status = SNAPSHOT_PASS;
    memory_barrier();
    xil_printf("B2_PRESSURE_PASS frames=%u crc32=0x%08x last_sequence=%u\r\n",
               snapshot->pressure_passed, snapshot->pressure_crc32,
               snapshot->pressure_last_sequence);
    return XST_SUCCESS;
}

int main(void)
{
    XAxiDma_Config *config;
    static const monitor_snapshot empty_monitor = {0};
    static const u32 frame_lengths[FRAME_COUNT] = FRAME_LENGTHS;
    u32 index;
    u32 rejected_zero = 0U;

    Xil_DCacheDisable();
    snapshot->magic = 0x42324431U;
    snapshot->status = SNAPSHOT_RUNNING;
    snapshot->sequence = 1U;
    snapshot->length_bytes = 0U;
    snapshot->frames_total = FRAME_COUNT;
    snapshot->frames_passed = 0U;
    snapshot->frames_rejected = 0U;
    snapshot->frames_failed = 0U;
    snapshot->pressure_status = 0U;
    snapshot->pressure_total = 0U;
    snapshot->pressure_passed = 0U;
    snapshot->pressure_failed = 0U;
    snapshot->pressure_crc32 = 0U;
    snapshot->pressure_last_sequence = 0U;
    for (index = 0U; index < FRAME_COUNT; ++index) {
        record_ledger(index, index + 1U, 0U, SNAPSHOT_RUNNING, 0U, 0U, 0U,
                      &empty_monitor, &empty_monitor);
    }
    memory_barrier();

    xil_printf("B2_DMA_BEGIN\r\n");
    xil_printf("PROTOCOL=B2_DMA_LOOPBACK_V1\r\n");
    xil_printf("TARGET=xc7z020clg484-2\r\n");
    xil_printf("TX_BUFFER=0x%08x RX_BUFFER=0x%08x\r\n",
               TX_BUFFER_BASE, RX_BUFFER_BASE);
    xil_printf("FRAME_LIMIT=%u ALIGNMENT=%u\r\n",
               MAX_FRAME_BYTES, BUFFER_ALIGNMENT);
    xil_printf("FRAME_LENGTHS=0,1,4,16,64,512,1472,4096\r\n");

    config = XAxiDma_LookupConfig(DMA_DEVICE_ID);
    if (config == NULL) {
        return fail("lookup_config");
    }
    if (XAxiDma_CfgInitialize(&dma, config) != XST_SUCCESS) {
        return fail("cfg_initialize");
    }
    dma_base = config->BaseAddr;
    if (XAxiDma_HasSg(&dma)) {
        return fail("sg_enabled");
    }
    if (reset_and_wait() != XST_SUCCESS) {
        return fail("reset_timeout");
    }
    for (index = 0U; index < FRAME_COUNT; ++index) {
        if (run_one_frame(index + 1U, frame_lengths[index], index) !=
            XST_SUCCESS) {
            ++snapshot->frames_failed;
            return XST_FAILURE;
        }
        if (frame_lengths[index] == 0U) {
            ++rejected_zero;
        }
    }

    if (run_pressure() != XST_SUCCESS) {
        return XST_FAILURE;
    }

    snapshot->status = SNAPSHOT_PASS;
    memory_barrier();
    xil_printf("B2_DMA_PASS frames=%u rejected_zero=%u\r\n",
               FRAME_COUNT - rejected_zero, rejected_zero);

    while (1) {
        sleep(1U);
        xil_printf("B2_DMA_ALIVE PASS\r\n");
    }
}
