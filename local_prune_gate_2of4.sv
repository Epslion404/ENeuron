// 独立四选二局部剪枝控制器。
//
// 控制器只消费已经归一化到 0..3 的四路证据，不包含神经元方程。
// PRUNE_COMMIT 用四拍顺序扫描形成 top-2，并在最后一拍原子切换结构掩码。
module local_prune_gate_2of4 (
    input  logic                         clk,
    input  logic                         rst,

    // 与神经元共用的模式：0=CONFIG，1=TRAIN，2=INFER。
    input  logic [1:0]                   mode_state,

    // 单槽运行命令与响应。
    input  logic                         cmd_valid,
    output logic                         cmd_ready,
    input  logic [2:0]                   cmd_opcode,
    input  logic [15:0]                  cmd_id,
    input  logic [7:0]                   evidence_levels_flat,
    input  logic                         modulator_nonzero,
    input  logic                         core_idle,
    input  logic                         pending_snapshot,
    input  logic                         pending_mod_commit,
    output logic                         rsp_valid,
    input  logic                         rsp_ready,
    output logic [2:0]                   rsp_status,
    output logic [15:0]                  rsp_id,
    output logic [3:0]                   rsp_mask,

    // CONFIG 专用直接掩码测试口；运行时剪枝不得使用此入口。
    input  logic                         cfg_mask_valid,
    output logic                         cfg_mask_ready,
    input  logic [3:0]                   cfg_mask_data,
    output logic                         cfg_mask_done,
    output logic                         cfg_mask_error,

    // 读取/计算发射前的结构门控与分层工作量账本。
    input  logic                         issue_valid,
    input  logic [3:0]                   activity_mask,
    input  logic                         issue_layer_output,
    output logic [3:0]                   issue_mask,

    output logic                         busy,
    output logic                         protocol_error,
    output logic                         fsm_state,
    output logic [1:0]                   scan_index_state,
    output logic [15:0]                  utility_flat,
    output logic [3:0]                   structural_mask_state,
    output logic                         mask_valid_state,
    output logic                         last_observation_valid_state,
    output logic [15:0]                  last_observation_id_state,
    output logic                         last_commit_valid_state,
    output logic [15:0]                  last_commit_id_state,
    output logic [31:0]                  mask_commits_state,
    output logic [31:0]                  illegal_commands_state,
    output logic [31:0]                  hidden_dense_reads_state,
    output logic [31:0]                  hidden_reads_issued_state,
    output logic [31:0]                  hidden_synapse_ops_state,
    output logic [31:0]                  hidden_reads_saved_state,
    output logic [31:0]                  output_dense_reads_state,
    output logic [31:0]                  output_reads_issued_state,
    output logic [31:0]                  output_synapse_ops_state,
    output logic [31:0]                  output_reads_saved_state,
    output logic [31:0]                  inactive_groups_state,
    output logic [31:0]                  groups_skipped_state
);

    localparam logic [1:0] MODE_CONFIG = 2'd0;
    localparam logic [1:0] MODE_TRAIN  = 2'd1;
    localparam logic [1:0] MODE_INFER  = 2'd2;

    localparam logic [2:0] OP_OBSERVE      = 3'd0;
    localparam logic [2:0] OP_PRUNE_CLEAR  = 3'd1;
    localparam logic [2:0] OP_PRUNE_COMMIT = 3'd2;
    localparam logic [2:0] OP_MASK_READ    = 3'd3;

    localparam logic [2:0] ST_OK                = 3'd0;
    localparam logic [2:0] ST_BAD_OPCODE        = 3'd1;
    localparam logic [2:0] ST_BAD_MODE          = 3'd2;
    localparam logic [2:0] ST_UNSAFE            = 3'd3;
    localparam logic [2:0] ST_STALE_ID          = 3'd4;
    localparam logic [2:0] ST_ALREADY_COMMITTED = 3'd5;
    localparam logic [2:0] ST_BAD_ARG           = 3'd6;

    typedef enum logic {
        S_IDLE,
        S_SCAN
    } state_t;

    state_t state;
    logic [3:0] utility [0:3];
    logic [3:0] structural_mask;
    logic mask_valid;
    logic last_observation_valid;
    logic [15:0] last_observation_id;
    logic last_commit_valid;
    logic [15:0] last_commit_id;

    logic rsp_valid_reg;
    logic [2:0] rsp_status_reg;
    logic [15:0] rsp_id_reg;
    logic [3:0] rsp_mask_reg;

    logic [1:0] scan_index;
    logic [15:0] pending_commit_id;
    logic best1_valid;
    logic best2_valid;
    logic [3:0] best1_score;
    logic [3:0] best2_score;
    logic [1:0] best1_index;
    logic [1:0] best2_index;
    logic next_best1_valid;
    logic next_best2_valid;
    logic [3:0] next_best1_score;
    logic [3:0] next_best2_score;
    logic [1:0] next_best1_index;
    logic [1:0] next_best2_index;
    logic [3:0] completed_commit_mask;

    logic [31:0] mask_commits;
    logic [31:0] illegal_commands;
    logic [31:0] hidden_dense_reads;
    logic [31:0] hidden_reads_issued;
    logic [31:0] hidden_synapse_ops;
    logic [31:0] hidden_reads_saved;
    logic [31:0] output_dense_reads;
    logic [31:0] output_reads_issued;
    logic [31:0] output_synapse_ops;
    logic [31:0] output_reads_saved;
    logic [31:0] inactive_groups;
    logic [31:0] groups_skipped;

    integer i;
    integer decayed_value;
    integer accumulated_value;

    function automatic [2:0] popcount4(input logic [3:0] value);
        popcount4 = value[0] + value[1] + value[2] + value[3];
    endfunction

    function automatic logic exact_two(input logic [3:0] value);
        exact_two = popcount4(value) == 3'd2;
    endfunction

    wire [3:0] effective_structural_mask = mask_valid ? structural_mask : 4'b1111;
    wire [2:0] dense_work = popcount4(activity_mask);
    wire [2:0] issued_work = popcount4(issue_mask);
    wire [2:0] saved_work = dense_work - issued_work;

    assign cmd_ready = (state == S_IDLE) && !rsp_valid_reg;
    assign cfg_mask_ready = cmd_ready && !cmd_valid;
    assign busy = (state != S_IDLE) || rsp_valid_reg;
    assign fsm_state = state;
    assign scan_index_state = scan_index;
    assign rsp_valid = rsp_valid_reg;
    assign rsp_status = rsp_status_reg;
    assign rsp_id = rsp_id_reg;
    assign rsp_mask = rsp_mask_reg;
    assign issue_mask = activity_mask & effective_structural_mask;
    assign utility_flat = {utility[3], utility[2], utility[1], utility[0]};
    assign structural_mask_state = structural_mask;
    assign mask_valid_state = mask_valid;
    assign last_observation_valid_state = last_observation_valid;
    assign last_observation_id_state = last_observation_id;
    assign last_commit_valid_state = last_commit_valid;
    assign last_commit_id_state = last_commit_id;
    assign mask_commits_state = mask_commits;
    assign illegal_commands_state = illegal_commands;
    assign hidden_dense_reads_state = hidden_dense_reads;
    assign hidden_reads_issued_state = hidden_reads_issued;
    assign hidden_synapse_ops_state = hidden_synapse_ops;
    assign hidden_reads_saved_state = hidden_reads_saved;
    assign output_dense_reads_state = output_dense_reads;
    assign output_reads_issued_state = output_reads_issued;
    assign output_synapse_ops_state = output_synapse_ops;
    assign output_reads_saved_state = output_reads_saved;
    assign inactive_groups_state = inactive_groups;
    assign groups_skipped_state = groups_skipped;

    // 当前扫描项与已保存 top-2 比较。扫描顺序固定为 0..3，只有严格更大才
    // 替换，因此完全同分时自然保留编号更小的连接。
    always_comb begin
        next_best1_valid = best1_valid;
        next_best2_valid = best2_valid;
        next_best1_score = best1_score;
        next_best2_score = best2_score;
        next_best1_index = best1_index;
        next_best2_index = best2_index;

        if (!best1_valid || (utility[scan_index] > best1_score)) begin
            next_best2_valid = best1_valid;
            next_best2_score = best1_score;
            next_best2_index = best1_index;
            next_best1_valid = 1'b1;
            next_best1_score = utility[scan_index];
            next_best1_index = scan_index;
        end else if (!best2_valid || (utility[scan_index] > best2_score)) begin
            next_best2_valid = 1'b1;
            next_best2_score = utility[scan_index];
            next_best2_index = scan_index;
        end

        completed_commit_mask = (4'b0001 << next_best1_index)
            | (4'b0001 << next_best2_index);
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= S_IDLE;
            for (i = 0; i < 4; i = i + 1)
                utility[i] <= '0;
            structural_mask <= 4'b1111;
            mask_valid <= 1'b0;
            last_observation_valid <= 1'b0;
            last_observation_id <= '0;
            last_commit_valid <= 1'b0;
            last_commit_id <= '0;
            rsp_valid_reg <= 1'b0;
            rsp_status_reg <= ST_OK;
            rsp_id_reg <= '0;
            rsp_mask_reg <= 4'b1111;
            scan_index <= '0;
            pending_commit_id <= '0;
            best1_valid <= 1'b0;
            best2_valid <= 1'b0;
            best1_score <= '0;
            best2_score <= '0;
            best1_index <= '0;
            best2_index <= '0;
            mask_commits <= '0;
            illegal_commands <= '0;
            hidden_dense_reads <= '0;
            hidden_reads_issued <= '0;
            hidden_synapse_ops <= '0;
            hidden_reads_saved <= '0;
            output_dense_reads <= '0;
            output_reads_issued <= '0;
            output_synapse_ops <= '0;
            output_reads_saved <= '0;
            inactive_groups <= '0;
            groups_skipped <= '0;
            cfg_mask_done <= 1'b0;
            cfg_mask_error <= 1'b0;
            protocol_error <= 1'b0;
        end else begin
            cfg_mask_done <= 1'b0;
            cfg_mask_error <= 1'b0;
            protocol_error <= 1'b0;

            if (rsp_valid_reg && rsp_ready)
                rsp_valid_reg <= 1'b0;

            // 工作量按 issue 当拍、掩码切换前的稳定结构状态记账。
            if (issue_valid) begin
                if (activity_mask == 0)
                    inactive_groups <= inactive_groups + 1'b1;
                else if (issue_mask == 0)
                    groups_skipped <= groups_skipped + 1'b1;

                if (issue_layer_output) begin
                    output_dense_reads <= output_dense_reads + dense_work;
                    output_reads_issued <= output_reads_issued + issued_work;
                    output_synapse_ops <= output_synapse_ops + issued_work;
                    output_reads_saved <= output_reads_saved + saved_work;
                end else begin
                    hidden_dense_reads <= hidden_dense_reads + dense_work;
                    hidden_reads_issued <= hidden_reads_issued + issued_work;
                    hidden_synapse_ops <= hidden_synapse_ops + issued_work;
                    hidden_reads_saved <= hidden_reads_saved + saved_work;
                end
            end

            case (state)
                S_IDLE: begin
                    if (cmd_valid && cmd_ready) begin
                        rsp_id_reg <= cmd_id;
                        rsp_mask_reg <= effective_structural_mask;
                        case (cmd_opcode)
                            OP_OBSERVE: begin
                                rsp_valid_reg <= 1'b1;
                                if (mode_state != MODE_TRAIN) begin
                                    rsp_status_reg <= ST_BAD_MODE;
                                    protocol_error <= 1'b1;
                                    illegal_commands <= illegal_commands + 1'b1;
                                end else if (last_observation_valid
                                        && (cmd_id <= last_observation_id)) begin
                                    rsp_status_reg <= ST_STALE_ID;
                                    protocol_error <= 1'b1;
                                    illegal_commands <= illegal_commands + 1'b1;
                                end else begin
                                    rsp_status_reg <= ST_OK;
                                    if (modulator_nonzero) begin
                                        for (i = 0; i < 4; i = i + 1) begin
                                            if (effective_structural_mask[i]) begin
                                                decayed_value = utility[i] == 0
                                                    ? 0 : utility[i] - 1;
                                                accumulated_value = decayed_value
                                                    + evidence_levels_flat[i*2 +: 2];
                                                utility[i] <= accumulated_value > 15
                                                    ? 4'd15 : accumulated_value[3:0];
                                            end
                                        end
                                    end
                                    last_observation_valid <= 1'b1;
                                    last_observation_id <= cmd_id;
                                end
                            end

                            OP_PRUNE_CLEAR: begin
                                rsp_valid_reg <= 1'b1;
                                if (mode_state != MODE_CONFIG) begin
                                    rsp_status_reg <= ST_BAD_MODE;
                                    protocol_error <= 1'b1;
                                    illegal_commands <= illegal_commands + 1'b1;
                                end else begin
                                    rsp_status_reg <= ST_OK;
                                    rsp_mask_reg <= 4'b1111;
                                    for (i = 0; i < 4; i = i + 1)
                                        utility[i] <= '0;
                                    structural_mask <= 4'b1111;
                                    mask_valid <= 1'b0;
                                    last_observation_valid <= 1'b0;
                                    last_observation_id <= '0;
                                    last_commit_valid <= 1'b0;
                                    last_commit_id <= '0;
                                end
                            end

                            OP_PRUNE_COMMIT: begin
                                if (mode_state != MODE_TRAIN) begin
                                    rsp_valid_reg <= 1'b1;
                                    rsp_status_reg <= ST_BAD_MODE;
                                    protocol_error <= 1'b1;
                                    illegal_commands <= illegal_commands + 1'b1;
                                end else if (!core_idle || issue_valid
                                        || pending_snapshot || pending_mod_commit) begin
                                    rsp_valid_reg <= 1'b1;
                                    rsp_status_reg <= ST_UNSAFE;
                                    protocol_error <= 1'b1;
                                    illegal_commands <= illegal_commands + 1'b1;
                                end else if (mask_valid) begin
                                    rsp_valid_reg <= 1'b1;
                                    rsp_status_reg <= ST_ALREADY_COMMITTED;
                                    protocol_error <= 1'b1;
                                    illegal_commands <= illegal_commands + 1'b1;
                                end else if (last_commit_valid
                                        && (cmd_id <= last_commit_id)) begin
                                    rsp_valid_reg <= 1'b1;
                                    rsp_status_reg <= ST_STALE_ID;
                                    protocol_error <= 1'b1;
                                    illegal_commands <= illegal_commands + 1'b1;
                                end else begin
                                    pending_commit_id <= cmd_id;
                                    scan_index <= 2'd0;
                                    best1_valid <= 1'b0;
                                    best2_valid <= 1'b0;
                                    best1_score <= '0;
                                    best2_score <= '0;
                                    best1_index <= '0;
                                    best2_index <= '0;
                                    state <= S_SCAN;
                                end
                            end

                            OP_MASK_READ: begin
                                rsp_valid_reg <= 1'b1;
                                if ((mode_state != MODE_CONFIG)
                                        && (mode_state != MODE_TRAIN)
                                        && (mode_state != MODE_INFER)) begin
                                    rsp_status_reg <= ST_BAD_MODE;
                                    protocol_error <= 1'b1;
                                    illegal_commands <= illegal_commands + 1'b1;
                                end else begin
                                    rsp_status_reg <= ST_OK;
                                end
                            end

                            default: begin
                                rsp_valid_reg <= 1'b1;
                                rsp_status_reg <= ST_BAD_OPCODE;
                                protocol_error <= 1'b1;
                                illegal_commands <= illegal_commands + 1'b1;
                            end
                        endcase
                    end else if (cfg_mask_valid && cfg_mask_ready) begin
                        cfg_mask_done <= 1'b1;
                        if ((mode_state != MODE_CONFIG) || !exact_two(cfg_mask_data)) begin
                            cfg_mask_error <= 1'b1;
                            protocol_error <= 1'b1;
                            illegal_commands <= illegal_commands + 1'b1;
                        end else begin
                            structural_mask <= cfg_mask_data;
                            mask_valid <= 1'b1;
                        end
                    end
                end

                S_SCAN: begin
                    best1_valid <= next_best1_valid;
                    best2_valid <= next_best2_valid;
                    best1_score <= next_best1_score;
                    best2_score <= next_best2_score;
                    best1_index <= next_best1_index;
                    best2_index <= next_best2_index;
                    if (scan_index == 2'd3) begin
                        structural_mask <= completed_commit_mask;
                        mask_valid <= 1'b1;
                        last_commit_valid <= 1'b1;
                        last_commit_id <= pending_commit_id;
                        mask_commits <= mask_commits + 1'b1;
                        rsp_valid_reg <= 1'b1;
                        rsp_status_reg <= exact_two(completed_commit_mask)
                            ? ST_OK : ST_BAD_ARG;
                        rsp_id_reg <= pending_commit_id;
                        rsp_mask_reg <= completed_commit_mask;
                        state <= S_IDLE;
                    end else begin
                        scan_index <= scan_index + 1'b1;
                    end
                end

                default: state <= S_IDLE;
            endcase
        end
    end

`ifdef FORMAL
    always_ff @(posedge clk) begin
        if (!rst) begin
            if (mask_valid)
                assert(exact_two(structural_mask));
            else
                assert(effective_structural_mask == 4'b1111);
            if (state == S_SCAN)
                assert(!cmd_ready);
            assert(issue_mask == (activity_mask & effective_structural_mask));
        end
    end
`endif

endmodule
