// NP7 共享突触 lane 的 gate 与带符号饱和加法树（dense 与 sparse 顶层共用同一模块）。
//
// P1 周期合同（PR #6 管理员裁定 5085536010，2026-09-02）：允许在 lane 的饱和加法/
// 事件计数路径插入一拍流水寄存器，本模块据此切成均衡的两级：
//   Stage A（组合）：gated -> stage1 -> stage2，只算部分和，完全不碰累加器；
//   流水寄存器：stage2_q[0:1] 与 in-flight 标记 valid_q；
//   Stage B（组合）：tree_value = sat12(stage2_q[0], stage2_q[1])，
//                   raw_next = acc_seed + tree_value，acc_next/saturated 由它得出。
// 关键性质：任意一批的 acc_next 数值与插流水前逐 bit 相同，只是晚 1 拍出现；lane 吞吐
// 仍是 1 batch/拍，非零事务因此多出 1 个折叠拍（顶层新增 S_DRAIN 状态）。
//
// 每个 lane 只有一个"乘数"：门控是"结构掩码 AND 活动输入"，signed 8-bit 权重做符号
// 扩展后进入 12-bit 带符号饱和加法树。未使用的 lane 仍参与加 0，这不改变数值语义
// （x+0 不改变饱和值），也不改变端点：累加器仍是 12-bit，饱和上/下界 +2047/-2048。
//
// hold 语义：fold_hold=1 时 Stage B 既不折叠也不写回，in-flight 批次保持在流水级里
// 下一拍重试；顶层保证 op_valid 与 fold_hold 互斥（两者都由同一个 lane_stall 门控）。
module np7_shared_synapse_lane #(
    parameter int LANES = 4
) (
    input  logic                             clk,
    input  logic                             rst,
    input  logic                             op_valid,   // 本拍 Stage A 采样一个 batch
    input  logic                             fold_hold,  // = lane_stall：Stage B 冻结
    input  logic        [LANES * 8 - 1:0]    op_weights,
    input  logic [2:0]                       op_count,
    input  logic signed [11:0]               acc_seed,   // 顶层 acc 寄存器（Stage B 输入）
    output logic signed [11:0]               acc_next,   // Stage B 本拍折叠结果
    output logic                             saturated,  // Stage B 是否饱和（事件计数）
    output logic                             fold_valid  // 本拍有 in-flight 且未 hold
);
    logic signed [11:0] gated [0:7];
    logic signed [11:0] stage1 [0:3];
    logic signed [11:0] stage2 [0:1];
    logic signed [11:0] stage2_q [0:1];
    logic               valid_q;
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

    // ---- P1 流水寄存器：Stage A 的部分和 + in-flight 标记 ----
    always_ff @(posedge clk) begin
        if (rst) begin
            valid_q <= 1'b0;
            stage2_q[0] <= 12'sd0;
            stage2_q[1] <= 12'sd0;
        end else if (op_valid) begin
            stage2_q[0] <= stage2[0];
            stage2_q[1] <= stage2[1];
            valid_q <= 1'b1;
        end else if (valid_q && !fold_hold) begin
            valid_q <= 1'b0;      // 折叠提交，流水级清空
        end
        // fold_hold=1 且有 in-flight：保持原值，下一拍重试同一批
    end

    // ---- Stage B：根节点 + 累加折叠 + 饱和判定（全部只依赖寄存值）----
    assign tree_value = sat12(stage2_q[0], stage2_q[1]);
    assign raw_next = {{2{acc_seed[11]}}, acc_seed} + {{2{tree_value[11]}}, tree_value};
    assign saturated = (raw_next > 14'sd2047) || (raw_next < -14'sd2048);
    assign acc_next = saturated ? (raw_next[13] ? -12'sd2048 : 12'sd2047) : raw_next[11:0];
    assign fold_valid = valid_q && !fold_hold;

endmodule