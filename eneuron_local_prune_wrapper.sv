// ENeuron 单核与公共 2:4 gate 的薄适配器。
// 只负责事务协调、committed snapshot 量化和 TICK 前输入门控；不复制神经元方程。
module eneuron_local_prune_wrapper #(
    // 单核使用 1；网络级 all-done barrier 使用 0 并随后广播 STATE_CLEAR。
    parameter bit AUTO_CLEAR_ON_COMMIT = 1'b1
) (
    input  logic                         clk,
    input  logic                         rst,
    input  logic [1:0]                   mode_state,

    input  logic                         state_clear,
    input  logic                         tick_valid,
    input  logic [3:0]                   input_spikes,
    input  logic                         snapshot_we,
    input  logic [15:0]                  snapshot_commit_id,
    input  logic                         mod_valid,
    input  logic [15:0]                  mod_commit_id,
    input  logic signed [1:0]            modulator,
    input  logic                         weight_we,
    input  logic [1:0]                   weight_addr,
    input  logic signed [7:0]            weight_wdata,
    output logic signed [7:0]            weight_rdata,
    output logic                         ready,
    output logic                         busy,
    output logic                         done,
    output logic                         protocol_error,
    output logic                         spike,
    output logic signed [15:0]           membrane,
    output logic [7:0]                   threshold_state,
    output logic                         snapshot_valid_state,
    output logic [47:0]                  eligibility_snapshot_flat_state,
    output logic                         pending_snapshot_valid_state,
    output logic [15:0]                  pending_snapshot_id_state,

    input  logic                         prune_cmd_valid,
    output logic                         prune_cmd_ready,
    input  logic [2:0]                   prune_cmd_opcode,
    input  logic [15:0]                  prune_cmd_id,
    output logic                         prune_rsp_valid,
    input  logic                         prune_rsp_ready,
    output logic [2:0]                   prune_rsp_status,
    output logic [15:0]                  prune_rsp_id,
    output logic [3:0]                   prune_rsp_mask,

    input  logic                         cfg_mask_valid,
    output logic                         cfg_mask_ready,
    input  logic [3:0]                   cfg_mask_data,
    output logic                         cfg_mask_done,
    output logic                         cfg_mask_error,

    output logic [3:0]                   issue_mask,
    output logic [15:0]                  utility_flat,
    output logic [3:0]                   structural_mask_state,
    output logic                         mask_valid_state,
    output logic                         last_observation_valid_state,
    output logic [15:0]                  last_observation_id_state
);

    localparam logic [1:0] MODE_CONFIG = 2'd0;
    localparam logic [1:0] MODE_TRAIN  = 2'd1;
    localparam logic [2:0] OP_OBSERVE = 3'd0;
    localparam logic [2:0] ST_OK = 3'd0;

    typedef enum logic [2:0] {
        S_IDLE,
        S_WAIT_CORE,
        S_WAIT_MOD,
        S_WAIT_PRUNE,
        S_START_COMMIT_CLEAR,
        S_WAIT_COMMIT_CLEAR,
        S_HOLD_PRUNE_RSP
    } wrapper_state_t;

    typedef enum logic [2:0] {
        C_NONE,
        C_CLEAR,
        C_TICK,
        C_SNAPSHOT,
        C_MOD,
        C_WEIGHT
    } core_command_t;

    wrapper_state_t state;
    core_command_t active_command;
    logic [15:0] accepted_snapshot_id;
    logic pending_snapshot_valid;
    logic [15:0] pending_snapshot_id;

    logic core_state_clear;
    logic core_tick_valid;
    logic core_snapshot_we;
    logic core_mod_valid;
    logic core_weight_we;
    logic core_ready;
    logic core_done;
    logic core_spike;

    logic gate_cmd_valid;
    logic gate_cmd_ready;
    logic [2:0] gate_cmd_opcode;
    logic [15:0] gate_cmd_id;
    logic [7:0] gate_evidence_levels;
    logic gate_modulator_nonzero;
    logic gate_rsp_valid;
    logic gate_rsp_ready;
    logic [2:0] gate_rsp_status;
    logic [15:0] gate_rsp_id;
    logic [3:0] gate_rsp_mask;
    logic gate_busy;
    logic gate_protocol_error;
    logic gate_cfg_mask_ready;
    logic gate_cfg_mask_done;
    logic gate_cfg_mask_error;
    logic gate_last_observation_valid;
    logic [15:0] gate_last_observation_id;
    logic [2:0] accepted_prune_opcode;
    logic prune_rsp_valid_reg;
    logic [2:0] prune_rsp_status_reg;
    logic [15:0] prune_rsp_id_reg;
    logic [3:0] prune_rsp_mask_reg;

    logic runtime_request;
    logic selected_mod;
    logic mod_metadata_valid;
    logic mod_observation_id_valid;
    logic internal_observe_request;
    logic gate_issue_valid;

    function automatic [1:0] quantize_snapshot(
        input logic signed [11:0] snapshot_value
    );
        logic signed [12:0] extended_value;
        logic [12:0] magnitude;
        begin
            extended_value = {snapshot_value[11], snapshot_value};
            magnitude = extended_value < 0 ? -extended_value : extended_value;
            if (magnitude == 0)
                quantize_snapshot = 2'd0;
            else if (magnitude <= 13'd16)
                quantize_snapshot = 2'd1;
            else if (magnitude <= 13'd32)
                quantize_snapshot = 2'd2;
            else
                quantize_snapshot = 2'd3;
        end
    endfunction

    generate
        genvar evidence_lane;
        for (evidence_lane = 0; evidence_lane < 4;
             evidence_lane = evidence_lane + 1) begin : gen_evidence_quantizer
            assign gate_evidence_levels[evidence_lane*2 +: 2] = quantize_snapshot(
                $signed(eligibility_snapshot_flat_state[evidence_lane*12 +: 12])
            );
        end
    endgenerate

    assign runtime_request = state_clear || snapshot_we || weight_we || mod_valid || tick_valid;
    assign selected_mod = !state_clear && !snapshot_we && !weight_we && mod_valid;
    assign mod_metadata_valid = (mode_state == MODE_TRAIN)
        && pending_snapshot_valid && (mod_commit_id == pending_snapshot_id);
    assign mod_observation_id_valid = !gate_last_observation_valid
        || (mod_commit_id > gate_last_observation_id);
    assign internal_observe_request = (state == S_IDLE) && ready && selected_mod
        && mod_metadata_valid && (modulator != 0) && mod_observation_id_valid;

    assign ready = (state == S_IDLE) && core_ready && !gate_busy && !gate_rsp_valid;
    assign busy = (state != S_IDLE) || gate_busy || gate_rsp_valid;
    assign pending_snapshot_valid_state = pending_snapshot_valid;
    assign pending_snapshot_id_state = pending_snapshot_id;

    assign prune_cmd_ready = (state == S_IDLE) && core_ready && !runtime_request
        && gate_cmd_ready;
    assign prune_rsp_valid = prune_rsp_valid_reg;
    assign prune_rsp_status = prune_rsp_status_reg;
    assign prune_rsp_id = prune_rsp_id_reg;
    assign prune_rsp_mask = prune_rsp_mask_reg;

    assign cfg_mask_ready = (state == S_IDLE) && core_ready && !runtime_request
        && !prune_cmd_valid && gate_cfg_mask_ready;
    assign cfg_mask_done = gate_cfg_mask_done;
    assign cfg_mask_error = gate_cfg_mask_error;

    always_comb begin
        gate_cmd_valid = 1'b0;
        gate_cmd_opcode = prune_cmd_opcode;
        gate_cmd_id = prune_cmd_id;
        gate_modulator_nonzero = 1'b0;
        if (internal_observe_request) begin
            gate_cmd_valid = 1'b1;
            gate_cmd_opcode = OP_OBSERVE;
            gate_cmd_id = mod_commit_id;
            gate_modulator_nonzero = 1'b1;
        end else if ((state == S_IDLE) && core_ready && !runtime_request) begin
            gate_cmd_valid = prune_cmd_valid;
        end
    end

    assign gate_rsp_ready = ((state == S_WAIT_MOD) && core_done)
        || (state == S_WAIT_PRUNE);
    assign gate_issue_valid = (state == S_IDLE) && ready
        && !state_clear && !snapshot_we && !weight_we && !mod_valid && tick_valid;

    always_comb begin
        core_state_clear = 1'b0;
        core_tick_valid = 1'b0;
        core_snapshot_we = 1'b0;
        core_mod_valid = 1'b0;
        core_weight_we = 1'b0;

        if (state == S_START_COMMIT_CLEAR) begin
            core_state_clear = core_ready;
        end else if (ready) begin
            if (state_clear) begin
                core_state_clear = 1'b1;
            end else if (snapshot_we) begin
                if ((mode_state == MODE_TRAIN) && !pending_snapshot_valid)
                    core_snapshot_we = 1'b1;
            end else if (weight_we) begin
                if (mode_state == MODE_TRAIN)
                    core_weight_we = 1'b1;
            end else if (mod_valid) begin
                if (mod_metadata_valid
                        && ((modulator == 0)
                            || (mod_observation_id_valid && gate_cmd_ready)))
                    core_mod_valid = 1'b1;
            end else if (tick_valid) begin
                core_tick_valid = 1'b1;
            end
        end
    end

    digital_lif_engine core (
        .clk(clk),
        .rst(rst),
        .state_clear(core_state_clear),
        .tick_valid(core_tick_valid),
        .input_spikes(issue_mask),
        .learn_enable(mode_state == MODE_TRAIN),
        .snapshot_we(core_snapshot_we),
        .mod_valid(core_mod_valid),
        .modulator(modulator),
        .weight_we(core_weight_we),
        .weight_addr(weight_addr),
        .weight_wdata(weight_wdata),
        .weight_rdata(weight_rdata),
        .ready(core_ready),
        .done(core_done),
        .spike(core_spike),
        .membrane(membrane),
        .threshold_state(threshold_state),
        .snapshot_valid_state(snapshot_valid_state),
        .eligibility_snapshot_flat_state(eligibility_snapshot_flat_state)
    );

    local_prune_gate_2of4 gate (
        .clk(clk),
        .rst(rst),
        .mode_state(mode_state),
        .cmd_valid(gate_cmd_valid),
        .cmd_ready(gate_cmd_ready),
        .cmd_opcode(gate_cmd_opcode),
        .cmd_id(gate_cmd_id),
        .evidence_levels_flat(gate_evidence_levels),
        .modulator_nonzero(gate_modulator_nonzero),
        .core_idle((state == S_IDLE) && core_ready),
        .pending_snapshot(pending_snapshot_valid),
        .pending_mod_commit(state == S_WAIT_MOD),
        .rsp_valid(gate_rsp_valid),
        .rsp_ready(gate_rsp_ready),
        .rsp_status(gate_rsp_status),
        .rsp_id(gate_rsp_id),
        .rsp_mask(gate_rsp_mask),
        .cfg_mask_valid(cfg_mask_valid && (state == S_IDLE) && !runtime_request
            && !prune_cmd_valid),
        .cfg_mask_ready(gate_cfg_mask_ready),
        .cfg_mask_data(cfg_mask_data),
        .cfg_mask_done(gate_cfg_mask_done),
        .cfg_mask_error(gate_cfg_mask_error),
        .issue_valid(gate_issue_valid),
        .activity_mask(input_spikes),
        .issue_layer_output(1'b0),
        .issue_mask(issue_mask),
        .busy(gate_busy),
        .protocol_error(gate_protocol_error),
        .fsm_state(),
        .scan_index_state(),
        .utility_flat(utility_flat),
        .structural_mask_state(structural_mask_state),
        .mask_valid_state(mask_valid_state),
        .last_observation_valid_state(gate_last_observation_valid),
        .last_observation_id_state(gate_last_observation_id),
        .last_commit_valid_state(),
        .last_commit_id_state(),
        .mask_commits_state(),
        .illegal_commands_state(),
        .hidden_dense_reads_state(),
        .hidden_reads_issued_state(),
        .hidden_synapse_ops_state(),
        .hidden_reads_saved_state(),
        .output_dense_reads_state(),
        .output_reads_issued_state(),
        .output_synapse_ops_state(),
        .output_reads_saved_state(),
        .inactive_groups_state(),
        .groups_skipped_state()
    );

    assign last_observation_valid_state = gate_last_observation_valid;
    assign last_observation_id_state = gate_last_observation_id;

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= S_IDLE;
            active_command <= C_NONE;
            accepted_snapshot_id <= '0;
            pending_snapshot_valid <= 1'b0;
            pending_snapshot_id <= '0;
            accepted_prune_opcode <= '0;
            prune_rsp_valid_reg <= 1'b0;
            prune_rsp_status_reg <= ST_OK;
            prune_rsp_id_reg <= '0;
            prune_rsp_mask_reg <= 4'b1111;
            done <= 1'b0;
            protocol_error <= 1'b0;
            spike <= 1'b0;
        end else begin
            done <= 1'b0;
            protocol_error <= 1'b0;
            spike <= 1'b0;

            if (prune_rsp_valid_reg && prune_rsp_ready) begin
                prune_rsp_valid_reg <= 1'b0;
                if (state == S_HOLD_PRUNE_RSP)
                    state <= S_IDLE;
            end

            case (state)
                S_IDLE: begin
                    active_command <= C_NONE;
                    if (prune_cmd_valid && prune_cmd_ready) begin
                        accepted_prune_opcode <= prune_cmd_opcode;
                        state <= S_WAIT_PRUNE;
                    end else if (runtime_request && ready) begin
                        if (state_clear) begin
                            active_command <= C_CLEAR;
                            state <= S_WAIT_CORE;
                        end else if (snapshot_we) begin
                            if ((mode_state != MODE_TRAIN) || pending_snapshot_valid) begin
                                done <= 1'b1;
                                protocol_error <= 1'b1;
                            end else begin
                                accepted_snapshot_id <= snapshot_commit_id;
                                active_command <= C_SNAPSHOT;
                                state <= S_WAIT_CORE;
                            end
                        end else if (weight_we) begin
                            if (mode_state != MODE_TRAIN) begin
                                done <= 1'b1;
                                protocol_error <= 1'b1;
                            end else begin
                                active_command <= C_WEIGHT;
                                state <= S_WAIT_CORE;
                            end
                        end else if (mod_valid) begin
                            if (!mod_metadata_valid || ((modulator != 0)
                                    && (!mod_observation_id_valid || !gate_cmd_ready))) begin
                                done <= 1'b1;
                                protocol_error <= 1'b1;
                            end else begin
                                active_command <= C_MOD;
                                state <= modulator == 0 ? S_WAIT_CORE : S_WAIT_MOD;
                            end
                        end else if (tick_valid) begin
                            active_command <= C_TICK;
                            state <= S_WAIT_CORE;
                        end
                    end
                end

                S_WAIT_CORE: begin
                    if (core_done) begin
                        if (active_command == C_SNAPSHOT) begin
                            pending_snapshot_valid <= 1'b1;
                            pending_snapshot_id <= accepted_snapshot_id;
                        end else if (active_command == C_MOD) begin
                            pending_snapshot_valid <= 1'b0;
                        end
                        spike <= core_spike;
                        done <= 1'b1;
                        state <= S_IDLE;
                    end
                end

                S_WAIT_MOD: begin
                    if (core_done && gate_rsp_valid) begin
                        pending_snapshot_valid <= 1'b0;
                        spike <= core_spike;
                        done <= 1'b1;
                        if (gate_rsp_status != ST_OK)
                            protocol_error <= 1'b1;
                        state <= S_IDLE;
                    end
                end

                S_WAIT_PRUNE: begin
                    if (gate_rsp_valid) begin
                        prune_rsp_status_reg <= gate_rsp_status;
                        prune_rsp_id_reg <= gate_rsp_id;
                        prune_rsp_mask_reg <= gate_rsp_mask;
                        if ((accepted_prune_opcode == 3'd2)
                                && (gate_rsp_status == ST_OK)
                                && AUTO_CLEAR_ON_COMMIT) begin
                            state <= S_START_COMMIT_CLEAR;
                        end else begin
                            prune_rsp_valid_reg <= 1'b1;
                            if (gate_rsp_status != ST_OK)
                                protocol_error <= 1'b1;
                            state <= S_HOLD_PRUNE_RSP;
                        end
                    end
                end

                S_START_COMMIT_CLEAR: begin
                    if (core_ready)
                        state <= S_WAIT_COMMIT_CLEAR;
                end

                S_WAIT_COMMIT_CLEAR: begin
                    if (core_done) begin
                        prune_rsp_valid_reg <= 1'b1;
                        state <= S_HOLD_PRUNE_RSP;
                    end
                end

                S_HOLD_PRUNE_RSP: begin
                    // 响应保持逻辑位于 case 前，等待上游 ready。
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule
