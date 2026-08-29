// NeuronGate V1：给向量 NPU 使用的四连接结构化门控核心。
//
// 这个模块不执行 MAC，不读取 NPU 的 BRAM/DSP 数据。它只维护每条连接的
// 重要性分数、当前保留掩码、候选掩码和冷却计数，输出 keep_mask 给 NPU。
// 训练阶段由 tick/image_end/epoch_end 三个边界驱动；推理阶段 train_mode=0，
// 掩码与分数全部冻结。image_end 与 epoch_end 设计为互斥边界，不要在同一个
// 时钟周期同时置位。

module neuron_gate_core #(
    parameter int SCORE_DECAY_INTERVAL = 8,
    parameter int PRUNE_LO            = 16,
    parameter int REGROW_HI           = 48,
    parameter int COOLDOWN_LENGTH     = 4,
    parameter int MAX_KEEP            = 2,
    parameter int ACTIVITY_INC        = 1,
    parameter int COINCIDENCE_INC     = 3,
    parameter int CORRECT_INC         = 4,
    parameter int INCORRECT_DEC       = 2,
    parameter logic [3:0] INIT_MASK   = 4'b1111,
    parameter int INIT_SCORE          = 128
) (
    input  logic         clk,
    input  logic         rst,
    input  logic         train_mode,
    input  logic         tick_valid,
    input  logic [3:0]   pre_mask,
    input  logic         post_event,
    input  logic         feedback_valid,
    input  logic         feedback_correct,
    input  logic         image_end,
    input  logic         epoch_end,
    output logic [3:0]   keep_mask,
    output logic [3:0]   candidate_mask,
    output logic         candidate_valid,
    output logic [31:0]  score_flat,
    output logic [15:0]  cooldown_flat,
    output logic [2:0]   keep_count
);

    logic [7:0] score_reg [0:3];
    logic [3:0] cooldown_reg [0:3];
    logic [3:0] mask_reg;
    logic [3:0] candidate_mask_reg;
    logic       candidate_valid_reg;
    integer     tick_count_reg;

    integer i;
    integer count;
    integer k;
    integer score_next [0:3];
    integer tick_count_next;
    integer raw_count;
    integer best0;
    integer best1;
    logic [3:0] raw_mask;

    assign keep_mask = mask_reg;
    assign candidate_mask = candidate_mask_reg;
    assign candidate_valid = candidate_valid_reg;

    assign score_flat[7:0]   = score_reg[0];
    assign score_flat[15:8]  = score_reg[1];
    assign score_flat[23:16] = score_reg[2];
    assign score_flat[31:24] = score_reg[3];

    assign cooldown_flat[3:0]   = cooldown_reg[0];
    assign cooldown_flat[7:4]   = cooldown_reg[1];
    assign cooldown_flat[11:8]  = cooldown_reg[2];
    assign cooldown_flat[15:12] = cooldown_reg[3];

    always_comb begin
        count = 0;
        for (k = 0; k < 4; k = k + 1) begin
            if (mask_reg[k]) begin
                count = count + 1;
            end
        end
        keep_count = count[2:0];
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            for (i = 0; i < 4; i = i + 1) begin
                score_reg[i]    <= INIT_SCORE[7:0];
                cooldown_reg[i] <= '0;
            end
            mask_reg            <= INIT_MASK;
            candidate_mask_reg  <= INIT_MASK;
            candidate_valid_reg <= 1'b0;
            tick_count_reg      <= 0;
        end else begin
            for (i = 0; i < 4; i = i + 1) begin
                score_next[i] = score_reg[i];
            end
            tick_count_next = tick_count_reg;

            if (train_mode && tick_valid) begin
                for (i = 0; i < 4; i = i + 1) begin
                    if (pre_mask[i]) begin
                        score_next[i] = score_next[i] + ACTIVITY_INC;
                        if (post_event) begin
                            score_next[i] = score_next[i] + COINCIDENCE_INC;
                        end
                        if (feedback_valid) begin
                            if (feedback_correct) begin
                                score_next[i] = score_next[i] + CORRECT_INC;
                            end else begin
                                score_next[i] = score_next[i] - INCORRECT_DEC;
                            end
                        end
                    end else if (tick_count_reg == SCORE_DECAY_INTERVAL - 1) begin
                        score_next[i] = score_next[i] - 1;
                    end

                    if (score_next[i] > 255) begin
                        score_next[i] = 255;
                    end
                    if (score_next[i] < 0) begin
                        score_next[i] = 0;
                    end
                end

                if (tick_count_reg == SCORE_DECAY_INTERVAL - 1) begin
                    tick_count_next = 0;
                end else begin
                    tick_count_next = tick_count_reg + 1;
                end
            end

            if (train_mode && image_end) begin
                raw_mask = mask_reg;
                for (i = 0; i < 4; i = i + 1) begin
                    if (!mask_reg[i] && cooldown_reg[i] == 0 && score_next[i] > REGROW_HI) begin
                        raw_mask[i] = 1'b1;
                    end else if (mask_reg[i] && cooldown_reg[i] == 0 && score_next[i] < PRUNE_LO) begin
                        raw_mask[i] = 1'b0;
                        cooldown_reg[i] <= COOLDOWN_LENGTH[3:0];
                    end
                end

                raw_count = 0;
                for (i = 0; i < 4; i = i + 1) begin
                    raw_count = raw_count + raw_mask[i];
                end

                if (MAX_KEEP > 0 && raw_count > MAX_KEEP) begin
                    best0 = -1;
                    best1 = -1;
                    for (i = 0; i < 4; i = i + 1) begin
                        if (raw_mask[i]) begin
                            if (best0 < 0 || score_next[i] > score_next[best0]) begin
                                best1 = best0;
                                best0 = i;
                            end else if (best1 < 0 || score_next[i] > score_next[best1]) begin
                                best1 = i;
                            end
                        end
                    end
                    raw_mask = '0;
                    if (best0 >= 0) begin
                        raw_mask[best0] = 1'b1;
                    end
                    if (best1 >= 0) begin
                        raw_mask[best1] = 1'b1;
                    end
                end

                candidate_mask_reg  <= raw_mask;
                candidate_valid_reg <= 1'b1;
            end

            if (train_mode && epoch_end) begin
                if (candidate_valid_reg) begin
                    mask_reg            <= candidate_mask_reg;
                    candidate_valid_reg <= 1'b0;
                end
                for (i = 0; i < 4; i = i + 1) begin
                    if (cooldown_reg[i] > 0) begin
                        cooldown_reg[i] <= cooldown_reg[i] - 1'b1;
                    end
                end
            end

            for (i = 0; i < 4; i = i + 1) begin
                score_reg[i] <= score_next[i][7:0];
            end
            tick_count_reg <= tick_count_next;
        end
    end

endmodule
