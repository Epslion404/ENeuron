#include <stdint.h>

#include "sleep.h"
#include "xil_cache.h"
#include "xil_printf.h"
#include "xil_types.h"

#ifndef B1B_SW_GIT_HEAD
#define B1B_SW_GIT_HEAD "UNKNOWN"
#endif

#ifndef B1A_HW_SOURCE_COMMIT
#define B1A_HW_SOURCE_COMMIT "UNKNOWN"
#endif

#ifndef B1A_BITSTREAM_SHA256
#define B1A_BITSTREAM_SHA256 "UNKNOWN"
#endif

#ifndef B1A_XSA_SHA256
#define B1A_XSA_SHA256 "UNKNOWN"
#endif

#define RESULT_RECORD_BASE 0x0002F000U
#define DDR_WINDOW_BASE 0x10000000U
#define DDR_WINDOW_BYTES 0x00001000U
#define DDR_WINDOW_WORDS (DDR_WINDOW_BYTES / sizeof(u32))
#define FIXED_PATTERN 0xA55A3CC3U
#define GO_COMMAND 0x474F4444U

struct high_diag_result {
    u32 magic;
    u32 version;
    u32 status;
    u32 phase;
    u32 window_base;
    u32 address;
    u32 operation;
    u32 access_width;
    u32 expected;
    u32 actual;
    u32 completed_accesses;
    u32 command;
    u32 execution_address;
};

static volatile struct high_diag_result *const result =
    (volatile struct high_diag_result *)RESULT_RECORD_BASE;

enum {
    RESULT_RUNNING = 1U,
    RESULT_PASS = 2U,
    RESULT_FAIL = 3U,
    RESULT_READY = 4U
};

enum {
    PHASE_OCM_READY = 1U,
    PHASE_SPARSE_WRITE = 2U,
    PHASE_SPARSE_READ = 3U,
    PHASE_WINDOW_WRITE = 4U,
    PHASE_WINDOW_READ = 5U,
    PHASE_COMPLETE = 6U
};

enum {
    OP_NONE = 0U,
    OP_WRITE = 1U,
    OP_READ = 2U
};

static const u32 sparse_offsets[] = {
    0x000U, 0x004U, 0x040U, 0x100U, 0x400U, 0xFFCU
};

static void memory_barrier(void)
{
    __asm__ volatile("dmb sy" ::: "memory");
}

static void record_attempt(u32 phase, u32 address, u32 operation, u32 expected)
{
    result->status = RESULT_RUNNING;
    result->phase = phase;
    result->window_base = DDR_WINDOW_BASE;
    result->address = address;
    result->operation = operation;
    result->access_width = sizeof(u32);
    result->expected = expected;
    result->actual = 0U;
    memory_barrier();
}

static void write_word(u32 phase, u32 address, u32 value)
{
    record_attempt(phase, address, OP_WRITE, value);
    *(volatile u32 *)address = value;
    memory_barrier();
    result->completed_accesses += 1U;
    memory_barrier();
}

static int read_and_compare(u32 phase, u32 address, u32 expected)
{
    u32 actual;

    record_attempt(phase, address, OP_READ, expected);
    actual = *(volatile u32 *)address;
    result->actual = actual;
    result->completed_accesses += 1U;
    memory_barrier();
    if (actual != expected) {
        result->status = RESULT_FAIL;
        memory_barrier();
        xil_printf("DDR_HIGH_FAIL_ADDR=0x%08x\r\n", address);
        xil_printf("DDR_HIGH_EXPECTED=0x%08x\r\n", expected);
        xil_printf("DDR_HIGH_ACTUAL=0x%08x\r\n", actual);
        return 1;
    }
    return 0;
}

static int test_sparse_addresses(void)
{
    u32 index;

    for (index = 0U; index < (u32)(sizeof(sparse_offsets) / sizeof(sparse_offsets[0])); ++index) {
        u32 address = DDR_WINDOW_BASE + sparse_offsets[index];
        u32 value = FIXED_PATTERN ^ address;
        write_word(PHASE_SPARSE_WRITE, address, value);
    }
    for (index = 0U; index < (u32)(sizeof(sparse_offsets) / sizeof(sparse_offsets[0])); ++index) {
        u32 address = DDR_WINDOW_BASE + sparse_offsets[index];
        u32 expected = FIXED_PATTERN ^ address;
        if (read_and_compare(PHASE_SPARSE_READ, address, expected) != 0) {
            return 1;
        }
    }
    xil_printf("DDR_HIGH_PHASE=SPARSE PASS\r\n");
    return 0;
}

