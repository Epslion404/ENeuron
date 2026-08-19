// 固定四输入 Pulse-Mini 复制阵列。
// 同一条命令广播到所有单元，响应在所有单元完成后汇总；该模块只用于
// P7 资源/吞吐基线，不宣称这是最终的可寻址网络互连。
module pulse_mini_array #(
    parameter integer N_CORES = 32
) (
    input logic clk,
    input logic rst,
    input logic cmd_valid,
    output logic cmd_ready,
    input logic [2:0] cmd_opcode,
    input logic [7:0] cmd_arg0,
    input logic [7:0] cmd_arg1,
    output logic rsp_valid,
    input logic rsp_ready,
    output logic [2:0] rsp_status,
    output logic signed [7:0] rsp_data,
    output logic [N_CORES-1:0] spike_vector,
    output logic [N_CORES-1:0] pending_vector,
    output logic [N_CORES-1:0] protocol_error_vector
);
    logic [N_CORES-1:0] core_cmd_ready;
    logic [N_CORES-1:0] core_rsp_valid;
    logic [N_CORES-1:0][2:0] core_rsp_status;
    logic signed [N_CORES-1:0][7:0] core_rsp_data;
    genvar g;
    generate
        for (g = 0; g < N_CORES; g = g + 1) begin : gen_core
            logic signed [3:0] weight0, weight1, weight2, weight3;
            logic signed [7:0] soma_state;
            logic [3:0] refractory_state, post_age_state;
            logic [15:0] pre_age_flat;
            logic [3:0] positive_evidence, negative_evidence;
            logic signed [7:0] captured_direction_flat;
            logic [1:0] mode_state;
            (* keep_hierarchy = "yes", dont_touch = "yes" *)
            pulse_mini_core core (
                .clk, .rst, .cmd_valid, .cmd_ready(core_cmd_ready[g]),
                .cmd_opcode, .cmd_arg0, .cmd_arg1,
                .rsp_valid(core_rsp_valid[g]), .rsp_ready,
                .rsp_status(core_rsp_status[g]), .rsp_data(core_rsp_data[g]),
                .spike(spike_vector[g]), .pending_valid(pending_vector[g]),
                .protocol_error(protocol_error_vector[g]), .mode_state,
                .weight0, .weight1, .weight2, .weight3, .soma_state,
                .refractory_state, .pre_age_flat, .post_age_state,
                .positive_evidence, .negative_evidence, .captured_direction_flat
            );
        end
    endgenerate

    assign cmd_ready = &core_cmd_ready;
    assign rsp_valid = &core_rsp_valid;
    assign rsp_status = core_rsp_status[0];
    assign rsp_data = core_rsp_data[0];
endmodule
