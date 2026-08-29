// Pulse-Mini-L/L2 共用的局部剪枝事务桥。
//
// 神经元核心的 opcode 和内部方程保持不变。桥只负责在 FEEDBACK 接受沿锁存
// 旧 captured direction、串行提交一次 OBSERVE，以及在 PRUNE_COMMIT 成功后
// 自动执行 STATE_CLEAR。任何已更新核心却未更新 utility 的异常都会进入粘滞停机。
module pulse_mini_prune_bridge #(
    parameter bit LAYER_OUTPUT = 1'b0,
    // 单核部署保持原子 commit→clear；网络 barrier 部署关闭后统一广播 clear。
    parameter bit AUTO_CLEAR_ON_COMMIT = 1'b1
) (
    input  logic                         clk,
    input  logic                         rst,

    // 对上保持原 Pulse 命令/响应语义。
    input  logic                         cmd_valid,
    output logic                         cmd_ready,
    input  logic [2:0]                   cmd_opcode,
    input  logic [7:0]                   cmd_arg0,
    input  logic [7:0]                   cmd_arg1,
    output logic                         rsp_valid,
    input  logic                         rsp_ready,
    output logic [2:0]                   rsp_status,
    output logic signed [7:0]            rsp_data,
    output logic                         rsp_spike,

    // 对下连接未经修改的 Pulse 核心。
    output logic                         core_cmd_valid,
    input  logic                         core_cmd_ready,
    output logic [2:0]                   core_cmd_opcode,
    output logic [7:0]                   core_cmd_arg0,
    output logic [7:0]                   core_cmd_arg1,
    input  logic                         core_rsp_valid,
    output logic                         core_rsp_ready,
    input  logic [2:0]                   core_rsp_status,
    input  logic signed [7:0]            core_rsp_data,
    input  logic                         core_rsp_spike,
    input  logic [1:0]                   core_mode_state,
    input  logic                         core_pending_valid,
    input  logic [3:0]                   core_refractory_state,

    // wrapper 已完成绝对值、合法性检查和固定 gain。
    input  logic [7:0]                   scaled_evidence_flat,
    input  logic                         evidence_invalid,

    // 独立剪枝 sideband。OBSERVE 只允许由 FEEDBACK 自动产生。
    input  logic                         prune_cmd_valid,
    output logic                         prune_cmd_ready,
    input  logic [2:0]                   prune_cmd_opcode,
    input  logic [15:0]                  prune_cmd_id,
    output logic                         prune_rsp_valid,
    input  logic                         prune_rsp_ready,
    output logic [2:0]                   prune_rsp_status,
    output logic [15:0]                  prune_rsp_id,
    output logic [3:0]                   prune_rsp_mask,

    // 固定宽度审计状态。
    output logic                         protocol_error,
    output logic [15:0]                  prune_utility_state,
    output logic [3:0]                   prune_structural_mask_state,
    output logic                         prune_mask_valid_state,
    output logic [31:0]                  prune_observe_count_state,
    output logic [31:0]                  prune_refractory_skips_state,
    output logic                         prune_sticky_halt_state,
    output logic [7:0]                   prune_latched_evidence_state,
    output logic [31:0]                  prune_dense_reads_state,
    output logic [31:0]                  prune_reads_issued_state,
    output logic [31:0]                  prune_reads_saved_state
);
    localparam logic [2:0] OP_STATE_CLEAR = 3'd1;
    localparam logic [2:0] OP_TICK = 3'd2;
    localparam logic [2:0] OP_FEEDBACK = 3'd4;

    localparam logic [2:0] PRUNE_OBSERVE = 3'd0;
    localparam logic [2:0] PRUNE_CLEAR = 3'd1;
    localparam logic [2:0] PRUNE_COMMIT = 3'd2;
    localparam logic [2:0] PRUNE_MASK_READ = 3'd3;

    localparam logic [2:0] ST_OK = 3'd0;
    localparam logic [2:0] ST_BAD_OPCODE = 3'd1;
    localparam logic [2:0] ST_BAD_ARG = 3'd2;
    localparam logic [2:0] ST_INTERNAL = 3'd7;

    localparam logic [1:0] MODE_CONFIG = 2'd0;
    localparam logic [1:0] MODE_INFER = 2'd2;

    typedef enum logic [3:0] {
        S_IDLE,
        S_WAIT_CORE_RSP,
        S_ISSUE_OBSERVE,
        S_WAIT_OBSERVE_RSP,
        S_WAIT_PRUNE_RSP,
        S_ISSUE_STATE_CLEAR,
        S_WAIT_STATE_CLEAR_RSP,
        S_ERROR_HALT
    } state_t;

    state_t state;
    logic accepted_feedback;
    logic accepted_feedback_nonzero;
    logic [7:0] latched_evidence;
    logic [15:0] next_observation_id;
    logic observation_id_exhausted;
    logic [31:0] observe_count;
    logic [31:0] refractory_skips;
    logic sticky_halt;

    logic run_rsp_valid_reg;
    logic [2:0] run_rsp_status_reg;
    logic signed [7:0] run_rsp_data_reg;
    logic run_rsp_spike_reg;
    logic prune_rsp_valid_reg;
    logic [2:0] prune_rsp_status_reg;
    logic [15:0] prune_rsp_id_reg;
    logic [3:0] prune_rsp_mask_reg;
    logic [2:0] pending_prune_opcode;
    logic [2:0] buffered_prune_status;
    logic [15:0] buffered_prune_id;
    logic [3:0] buffered_prune_mask;

    logic gate_cmd_valid;
    logic gate_cmd_ready;
    logic [2:0] gate_cmd_opcode;
    logic [15:0] gate_cmd_id;
    logic [7:0] gate_evidence;
    logic gate_modulator_nonzero;
    logic gate_rsp_valid;
    logic gate_rsp_ready;
    logic [2:0] gate_rsp_status;
    logic [15:0] gate_rsp_id;
    logic [3:0] gate_rsp_mask;
    logic gate_protocol_error;
    logic gate_issue_valid;
    logic [3:0] gate_activity_mask;
    logic [3:0] gate_issue_mask;
    logic [31:0] hidden_dense_reads;
    logic [31:0] hidden_reads_issued;
    logic [31:0] hidden_reads_saved;
    logic [31:0] output_dense_reads;
    logic [31:0] output_reads_issued;
    logic [31:0] output_reads_saved;

    wire idle = state == S_IDLE;
    wire feedback_request = cmd_opcode == OP_FEEDBACK;
    wire feedback_nonzero = (cmd_arg0 == 8'd1) || (cmd_arg0 == 8'd3);
    wire local_feedback_error = feedback_request && feedback_nonzero
        && (evidence_invalid || observation_id_exhausted);
    wire tick_shape_valid = (cmd_arg0[7:4] == 0) && (cmd_arg1[7:1] == 0);
    wire tick_mode_valid = (core_mode_state != MODE_CONFIG)
        && !core_pending_valid
        && !((core_mode_state == MODE_INFER) && cmd_arg1[0]);
    wire legal_tick = (cmd_opcode == OP_TICK) && tick_shape_valid && tick_mode_valid;
    wire upstream_core_accept = core_cmd_valid && core_cmd_ready && idle;

    assign rsp_valid = run_rsp_valid_reg;
    assign rsp_status = run_rsp_status_reg;
    assign rsp_data = run_rsp_data_reg;
    assign rsp_spike = run_rsp_spike_reg;
    assign prune_rsp_valid = prune_rsp_valid_reg;
    assign prune_rsp_status = prune_rsp_status_reg;
    assign prune_rsp_id = prune_rsp_id_reg;
    assign prune_rsp_mask = prune_rsp_mask_reg;

    assign prune_utility_state = gate_utility_flat;
    assign prune_structural_mask_state = gate_structural_mask;
    assign prune_mask_valid_state = gate_mask_valid;
    assign prune_observe_count_state = observe_count;
    assign prune_refractory_skips_state = refractory_skips;
    assign prune_sticky_halt_state = sticky_halt;
    assign prune_latched_evidence_state = latched_evidence;
    assign prune_dense_reads_state = LAYER_OUTPUT ? output_dense_reads : hidden_dense_reads;
    assign prune_reads_issued_state = LAYER_OUTPUT ? output_reads_issued : hidden_reads_issued;
    assign prune_reads_saved_state = LAYER_OUTPUT ? output_reads_saved : hidden_reads_saved;
    assign protocol_error = gate_protocol_error || sticky_halt;

    // 运行与 sideband 互斥，避免同拍改变核心和结构状态。
    always_comb begin
        cmd_ready = 1'b0;
        prune_cmd_ready = 1'b0;
        core_cmd_valid = 1'b0;
        core_cmd_opcode = cmd_opcode;
        core_cmd_arg0 = cmd_arg0;
        core_cmd_arg1 = cmd_arg1;
        core_rsp_ready = 1'b0;
        gate_cmd_valid = 1'b0;
        gate_cmd_opcode = prune_cmd_opcode;
        gate_cmd_id = prune_cmd_id;
        gate_evidence = '0;
        gate_modulator_nonzero = 1'b0;
        gate_rsp_ready = 1'b0;

        if (idle && !sticky_halt && !run_rsp_valid_reg && !prune_rsp_valid_reg) begin
            if (prune_cmd_valid) begin
                if (prune_cmd_opcode == PRUNE_CLEAR
                        || prune_cmd_opcode == PRUNE_COMMIT
                        || prune_cmd_opcode == PRUNE_MASK_READ) begin
                    prune_cmd_ready = gate_cmd_ready;
                    gate_cmd_valid = prune_cmd_valid;
                end else begin
                    prune_cmd_ready = 1'b1;
                end
            end else begin
                cmd_ready = local_feedback_error ? 1'b1 : core_cmd_ready;
                if (!local_feedback_error) begin
                    core_cmd_valid = cmd_valid;
                    if (legal_tick) begin
                        core_cmd_arg0[3:0] = core_refractory_state != 0
                            ? 4'b0000 : gate_issue_mask;
                    end
                end
            end
        end else if (state == S_WAIT_CORE_RSP || state == S_WAIT_STATE_CLEAR_RSP) begin
            core_rsp_ready = 1'b1;
        end else if (state == S_ISSUE_OBSERVE) begin
            gate_cmd_valid = 1'b1;
            gate_cmd_opcode = PRUNE_OBSERVE;
            gate_cmd_id = next_observation_id;
            gate_evidence = latched_evidence;
            gate_modulator_nonzero = 1'b1;
        end else if (state == S_WAIT_OBSERVE_RSP || state == S_WAIT_PRUNE_RSP) begin
            gate_rsp_ready = 1'b1;
        end else if (state == S_ISSUE_STATE_CLEAR) begin
            core_cmd_valid = 1'b1;
            core_cmd_opcode = OP_STATE_CLEAR;
            core_cmd_arg0 = '0;
            core_cmd_arg1 = '0;
        end
    end

    assign gate_activity_mask = cmd_arg0[3:0];
    assign gate_issue_valid = upstream_core_accept && legal_tick
        && (core_refractory_state == 0);

    logic [15:0] gate_utility_flat;
    logic [3:0] gate_structural_mask;
    logic gate_mask_valid;
    logic [31:0] unused_hidden_ops, unused_output_ops;
    logic [31:0] unused_mask_commits, unused_illegal;
    logic [31:0] unused_inactive, unused_skipped;
    logic unused_busy, unused_fsm, unused_cfg_ready, unused_cfg_done, unused_cfg_error;
    logic [1:0] unused_scan;
    logic unused_obs_valid, unused_commit_valid;
    logic [15:0] unused_obs_id, unused_commit_id;

    local_prune_gate_2of4 gate (
        .clk(clk),
        .rst(rst),
        .mode_state(core_mode_state),
        .cmd_valid(gate_cmd_valid),
        .cmd_ready(gate_cmd_ready),
        .cmd_opcode(gate_cmd_opcode),
        .cmd_id(gate_cmd_id),
        .evidence_levels_flat(gate_evidence),
        .modulator_nonzero(gate_modulator_nonzero),
        .core_idle(idle && core_cmd_ready && !core_rsp_valid),
        .pending_snapshot(1'b0),
        .pending_mod_commit(core_pending_valid),
        .rsp_valid(gate_rsp_valid),
        .rsp_ready(gate_rsp_ready),
        .rsp_status(gate_rsp_status),
        .rsp_id(gate_rsp_id),
        .rsp_mask(gate_rsp_mask),
        .cfg_mask_valid(1'b0),
        .cfg_mask_ready(unused_cfg_ready),
        .cfg_mask_data(4'b0000),
        .cfg_mask_done(unused_cfg_done),
        .cfg_mask_error(unused_cfg_error),
        .issue_valid(gate_issue_valid),
        .activity_mask(gate_activity_mask),
        .issue_layer_output(LAYER_OUTPUT),
        .issue_mask(gate_issue_mask),
        .busy(unused_busy),
        .protocol_error(gate_protocol_error),
        .fsm_state(unused_fsm),
        .scan_index_state(unused_scan),
        .utility_flat(gate_utility_flat),
        .structural_mask_state(gate_structural_mask),
        .mask_valid_state(gate_mask_valid),
        .last_observation_valid_state(unused_obs_valid),
        .last_observation_id_state(unused_obs_id),
        .last_commit_valid_state(unused_commit_valid),
        .last_commit_id_state(unused_commit_id),
        .mask_commits_state(unused_mask_commits),
        .illegal_commands_state(unused_illegal),
        .hidden_dense_reads_state(hidden_dense_reads),
        .hidden_reads_issued_state(hidden_reads_issued),
        .hidden_synapse_ops_state(unused_hidden_ops),
        .hidden_reads_saved_state(hidden_reads_saved),
        .output_dense_reads_state(output_dense_reads),
        .output_reads_issued_state(output_reads_issued),
        .output_synapse_ops_state(unused_output_ops),
        .output_reads_saved_state(output_reads_saved),
        .inactive_groups_state(unused_inactive),
        .groups_skipped_state(unused_skipped)
    );

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= S_IDLE;
            accepted_feedback <= 1'b0;
            accepted_feedback_nonzero <= 1'b0;
            latched_evidence <= '0;
            next_observation_id <= '0;
            observation_id_exhausted <= 1'b0;
            observe_count <= '0;
            refractory_skips <= '0;
            sticky_halt <= 1'b0;
            run_rsp_valid_reg <= 1'b0;
            run_rsp_status_reg <= ST_OK;
            run_rsp_data_reg <= '0;
            run_rsp_spike_reg <= 1'b0;
            prune_rsp_valid_reg <= 1'b0;
            prune_rsp_status_reg <= ST_OK;
            prune_rsp_id_reg <= '0;
            prune_rsp_mask_reg <= 4'b1111;
            pending_prune_opcode <= '0;
            buffered_prune_status <= ST_OK;
            buffered_prune_id <= '0;
            buffered_prune_mask <= 4'b1111;
        end else begin
            if (run_rsp_valid_reg && rsp_ready)
                run_rsp_valid_reg <= 1'b0;
            if (prune_rsp_valid_reg && prune_rsp_ready)
                prune_rsp_valid_reg <= 1'b0;

            if (idle && cmd_valid && cmd_ready) begin
                if (local_feedback_error) begin
                    run_rsp_valid_reg <= 1'b1;
                    run_rsp_status_reg <= evidence_invalid ? ST_INTERNAL : ST_BAD_ARG;
                    run_rsp_data_reg <= '0;
                    run_rsp_spike_reg <= 1'b0;
                    if (evidence_invalid) begin
                        sticky_halt <= 1'b1;
                        state <= S_ERROR_HALT;
                    end
                end else begin
                    accepted_feedback <= feedback_request;
                    accepted_feedback_nonzero <= feedback_nonzero;
                    if (feedback_request)
                        latched_evidence <= scaled_evidence_flat;
                    if (legal_tick && core_refractory_state != 0)
                        refractory_skips <= refractory_skips + 1'b1;
                    state <= S_WAIT_CORE_RSP;
                end
            end else if (idle && prune_cmd_valid && prune_cmd_ready) begin
                if (prune_cmd_opcode != PRUNE_CLEAR
                        && prune_cmd_opcode != PRUNE_COMMIT
                        && prune_cmd_opcode != PRUNE_MASK_READ) begin
                    prune_rsp_valid_reg <= 1'b1;
                    prune_rsp_status_reg <= ST_BAD_OPCODE;
                    prune_rsp_id_reg <= prune_cmd_id;
                    prune_rsp_mask_reg <= gate_mask_valid
                        ? gate_structural_mask : 4'b1111;
                end else begin
                    pending_prune_opcode <= prune_cmd_opcode;
                    state <= S_WAIT_PRUNE_RSP;
                end
            end

            case (state)
                S_WAIT_CORE_RSP: begin
                    if (core_rsp_valid && core_rsp_ready) begin
                        run_rsp_status_reg <= core_rsp_status;
                        run_rsp_data_reg <= core_rsp_data;
                        run_rsp_spike_reg <= core_rsp_spike;
                        if (accepted_feedback && accepted_feedback_nonzero
                                && core_rsp_status == ST_OK) begin
                            state <= S_ISSUE_OBSERVE;
                        end else begin
                            run_rsp_valid_reg <= 1'b1;
                            state <= S_IDLE;
                        end
                    end
                end

                S_ISSUE_OBSERVE: begin
                    if (gate_cmd_valid && gate_cmd_ready)
                        state <= S_WAIT_OBSERVE_RSP;
                end

                S_WAIT_OBSERVE_RSP: begin
                    if (gate_rsp_valid && gate_rsp_ready) begin
                        if (gate_rsp_status == ST_OK) begin
                            observe_count <= observe_count + 1'b1;
                            if (next_observation_id == 16'hffff)
                                observation_id_exhausted <= 1'b1;
                            else
                                next_observation_id <= next_observation_id + 1'b1;
                            run_rsp_valid_reg <= 1'b1;
                            state <= S_IDLE;
                        end else begin
                            run_rsp_valid_reg <= 1'b1;
                            run_rsp_status_reg <= ST_INTERNAL;
                            run_rsp_data_reg <= '0;
                            run_rsp_spike_reg <= 1'b0;
                            sticky_halt <= 1'b1;
                            state <= S_ERROR_HALT;
                        end
                    end
                end

                S_WAIT_PRUNE_RSP: begin
                    if (gate_rsp_valid && gate_rsp_ready) begin
                        if (pending_prune_opcode == PRUNE_COMMIT
                                && gate_rsp_status == ST_OK
                                && AUTO_CLEAR_ON_COMMIT) begin
                            buffered_prune_status <= gate_rsp_status;
                            buffered_prune_id <= gate_rsp_id;
                            buffered_prune_mask <= gate_rsp_mask;
                            state <= S_ISSUE_STATE_CLEAR;
                        end else begin
                            prune_rsp_valid_reg <= 1'b1;
                            prune_rsp_status_reg <= gate_rsp_status;
                            prune_rsp_id_reg <= gate_rsp_id;
                            prune_rsp_mask_reg <= gate_rsp_mask;
                            if (pending_prune_opcode == PRUNE_CLEAR
                                    && gate_rsp_status == ST_OK) begin
                                next_observation_id <= '0;
                                observation_id_exhausted <= 1'b0;
                            end
                            state <= S_IDLE;
                        end
                    end
                end

                S_ISSUE_STATE_CLEAR: begin
                    if (core_cmd_valid && core_cmd_ready)
                        state <= S_WAIT_STATE_CLEAR_RSP;
                end

                S_WAIT_STATE_CLEAR_RSP: begin
                    if (core_rsp_valid && core_rsp_ready) begin
                        prune_rsp_valid_reg <= 1'b1;
                        prune_rsp_id_reg <= buffered_prune_id;
                        prune_rsp_mask_reg <= buffered_prune_mask;
                        if (core_rsp_status == ST_OK) begin
                            prune_rsp_status_reg <= buffered_prune_status;
                            state <= S_IDLE;
                        end else begin
                            prune_rsp_status_reg <= ST_INTERNAL;
                            sticky_halt <= 1'b1;
                            state <= S_ERROR_HALT;
                        end
                    end
                end

                S_ERROR_HALT: begin
                    sticky_halt <= 1'b1;
                end

                default: begin
                end
            endcase
        end
    end
endmodule
