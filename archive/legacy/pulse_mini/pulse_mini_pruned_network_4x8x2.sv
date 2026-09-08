// Pulse-Mini-L/L2 固定 4→8→2 网络的共享控制面。
// USE_L2 只选择神经元 wrapper；调度、Host 与 commit 协议不随核心复制。
module pulse_mini_pruned_network_4x8x2 #(
    parameter bit USE_L2 = 1'b0
) (
    input  logic clk,
    input  logic rst,
    input  logic tick_valid,
    output logic tick_ready,
    input  logic route_flush_valid,
    output logic route_flush_ready,
    input  logic [3:0] input_spikes,
    input  logic [7:0] hidden_train_post,
    input  logic [1:0] output_train_post,
    output logic tick_rsp_valid,
    input  logic tick_rsp_ready,
    output logic [2:0] tick_rsp_status,
    output logic [7:0] hidden_spikes,
    output logic [1:0] output_spikes,
    output logic [7:0] pending_hidden_state,
    input  logic host_cmd_valid,
    output logic host_cmd_ready,
    input  logic [2:0] host_cmd_opcode,
    input  logic host_cmd_broadcast,
    input  logic [3:0] host_neuron_addr,
    input  logic [7:0] host_cmd_arg0,
    input  logic [7:0] host_cmd_arg1,
    output logic host_rsp_valid,
    input  logic host_rsp_ready,
    output logic [2:0] host_rsp_status,
    output logic [3:0] host_rsp_neuron_addr,
    output logic signed [7:0] host_rsp_data,
    output logic host_rsp_spike,
    input  logic prune_commit_valid,
    output logic prune_commit_ready,
    input  logic [15:0] prune_commit_id,
    output logic prune_rsp_valid,
    input  logic prune_rsp_ready,
    output logic [2:0] prune_rsp_status,
    output logic [15:0] prune_rsp_id,
    output logic [39:0] prune_rsp_masks_flat,
    output logic busy,
    output logic protocol_error,
    output logic [31:0] commit_epoch_state,
    output logic [39:0] issue_masks_flat,
    output logic [39:0] structural_masks_flat,
    output logic [9:0] mask_valids_state,
    output logic [9:0] pending_valids_state,
    output logic [19:0] mode_states_flat,
    output logic [159:0] weights_flat_state,
    output logic [79:0] soma_states_flat,
    output logic [39:0] refractory_states_flat,
    output logic [39:0] leak_timer_states_flat,
    output logic [39:0] post_age_states_flat,
    output logic signed [119:0] captured_direction_flat_state,
    output logic [159:0] pre_age_flat_state,
    output logic [79:0] positive_evidence_flat_state,
    output logic [79:0] negative_evidence_flat_state,
    output logic [159:0] utility_flat_state,
    output logic [319:0] observe_counts_flat_state,
    output logic [319:0] refractory_skips_flat_state,
    output logic [35:0] network_hidden_dense_reads_state,
    output logic [35:0] network_hidden_reads_issued_state,
    output logic [35:0] network_hidden_reads_saved_state,
    output logic [35:0] network_output_dense_reads_state,
    output logic [35:0] network_output_reads_issued_state,
    output logic [35:0] network_output_reads_saved_state
);
    localparam integer N_NEURONS = 10;
    localparam logic [2:0] OP_STATE_CLEAR = 3'd1;
    localparam logic [2:0] OP_TICK = 3'd2;
    localparam logic [2:0] PRUNE_COMMIT = 3'd2;
    localparam logic [2:0] ST_OK = 3'd0;
    localparam logic [2:0] ST_BAD_ARG = 3'd1;
    localparam logic [2:0] ST_CORE_ERROR = 3'd2;
    localparam logic [1:0] MODE_TRAIN = 2'd1;

    typedef enum logic [1:0] {
        H_IDLE,
        H_WAIT,
        H_RSP
    } host_state_t;

    host_state_t host_state;
    logic [9:0] host_targets;
    logic [9:0] host_seen;
    logic [2:0] host_status_reg;
    logic [3:0] host_addr_reg;
    logic host_broadcast_reg;
    logic signed [7:0] host_data_reg;
    logic host_spike_reg;

    logic [9:0] wrapper_cmd_valid;
    logic [9:0] wrapper_cmd_ready;
    logic [29:0] wrapper_cmd_opcode_flat;
    logic [79:0] wrapper_cmd_arg0_flat;
    logic [79:0] wrapper_cmd_arg1_flat;
    logic [9:0] wrapper_rsp_valid;
    logic [9:0] wrapper_rsp_ready;
    logic [29:0] wrapper_rsp_status_flat;
    logic [79:0] wrapper_rsp_data_flat;
    logic [9:0] wrapper_rsp_spike;
    logic [9:0] wrapper_protocol_error;

    logic [9:0] wrapper_prune_cmd_valid;
    logic [9:0] wrapper_prune_cmd_ready;
    logic [9:0] wrapper_prune_rsp_valid;
    logic [9:0] wrapper_prune_rsp_ready;
    logic [29:0] wrapper_prune_rsp_status_flat;
    logic [159:0] wrapper_prune_rsp_id_flat;
    logic [39:0] wrapper_prune_rsp_mask_flat;

    logic [319:0] wrapper_hidden_dense_flat;
    logic [319:0] wrapper_hidden_issued_flat;
    logic [319:0] wrapper_hidden_saved_flat;
    logic [319:0] wrapper_output_dense_flat;
    logic [319:0] wrapper_output_issued_flat;
    logic [319:0] wrapper_output_saved_flat;

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
    logic [7:0] scheduler_hidden_train_post;
    logic [1:0] scheduler_output_train_post;
    logic [7:0] scheduler_hidden_rsp_ready;
    logic [1:0] scheduler_output_rsp_ready;

    logic [9:0] barrier_gate_cmd_valid;
    logic [15:0] barrier_gate_cmd_id;
    logic [9:0] barrier_clear_cmd_valid;
    logic [9:0] barrier_clear_cmd_ready;
    logic [9:0] barrier_clear_rsp_ready;
    logic barrier_runtime_blocked;
    logic barrier_internal_error;

    logic runtime_idle;
    logic host_address_valid;
    logic [9:0] requested_host_targets;
    logic requested_host_targets_ready;
    logic host_issue;
    logic [9:0] host_response_accept;
    logic [9:0] host_seen_next;
    logic host_error_now;
    logic all_train;

    assign host_address_valid = host_cmd_broadcast
        || (host_neuron_addr < N_NEURONS);
    assign requested_host_targets = host_cmd_broadcast
        ? 10'h3ff
        : (host_address_valid ? (10'b1 << host_neuron_addr) : 10'h000);
    assign requested_host_targets_ready =
        (wrapper_cmd_ready & requested_host_targets) == requested_host_targets;
    assign runtime_idle = (host_state == H_IDLE) && !scheduler_busy
        && !barrier_runtime_blocked;

    // 单槽优先级固定为 commit > Host > flush > TICK。
    assign host_cmd_ready = runtime_idle && !prune_commit_valid
        && (!host_address_valid || requested_host_targets_ready);
    assign host_issue = host_cmd_valid && host_cmd_ready && host_address_valid;
    assign scheduler_tick_valid = tick_valid && !prune_commit_valid
        && !host_cmd_valid && (host_state == H_IDLE) && !barrier_runtime_blocked;
    assign scheduler_flush_valid = route_flush_valid && !prune_commit_valid
        && !host_cmd_valid && (host_state == H_IDLE) && !barrier_runtime_blocked;
    assign tick_ready = scheduler_tick_ready && !prune_commit_valid
        && !host_cmd_valid && (host_state == H_IDLE) && !barrier_runtime_blocked;
    assign route_flush_ready = scheduler_flush_ready && !prune_commit_valid
        && !host_cmd_valid && (host_state == H_IDLE) && !barrier_runtime_blocked;

    assign host_rsp_valid = host_state == H_RSP;
    assign host_rsp_status = host_status_reg;
    assign host_rsp_neuron_addr = host_addr_reg;
    assign host_rsp_data = host_data_reg;
    assign host_rsp_spike = host_spike_reg;
    assign busy = scheduler_busy || barrier_runtime_blocked
        || (host_state != H_IDLE) || host_rsp_valid || prune_rsp_valid;
    assign protocol_error = scheduler_protocol_error || barrier_internal_error
        || (|wrapper_protocol_error);
    assign all_train = mode_states_flat == {N_NEURONS{MODE_TRAIN}};

    pruned_network_tick_scheduler tick_scheduler (
        .clk(clk), .rst(rst),
        .tick_valid(scheduler_tick_valid), .tick_ready(scheduler_tick_ready),
        .flush_valid(scheduler_flush_valid), .flush_ready(scheduler_flush_ready),
        .input_spikes(input_spikes),
        .hidden_train_post(hidden_train_post),
        .output_train_post(output_train_post),
        .rsp_valid(tick_rsp_valid), .rsp_ready(tick_rsp_ready),
        .rsp_status(tick_rsp_status), .hidden_spikes(hidden_spikes),
        .output_spikes(output_spikes),
        .pending_hidden_state(pending_hidden_state),
        .hidden_cmd_valid(scheduler_hidden_cmd_valid),
        .hidden_cmd_ready(wrapper_cmd_ready[7:0]),
        .hidden_input_spikes_flat(scheduler_hidden_inputs_flat),
        .hidden_train_post_out(scheduler_hidden_train_post),
        .output_cmd_valid(scheduler_output_cmd_valid),
        .output_cmd_ready(wrapper_cmd_ready[9:8]),
        .output_input_spikes_flat(scheduler_output_inputs_flat),
        .output_train_post_out(scheduler_output_train_post),
        .hidden_rsp_valid(wrapper_rsp_valid[7:0]),
        .hidden_rsp_ready(scheduler_hidden_rsp_ready),
        .hidden_rsp_spike(wrapper_rsp_spike[7:0]),
        .hidden_rsp_status_flat(wrapper_rsp_status_flat[23:0]),
        .output_rsp_valid(wrapper_rsp_valid[9:8]),
        .output_rsp_ready(scheduler_output_rsp_ready),
        .output_rsp_spike(wrapper_rsp_spike[9:8]),
        .output_rsp_status_flat(wrapper_rsp_status_flat[29:24]),
        .busy(scheduler_busy), .protocol_error(scheduler_protocol_error)
    );

    local_prune_commit_barrier #(.N_GATES(N_NEURONS)) commit_barrier (
        .clk(clk), .rst(rst),
        .commit_valid(prune_commit_valid), .commit_ready(prune_commit_ready),
        .commit_id(prune_commit_id),
        .safe_boundary(runtime_idle && all_train && !(|pending_valids_state)),
        .rsp_valid(prune_rsp_valid), .rsp_ready(prune_rsp_ready),
        .rsp_status(prune_rsp_status), .rsp_id(prune_rsp_id),
        .rsp_masks_flat(prune_rsp_masks_flat),
        .gate_cmd_valid(barrier_gate_cmd_valid),
        .gate_cmd_ready(wrapper_prune_cmd_ready),
        .gate_cmd_id(barrier_gate_cmd_id),
        .gate_rsp_valid(wrapper_prune_rsp_valid),
        .gate_rsp_ready(wrapper_prune_rsp_ready),
        .gate_rsp_status_flat(wrapper_prune_rsp_status_flat),
        .gate_rsp_masks_flat(wrapper_prune_rsp_mask_flat),
        .clear_cmd_valid(barrier_clear_cmd_valid),
        .clear_cmd_ready(barrier_clear_cmd_ready),
        .clear_rsp_valid(wrapper_rsp_valid),
        .clear_rsp_ready(barrier_clear_rsp_ready),
        .clear_rsp_status_flat(wrapper_rsp_status_flat),
        .runtime_blocked(barrier_runtime_blocked),
        .internal_error(barrier_internal_error),
        .commit_epoch_state(commit_epoch_state)
    );

    assign wrapper_prune_cmd_valid = barrier_gate_cmd_valid;
    // IDLE 预检已由 safe_boundary 检查运行口；真正清理阶段再使用实时 ready。
    assign barrier_clear_cmd_ready = barrier_runtime_blocked
        ? wrapper_cmd_ready : 10'h3ff;

    integer mux_index;
    always_comb begin
        wrapper_cmd_valid = '0;
        wrapper_cmd_opcode_flat = '0;
        wrapper_cmd_arg0_flat = '0;
        wrapper_cmd_arg1_flat = '0;
        wrapper_rsp_ready = '0;
        for (mux_index = 0; mux_index < N_NEURONS; mux_index = mux_index + 1) begin
            if (barrier_clear_cmd_valid[mux_index]) begin
                wrapper_cmd_valid[mux_index] = 1'b1;
                wrapper_cmd_opcode_flat[mux_index*3 +: 3] = OP_STATE_CLEAR;
            end else if ((mux_index < 8)
                    && scheduler_hidden_cmd_valid[mux_index]) begin
                wrapper_cmd_valid[mux_index] = 1'b1;
                wrapper_cmd_opcode_flat[mux_index*3 +: 3] = OP_TICK;
                wrapper_cmd_arg0_flat[mux_index*8 +: 8] =
                    {4'b0000, scheduler_hidden_inputs_flat[mux_index*4 +: 4]};
                wrapper_cmd_arg1_flat[mux_index*8 +: 8] =
                    {7'b0000000, scheduler_hidden_train_post[mux_index]};
            end else if ((mux_index >= 8)
                    && scheduler_output_cmd_valid[mux_index-8]) begin
                wrapper_cmd_valid[mux_index] = 1'b1;
                wrapper_cmd_opcode_flat[mux_index*3 +: 3] = OP_TICK;
                wrapper_cmd_arg0_flat[mux_index*8 +: 8] =
                    {4'b0000, scheduler_output_inputs_flat[(mux_index-8)*4 +: 4]};
                wrapper_cmd_arg1_flat[mux_index*8 +: 8] =
                    {7'b0000000, scheduler_output_train_post[mux_index-8]};
            end else if (host_issue && requested_host_targets[mux_index]) begin
                wrapper_cmd_valid[mux_index] = 1'b1;
                wrapper_cmd_opcode_flat[mux_index*3 +: 3] = host_cmd_opcode;
                wrapper_cmd_arg0_flat[mux_index*8 +: 8] = host_cmd_arg0;
                wrapper_cmd_arg1_flat[mux_index*8 +: 8] = host_cmd_arg1;
            end

            wrapper_rsp_ready[mux_index] = barrier_clear_rsp_ready[mux_index]
                || ((mux_index < 8) && scheduler_hidden_rsp_ready[mux_index])
                || ((mux_index >= 8)
                    && scheduler_output_rsp_ready[mux_index-8])
                || ((host_state == H_WAIT) && host_targets[mux_index]
                    && !host_seen[mux_index]);
        end
    end

    assign host_response_accept = wrapper_rsp_valid & wrapper_rsp_ready & host_targets;
    assign host_seen_next = host_seen | host_response_accept;

    integer status_index;
    always_comb begin
        host_error_now = 1'b0;
        for (status_index = 0; status_index < N_NEURONS;
             status_index = status_index + 1) begin
            if (host_response_accept[status_index]
                    && (wrapper_rsp_status_flat[status_index*3 +: 3] != ST_OK))
                host_error_now = 1'b1;
        end
    end

    integer host_index;
    always_ff @(posedge clk) begin
        if (rst) begin
            host_state <= H_IDLE;
            host_targets <= '0;
            host_seen <= '0;
            host_status_reg <= ST_OK;
            host_addr_reg <= '0;
            host_broadcast_reg <= 1'b0;
            host_data_reg <= '0;
            host_spike_reg <= 1'b0;
        end else begin
            case (host_state)
                H_IDLE: begin
                    host_seen <= '0;
                    if (host_cmd_valid && host_cmd_ready) begin
                        host_addr_reg <= host_neuron_addr;
                        host_broadcast_reg <= host_cmd_broadcast;
                        host_data_reg <= '0;
                        host_spike_reg <= 1'b0;
                        if (!host_address_valid) begin
                            host_status_reg <= ST_BAD_ARG;
                            host_state <= H_RSP;
                        end else begin
                            host_targets <= requested_host_targets;
                            host_status_reg <= ST_OK;
                            host_state <= H_WAIT;
                        end
                    end
                end

                H_WAIT: begin
                    host_seen <= host_seen_next;
                    if (host_error_now)
                        host_status_reg <= ST_CORE_ERROR;
                    for (host_index = 0; host_index < N_NEURONS;
                         host_index = host_index + 1) begin
                        if (host_response_accept[host_index]) begin
                            host_spike_reg <= host_spike_reg
                                | wrapper_rsp_spike[host_index];
                            if (!host_broadcast_reg
                                    || (host_index == host_addr_reg))
                                host_data_reg <= wrapper_rsp_data_flat[
                                    host_index*8 +: 8];
                        end
                    end
                    if ((host_seen_next & host_targets) == host_targets)
                        host_state <= H_RSP;
                end

                H_RSP: begin
                    if (host_rsp_ready)
                        host_state <= H_IDLE;
                end

                default: begin
                    host_status_reg <= ST_CORE_ERROR;
                    host_state <= H_RSP;
                end
            endcase
        end
    end

    genvar neuron_index;
    generate
        for (neuron_index = 0; neuron_index < N_NEURONS;
             neuron_index = neuron_index + 1) begin : gen_neuron
            logic signed [3:0] weight0;
            logic signed [3:0] weight1;
            logic signed [3:0] weight2;
            logic signed [3:0] weight3;
            logic [3:0] l_positive;
            logic [3:0] l_negative;
            logic [7:0] l2_positive;
            logic [7:0] l2_negative;
            logic signed [7:0] l_captured_direction;
            logic signed [11:0] l2_captured_direction;
            logic [31:0] local_dense_reads;
            logic [31:0] local_reads_issued;
            logic [31:0] local_reads_saved;

            assign weights_flat_state[neuron_index*16 +: 16] =
                {weight3, weight2, weight1, weight0};
            assign wrapper_hidden_dense_flat[neuron_index*32 +: 32] =
                neuron_index < 8 ? local_dense_reads : 32'd0;
            assign wrapper_hidden_issued_flat[neuron_index*32 +: 32] =
                neuron_index < 8 ? local_reads_issued : 32'd0;
            assign wrapper_hidden_saved_flat[neuron_index*32 +: 32] =
                neuron_index < 8 ? local_reads_saved : 32'd0;
            assign wrapper_output_dense_flat[neuron_index*32 +: 32] =
                neuron_index >= 8 ? local_dense_reads : 32'd0;
            assign wrapper_output_issued_flat[neuron_index*32 +: 32] =
                neuron_index >= 8 ? local_reads_issued : 32'd0;
            assign wrapper_output_saved_flat[neuron_index*32 +: 32] =
                neuron_index >= 8 ? local_reads_saved : 32'd0;

            genvar direction_lane;
            for (direction_lane = 0; direction_lane < 4;
                 direction_lane = direction_lane + 1) begin : gen_direction_lane
                if (USE_L2) begin : gen_l2_direction
                    assign captured_direction_flat_state[
                        neuron_index*12 + direction_lane*3 +: 3] =
                        l2_captured_direction[direction_lane*3 +: 3];
                end else begin : gen_l_direction
                    assign captured_direction_flat_state[
                        neuron_index*12 + direction_lane*3 +: 3] = {
                            l_captured_direction[direction_lane*2 + 1],
                            l_captured_direction[direction_lane*2 +: 2]
                        };
                end
            end

            if (USE_L2) begin : gen_l2
                assign positive_evidence_flat_state[neuron_index*8 +: 8] = l2_positive;
                assign negative_evidence_flat_state[neuron_index*8 +: 8] = l2_negative;
                pulse_mini_l2_prune_wrapper #(
                    .LAYER_OUTPUT(neuron_index >= 8),
                    .AUTO_CLEAR_ON_COMMIT(1'b0)
                ) neuron (
                    .clk(clk), .rst(rst),
                    .cmd_valid(wrapper_cmd_valid[neuron_index]),
                    .cmd_ready(wrapper_cmd_ready[neuron_index]),
                    .cmd_opcode(wrapper_cmd_opcode_flat[neuron_index*3 +: 3]),
                    .cmd_arg0(wrapper_cmd_arg0_flat[neuron_index*8 +: 8]),
                    .cmd_arg1(wrapper_cmd_arg1_flat[neuron_index*8 +: 8]),
                    .rsp_valid(wrapper_rsp_valid[neuron_index]),
                    .rsp_ready(wrapper_rsp_ready[neuron_index]),
                    .rsp_status(wrapper_rsp_status_flat[neuron_index*3 +: 3]),
                    .rsp_data(wrapper_rsp_data_flat[neuron_index*8 +: 8]),
                    .spike(wrapper_rsp_spike[neuron_index]),
                    .prune_cmd_valid(wrapper_prune_cmd_valid[neuron_index]),
                    .prune_cmd_ready(wrapper_prune_cmd_ready[neuron_index]),
                    .prune_cmd_opcode(PRUNE_COMMIT),
                    .prune_cmd_id(barrier_gate_cmd_id),
                    .prune_rsp_valid(wrapper_prune_rsp_valid[neuron_index]),
                    .prune_rsp_ready(wrapper_prune_rsp_ready[neuron_index]),
                    .prune_rsp_status(wrapper_prune_rsp_status_flat[neuron_index*3 +: 3]),
                    .prune_rsp_id(wrapper_prune_rsp_id_flat[neuron_index*16 +: 16]),
                    .prune_rsp_mask(wrapper_prune_rsp_mask_flat[neuron_index*4 +: 4]),
                    .pending_valid(pending_valids_state[neuron_index]),
                    .protocol_error(wrapper_protocol_error[neuron_index]),
                    .mode_state(mode_states_flat[neuron_index*2 +: 2]),
                    .weight0(weight0), .weight1(weight1), .weight2(weight2), .weight3(weight3),
                    .soma_state(soma_states_flat[neuron_index*8 +: 8]),
                    .refractory_state(refractory_states_flat[neuron_index*4 +: 4]),
                    .leak_timer_state(leak_timer_states_flat[neuron_index*4 +: 4]),
                    .pre_age_flat(pre_age_flat_state[neuron_index*16 +: 16]),
                    .post_age_state(post_age_states_flat[neuron_index*4 +: 4]),
                    .positive_evidence(l2_positive),
                    .negative_evidence(l2_negative),
                    .captured_direction_flat(l2_captured_direction),
                    .prune_utility_state(utility_flat_state[neuron_index*16 +: 16]),
                    .prune_structural_mask_state(structural_masks_flat[neuron_index*4 +: 4]),
                    .prune_mask_valid_state(mask_valids_state[neuron_index]),
                    .prune_observe_count_state(observe_counts_flat_state[neuron_index*32 +: 32]),
                    .prune_refractory_skips_state(refractory_skips_flat_state[neuron_index*32 +: 32]),
                    .prune_sticky_halt_state(), .prune_latched_evidence_state(),
                    .prune_issue_mask_state(issue_masks_flat[neuron_index*4 +: 4]),
                    .prune_dense_reads_state(local_dense_reads),
                    .prune_reads_issued_state(local_reads_issued),
                    .prune_reads_saved_state(local_reads_saved)
                );
            end else begin : gen_l
                assign positive_evidence_flat_state[neuron_index*8 +: 8] =
                    {4'b0000, l_positive};
                assign negative_evidence_flat_state[neuron_index*8 +: 8] =
                    {4'b0000, l_negative};
                pulse_mini_l_prune_wrapper #(
                    .LAYER_OUTPUT(neuron_index >= 8),
                    .AUTO_CLEAR_ON_COMMIT(1'b0)
                ) neuron (
                    .clk(clk), .rst(rst),
                    .cmd_valid(wrapper_cmd_valid[neuron_index]),
                    .cmd_ready(wrapper_cmd_ready[neuron_index]),
                    .cmd_opcode(wrapper_cmd_opcode_flat[neuron_index*3 +: 3]),
                    .cmd_arg0(wrapper_cmd_arg0_flat[neuron_index*8 +: 8]),
                    .cmd_arg1(wrapper_cmd_arg1_flat[neuron_index*8 +: 8]),
                    .rsp_valid(wrapper_rsp_valid[neuron_index]),
                    .rsp_ready(wrapper_rsp_ready[neuron_index]),
                    .rsp_status(wrapper_rsp_status_flat[neuron_index*3 +: 3]),
                    .rsp_data(wrapper_rsp_data_flat[neuron_index*8 +: 8]),
                    .spike(wrapper_rsp_spike[neuron_index]),
                    .prune_cmd_valid(wrapper_prune_cmd_valid[neuron_index]),
                    .prune_cmd_ready(wrapper_prune_cmd_ready[neuron_index]),
                    .prune_cmd_opcode(PRUNE_COMMIT),
                    .prune_cmd_id(barrier_gate_cmd_id),
                    .prune_rsp_valid(wrapper_prune_rsp_valid[neuron_index]),
                    .prune_rsp_ready(wrapper_prune_rsp_ready[neuron_index]),
                    .prune_rsp_status(wrapper_prune_rsp_status_flat[neuron_index*3 +: 3]),
                    .prune_rsp_id(wrapper_prune_rsp_id_flat[neuron_index*16 +: 16]),
                    .prune_rsp_mask(wrapper_prune_rsp_mask_flat[neuron_index*4 +: 4]),
                    .pending_valid(pending_valids_state[neuron_index]),
                    .protocol_error(wrapper_protocol_error[neuron_index]),
                    .mode_state(mode_states_flat[neuron_index*2 +: 2]),
                    .weight0(weight0), .weight1(weight1), .weight2(weight2), .weight3(weight3),
                    .soma_state(soma_states_flat[neuron_index*8 +: 8]),
                    .refractory_state(refractory_states_flat[neuron_index*4 +: 4]),
                    .leak_timer_state(leak_timer_states_flat[neuron_index*4 +: 4]),
                    .pre_age_flat(pre_age_flat_state[neuron_index*16 +: 16]),
                    .post_age_state(post_age_states_flat[neuron_index*4 +: 4]),
                    .positive_evidence(l_positive),
                    .negative_evidence(l_negative),
                    .captured_direction_flat(l_captured_direction),
                    .prune_utility_state(utility_flat_state[neuron_index*16 +: 16]),
                    .prune_structural_mask_state(structural_masks_flat[neuron_index*4 +: 4]),
                    .prune_mask_valid_state(mask_valids_state[neuron_index]),
                    .prune_observe_count_state(observe_counts_flat_state[neuron_index*32 +: 32]),
                    .prune_refractory_skips_state(refractory_skips_flat_state[neuron_index*32 +: 32]),
                    .prune_sticky_halt_state(), .prune_latched_evidence_state(),
                    .prune_issue_mask_state(issue_masks_flat[neuron_index*4 +: 4]),
                    .prune_dense_reads_state(local_dense_reads),
                    .prune_reads_issued_state(local_reads_issued),
                    .prune_reads_saved_state(local_reads_saved)
                );
            end
        end
    endgenerate

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
                + {4'b0000, wrapper_hidden_dense_flat[account_index*32 +: 32]};
            network_hidden_reads_issued_state = network_hidden_reads_issued_state
                + {4'b0000, wrapper_hidden_issued_flat[account_index*32 +: 32]};
            network_hidden_reads_saved_state = network_hidden_reads_saved_state
                + {4'b0000, wrapper_hidden_saved_flat[account_index*32 +: 32]};
            network_output_dense_reads_state = network_output_dense_reads_state
                + {4'b0000, wrapper_output_dense_flat[account_index*32 +: 32]};
            network_output_reads_issued_state = network_output_reads_issued_state
                + {4'b0000, wrapper_output_issued_flat[account_index*32 +: 32]};
            network_output_reads_saved_state = network_output_reads_saved_state
                + {4'b0000, wrapper_output_saved_flat[account_index*32 +: 32]};
        end
    end
endmodule
