#include "xaxidma.h"
#include "xaxidma_hw.h"
#include "xil_cache.h"
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
#define TEST_LENGTH 64U

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
};

static volatile struct dma_snapshot *const snapshot =
    (volatile struct dma_snapshot *)STATUS_BASE;

static XAxiDma dma;
static UINTPTR dma_base;

enum {
    SNAPSHOT_RUNNING = 1U,
    SNAPSHOT_PASS = 2U,
    SNAPSHOT_FAIL = 3U
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

static int run_one_frame(u32 sequence)
{
    volatile u8 *const tx = (volatile u8 *)TX_BUFFER_BASE;
    volatile u8 *const rx = (volatile u8 *)RX_BUFFER_BASE;
    u32 index;
    u32 elapsed = 0U;
    u32 status;
    u32 expected_crc;

    snapshot->sequence = sequence;
    snapshot->length_bytes = TEST_LENGTH;
    snapshot->tx_address = TX_BUFFER_BASE;
    snapshot->rx_address = RX_BUFFER_BASE;
    snapshot->cache_flush_tx = 0U;
    snapshot->cache_invalidate_rx = 0U;

    for (index = 0U; index < TEST_LENGTH; ++index) {
        tx[index] = (u8)(sequence + index * 3U + 0x11U);
        rx[index] = 0U;
    }
    Xil_DCacheFlushRange(TX_BUFFER_BASE, TEST_LENGTH);
    snapshot->cache_flush_tx = 1U;
    Xil_DCacheInvalidateRange(RX_BUFFER_BASE, TEST_LENGTH);
    snapshot->cache_invalidate_rx = 1U;

    /* 合同要求先让 S2MM 接收端拥有 RX，再提交 MM2S 发送端。 */
    status = XAxiDma_SimpleTransfer(&dma, RX_BUFFER_BASE, TEST_LENGTH,
                                    XAXIDMA_DEVICE_TO_DMA);
    if (status != XST_SUCCESS) {
        return fail("submit_s2mm");
    }
    status = XAxiDma_SimpleTransfer(&dma, TX_BUFFER_BASE, TEST_LENGTH,
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

    Xil_DCacheInvalidateRange(RX_BUFFER_BASE, TEST_LENGTH);
    snapshot->cache_invalidate_rx = 2U;
    for (index = 0U; index < TEST_LENGTH; ++index) {
        u8 expected = (u8)(sequence + index * 3U + 0x11U);
        if (rx[index] != expected) {
            return fail("payload_mismatch");
        }
    }

    expected_crc = crc32((const u8 *)rx, TEST_LENGTH);
    snapshot->crc32 = expected_crc;
    capture_registers();
    snapshot->status = SNAPSHOT_PASS;
    memory_barrier();
    xil_printf("B2_DMA_PASS sequence=%u length=%u crc32=0x%08x\r\n",
               sequence, TEST_LENGTH, expected_crc);
    return XST_SUCCESS;
}

int main(void)
{
    XAxiDma_Config *config;

    Xil_DCacheDisable();
    snapshot->magic = 0x42324431U;
    snapshot->status = SNAPSHOT_RUNNING;
    snapshot->sequence = 1U;
    snapshot->length_bytes = TEST_LENGTH;
    memory_barrier();

    xil_printf("B2_DMA_BEGIN\r\n");
    xil_printf("PROTOCOL=B2_DMA_LOOPBACK_V1\r\n");
    xil_printf("TARGET=xc7z020clg484-2\r\n");
    xil_printf("TX_BUFFER=0x%08x RX_BUFFER=0x%08x\r\n",
               TX_BUFFER_BASE, RX_BUFFER_BASE);
    xil_printf("FRAME_LIMIT=%u ALIGNMENT=%u\r\n",
               MAX_FRAME_BYTES, BUFFER_ALIGNMENT);

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
    if (run_one_frame(1U) != XST_SUCCESS) {
        return XST_FAILURE;
    }

    while (1) {
        sleep(1U);
        xil_printf("B2_DMA_ALIVE PASS\r\n");
    }
}
