// 固定 4→8→2 ENeuron 剪枝网络。
//
// 八个 detector 与两个 output 都是四输入单元。output 0 固定读取上一逻辑
// TICK 的 detector[3:0]，output 1 固定读取 detector[7:4]。网络只转发 Host
// 提供的训练事务，不在片上生成标签、损失或调制值。
module eneuron_pruned_network_4x8x2 (
    input  logic                         clk,
    input  logic                         rst,
    input  logic [1:0]                   mode_state,

    input  logic                         tick_valid,
    output logic                         tick_ready,
    input  logic                         route_flush_valid,
    output logic                         route_flush_ready,
    input  logic [3:0]                   input_spikes,
    output logic                         tick_rsp_valid,
    input  logic                         tick_rsp_ready,
    output logic [2:0]                   tick_rsp_status,
    output logic [7:0]                   hidden_spikes,
    output logic [1:0]                   output_spikes,
    output logic [7:0]                   pending_hidden_state,

    // Host 单槽事务：0=STATE_CLEAR，1=SNAPSHOT，2=MOD，3=WEIGHT_WRITE。
    input  logic                         host_cmd_valid,
    output logic                         host_cmd_ready,
    input  logic [2:0]                   host_cmd_opcode,
    input  logic                         host_cmd_broadcast,
    input  logic [3:0]                   host_neuron_addr,
    input  logic [15:0]                  host_snapshot_commit_id,
    input  logic [15:0]                  host_mod_commit_id,
    input  logic signed [1:0]            host_modulator,
    input  logic [1:0]                   host_weight_addr,
    input  logic signed [7:0]            host_weight_wdata,
    output logic                         host_rsp_valid,
    input  logic                         host_rsp_ready,
    output logic [2:0]                   host_rsp_status,
    output logic [3:0]                   host_rsp_neuron_addr,
    output logic signed [7:0]            host_weight_rdata,

    // 十个 gate 共用的一次网络级 PRUNE_COMMIT。
    input  logic                         prune_commit_valid,
    output logic                         prune_commit_ready,
    input  logic [15:0]                  prune_commit_id,
    output logic                         prune_rsp_valid,
    input  logic                         prune_rsp_ready,
    output logic [2:0]                   prune_rsp_status,
    output logic [15:0]                  prune_rsp_id,
    output logic [39:0]                  prune_rsp_masks_flat,

    output logic                         busy,
    output logic                         protocol_error,
    output logic [31:0]                  commit_epoch_state,
    output logic [39:0]                  issue_masks_flat,
    output logic [39:0]                  structural_masks_flat,
    output logic [9:0]                   mask_valids_state,
    output logic [9:0]                   pending_snapshot_valids_state,
    output logic [159:0]                 pending_snapshot_ids_flat_state,
    output logic [159:0]                 utility_flat_state,
    output logic [35:0]                  network_hidden_dense_reads_state,
    output logic [35:0]                  network_hidden_reads_issued_state,
    output logic [35:0]                  network_hidden_reads_saved_state,
    output logic [35:0]                  network_output_dense_reads_state,
    output logic [35:0]                  network_output_reads_issued_state,
    output logic [35:0]                  network_output_reads_saved_state,
    output logic [9:0]                   last_observation_valids_state,
    output logic [159:0]                 last_observation_ids_flat_state,
    output logic [9:0]                   last_commit_valids_state,
    output logic [159:0]                 last_commit_ids_flat_state,
    output logic [159:0]                 membranes_flat_state,
    output logic [79:0]                  thresholds_flat_state,
    output logic [9:0]                   core_snapshot_valids_state,
    output logic [479:0]                 eligibility_snapshots_flat_state
);

    localparam integer N_NEURONS = 10;
    localparam logic [2:0] HOST_STATE_CLEAR = 3'd0;
    localparam logic [2:0] HOST_SNAPSHOT    = 3'd1;
    localparam logic [2:0] HOST_MOD         = 3'd2;
    localparam logic [2:0] HOST_WEIGHT      = 3'd3;
    localparam logic [2:0] ST_OK            = 3'd0;
    localparam logic [2:0] ST_BAD_ARG       = 3'd1;
    localparam logic [2:0] ST_CORE_ERROR    = 3'd2;

    typedef enum logic [1:0] {
        H_IDLE,
        H_WAIT,
        H_RSP
    } host_state_t;

    host_state_t host_state;
    logic [9:0] host_targets;
    logic [9:0] host_seen;
    logic host_response_error;
    logic [2:0] host_response_status;
    logic [3:0] accepted_host_neuron;
    logic accepted_host_broadcast;
    logic signed [7:0] host_weight_rdata_reg;

    logic [9:0] wrapper_ready;
    logic [9:0] wrapper_busy;
    logic [9:0] wrapper_done;
    logic [9:0] wrapper_protocol_error;
    logic [9:0] wrapper_spike;
    logic [9:0] wrapper_state_clear;
    logic [9:0] wrapper_tick_valid;
    logic [9:0] wrapper_snapshot_we;
    logic [9:0] wrapper_mod_valid;
    logic [9:0] wrapper_weight_we;
    logic [39:0] wrapper_inputs_flat;
    logic [79:0] wrapper_weight_rdata_flat;
    logic [319:0] wrapper_hidden_dense_reads_flat;
    logic [319:0] wrapper_hidden_reads_issued_flat;
    logic [319:0] wrapper_hidden_reads_saved_flat;
    logic [319:0] wrapper_output_dense_reads_flat;
    logic [319:0] wrapper_output_reads_issued_flat;
    logic [319:0] wrapper_output_reads_saved_flat;

    logic [9:0] wrapper_prune_cmd_valid;
    logic [9:0] wrapper_prune_cmd_ready;
    logic [9:0] wrapper_prune_rsp_valid;
    logic [9:0] wrapper_prune_rsp_ready;
    logic [29:0] wrapper_prune_rsp_status_flat;
    logic [159:0] wrapper_prune_rsp_id_flat;
    logic [39:0] wrapper_prune_rsp_masks_flat;

    logic scheduler_tick_valid;
    logic scheduler_flush_valid;
    logic scheduler_tick_ready;
    logic scheduler_flush_ready;
    logic scheduler_busy;
    logic scheduler_protocol_error;
    logic [7:0] scheduler_hidden_cmd_valid;
    logic [1:0] scheduler_output_cmd_valid;
    logic [31:0] scheduler_hidden_inputs_flat;
    logic [7:0] scheduler_output_inputs_flat;
    logic [7:0] scheduler_hidden_rsp_ready;
    logic [1:0] scheduler_output_rsp_ready;
    logic [23:0] scheduler_hidden_rsp_status_flat;
    logic [5:0] scheduler_output_rsp_status_flat;

    logic [9:0] barrier_clear_cmd_valid;
    logic [9:0] barrier_clear_rsp_ready;
    logic [29:0] barrier_clear_rsp_status_flat;
    logic [15:0] barrier_gate_cmd_id;
    logic barrier_runtime_blocked;
    logic barrier_internal_error;
    logic barrier_safe_boundary;

    logic host_address_valid;
    logic host_opcode_valid;
    logic [9:0] requested_host_targets;
    logic requested_host_targets_ready;
    logic host_issue;
    logic [9:0] host_accept;
    logic [9:0] host_seen_next;
    logic host_error_now;
    logic runtime_idle;

    assign host_address_valid = host_cmd_broadcast
        || (host_neuron_addr < N_NEURONS);
    assign host_opcode_valid = host_cmd_opcode <= HOST_WEIGHT;
    assign requested_host_targets = host_cmd_broadcast
        ? 10'h3ff
        : (host_address_valid ? (10'b0000000001 << host_neuron_addr) : 10'h000);
    assign requested_host_targets_ready =
        (wrapper_ready & requested_host_targets) == requested_host_targets;

    // PRUNE_COMMIT 的当拍请求优先于 Host、flush 和普通 TICK。
    assign runtime_idle = (host_state == H_IDLE) && !scheduler_busy
        && !barrier_runtime_blocked;
    assign host_cmd_ready = runtime_idle && !prune_commit_valid
        && (!host_address_valid || requested_host_targets_ready);
    assign host_issue = host_cmd_valid && host_cmd_ready
        && host_address_valid && host_opcode_valid;
    assign scheduler_tick_valid = tick_valid && !prune_commit_valid
        && !host_cmd_valid && !barrier_runtime_blocked && (host_state == H_IDLE);
    assign scheduler_flush_valid = route_flush_valid && !prune_commit_valid
        && !host_cmd_valid && !barrier_runtime_blocked && (host_state == H_IDLE);
    assign tick_ready = scheduler_tick_ready && !prune_commit_valid
        && !host_cmd_valid && !barrier_runtime_blocked && (host_state == H_IDLE);
    assign route_flush_ready = scheduler_flush_ready && !prune_commit_valid
        && !host_cmd_valid && !barrier_runtime_blocked && (host_state == H_IDLE);

    assign host_rsp_valid = host_state == H_RSP;
    assign host_rsp_status = host_response_status;
    assign host_rsp_neuron_addr = accepted_host_neuron;
    assign busy = scheduler_busy || barrier_runtime_blocked
        || (host_state != H_IDLE) || (|wrapper_busy);
    assign protocol_error = scheduler_protocol_error || barrier_internal_error
        || (|wrapper_protocol_error) || host_response_error;

    assign barrier_safe_boundary = (host_state == H_IDLE) && !scheduler_busy
        && (&wrapper_ready);

    // 空闲时复用既有读数据口做无副作用寻址读取；事务处理中保持锁存响应。
    always_comb begin
        host_weight_rdata = host_weight_rdata_reg;
        if (host_state == H_IDLE) begin
            if (!host_cmd_broadcast && (host_neuron_addr < N_NEURONS))
                host_weight_rdata = wrapper_weight_rdata_flat[
                    host_neuron_addr*8 +: 8];
            else
                host_weight_rdata = '0;
        end
    end

    pruned_network_tick_scheduler tick_scheduler (
        .clk(clk),
        .rst(rst),
        .tick_valid(scheduler_tick_valid),
        .tick_ready(scheduler_tick_ready),
        .flush_valid(scheduler_flush_valid),
        .flush_ready(scheduler_flush_ready),
        .input_spikes(input_spikes),
        .hidden_train_post(8'h00),
        .output_train_post(2'b00),
        .rsp_valid(tick_rsp_valid),
        .rsp_ready(tick_rsp_ready),
        .rsp_status(tick_rsp_status),
        .hidden_spikes(hidden_spikes),
        .output_spikes(output_spikes),
        .pending_hidden_state(pending_hidden_state),
        .hidden_cmd_valid(scheduler_hidden_cmd_valid),
        .hidden_cmd_ready(wrapper_ready[7:0]),
        .hidden_input_spikes_flat(scheduler_hidden_inputs_flat),
        .hidden_train_post_out(),
        .output_cmd_valid(scheduler_output_cmd_valid),
        .output_cmd_ready(wrapper_ready[9:8]),
        .output_input_spikes_flat(scheduler_output_inputs_flat),
        .output_train_post_out(),
        .hidden_rsp_valid(wrapper_done[7:0]),
        .hidden_rsp_ready(scheduler_hidden_rsp_ready),
        .hidden_rsp_spike(wrapper_spike[7:0]),
        .hidden_rsp_status_flat(scheduler_hidden_rsp_status_flat),
        .output_rsp_valid(wrapper_done[9:8]),
        .output_rsp_ready(scheduler_output_rsp_ready),
        .output_rsp_spike(wrapper_spike[9:8]),
        .output_rsp_status_flat(scheduler_output_rsp_status_flat),
        .busy(scheduler_busy),
        .protocol_error(scheduler_protocol_error)
    );

    local_prune_commit_barrier #(.N_GATES(N_NEURONS)) commit_barrier (
        .clk(clk),
        .rst(rst),
        .commit_valid(prune_commit_valid),
        .commit_ready(prune_commit_ready),
        .commit_id(prune_commit_id),
        .safe_boundary(barrier_safe_boundary),
        .rsp_valid(prune_rsp_valid),
        .rsp_ready(prune_rsp_ready),
        .rsp_status(prune_rsp_status),
        .rsp_id(prune_rsp_id),
        .rsp_masks_flat(prune_rsp_masks_flat),
        .gate_cmd_valid(wrapper_prune_cmd_valid),
        .gate_cmd_ready(wrapper_prune_cmd_ready),
        .gate_cmd_id(barrier_gate_cmd_id),
        .gate_rsp_valid(wrapper_prune_rsp_valid),
        .gate_rsp_ready(wrapper_prune_rsp_ready),
        .gate_rsp_status_flat(wrapper_prune_rsp_status_flat),
        .gate_rsp_masks_flat(wrapper_prune_rsp_masks_flat),
        .clear_cmd_valid(barrier_clear_cmd_valid),
        .clear_cmd_ready(wrapper_ready),
        .clear_rsp_valid(wrapper_done),
        .clear_rsp_ready(barrier_clear_rsp_ready),
        .clear_rsp_status_flat(barrier_clear_rsp_status_flat),
        .runtime_blocked(barrier_runtime_blocked),
        .internal_error(barrier_internal_error),
        .commit_epoch_state(commit_epoch_state)
    );

    genvar neuron_index;
    generate
        for (neuron_index = 0; neuron_index < N_NEURONS;
             neuron_index = neuron_index + 1) begin : gen_neuron
            if (neuron_index < 8) begin : gen_hidden_input
                assign wrapper_inputs_flat[neuron_index*4 +: 4] =
                    scheduler_hidden_inputs_flat[neuron_index*4 +: 4];
                assign wrapper_tick_valid[neuron_index] =
                    scheduler_hidden_cmd_valid[neuron_index];
                assign scheduler_hidden_rsp_status_flat[neuron_index*3 +: 3] =
                    wrapper_protocol_error[neuron_index]
                        ? ST_CORE_ERROR : ST_OK;
            end else begin : gen_output_input
                assign wrapper_inputs_flat[neuron_index*4 +: 4] =
                    scheduler_output_inputs_flat[(neuron_index-8)*4 +: 4];
                assign wrapper_tick_valid[neuron_index] =
                    scheduler_output_cmd_valid[neuron_index-8];
            end

            assign wrapper_state_clear[neuron_index] =
                barrier_clear_cmd_valid[neuron_index]
                || (host_issue && requested_host_targets[neuron_index]
                    && (host_cmd_opcode == HOST_STATE_CLEAR));
            assign wrapper_snapshot_we[neuron_index] = host_issue
                && requested_host_targets[neuron_index]
                && (host_cmd_opcode == HOST_SNAPSHOT);
            assign wrapper_mod_valid[neuron_index] = host_issue
                && requested_host_targets[neuron_index]
                && (host_cmd_opcode == HOST_MOD);
            assign wrapper_weight_we[neuron_index] = host_issue
                && requested_host_targets[neuron_index]
                && (host_cmd_opcode == HOST_WEIGHT);

            if (neuron_index >= 8) begin : gen_output_status
                assign scheduler_output_rsp_status_flat[(neuron_index-8)*3 +: 3] =
                    wrapper_protocol_error[neuron_index] ? ST_CORE_ERROR : ST_OK;
            end
            assign barrier_clear_rsp_status_flat[neuron_index*3 +: 3] =
                wrapper_protocol_error[neuron_index] ? ST_CORE_ERROR : ST_OK;

            eneuron_local_prune_wrapper #(
                .AUTO_CLEAR_ON_COMMIT(1'b0),
                .LAYER_OUTPUT(neuron_index >= 8)
            ) neuron (
                .clk(clk),
                .rst(rst),
                .mode_state(mode_state),
                .state_clear(wrapper_state_clear[neuron_index]),
                .tick_valid(wrapper_tick_valid[neuron_index]),
                .input_spikes(wrapper_inputs_flat[neuron_index*4 +: 4]),
                .snapshot_we(wrapper_snapshot_we[neuron_index]),
                .snapshot_commit_id(host_snapshot_commit_id),
                .mod_valid(wrapper_mod_valid[neuron_index]),
                .mod_commit_id(host_mod_commit_id),
                .modulator(host_modulator),
                .weight_we(wrapper_weight_we[neuron_index]),
                .weight_addr(host_weight_addr),
                .weight_wdata(host_weight_wdata),
                .weight_rdata(wrapper_weight_rdata_flat[neuron_index*8 +: 8]),
                .ready(wrapper_ready[neuron_index]),
                .busy(wrapper_busy[neuron_index]),
                .done(wrapper_done[neuron_index]),
                .protocol_error(wrapper_protocol_error[neuron_index]),
                .spike(wrapper_spike[neuron_index]),
                .membrane(membranes_flat_state[neuron_index*16 +: 16]),
                .threshold_state(thresholds_flat_state[neuron_index*8 +: 8]),
                .snapshot_valid_state(core_snapshot_valids_state[neuron_index]),
                .eligibility_snapshot_flat_state(
                    eligibility_snapshots_flat_state[neuron_index*48 +: 48]),
                .pending_snapshot_valid_state(
                    pending_snapshot_valids_state[neuron_index]),
                .pending_snapshot_id_state(
                    pending_snapshot_ids_flat_state[neuron_index*16 +: 16]),
                .prune_cmd_valid(wrapper_prune_cmd_valid[neuron_index]),
                .prune_cmd_ready(wrapper_prune_cmd_ready[neuron_index]),
                .prune_cmd_opcode(3'd2),
                .prune_cmd_id(barrier_gate_cmd_id),
                .prune_rsp_valid(wrapper_prune_rsp_valid[neuron_index]),
                .prune_rsp_ready(wrapper_prune_rsp_ready[neuron_index]),
                .prune_rsp_status(
                    wrapper_prune_rsp_status_flat[neuron_index*3 +: 3]),
                .prune_rsp_id(wrapper_prune_rsp_id_flat[neuron_index*16 +: 16]),
                .prune_rsp_mask(
                    wrapper_prune_rsp_masks_flat[neuron_index*4 +: 4]),
                .cfg_mask_valid(1'b0),
                .cfg_mask_ready(),
                .cfg_mask_data(4'b0000),
                .cfg_mask_done(),
                .cfg_mask_error(),
                .issue_mask(issue_masks_flat[neuron_index*4 +: 4]),
                .utility_flat(utility_flat_state[neuron_index*16 +: 16]),
                .structural_mask_state(
                    structural_masks_flat[neuron_index*4 +: 4]),
                .mask_valid_state(mask_valids_state[neuron_index]),
                .last_observation_valid_state(
                    last_observation_valids_state[neuron_index]),
                .last_observation_id_state(
                    last_observation_ids_flat_state[neuron_index*16 +: 16]),
                .last_commit_valid_state(last_commit_valids_state[neuron_index]),
                .last_commit_id_state(
                    last_commit_ids_flat_state[neuron_index*16 +: 16]),
                .hidden_dense_reads_state(
                    wrapper_hidden_dense_reads_flat[neuron_index*32 +: 32]),
                .hidden_reads_issued_state(
                    wrapper_hidden_reads_issued_flat[neuron_index*32 +: 32]),
                .hidden_reads_saved_state(
                    wrapper_hidden_reads_saved_flat[neuron_index*32 +: 32]),
                .output_dense_reads_state(
                    wrapper_output_dense_reads_flat[neuron_index*32 +: 32]),
                .output_reads_issued_state(
                    wrapper_output_reads_issued_flat[neuron_index*32 +: 32]),
                .output_reads_saved_state(
                    wrapper_output_reads_saved_flat[neuron_index*32 +: 32])
            );
        end
    endgenerate

    // 32-bit 单 gate 账本扩展到 36 bit 后求和，覆盖十个参与者的最大总量。
    integer account_index;
    always_comb begin
        network_hidden_dense_reads_state = '0;
        network_hidden_reads_issued_state = '0;
        network_hidden_reads_saved_state = '0;
        network_output_dense_reads_state = '0;
        network_output_reads_issued_state = '0;
        network_output_reads_saved_state = '0;
        for (account_index = 0; account_index < N_NEURONS;
             account_index = account_index + 1) begin
            network_hidden_dense_reads_state = network_hidden_dense_reads_state
                + {4'b0000, wrapper_hidden_dense_reads_flat[
                    account_index*32 +: 32]};
            network_hidden_reads_issued_state = network_hidden_reads_issued_state
                + {4'b0000, wrapper_hidden_reads_issued_flat[
                    account_index*32 +: 32]};
            network_hidden_reads_saved_state = network_hidden_reads_saved_state
                + {4'b0000, wrapper_hidden_reads_saved_flat[
                    account_index*32 +: 32]};
            network_output_dense_reads_state = network_output_dense_reads_state
                + {4'b0000, wrapper_output_dense_reads_flat[
                    account_index*32 +: 32]};
            network_output_reads_issued_state = network_output_reads_issued_state
                + {4'b0000, wrapper_output_reads_issued_flat[
                    account_index*32 +: 32]};
            network_output_reads_saved_state = network_output_reads_saved_state
                + {4'b0000, wrapper_output_reads_saved_flat[
                    account_index*32 +: 32]};
        end
    end

    assign host_accept = wrapper_done & host_targets;
    assign host_seen_next = host_seen | host_accept;
    assign host_error_now = |(wrapper_protocol_error & host_accept);

    integer host_index;
    always_ff @(posedge clk) begin
        if (rst) begin
            host_state <= H_IDLE;
            host_targets <= '0;
            host_seen <= '0;
            host_response_error <= 1'b0;
            host_response_status <= ST_OK;
            accepted_host_neuron <= '0;
            accepted_host_broadcast <= 1'b0;
            host_weight_rdata_reg <= '0;
        end else begin
            case (host_state)
                H_IDLE: begin
                    host_seen <= '0;
                    host_response_error <= 1'b0;
                    if (host_cmd_valid && host_cmd_ready) begin
                        accepted_host_neuron <= host_neuron_addr;
                        accepted_host_broadcast <= host_cmd_broadcast;
                        if (!host_address_valid || !host_opcode_valid) begin
                            host_response_status <= ST_BAD_ARG;
                            host_response_error <= 1'b1;
                            host_state <= H_RSP;
                        end else begin
                            host_targets <= requested_host_targets;
                            host_response_status <= ST_OK;
                            host_state <= H_WAIT;
                        end
                    end
                end

                H_WAIT: begin
                    host_seen <= host_seen_next;
                    host_response_error <= host_response_error | host_error_now;
                    if ((host_seen_next & host_targets) == host_targets) begin
                        host_response_status <= host_error_now || host_response_error
                            ? ST_CORE_ERROR : ST_OK;
                        if (!accepted_host_broadcast
                                && (accepted_host_neuron < N_NEURONS))
                            host_weight_rdata_reg <= wrapper_weight_rdata_flat[
                                accepted_host_neuron*8 +: 8];
                        host_state <= H_RSP;
                    end
                end

                H_RSP: begin
                    if (host_rsp_ready)
                        host_state <= H_IDLE;
                end

                default: begin
                    host_response_status <= ST_CORE_ERROR;
                    host_response_error <= 1'b1;
                    host_state <= H_RSP;
                end
            endcase
        end
    end

`ifdef FORMAL
    always_ff @(posedge clk) begin
        if (!rst) begin
            if (barrier_runtime_blocked) begin
                assert(!tick_ready);
                assert(!route_flush_ready);
                assert(!host_cmd_ready);
            end
            if (&mask_valids_state) begin
                for (host_index = 0; host_index < N_NEURONS;
                     host_index = host_index + 1)
                    assert($countones(
                        structural_masks_flat[host_index*4 +: 4]) == 2);
            end
        end
    end
`endif

endmodule
