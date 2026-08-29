// Pulse-Mini-L 薄剪枝 wrapper：核心保持原样，仅归一化 captured direction。
module pulse_mini_l_prune_wrapper #(
    parameter bit LAYER_OUTPUT = 1'b0,
    parameter bit AUTO_CLEAR_ON_COMMIT = 1'b1
) (
    input  logic clk, input logic rst,
    input  logic cmd_valid, output logic cmd_ready,
    input  logic [2:0] cmd_opcode, input logic [7:0] cmd_arg0, cmd_arg1,
    output logic rsp_valid, input logic rsp_ready,
    output logic [2:0] rsp_status, output logic signed [7:0] rsp_data,
    output logic spike,
    input  logic prune_cmd_valid, output logic prune_cmd_ready,
    input  logic [2:0] prune_cmd_opcode, input logic [15:0] prune_cmd_id,
    output logic prune_rsp_valid, input logic prune_rsp_ready,
    output logic [2:0] prune_rsp_status, output logic [15:0] prune_rsp_id,
    output logic [3:0] prune_rsp_mask,
    output logic pending_valid, output logic protocol_error,
    output logic [1:0] mode_state,
    output logic signed [3:0] weight0, weight1, weight2, weight3,
    output logic signed [7:0] soma_state,
    output logic [3:0] refractory_state, leak_timer_state,
    output logic [15:0] pre_age_flat,
    output logic [3:0] post_age_state,
    output logic [3:0] positive_evidence, negative_evidence,
    output logic signed [7:0] captured_direction_flat,
    output logic [15:0] prune_utility_state,
    output logic [3:0] prune_structural_mask_state,
    output logic prune_mask_valid_state,
    output logic [31:0] prune_observe_count_state,
    output logic [31:0] prune_refractory_skips_state,
    output logic prune_sticky_halt_state,
    output logic [7:0] prune_latched_evidence_state,
    output logic [31:0] prune_dense_reads_state,
    output logic [31:0] prune_reads_issued_state,
    output logic [31:0] prune_reads_saved_state
);
    logic core_cmd_valid, core_cmd_ready;
    logic [2:0] core_cmd_opcode;
    logic [7:0] core_cmd_arg0, core_cmd_arg1;
    logic core_rsp_valid, core_rsp_ready;
    logic [2:0] core_rsp_status;
    logic signed [7:0] core_rsp_data;
    logic core_rsp_spike, core_protocol_error;
    logic [7:0] raw_evidence_flat, scaled_evidence_flat;
    logic evidence_invalid;
    integer i;

    always_comb begin
        raw_evidence_flat = '0;
        evidence_invalid = 1'b0;
        for (i = 0; i < 4; i = i + 1) begin
            case (captured_direction_flat[i*2 +: 2])
                2'b00: raw_evidence_flat[i*2 +: 2] = 2'd0;
                2'b01, 2'b11: raw_evidence_flat[i*2 +: 2] = 2'd1;
                default: evidence_invalid = 1'b1;
            endcase
        end
    end

    pulse_mini_l_prune_evidence_gain gain (
        .raw_evidence_flat(raw_evidence_flat),
        .scaled_evidence_flat(scaled_evidence_flat)
    );

    pulse_mini_core core (
        .clk(clk), .rst(rst),
        .cmd_valid(core_cmd_valid), .cmd_ready(core_cmd_ready),
        .cmd_opcode(core_cmd_opcode), .cmd_arg0(core_cmd_arg0), .cmd_arg1(core_cmd_arg1),
        .rsp_valid(core_rsp_valid), .rsp_ready(core_rsp_ready),
        .rsp_status(core_rsp_status), .rsp_data(core_rsp_data),
        .spike(core_rsp_spike), .pending_valid(pending_valid),
        .protocol_error(core_protocol_error), .mode_state(mode_state),
        .weight0(weight0), .weight1(weight1), .weight2(weight2), .weight3(weight3),
        .soma_state(soma_state), .refractory_state(refractory_state),
        .leak_timer_state(leak_timer_state), .pre_age_flat(pre_age_flat),
        .post_age_state(post_age_state), .positive_evidence(positive_evidence),
        .negative_evidence(negative_evidence),
        .captured_direction_flat(captured_direction_flat)
    );

    logic bridge_protocol_error;
    pulse_mini_prune_bridge #(
        .LAYER_OUTPUT(LAYER_OUTPUT),
        .AUTO_CLEAR_ON_COMMIT(AUTO_CLEAR_ON_COMMIT)
    ) bridge (
        .clk(clk), .rst(rst),
        .cmd_valid(cmd_valid), .cmd_ready(cmd_ready), .cmd_opcode(cmd_opcode),
        .cmd_arg0(cmd_arg0), .cmd_arg1(cmd_arg1), .rsp_valid(rsp_valid),
        .rsp_ready(rsp_ready), .rsp_status(rsp_status), .rsp_data(rsp_data),
        .rsp_spike(spike),
        .core_cmd_valid(core_cmd_valid), .core_cmd_ready(core_cmd_ready),
        .core_cmd_opcode(core_cmd_opcode), .core_cmd_arg0(core_cmd_arg0),
        .core_cmd_arg1(core_cmd_arg1), .core_rsp_valid(core_rsp_valid),
        .core_rsp_ready(core_rsp_ready), .core_rsp_status(core_rsp_status),
        .core_rsp_data(core_rsp_data), .core_rsp_spike(core_rsp_spike),
        .core_mode_state(mode_state), .core_pending_valid(pending_valid),
        .core_refractory_state(refractory_state),
        .scaled_evidence_flat(scaled_evidence_flat), .evidence_invalid(evidence_invalid),
        .prune_cmd_valid(prune_cmd_valid), .prune_cmd_ready(prune_cmd_ready),
        .prune_cmd_opcode(prune_cmd_opcode), .prune_cmd_id(prune_cmd_id),
        .prune_rsp_valid(prune_rsp_valid), .prune_rsp_ready(prune_rsp_ready),
        .prune_rsp_status(prune_rsp_status), .prune_rsp_id(prune_rsp_id),
        .prune_rsp_mask(prune_rsp_mask), .protocol_error(bridge_protocol_error),
        .prune_utility_state(prune_utility_state),
        .prune_structural_mask_state(prune_structural_mask_state),
        .prune_mask_valid_state(prune_mask_valid_state),
        .prune_observe_count_state(prune_observe_count_state),
        .prune_refractory_skips_state(prune_refractory_skips_state),
        .prune_sticky_halt_state(prune_sticky_halt_state),
        .prune_latched_evidence_state(prune_latched_evidence_state),
        .prune_dense_reads_state(prune_dense_reads_state),
        .prune_reads_issued_state(prune_reads_issued_state),
        .prune_reads_saved_state(prune_reads_saved_state)
    );

    assign protocol_error = core_protocol_error || bridge_protocol_error;

`ifdef FORMAL
    always_ff @(posedge clk)
        if (!rst) assert(!evidence_invalid);
`endif
endmodule