static int test_fixed_window(void)
{
    u32 index;

    for (index = 0U; index < DDR_WINDOW_WORDS; ++index) {
        write_word(PHASE_WINDOW_WRITE,
                   DDR_WINDOW_BASE + index * sizeof(u32),
                   FIXED_PATTERN);
    }
    for (index = 0U; index < DDR_WINDOW_WORDS; ++index) {
        if (read_and_compare(PHASE_WINDOW_READ,
                             DDR_WINDOW_BASE + index * sizeof(u32),
                             FIXED_PATTERN) != 0) {
            return 1;
        }
    }
    xil_printf("DDR_HIGH_PHASE=FIXED_4K PASS\r\n");
    return 0;
}

int main(void)
{
    const char *terminal_marker;
    u32 main_address = (u32)(uintptr_t)&main;

    Xil_DCacheDisable();
    result->magic = 0x42314844U;
    result->version = 1U;
    result->status = RESULT_RUNNING;
    result->phase = PHASE_OCM_READY;
    result->window_base = DDR_WINDOW_BASE;
    result->address = 0U;
    result->operation = OP_NONE;
    result->access_width = sizeof(u32);
    result->expected = 0U;
    result->actual = 0U;
    result->completed_accesses = 0U;
    result->command = 0U;
    result->execution_address = main_address;
    memory_barrier();

    xil_printf("ENEURON_B1B_HIGH_DIAG_BEGIN\r\n");
    xil_printf("PROTOCOL=B1B_HIGH_DIAG_V1\r\n");
    xil_printf("SW_GIT_HEAD=%s\r\n", B1B_SW_GIT_HEAD);
    xil_printf("HW_SOURCE_COMMIT=%s\r\n", B1A_HW_SOURCE_COMMIT);
    xil_printf("BITSTREAM_SHA256=%s\r\n", B1A_BITSTREAM_SHA256);
    xil_printf("XSA_SHA256=%s\r\n", B1A_XSA_SHA256);
    xil_printf("EXECUTION_ADDRESS=0x%08x\r\n", main_address);
    xil_printf("RESULT_RECORD_BASE=0x%08x\r\n", RESULT_RECORD_BASE);
    xil_printf("DDR_WINDOW_BASE=0x%08x\r\n", DDR_WINDOW_BASE);
    xil_printf("DDR_WINDOW_BYTES=0x%08x\r\n", DDR_WINDOW_BYTES);
    xil_printf("DCACHE=DISABLED\r\n");

    if (main_address >= RESULT_RECORD_BASE) {
        result->status = RESULT_FAIL;
        result->address = main_address;
        memory_barrier();
        xil_printf("OCM_EXECUTION_CHECK=FAIL\r\n");
        xil_printf("ENEURON_B1B_HIGH_DIAG_FAIL\r\n");
        terminal_marker = "ENEURON_B1B_HIGH_DIAG_ALIVE FAIL";
    } else {
        result->status = RESULT_READY;
        memory_barrier();
        xil_printf("OCM_EXECUTION_CHECK=PASS\r\n");
        xil_printf("ENEURON_B1B_HIGH_DIAG_READY\r\n");
        while (result->command != GO_COMMAND) {
        }
        result->status = RESULT_RUNNING;
        memory_barrier();
        xil_printf("ENEURON_B1B_HIGH_DIAG_GO\r\n");

        if (test_sparse_addresses() != 0 || test_fixed_window() != 0) {
            xil_printf("DDR_HIGH_RESULT=FAIL\r\n");
            xil_printf("ENEURON_B1B_HIGH_DIAG_FAIL\r\n");
            terminal_marker = "ENEURON_B1B_HIGH_DIAG_ALIVE FAIL";
        } else {
            result->phase = PHASE_COMPLETE;
            result->status = RESULT_PASS;
            memory_barrier();
            xil_printf("DDR_HIGH_RESULT=PASS\r\n");
            xil_printf("ENEURON_B1B_HIGH_DIAG_PASS\r\n");
            terminal_marker = "ENEURON_B1B_HIGH_DIAG_ALIVE PASS";
        }
    }

    while (1) {
        sleep(1U);
        xil_printf("%s\r\n", terminal_marker);
    }
}
