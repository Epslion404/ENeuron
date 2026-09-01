// NP7 共享突触 lane 阵列与饱和加法树（dense 与 sparse 顶层共用同一模块）。
//
// 每个 lane 只做一件事：把命中"结构保留 AND 活动"的 signed 8-bit 权重送进平衡
// 二叉饱和加法树。未使用的 lane 恒输入零，因此 lane 数只改变每周期可发射的操作
// 数与周期数，不改变数学结果（含饱和端点：x+0 不改变钳位值）。累加域 12-bit，
// 溢出钳位到 +2047/-2048，不回绕。
module np7_shared_synapse_lane #(
    parameter int LANES = 4
) (
    input  logic                   [LANES * 8 - 1:0] op_weights,
    input  logic [2:0]                               op_count,
    input  logic signed [11:0]                       acc_seed,
    output logic signed [11:0]                       acc_next,
    output logic                                     saturated
);
    logic signed [11:0] gated [0:7];
    logic signed [11:0] stage1 [0:3];
    logic signed [11:0] stage2 [0:1];
    logic signed [11:0] tree_value;
    logic signed [13:0] raw_next;

    function automatic logic signed [11:0] sat12(input logic signed [11:0] a,
                                                 input logic signed [11:0] b);
        logic signed [13:0] wide;
        wide = {{2{a[11]}}, a} + {{2{b[11]}}, b};
        if (wide > 14'sd2047)
            sat12 = 12'sd2047;
        else if (wide < -14'sd2048)
            sat12 = -12'sd2048;
        else
            sat12 = wide[11:0];
    endfunction

    genvar gi;
    generate
        for (gi = 0; gi < 8; gi = gi + 1) begin : g_lane
            if (gi < LANES) begin : g_used
                assign gated[gi] = (gi < op_count)
                    ? {{4{op_weights[gi * 8 + 7]}}, op_weights[gi * 8 +: 8]}
                    : 12'sd0;
            end else begin : g_tied
                assign gated[gi] = 12'sd0;
            end
        end
        for (gi = 0; gi < 4; gi = gi + 1) begin : g_stage1
            assign stage1[gi] = sat12(gated[2 * gi], gated[2 * gi + 1]);
        end
        for (gi = 0; gi < 2; gi = gi + 1) begin : g_stage2
            assign stage2[gi] = sat12(stage1[2 * gi], stage1[2 * gi + 1]);
        end
    endgenerate

    assign tree_value = sat12(stage2[0], stage2[1]);
    assign raw_next = {{2{acc_seed[11]}}, acc_seed} + {{2{tree_value[11]}}, tree_value};
    assign saturated = (raw_next > 14'sd2047) || (raw_next < -14'sd2048);
    assign acc_next = saturated ? (raw_next[13] ? -12'sd2048 : 12'sd2047) : raw_next[11:0];

endmodule