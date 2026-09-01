// NP7 dense 格式共享突触执行单元顶层。
//
// 一组 = 4 个权重槽 = 两个 20-bit RAM 字（每字 2 权重 + 4 bit 保留必须为 0）。
// 因此 dense 每非零事务发 2 次 RAM 请求、读取 4 个权重槽。lane 阵列与饱和加法
// 来自共享模块 np7_shared_synapse_lane，与 sparse 顶层完全同源：格式只改变读取
// 数、请求数与周期，不改变执行语义与突触和。
//
// 周期合同（NP7.0 §2.1）：ACCEPT 1 拍 + READ 2 拍 + LATENCY 1 拍
// + ceil(k/L) 拍发射 + DONE 至少 1 拍；issue_mask=0 时走零快速路径
// （ACCEPT 1 拍 + DONE 1 拍），不发 RAM 请求、不发 lane 操作，仍产生恰好一个 done。
module np7_exec_unit_dense #(
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
    logic       zero_path_reg;
    logic [19:0] word0;
    logic [19:0] word1;
    logic signed [11:0] acc;
    logic [2:0] remaining_n;
    logic [2:0] batch_n;
    logic [1:0] sel0, sel1, sel2, sel3;
    logic [2:0] rank1, rank2, rank3;
    logic [4:0] read_offset;
    logic [LANES * 8 - 1:0] lane_weights;
    logic signed [11:0] acc_next;
    logic lane_saturated;
    logic lane_fire;
    logic [19:0] ram_q;

    // dense 记录无位置索引；CONFIG 拒绝保留位非零的字。
    assign cfg_illegal_index = cfg_valid && cfg_open
        && (cfg_wdata[19:16] != 4'b0000);
    assign issue_ready = (state == S_IDLE) && !cfg_open;
    assign accept_pulse = issue_valid && issue_ready;
    assign state_code = state;
    assign result_sum = acc;
    assign result_valid = (state == S_DONE);
    assign result_zero_path = zero_path_reg;
    assign ram_ce = (state == S_RD0) || (state == S_RD1);
    assign read_offset = (state == S_RD1) ? 5'd1 : 5'd0;
    assign ram_addr = {group_reg, 1'b0} + read_offset;

    // dense 记录解码：两组权重 + 4 bit 保留；slot 位置固定 0..3。
    wire signed [7:0] slot0_val = $signed(word0[7:0]);
    wire signed [7:0] slot1_val = $signed(word0[15:8]);
    wire signed [7:0] slot2_val = $signed(word1[7:0]);
    wire signed [7:0] slot3_val = $signed(word1[15:8]);

    // Icarus 对 always_comb 内的位选支持有限，先以常量位选引出单比特线网。
    wire pm0 = pending_mask[0];
    wire pm1 = pending_mask[1];
    wire pm2 = pending_mask[2];
    wire pm3 = pending_mask[3];

    // 升序压缩：把 pending_mask 的置位位置按索引升序写入 sel0..sel3。
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
    logic [63:0] lane_all;

    // 压缩槽位 -> 权重值的多路选择（只有常量位选，便于 Icarus/Vivado 一致展开）。
    always_comb begin
        case (sel0)
            2'd0: lv0 = slot0_val; 2'd1: lv0 = slot1_val;
            2'd2: lv0 = slot2_val; default: lv0 = slot3_val;
        endcase
        case (sel1)
            2'd0: lv1 = slot0_val; 2'd1: lv1 = slot1_val;
            2'd2: lv1 = slot2_val; default: lv1 = slot3_val;
        endcase
        case (sel2)
            2'd0: lv2 = slot0_val; 2'd1: lv2 = slot1_val;
            2'd2: lv2 = slot2_val; default: lv2 = slot3_val;
        endcase
        case (sel3)
            2'd0: lv3 = slot0_val; 2'd1: lv3 = slot1_val;
            2'd2: lv3 = slot2_val; default: lv3 = slot3_val;
        endcase
        if (3'd0 >= remaining_n) lv0 = 8'sd0;
        if (3'd1 >= remaining_n) lv1 = 8'sd0;
        if (3'd2 >= remaining_n) lv2 = 8'sd0;
        if (3'd3 >= remaining_n) lv3 = 8'sd0;
    end

    genvar gi;
    generate
        for (gi = 0; gi < 8; gi = gi + 1) begin : g_lane_op
            if (gi < LANES) begin : g_present
                assign lane_all[gi * 8 +: 8] = (gi == 0) ? lv0
                                            : (gi == 1) ? lv1
                                            : (gi == 2) ? lv2
                                            : (gi == 3) ? lv3 : 8'sd0;
            end else begin : g_absent
                assign lane_all[gi * 8 +: 8] = 8'sd0;
            end
        end
    endgenerate

    assign lane_weights = lane_all[LANES * 8 - 1:0];
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

    wire word_reserved_nonzero = (word0[19:16] != 4'b0000) || (ram_q[19:16] != 4'b0000);
    wire any_fire_now = (ram_ce) || lane_fire;
    wire stall_now = ((state == S_BATCH) && (pending_mask != 4'd0) && lane_stall)
                   || ((state == S_DONE) && !result_ready);
    wire done_handshake = (state == S_DONE) && result_ready;
    always_ff @(posedge clk) begin
        if (rst) begin
            state <= S_IDLE;
            pending_mask <= 4'd0;
            group_reg <= 4'd0;
            zero_path_reg <= 1'b0;
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
            // 账本：busy 与 stall 互斥，overhead（accept/latency/done）单独成段，
            // 恒等式 total = accept + latency + busy + stall + done 由 cosim 核对。
            if (accept_pulse || state != S_IDLE)
                total_cycles_state <= total_cycles_state + 32'd1;
            if (any_fire_now)
                busy_cycles_state <= busy_cycles_state + 32'd1;
            if (stall_now)
                stall_cycles_state <= stall_cycles_state + 32'd1;
            if (ram_ce)
                group_read_requests_state <= group_read_requests_state + 32'd1;
            if (lane_fire)
                lane_ops_issued_state <= lane_ops_issued_state
                    + {29'd0, batch_n};
            if (lane_fire && lane_saturated)
                saturation_events_state <= saturation_events_state + 32'd1;
            if (done_handshake) begin
                completed_groups_state <= completed_groups_state + 32'd1;
                if (zero_path_reg)
                    zero_fast_paths_state <= zero_fast_paths_state + 32'd1;
            end
            if (word_reserved_nonzero && state == S_BATCH)
                protocol_error <= 1'b1;
            case (state)
                S_IDLE: begin
                    if (accept_pulse) begin
                        group_reg <= issue_group;
                        if (issue_mask != issue_activity)
                            protocol_error <= 1'b1;
                        acc <= 12'sd0;
                        word0 <= 20'd0;
                        word1 <= 20'd0;
                        pending_mask <= issue_mask;
                        // 分账：输入为零与结构跳过互斥，两者都不发 RAM 请求。
                        if (issue_activity == 4'd0)
                            input_zero_groups_state <= input_zero_groups_state + 32'd1;
                        else if (issue_mask == 4'd0)
                            activity_zero_after_structure_state
                                <= activity_zero_after_structure_state + 32'd1;
                        structural_skips_state <= structural_skips_state
                            + {29'd0, issue_skip_count};
                        if (issue_mask == 4'd0) begin
                            // 零突触快速路径：无读、无 lane 发射，仍走 DONE 协议。
                            zero_path_reg <= 1'b1;
                            state <= S_DONE;
                        end else begin
                            zero_path_reg <= 1'b0;
                            state <= S_RD0;
                        end
                    end
                end
                S_RD0: state <= S_RD1;
                S_RD1: begin
                    word0 <= ram_q;
                    state <= S_LAT;
                end
                S_LAT: begin
                    word1 <= ram_q;
                    weight_values_fetched_state <= weight_values_fetched_state + 32'd4;
                    state <= S_BATCH;
                end
                S_BATCH: begin
                    if (pending_mask == 4'd0) begin
                        state <= S_DONE;
                    end else if (!lane_stall) begin
                        acc <= acc_next;
                        pending_mask <= pending_mask & ~batch_mask;
                        // 最后一批发射的当拍直接进 DONE，不额外消耗空拍。
                        if ((pending_mask & ~batch_mask) == 4'd0)
                            state <= S_DONE;
                    end
                end
                S_DONE: begin
                    if (result_ready)
                        state <= S_IDLE;
                end
                default: state <= S_IDLE;
            endcase
        end
    end

endmodule