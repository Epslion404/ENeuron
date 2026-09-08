#include "xil_cache.h"
#include "xil_printf.h"
#include "xil_types.h"
#include "xparameters.h"
#include "sleep.h"

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

#define DDR_TEST_BASE  0x01000000U
#define DDR_TEST_BYTES 0x00100000U
#define DDR_TEST_WORDS (DDR_TEST_BYTES / sizeof(u32))
#define RESULT_RECORD_BASE 0x0002F000U

static volatile u32 *const ddr = (volatile u32 *)DDR_TEST_BASE;

struct result_record {
    u32 magic;
    u32 status;
    u32 phase;
    u32 fail_address;
    u32 expected;
    u32 actual;
};

static volatile struct result_record *const result =
    (volatile struct result_record *)RESULT_RECORD_BASE;

enum {
    RESULT_RUNNING = 1U,
    RESULT_PASS = 2U,
    RESULT_FAIL = 3U
};

static void memory_barrier(void)
{
    __asm__ volatile("dmb sy" ::: "memory");
}

static int fail(const char *phase, u32 index, u32 expected, u32 actual)
{
    result->status = RESULT_FAIL;
    result->fail_address = DDR_TEST_BASE + index * sizeof(u32);
    result->expected = expected;
    result->actual = actual;
    memory_barrier();
    xil_printf("DDR_PHASE=%s FAIL\r\n", phase);
    xil_printf("DDR_FAIL_ADDR=0x%08x\r\n", result->fail_address);
    xil_printf("DDR_EXPECTED=0x%08x\r\n", expected);
    xil_printf("DDR_ACTUAL=0x%08x\r\n", actual);
    return 1;
}

static int test_address_alias(void)
{
    u32 offset;

    ddr[0] = 0xAAAAAAAAU;
    for (offset = 1U; offset < DDR_TEST_WORDS; offset <<= 1U) {
        ddr[offset] = 0x55555555U ^ offset;
    }
    memory_barrier();

    if (ddr[0] != 0xAAAAAAAAU) {
        return fail("ADDRESS_ALIAS", 0U, 0xAAAAAAAAU, ddr[0]);
    }
    for (offset = 1U; offset < DDR_TEST_WORDS; offset <<= 1U) {
        u32 expected = 0x55555555U ^ offset;
        if (ddr[offset] != expected) {
            return fail("ADDRESS_ALIAS", offset, expected, ddr[offset]);
        }
    }

    xil_printf("DDR_PHASE=ADDRESS_ALIAS PASS\r\n");
    return 0;
}

static int test_constant(const char *phase, u32 pattern)
{
    u32 index;

    for (index = 0U; index < DDR_TEST_WORDS; ++index) {
        ddr[index] = pattern;
    }
    memory_barrier();

    for (index = 0U; index < DDR_TEST_WORDS; ++index) {
        u32 actual = ddr[index];
        if (actual != pattern) {
            return fail(phase, index, pattern, actual);
        }
    }

    xil_printf("DDR_PHASE=%s PASS\r\n", phase);
    return 0;
}

static int test_address_data(void)
{
    u32 index;

    for (index = 0U; index < DDR_TEST_WORDS; ++index) {
        ddr[index] = (DDR_TEST_BASE + index * sizeof(u32)) ^ 0xA5A55A5AU;
    }
    memory_barrier();

    for (index = 0U; index < DDR_TEST_WORDS; ++index) {
        u32 expected = (DDR_TEST_BASE + index * sizeof(u32)) ^ 0xA5A55A5AU;
        u32 actual = ddr[index];
        if (actual != expected) {
            return fail("ADDRESS_DATA", index, expected, actual);
        }
    }

    xil_printf("DDR_PHASE=ADDRESS_DATA PASS\r\n");
    return 0;
}

static int test_walking(const char *phase, int invert)
{
    u32 bit;
    u32 index;
    const u32 words = 1024U;

    for (bit = 0U; bit < 32U; ++bit) {
        u32 pattern = 1U << bit;
        if (invert != 0) {
            pattern = ~pattern;
        }
        for (index = 0U; index < words; ++index) {
            ddr[index] = pattern;
        }
        memory_barrier();
        for (index = 0U; index < words; ++index) {
            u32 actual = ddr[index];
            if (actual != pattern) {
                return fail(phase, index, pattern, actual);
            }
        }
    }

    xil_printf("DDR_PHASE=%s PASS\r\n", phase);
    return 0;
}

