// NP7 dense 格式共享突触执行单元顶层。
//
// 一组 = 4 个权重槽 = 两个 20-bit RAM 字（每字 2 权重 + 4 bit 保留必须为 0）。
// 因此 dense 每非零事务发 2 次 RAM 请求、读取 4 个权重槽。lane 阵列与饱和加法
// 来自共享模块 np7_shared_synapse_lane，与 sparse 顶层完全同源：格式只改变读取
// 数、请求数与周期，不改变执行语义与突触和。
//
// 周期合同（PR #6 管理员裁定 B-V1+V2，见 docs/planning/NPU_PRUNING_NP7_DECISION_B_V1_V2.md）：
// 非零事务 = 2(READ) + 1(LAT) + ceil(k/L)(BATCH) 拍，accept 折进上一事务的退出边沿，
// 只有首事务额外计 1 拍冷启动；issue_mask=0 走 V1 零路径，恰好 1 拍（accept 与 result
// 同一边沿完成），不发 RAM 请求、不发 lane 操作。不存在独立 DONE 拍：结果退出与下一
// 事务接受允许同边沿重叠（V2），但任意时刻最多保存一个未退出结果（单槽弹性流水）。
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
    localparam logic [2:0] S_HOLD = 3'd5;
    logic [2:0] state;
    logic [3:0] pending_mask;
    logic [3:0] group_reg;
    logic       zero_path_reg;
    logic [19:0] word0;
    logic [19:0] word1;
    logic signed [11:0] acc;
    logic signed [11:0] hold_sum;
    logic hold_zero;
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

    // dense 记录无位置索引；CONFIG 拒绝保留位非零的字（PR #6 评审意见 2）。
    // cfg_wr_ok 进 RAM 写使能：非法字被硬件丢弃、cfg_error 锁存，提示信号仅供观测。
    wire dense_record_illegal_next = (cfg_wdata[19:16] != 4'b0000);
    wire cfg_wr_ok = !dense_record_illegal_next;
    assign cfg_illegal_index = cfg_valid && cfg_open && dense_record_illegal_next;
    assign state_code = state;

    // ===================== B-V1+V2 周期协议 =====================
    // 合同来源：PR #6 管理员评论 5498372499（docs/planning/NPU_PRUNING_NP7_DECISION_B_V1_V2.md）。
    // V1 零路径单拍：issue_valid && issue_ready && issue_mask==0 不发 RAM 请求、不发 lane
    //   操作，结果为 0 且 result_zero_path=1；当拍 result_ready=1 时 accept 与 result 同一
    //   边沿完成（只计 1 拍）；result_ready=0 时把 0 结果锁存进 S_HOLD 稳定保持。
    // V2 退出与接受重叠：非零事务最后一批 BATCH 得到最终 acc_next 的当拍，若 result_ready=1
    //   就当拍完成结果，不再进独立 DONE 拍；同一边沿允许 issue_ready=1 并接受下一事务。
    //   结果背压时锁存旧结果并停止接收，只有旧结果退出的同一边沿才可接受下一事务；
    //   lane_stall=1 时 batch_last 不成立，因此既不会提前完成也不会提前接受。
    // 元数据分离：正在退出的结果走组合 acc_next / 寄存器 hold_sum，accept 只写新事务寄存器。
    wire hold_active = (state == S_HOLD);
    wire batch_last = (state == S_BATCH) && (pending_mask != 4'd0) && !lane_stall
                      && ((pending_mask & ~batch_mask) == 4'd0);
    wire retire_prev = result_ready && (hold_active || batch_last);
    assign issue_ready = !cfg_open && ((state == S_IDLE) || retire_prev);
    assign accept_pulse = issue_valid && issue_ready;
    wire zero_now = (state == S_IDLE) && accept_pulse && (issue_mask == 4'd0) && result_ready;
    assign result_valid = hold_active || batch_last || zero_now;
    assign result_sum = hold_active ? hold_sum : (batch_last ? acc_next : 12'sd0);
    assign result_zero_path = hold_active ? hold_zero : zero_now;
    wire retire_now = result_valid && result_ready;
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
        .cfg_wr_ok(cfg_wr_ok),
        .cfg_error(cfg_error), .rd_ce(ram_ce), .rd_addr(ram_addr), .rd_q(ram_q)
    );

    np7_shared_synapse_lane #(.LANES(LANES)) lanes (
        .op_weights(lane_weights), .op_count(batch_n), .acc_seed(acc),
        .acc_next(acc_next), .saturated(lane_saturated)
    );

    wire word_reserved_nonzero = (word0[19:16] != 4'b0000) || (ram_q[19:16] != 4'b0000);

    // 逐拍互斥类别（与 oracle/验证器同一优先级：RAM>LANE>LAT>LANE_STALL>BACKPRESSURE
    // >HOLD_RETIRE>ZERO>ACCEPT），busy 与 stall 不重叠。
    wire edge_busy = ram_ce || lane_fire;
    wire edge_lat = (state == S_LAT);
    wire edge_lstall = (state == S_BATCH) && (pending_mask != 4'd0) && lane_stall;
    wire edge_bp = hold_active && !result_ready;
    wire edge_hold_retire = hold_active && result_ready;
    wire edge_zero = zero_now;
    wire edge_accept = accept_pulse && !zero_now && !retire_prev;
    wire edge_active = edge_busy || edge_lat || edge_lstall || edge_bp
                       || edge_hold_retire || edge_zero || edge_accept;
    wire any_fire_now = edge_busy;
    wire stall_now = edge_lstall || edge_bp;
    always_ff @(posedge clk) begin
        if (rst) begin
            state <= S_IDLE;
            pending_mask <= 4'd0;
            group_reg <= 4'd0;
            zero_path_reg <= 1'b0;
            word0 <= 20'd0;
            word1 <= 20'd0;
            acc <= 12'sd0;
            hold_sum <= 12'sd0;
            hold_zero <= 1'b0;
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
            // 账本：逐拍互斥类别，busy 与 stall 不重叠。新恒等式
            // total = busy + latency + lane_stall + backpressure + hold_retire
            //       + zero_single + accept_own（stall = lane_stall + backpressure）由 cosim
            // 核对；旧口径 total = accept + latency + busy + stall + done 已随 B-V1+V2 作废。
            if (edge_active)
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
            if (accept_pulse && issue_mask == 4'd0)
                zero_fast_paths_state <= zero_fast_paths_state + 32'd1;
            if (retire_now) begin
                completed_groups_state <= completed_groups_state + 32'd1;
            end
            if (word_reserved_nonzero && state == S_BATCH)
                protocol_error <= 1'b1;
            if (accept_pulse) begin
                // 元数据与正在退出的结果严格分离：退出结果走 acc_next/hold_sum，
                // accept 只写新事务寄存器（group/pending/acc/word），同拍不互相覆盖。
                group_reg <= issue_group;
                if (issue_mask & ~issue_activity)
                    protocol_error <= 1'b1;
                acc <= 12'sd0;
                word0 <= 20'd0;
                word1 <= 20'd0;
                pending_mask <= issue_mask;
                if (issue_activity == 4'd0)
                    input_zero_groups_state <= input_zero_groups_state + 32'd1;
                else if (issue_mask == 4'd0)
                    activity_zero_after_structure_state
                        <= activity_zero_after_structure_state + 32'd1;
                structural_skips_state <= structural_skips_state
                    + {29'd0, issue_skip_count};
                if (issue_mask == 4'd0) begin
                    zero_path_reg <= 1'b1;
                    if (zero_now) begin
                        // V1：accept 与 result 同一边沿完成，只占 1 拍。
                        state <= S_IDLE;
                    end else begin
                        // V1 背压：0 结果锁存并稳定保持到 result_ready。
                        hold_sum <= 12'sd0;
                        hold_zero <= 1'b1;
                        state <= S_HOLD;
                    end
                end else begin
                    zero_path_reg <= 1'b0;
                    state <= S_RD0;
                end
            end else begin
                case (state)
                    S_IDLE: ;
                    S_RD0: begin
                        // 两组字：S_RD0 发低字地址请求，S_RD1 发高字地址请求。
                        state <= S_RD1;
                    end
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
                        if (lane_fire) begin
                            acc <= acc_next;
                            pending_mask <= pending_mask & ~batch_mask;
                            if (batch_last) begin
                                if (result_ready) begin
                                    // V2：最后一批当拍退出，不再进独立 DONE 拍。
                                    state <= S_IDLE;
                                end else begin
                                    hold_sum <= acc_next;
                                    hold_zero <= 1'b0;
                                    state <= S_HOLD;
                                end
                            end
                        end
                    end
                    S_HOLD: begin
                        if (result_ready)
                            state <= S_IDLE;
                    end
                    default: state <= S_IDLE;
                endcase
            end
        end
    end

endmodule