`timescale 1ns/1ps
// P1 原始四输入计数器/分频脉冲基线。
//
// 该模块故意保留最初方案的语义缺陷，不能作为 Pulse-Mini 完整实现：
//   1) 学习计数器在达到上限后回到 0；
//   2) 学习只能增加，不能削弱或产生抑制；
//   3) 分频进度跨 tick 保存；
//   4) 不应期用同步数据路径清零胞体，不生成内部时钟或异步复位。
//
// “计数越大连接越强”的冻结映射：period = MAX_LEARN - learn_count，
// 但最小 period 限定为 1。输入脉冲使分频进度加一，达到 period 时产生
// 一个 dendrite_pulse 并把该通道进度清零。学习脉冲在同一 tick 先更新
// learn_count，再用于本 tick 的 period 计算。
module pulse_original_core #(
    parameter int N_INPUTS = 4,
    parameter int LEARN_BITS = 8,
    parameter int DIV_BITS = 8,
    parameter int SOMA_BITS = 16,
    parameter int SLEEP_BITS = 4,
    parameter int THRESHOLD = 6,
    parameter int SLEEP_LENGTH = 1
) (
    input  logic                         clk,
    input  logic                         rst,
    input  logic                         tick_valid,
    input  logic [N_INPUTS-1:0]          input_spikes,
    input  logic [N_INPUTS-1:0]          learn_pulse,
    output logic                         spike,
    output logic [N_INPUTS-1:0]          dendrite_pulses,
    output logic [N_INPUTS*LEARN_BITS-1:0] learn_count_flat,
    output logic [N_INPUTS*DIV_BITS-1:0]   divider_progress_flat,
    output logic signed [SOMA_BITS-1:0]  soma_state,
    output logic [SLEEP_BITS-1:0]        sleep_count,
    output logic                         ready
);

    localparam int LEARN_MAX = (1 <<< LEARN_BITS) - 1;
    localparam int DIV_MAX = (1 <<< DIV_BITS) - 1;
    localparam int SOMA_MAX = (1 <<< (SOMA_BITS - 1)) - 1;
    localparam int SOMA_MIN = -(1 <<< (SOMA_BITS - 1));
    localparam logic [SLEEP_BITS-1:0] SLEEP_VALUE = SLEEP_LENGTH;

    logic [LEARN_BITS-1:0] learn_count [0:N_INPUTS-1];
    logic [LEARN_BITS-1:0] learn_count_next [0:N_INPUTS-1];
    logic [DIV_BITS-1:0] divider_progress [0:N_INPUTS-1];
    logic [DIV_BITS-1:0] divider_progress_next [0:N_INPUTS-1];
    logic signed [SOMA_BITS-1:0] soma_reg;
    logic signed [SOMA_BITS-1:0] soma_next;
    logic [SLEEP_BITS-1:0] sleep_reg;
    logic [SLEEP_BITS-1:0] sleep_next;
    logic [N_INPUTS-1:0] dendrite_next;
    logic spike_next;

    integer i_flat;
    integer i_comb;
    integer i_ff;
    integer learn_value;
    integer period_value;
    integer progress_value;
    integer soma_acc;
    integer pulse_count;

    assign soma_state = soma_reg;
    assign sleep_count = sleep_reg;
    assign ready = 1'b1;

    // Flattened state ports make the P1 directed test and Vivado hierarchy
    // audit deterministic without exposing implementation-specific arrays.
    always_comb begin
        learn_count_flat = '0;
        divider_progress_flat = '0;
        for (i_flat = 0; i_flat < N_INPUTS; i_flat = i_flat + 1) begin
            learn_count_flat[i_flat*LEARN_BITS +: LEARN_BITS] = learn_count[i_flat];
            divider_progress_flat[i_flat*DIV_BITS +: DIV_BITS] = divider_progress[i_flat];
        end
    end

    always_comb begin
        spike_next = 1'b0;
        dendrite_next = '0;
        soma_next = soma_reg;
        sleep_next = sleep_reg;
        pulse_count = 0;
        soma_acc = $signed(soma_reg);

        for (i_comb = 0; i_comb < N_INPUTS; i_comb = i_comb + 1) begin
            learn_count_next[i_comb] = learn_count[i_comb];
            divider_progress_next[i_comb] = divider_progress[i_comb];

            if (tick_valid) begin
                // 原始“上限复位向上计数器”：到达最大值后回绕到零。
                if (learn_pulse[i_comb]) begin
                    if (learn_count[i_comb] == LEARN_MAX[LEARN_BITS-1:0])
                        learn_count_next[i_comb] = '0;
                    else
                        learn_count_next[i_comb] = learn_count[i_comb] + 1'b1;
                end

                // 学习值越大，周期越短，因此通过概率/频率越高。
                learn_value = learn_pulse[i_comb] ?
                    (learn_count[i_comb] == LEARN_MAX[LEARN_BITS-1:0] ? 0 : learn_count[i_comb] + 1) :
                    learn_count[i_comb];
                period_value = LEARN_MAX - learn_value;
                if (period_value < 1)
                    period_value = 1;
                if (period_value > DIV_MAX)
                    period_value = DIV_MAX;

                if (input_spikes[i_comb]) begin
                    progress_value = divider_progress[i_comb];
                    if (period_value == 1 || progress_value >= period_value - 1) begin
                        dendrite_next[i_comb] = 1'b1;
                        divider_progress_next[i_comb] = '0;
                    end else begin
                        divider_progress_next[i_comb] = progress_value + 1;
                    end
                end
            end
        end

        // 睡眠期是同步屏蔽：胞体累计器每拍清零，并逐拍倒计时。
        if (tick_valid) begin
            if (sleep_reg != 0) begin
                soma_next = '0;
                sleep_next = sleep_reg - 1'b1;
            end else begin
                pulse_count = 0;
                for (i_comb = 0; i_comb < N_INPUTS; i_comb = i_comb + 1)
                    pulse_count = pulse_count + dendrite_next[i_comb];
                soma_acc = $signed(soma_reg) + pulse_count;
                if (soma_acc > SOMA_MAX)
                    soma_acc = SOMA_MAX;
                else if (soma_acc < SOMA_MIN)
                    soma_acc = SOMA_MIN;

                if (soma_acc >= THRESHOLD) begin
                    spike_next = 1'b1;
                    soma_next = '0;
                    sleep_next = SLEEP_VALUE;
                end else begin
                    soma_next = soma_acc[SOMA_BITS-1:0];
                end
            end
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            spike <= 1'b0;
            soma_reg <= '0;
            sleep_reg <= '0;
            for (i_ff = 0; i_ff < N_INPUTS; i_ff = i_ff + 1) begin
                learn_count[i_ff] <= '0;
                divider_progress[i_ff] <= '0;
            end
        end else begin
            spike <= spike_next;
            soma_reg <= soma_next;
            sleep_reg <= sleep_next;
            for (i_ff = 0; i_ff < N_INPUTS; i_ff = i_ff + 1) begin
                learn_count[i_ff] <= learn_count_next[i_ff];
                divider_progress[i_ff] <= divider_progress_next[i_ff];
            end
        end
    end

    always_comb begin
        dendrite_pulses = dendrite_next;
    end

endmodule