static u32 xorshift32(u32 state)
{
    state ^= state << 13U;
    state ^= state >> 17U;
    state ^= state << 5U;
    return state;
}

static int test_prng(void)
{
    const u32 seed = 0x20260908U;
    u32 state = seed;
    u32 index;

    for (index = 0U; index < DDR_TEST_WORDS; ++index) {
        state = xorshift32(state);
        ddr[index] = state;
    }
    memory_barrier();

    state = seed;
    for (index = 0U; index < DDR_TEST_WORDS; ++index) {
        u32 actual;
        state = xorshift32(state);
        actual = ddr[index];
        if (actual != state) {
            return fail("PRNG", index, state, actual);
        }
    }

    xil_printf("DDR_PHASE=PRNG PASS\r\n");
    return 0;
}

int main(void)
{
    const char *terminal_marker;

    Xil_DCacheDisable();
    result->magic = 0x42314231U;
    result->status = RESULT_RUNNING;
    result->phase = 0U;
    result->fail_address = 0U;
    result->expected = 0U;
    result->actual = 0U;
    memory_barrier();

    xil_printf("ENEURON_B1B_BEGIN\r\n");
    xil_printf("PROTOCOL=B1B_UART_DDR_V1\r\n");
    xil_printf("SW_GIT_HEAD=%s\r\n", B1B_SW_GIT_HEAD);
    xil_printf("HW_SOURCE_COMMIT=%s\r\n", B1A_HW_SOURCE_COMMIT);
    xil_printf("BITSTREAM_SHA256=%s\r\n", B1A_BITSTREAM_SHA256);
    xil_printf("XSA_SHA256=%s\r\n", B1A_XSA_SHA256);
#ifdef XPAR_PS7_CORTEXA9_0_CPU_CLK_FREQ_HZ
    xil_printf("CPU_HZ=%u\r\n", XPAR_PS7_CORTEXA9_0_CPU_CLK_FREQ_HZ);
#else
    xil_printf("CPU_HZ=UNKNOWN\r\n");
#endif
    xil_printf("FCLK0_HZ=200000000\r\n");
    xil_printf("UART=115200_8N1\r\n");
    xil_printf("DDR_TEST_BASE=0x%08x\r\n", DDR_TEST_BASE);
    xil_printf("DDR_TEST_BYTES=0x%08x\r\n", DDR_TEST_BYTES);
    xil_printf("RESULT_RECORD_BASE=0x%08x\r\n", RESULT_RECORD_BASE);
    xil_printf("DCACHE=DISABLED\r\n");

    result->phase = 1U;
    if (test_address_alias() != 0 ||
        (result->phase = 2U, test_constant("CONST_00", 0x00000000U)) != 0 ||
        (result->phase = 3U, test_constant("CONST_FF", 0xFFFFFFFFU)) != 0 ||
        (result->phase = 4U, test_constant("CONST_AA", 0xAAAAAAAAU)) != 0 ||
        (result->phase = 5U, test_constant("CONST_55", 0x55555555U)) != 0 ||
        (result->phase = 6U, test_address_data()) != 0 ||
        (result->phase = 7U, test_walking("WALKING_1", 0)) != 0 ||
        (result->phase = 8U, test_walking("WALKING_0", 1)) != 0 ||
        (result->phase = 9U, test_prng()) != 0) {
        xil_printf("DDR_RESULT=FAIL\r\n");
        xil_printf("ENEURON_B1B_FAIL\r\n");
        terminal_marker = "ENEURON_B1B_ALIVE FAIL";
    } else {
        result->status = RESULT_PASS;
        memory_barrier();
        xil_printf("DDR_RESULT=PASS\r\n");
        xil_printf("ENEURON_B1B_PASS\r\n");
        terminal_marker = "ENEURON_B1B_ALIVE PASS";
    }

    while (1) {
        sleep(1U);
        xil_printf("%s\r\n", terminal_marker);
    }
}
