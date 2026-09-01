// NP7.5 负向控制实现（两个"伪收益"参考物）。
//
// 本文件不是交付 RTL，而是性能 verifier 的对抗样本：两者都保持与 golden 完全
// 相同的突触和与 done 协议（功能测试无法区分），只在"性能账本"上作弊。NP7.5
// 要求性能 verifier 必须拒绝它们，否则 NP7 的读取/操作/周期收益不可信。
//
// 1) np7_neg_read_all_then_gate：权重读取阶段无条件读取整组四槽（两字），
//    读取之后才用 issue_mask 门控 lane；自报账本却按 sparse 合同声称
//    "每组一次读请求、两组权重槽、零突触快速路径"。
// 2) np7_neg_mac_then_clear：lane 阶段无条件发射四条候选操作（未被选中的
//    位置在 MAC 上清零），自报 lane_ops_issued 却只记 popcount(issue_mask)。
//
// 检测口径（np7_ledger_reconstruction.py）：账本的每个字段都必须能由逐拍观测
// 重建；自报数字与观测不一致即拒绝，观测到的读取/操作下降不足门槛同样拒绝。
`timescale 1ns/1ps

// 负向实现 1：全读后门控（reads 不可重建）
module np7_neg_read_all_then_gate #(
    parameter int LANES = 4
) (
    input  logic               clk,
    input  logic               rst,
    input  logic               cfg_valid,
    output logic               cfg_ready,
    input  logic [4:0]         cfg_addr,
    input  logic [19:0]        cfg_wdata,
    input  logic               cfg_open,
    output logic               cfg_error,
    input  logic               issue_valid,
    output logic               issue_ready,
    input  logic [3:0]         issue_group,
    input  logic [3:0]         issue_activity,
    input  logic [3:0]         issue_mask,
    input  logic [2:0]         issue_skip_count,
    input  logic               lane_stall,
    output logic               result_valid,
    input  logic               result_ready,
    output logic signed [11:0] result_sum,
    output logic               result_zero_path,
    output logic               ram_ce,
    output logic [4:0]         ram_addr,
    output logic [3:0]         batch_mask,
    output logic [2:0]         lane_fire_count,
    output logic [2:0]         state_code,
    output logic               accept_pulse,
    output logic [31:0]        group_read_requests_state,
    output logic [31:0]        weight_values_fetched_state,
    output logic [31:0]        lane_ops_issued_state,
    output logic [31:0]        zero_fast_paths_state,
    output logic [31:0]        busy_cycles_state,
    output logic [31:0]        stall_cycles_state,
    output logic [31:0]        completed_groups_state,
    output logic [31:0]        structural_skips_state,
    output logic [31:0]        input_zero_groups_state,
    output logic [31:0]        activity_zero_after_structure_state,
    output logic [31:0]        saturation_events_state,
    output logic [31:0]        total_cycles_state,
    output logic               cfg_illegal_index,
    output logic               protocol_error
);
    localparam logic [2:0] S_IDLE = 3'd0;
    localparam logic [2:0] S_RD0 = 3'd1;
    localparam logic [2:0] S_RD1 = 3'd2;
    localparam logic [2:0] S_LAT = 3'd3;
    localparam logic [2:0] S_BATCH = 3'd4;
    localparam logic [2:0] S_DONE = 3'd5;

    logic [2:0] state;
    logic [3:0] pending_mask;
    logic [3:0] group_reg;
    logic       zero_claim;
    logic [19:0] word0;
    logic [19:0] word1;
    logic signed [11:0] acc;
    logic [2:0] remaining_n;
    logic [2:0] batch_n;
    logic [1:0] sel0, sel1, sel2, sel3;
    logic [2:0] rank1, rank2, rank3;
    logic [LANES * 8 - 1:0] lane_weights;
    logic signed [11:0] acc_next;
    logic lane_saturated;
    logic lane_fire;
    logic [19:0] ram_q;

    assign issue_ready = (state == S_IDLE) && !cfg_open;
    assign accept_pulse = issue_valid && issue_ready;
    assign state_code = state;
    assign result_sum = acc;
    assign result_valid = (state == S_DONE);
    // 作弊点：即使本事务实际读了两字，仍报告"走了零突触快速路径"。
    assign result_zero_path = zero_claim;
    // 观测事实：无条件发起两次读请求（四槽全读）。
    assign ram_ce = (state == S_RD0) || (state == S_RD1);
    // 稠密基线一组占两个字：地址 {group,0} 与 {group,1}。
    assign ram_addr = (state == S_RD0) ? {group_reg, 1'b0}
                                       : {group_reg, 1'b1};

    wire signed [7:0] w0_val = $signed(word0[7:0]);
    wire signed [7:0] w1_val = $signed(word0[15:8]);
    wire signed [7:0] w2_val = $signed(word1[7:0]);
    wire signed [7:0] w3_val = $signed(word1[15:8]);
    wire obs_lat = (state == S_LAT);
    wire done_handshake = (state == S_DONE) && result_ready;
    wire stall_now = ((state == S_BATCH) && (pending_mask != 4'd0) && lane_stall)
                   || ((state == S_DONE) && !result_ready);
    wire nonzero_txn = !zero_claim;

    wire pm0 = pending_mask[0];
    wire pm1 = pending_mask[1];
    wire pm2 = pending_mask[2];
    wire pm3 = pending_mask[3];

    always_comb begin
        rank1 = pm0 ? 3'd1 : 3'd0;
        rank2 = rank1 + (pm1 ? 3'd1 : 3'd0);
        rank3 = rank2 + (pm2 ? 3'd1 : 3'd0);
        remaining_n = rank3 + (pm3 ? 3'd1 : 3'd0);
        sel0 = 2'd0;
        sel1 = 2'd0;
        sel2 = 2'd0;
        sel3 = 2'd0;
        if (pm0)
            sel0 = 2'd0;
        if (pm1) begin
            case (rank1)
                3'd0: sel0 = 2'd1; 3'd1: sel1 = 2'd1;
                3'd2: sel2 = 2'd1; default: sel3 = 2'd1;
            endcase
        end
        if (pm2) begin
            case (rank2)
                3'd0: sel0 = 2'd2; 3'd1: sel1 = 2'd2;
                3'd2: sel2 = 2'd2; default: sel3 = 2'd2;
            endcase
        end
        if (pm3) begin
            case (rank3)
                3'd0: sel0 = 2'd3; 3'd1: sel1 = 2'd3;
                3'd2: sel2 = 2'd3; default: sel3 = 2'd3;
            endcase
        end
        if (LANES >= 4)
            batch_n = remaining_n;
        else if (LANES == 2)
            batch_n = (remaining_n >= 3'd2) ? 3'd2 : remaining_n;
        else
            batch_n = (remaining_n >= 3'd1) ? 3'd1 : remaining_n;
    end

    logic signed [7:0] lv0, lv1, lv2, lv3;
    logic signed [7:0] pos_val [0:3];
    always_comb begin
        pos_val[0] = w0_val;
        pos_val[1] = w1_val;
        pos_val[2] = w2_val;
        pos_val[3] = w3_val;
        lv0 = pos_val[sel0];
        lv1 = pos_val[sel1];
        lv2 = pos_val[sel2];
        lv3 = pos_val[sel3];
        if (3'd0 >= batch_n) lv0 = 8'sd0;
        if (3'd1 >= batch_n) lv1 = 8'sd0;
        if (3'd2 >= batch_n) lv2 = 8'sd0;
        if (3'd3 >= batch_n) lv3 = 8'sd0;
    end

    genvar gi;
    generate
        for (gi = 0; gi < 8; gi = gi + 1) begin : g_lane_op
            if (gi < LANES) begin : g_present
                assign lane_weights[gi * 8 +: 8] = (gi == 0) ? lv0
                                             : (gi == 1) ? lv1
                                             : (gi == 2) ? lv2
                                             : (gi == 3) ? lv3 : 8'sd0;
            end else begin : g_absent
                assign lane_weights[gi * 8 +: 8] = 8'sd0;
            end
        end
    endgenerate

    assign batch_mask = ((3'd0 < batch_n) ? (4'b1 << sel0) : 4'b0)
                      | ((3'd1 < batch_n) ? (4'b1 << sel1) : 4'b0)
                      | ((3'd2 < batch_n) ? (4'b1 << sel2) : 4'b0)
                      | ((3'd3 < batch_n) ? (4'b1 << sel3) : 4'b0);
    assign lane_fire = (state == S_BATCH) && (pending_mask != 4'd0) && !lane_stall;
    assign lane_fire_count = lane_fire ? batch_n : 3'd0;

    np7_weight_ram weight_ram (
        .clk(clk), .rst(rst), .cfg_valid(cfg_valid), .cfg_ready(cfg_ready),
        .cfg_addr(cfg_addr), .cfg_wdata(cfg_wdata), .cfg_open(cfg_open),
        .cfg_error(cfg_error), .rd_ce(ram_ce), .rd_addr(ram_addr), .rd_q(ram_q)
    );

    np7_shared_synapse_lane #(.LANES(LANES)) lanes (
        .op_weights(lane_weights), .op_count(batch_n), .acc_seed(acc),
        .acc_next(acc_next), .saturated(lane_saturated)
    );

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= S_IDLE;
            pending_mask <= 4'd0;
            group_reg <= 4'd0;
            zero_claim <= 1'b0;
            word0 <= 20'd0;
            word1 <= 20'd0;
            acc <= 12'sd0;
            protocol_error <= 1'b0;
            group_read_requests_state <= 32'd0;
            weight_values_fetched_state <= 32'd0;
            lane_ops_issued_state <= 32'd0;
            zero_fast_paths_state <= 32'd0;
            busy_cycles_state <= 32'd0;
            stall_cycles_state <= 32'd0;
            completed_groups_state <= 32'd0;
            structural_skips_state <= 32'd0;
            input_zero_groups_state <= 32'd0;
            activity_zero_after_structure_state <= 32'd0;
            saturation_events_state <= 32'd0;
            total_cycles_state <= 32'd0;
        end else begin
            // 自报账本按 sparse 合同伪造：读请求 1 次/非零事务、权重槽 2 个/非零事务、
            // busy 只记"一拍读 + 发射拍"，total 只记合同公式，与真实逐拍行为无关。
            if (accept_pulse)
                total_cycles_state <= total_cycles_state + 32'd1;
            if (obs_lat && nonzero_txn) begin
                total_cycles_state <= total_cycles_state + 32'd1;
                group_read_requests_state <= group_read_requests_state + 32'd1;
                weight_values_fetched_state <= weight_values_fetched_state + 32'd2;
                busy_cycles_state <= busy_cycles_state + 32'd1;
            end
            if (lane_fire) begin
                lane_ops_issued_state <= lane_ops_issued_state + {29'd0, batch_n};
                busy_cycles_state <= busy_cycles_state + 32'd1;
                total_cycles_state <= total_cycles_state + 32'd1;
                if (lane_saturated)
                    saturation_events_state <= saturation_events_state + 32'd1;
            end
            if (stall_now) begin
                stall_cycles_state <= stall_cycles_state + 32'd1;
                total_cycles_state <= total_cycles_state + 32'd1;
            end
            if (done_handshake) begin
                completed_groups_state <= completed_groups_state + 32'd1;
                total_cycles_state <= total_cycles_state + 32'd1;
                if (zero_claim)
                    zero_fast_paths_state <= zero_fast_paths_state + 32'd1;
            end
            case (state)
                S_IDLE: begin
                    if (accept_pulse) begin
                        group_reg <= issue_group;
                        if (issue_mask & ~issue_activity)
                            protocol_error <= 1'b1;
                        acc <= 12'sd0;
                        word0 <= 20'd0;
                        word1 <= 20'd0;
                        pending_mask <= issue_mask;
                        zero_claim <= (issue_mask == 4'd0);
                        structural_skips_state <= structural_skips_state
                            + {29'd0, issue_skip_count};
                        if (issue_activity == 4'd0)
                            input_zero_groups_state <= input_zero_groups_state + 32'd1;
                        else if (issue_mask == 4'd0)
                            activity_zero_after_structure_state
                                <= activity_zero_after_structure_state + 32'd1;
                        // 作弊点：无条件进入读取状态，先读全再门控。
                        state <= S_RD0;
                    end
                end
                S_RD0: state <= S_RD1;
                S_RD1: begin
                    // 第一字在第二次请求拍出现在 ram_q 上（同步 RAM 打一拍延迟）。
                    word0 <= ram_q;
                    state <= S_LAT;
                end
                S_LAT: begin
                    word1 <= ram_q;
                    state <= (pending_mask == 4'd0) ? S_DONE : S_BATCH;
                end
                S_BATCH: begin
                    if (pending_mask == 4'd0) begin
                        state <= S_DONE;
                    end else if (!lane_stall) begin
                        acc <= acc_next;
                        pending_mask <= pending_mask & ~batch_mask;
                        if ((pending_mask & ~batch_mask) == 4'd0)
                            state <= S_DONE;
                    end
                end
                S_DONE: if (result_ready) state <= S_IDLE;
                default: state <= S_IDLE;
            endcase
        end
    end
    assign cfg_illegal_index = 1'b0;
endmodule
// 负向实现 2：MAC 后清零（lane 发射数不可重建）。
//
// 读取侧与 golden sparse 完全一致（每非零事务 1 次读请求、2 个权重槽、零快速路径），
// 但 lane 阶段无条件发射四条候选操作，未选中的位置在操作数上清零；自报
// lane_ops_issued 只记 popcount(issue_mask)。功能与突触和与 golden 一致（x+0 保持
// 饱和钳位不变），因此只有"逐拍观测重建"能识破它。
module np7_neg_mac_then_clear #(
    parameter int LANES = 4
) (
    input  logic               clk,
    input  logic               rst,
    input  logic               cfg_valid,
    output logic               cfg_ready,
    input  logic [4:0]         cfg_addr,
    input  logic [19:0]        cfg_wdata,
    input  logic               cfg_open,
    output logic               cfg_error,
    input  logic               issue_valid,
    output logic               issue_ready,
    input  logic [3:0]         issue_group,
    input  logic [3:0]         issue_activity,
    input  logic [3:0]         issue_mask,
    input  logic [2:0]         issue_skip_count,
    input  logic               lane_stall,
    output logic               result_valid,
    input  logic               result_ready,
    output logic signed [11:0] result_sum,
    output logic               result_zero_path,
    output logic               ram_ce,
    output logic [4:0]         ram_addr,
    output logic [3:0]         batch_mask,
    output logic [2:0]         lane_fire_count,
    output logic [2:0]         state_code,
    output logic               accept_pulse,
    output logic [31:0]        group_read_requests_state,
    output logic [31:0]        weight_values_fetched_state,
    output logic [31:0]        lane_ops_issued_state,
    output logic [31:0]        zero_fast_paths_state,
    output logic [31:0]        busy_cycles_state,
    output logic [31:0]        stall_cycles_state,
    output logic [31:0]        completed_groups_state,
    output logic [31:0]        structural_skips_state,
    output logic [31:0]        input_zero_groups_state,
    output logic [31:0]        activity_zero_after_structure_state,
    output logic [31:0]        saturation_events_state,
    output logic [31:0]        total_cycles_state,
    output logic               cfg_illegal_index,
    output logic               protocol_error
);
    localparam logic [2:0] S_IDLE = 3'd0;
    localparam logic [2:0] S_RD0 = 3'd1;
    localparam logic [2:0] S_LAT = 3'd3;
    localparam logic [2:0] S_BATCH = 3'd4;
    localparam logic [2:0] S_DONE = 3'd5;

    logic [2:0] state;
    logic [3:0] slot_mask;
    logic [3:0] issue_reg;
    logic [3:0] group_reg;
    logic       zero_path_reg;
    logic [19:0] word0;
    logic signed [11:0] acc;
    logic [2:0] remaining_n;
    logic [2:0] batch_n;
    logic [1:0] sel0, sel1, sel2, sel3;
    logic [2:0] rank1, rank2, rank3;
    logic [LANES * 8 - 1:0] lane_weights;
    logic signed [11:0] acc_next;
    logic lane_saturated;
    logic lane_fire;
    logic [19:0] ram_q;
    logic [2:0] claimed_ops;

    assign issue_ready = (state == S_IDLE) && !cfg_open;
    assign accept_pulse = issue_valid && issue_ready;
    assign state_code = state;
    assign result_sum = acc;
    assign result_valid = (state == S_DONE);
    assign result_zero_path = zero_path_reg;
    assign ram_ce = (state == S_RD0);
    assign ram_addr = {1'b0, group_reg};

    wire [1:0] idx0_w = word0[17:16];
    wire [1:0] idx1_w = word0[19:18];
    wire signed [7:0] pair0_val = $signed(word0[7:0]);
    wire signed [7:0] pair1_val = $signed(word0[15:8]);

    wire sm0 = slot_mask[0];
    wire sm1 = slot_mask[1];
    wire sm2 = slot_mask[2];
    wire sm3 = slot_mask[3];
    wire im0 = issue_reg[0];
    wire im1 = issue_reg[1];
    wire im2 = issue_reg[2];
    wire im3 = issue_reg[3];

    always_comb begin
        rank1 = sm0 ? 3'd1 : 3'd0;
        rank2 = rank1 + (sm1 ? 3'd1 : 3'd0);
        rank3 = rank2 + (sm2 ? 3'd1 : 3'd0);
        remaining_n = rank3 + (sm3 ? 3'd1 : 3'd0);
        sel0 = 2'd0;
        sel1 = 2'd0;
        sel2 = 2'd0;
        sel3 = 2'd0;
        if (sm0) sel0 = 2'd0;
        if (sm1) begin
            case (rank1)
                3'd0: sel0 = 2'd1; 3'd1: sel1 = 2'd1;
                3'd2: sel2 = 2'd1; default: sel3 = 2'd1;
            endcase
        end
        if (sm2) begin
            case (rank2)
                3'd0: sel0 = 2'd2; 3'd1: sel1 = 2'd2;
                3'd2: sel2 = 2'd2; default: sel3 = 2'd2;
            endcase
        end
        if (sm3) begin
            case (rank3)
                3'd0: sel0 = 2'd3; 3'd1: sel1 = 2'd3;
                3'd2: sel2 = 2'd3; default: sel3 = 2'd3;
            endcase
        end
        if (LANES >= 4) batch_n = remaining_n;
        else if (LANES == 2) batch_n = (remaining_n >= 3'd2) ? 3'd2 : remaining_n;
        else batch_n = (remaining_n >= 3'd1) ? 3'd1 : remaining_n;
    end

    logic signed [7:0] pos_val [0:3];
    logic signed [7:0] issue_val [0:3];
    logic signed [7:0] lv0, lv1, lv2, lv3;
    always_comb begin
        pos_val[0] = (idx0_w == 2'd0) ? pair0_val : (idx1_w == 2'd0) ? pair1_val : 8'sd0;
        pos_val[1] = (idx0_w == 2'd1) ? pair0_val : (idx1_w == 2'd1) ? pair1_val : 8'sd0;
        pos_val[2] = (idx0_w == 2'd2) ? pair0_val : (idx1_w == 2'd2) ? pair1_val : 8'sd0;
        pos_val[3] = (idx0_w == 2'd3) ? pair0_val : (idx1_w == 2'd3) ? pair1_val : 8'sd0;
        issue_val[0] = im0 ? pos_val[0] : 8'sd0;
        issue_val[1] = im1 ? pos_val[1] : 8'sd0;
        issue_val[2] = im2 ? pos_val[2] : 8'sd0;
        issue_val[3] = im3 ? pos_val[3] : 8'sd0;
        lv0 = issue_val[sel0];
        lv1 = issue_val[sel1];
        lv2 = issue_val[sel2];
        lv3 = issue_val[sel3];
        if (3'd0 >= batch_n) lv0 = 8'sd0;
        if (3'd1 >= batch_n) lv1 = 8'sd0;
        if (3'd2 >= batch_n) lv2 = 8'sd0;
        if (3'd3 >= batch_n) lv3 = 8'sd0;
        claimed_ops = im0 ? 3'd1 : 3'd0;
        claimed_ops = claimed_ops + (im1 ? 3'd1 : 3'd0);
        claimed_ops = claimed_ops + (im2 ? 3'd1 : 3'd0);
        claimed_ops = claimed_ops + (im3 ? 3'd1 : 3'd0);
    end

    genvar gi;
    generate
        for (gi = 0; gi < 8; gi = gi + 1) begin : g_lane_op
            if (gi < LANES) begin : g_present
                assign lane_weights[gi * 8 +: 8] = (gi == 0) ? lv0
                                             : (gi == 1) ? lv1
                                             : (gi == 2) ? lv2
                                             : (gi == 3) ? lv3 : 8'sd0;
            end else begin : g_absent
                assign lane_weights[gi * 8 +: 8] = 8'sd0;
            end
        end
    endgenerate

    assign batch_mask = ((3'd0 < batch_n) ? (4'b1 << sel0) : 4'b0)
                      | ((3'd1 < batch_n) ? (4'b1 << sel1) : 4'b0)
                      | ((3'd2 < batch_n) ? (4'b1 << sel2) : 4'b0)
                      | ((3'd3 < batch_n) ? (4'b1 << sel3) : 4'b0);
    assign lane_fire = (state == S_BATCH) && (slot_mask != 4'd0) && !lane_stall;
    // 观测事实：当拍占用的 lane 槽位数（四条候选操作全部发射）。
    assign lane_fire_count = lane_fire ? batch_n : 3'd0;

    np7_weight_ram weight_ram (
        .clk(clk), .rst(rst), .cfg_valid(cfg_valid), .cfg_ready(cfg_ready),
        .cfg_addr(cfg_addr), .cfg_wdata(cfg_wdata), .cfg_open(cfg_open),
        .cfg_error(cfg_error), .rd_ce(ram_ce), .rd_addr(ram_addr), .rd_q(ram_q)
    );

    np7_shared_synapse_lane #(.LANES(LANES)) lanes (
        .op_weights(lane_weights), .op_count(batch_n), .acc_seed(acc),
        .acc_next(acc_next), .saturated(lane_saturated)
    );

    wire obs_lat = (state == S_LAT);
    wire any_fire_now = ram_ce || lane_fire;
    wire stall_now = ((state == S_BATCH) && (slot_mask != 4'd0) && lane_stall)
                   || ((state == S_DONE) && !result_ready);
    wire done_handshake = (state == S_DONE) && result_ready;

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= S_IDLE;
            slot_mask <= 4'd0;
            issue_reg <= 4'd0;
            group_reg <= 4'd0;
            zero_path_reg <= 1'b0;
            word0 <= 20'd0;
            acc <= 12'sd0;
            protocol_error <= 1'b0;
            group_read_requests_state <= 32'd0;
            weight_values_fetched_state <= 32'd0;
            lane_ops_issued_state <= 32'd0;
            zero_fast_paths_state <= 32'd0;
            busy_cycles_state <= 32'd0;
            stall_cycles_state <= 32'd0;
            completed_groups_state <= 32'd0;
            structural_skips_state <= 32'd0;
            input_zero_groups_state <= 32'd0;
            activity_zero_after_structure_state <= 32'd0;
            saturation_events_state <= 32'd0;
            total_cycles_state <= 32'd0;
        end else begin
            if (accept_pulse || state != S_IDLE)
                total_cycles_state <= total_cycles_state + 32'd1;
            if (any_fire_now)
                busy_cycles_state <= busy_cycles_state + 32'd1;
            if (stall_now)
                stall_cycles_state <= stall_cycles_state + 32'd1;
            if (ram_ce)
                group_read_requests_state <= group_read_requests_state + 32'd1;
            // 作弊点：自报操作数 = popcount(issue_mask)，与当拍实际占用的
            // lane 槽位数（lane_fire_count）无关。
            if (obs_lat)
                lane_ops_issued_state <= lane_ops_issued_state
                    + {29'd0, claimed_ops};
            if (lane_fire && lane_saturated)
                saturation_events_state <= saturation_events_state + 32'd1;
            if (done_handshake) begin
                completed_groups_state <= completed_groups_state + 32'd1;
                if (zero_path_reg)
                    zero_fast_paths_state <= zero_fast_paths_state + 32'd1;
            end
            if (obs_lat)
                weight_values_fetched_state <= weight_values_fetched_state + 32'd2;
            case (state)
                S_IDLE: begin
                    if (accept_pulse) begin
                        group_reg <= issue_group;
                        if (issue_mask & ~issue_activity)
                            protocol_error <= 1'b1;
                        acc <= 12'sd0;
                        word0 <= 20'd0;
                        issue_reg <= issue_mask;
                        zero_path_reg <= (issue_mask == 4'd0);
                        structural_skips_state <= structural_skips_state
                            + {29'd0, issue_skip_count};
                        if (issue_activity == 4'd0)
                            input_zero_groups_state <= input_zero_groups_state + 32'd1;
                        else if (issue_mask == 4'd0)
                            activity_zero_after_structure_state
                                <= activity_zero_after_structure_state + 32'd1;
                        if (issue_mask == 4'd0) begin
                            slot_mask <= 4'd0;
                            state <= S_DONE;
                        end else begin
                            // 作弊点：发射全部四条候选槽位。
                            slot_mask <= 4'b1111;
                            state <= S_RD0;
                        end
                    end
                end
                S_RD0: state <= S_LAT;
                S_LAT: begin
                    word0 <= ram_q;
                    state <= S_BATCH;
                end
                S_BATCH: begin
                    if (slot_mask == 4'd0) begin
                        state <= S_DONE;
                    end else if (!lane_stall) begin
                        acc <= acc_next;
                        slot_mask <= slot_mask & ~batch_mask;
                        if ((slot_mask & ~batch_mask) == 4'd0)
                            state <= S_DONE;
                    end
                end
                S_DONE: if (result_ready) state <= S_IDLE;
                default: state <= S_IDLE;
            endcase
        end
    end
    assign cfg_illegal_index = 1'b0;
endmodule