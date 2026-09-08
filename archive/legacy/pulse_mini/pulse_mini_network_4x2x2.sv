// 固定 4->2->2 Pulse-Mini 网络包装器。
//
// 网络命令与单核命令保持同一组 opcode，但 TICK 是网络级命令：隐藏层
// 先处理当前输入，输出层随后只读取 tick 开始时的 pending_hidden，因而
// 组合层间路径不存在。CAPTURE/FEEDBACK/WEIGHT_* 使用 cmd_arg0[7:6]
// 寻址四个神经元，低位保留给突触地址；MODE_SET/STATE_CLEAR 广播到四核。
module pulse_mini_network_4x2x2 (
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
    output logic [1:0] hidden_spikes,
    output logic [1:0] output_spikes,
    output logic [1:0] pending_hidden_state,
    output logic protocol_error
);
    localparam logic [2:0] OP_MODE_SET = 3'd0;
    localparam logic [2:0] OP_STATE_CLEAR = 3'd1;
    localparam logic [2:0] OP_TICK = 3'd2;
    localparam logic [2:0] OP_CAPTURE = 3'd3;
    localparam logic [2:0] OP_FEEDBACK = 3'd4;
    localparam logic [2:0] OP_WEIGHT_WRITE = 3'd5;
    localparam logic [2:0] OP_WEIGHT_READ = 3'd6;
    localparam logic [2:0] ST_OK = 3'd0;

    typedef enum logic [1:0] {S_IDLE, S_SEND, S_WAIT, S_RSP} state_t;
    state_t state;
    logic [2:0] active_opcode;
    logic [7:0] active_arg0;
    logic [7:0] active_arg1;
    logic [1:0] target_index;
    logic [1:0] target_last;
    logic tick_output_phase;
    logic [1:0] pending_hidden_reg;
    logic [1:0] hidden_spikes_reg;
    logic [1:0] output_spikes_reg;
    logic [1:0] tick_hidden_accum;
    logic [2:0] response_status_reg;
    logic signed [7:0] response_data_reg;
    logic response_error_reg;
    logic [3:0] core_cmd_valid;
    logic [3:0] core_cmd_ready;
    logic [3:0] core_rsp_valid;
    logic [3:0] core_rsp_ready;
    logic [2:0] core_cmd_opcode [0:3];
    logic [7:0] core_cmd_arg0 [0:3];
    logic [7:0] core_cmd_arg1 [0:3];
    logic [2:0] core_rsp_status [0:3];
    logic signed [7:0] core_rsp_data [0:3];
    logic [3:0] core_spike;
    logic [3:0] core_protocol_error;
    logic [3:0] core_pending;
    logic signed [3:0] unused_w0 [0:3];
    logic signed [3:0] unused_w1 [0:3];
    logic signed [3:0] unused_w2 [0:3];
    logic signed [3:0] unused_w3 [0:3];
    logic signed [7:0] unused_soma [0:3];
    logic [3:0] unused_refractory [0:3];
    logic [3:0] unused_leak_timer [0:3];
    logic [15:0] unused_pre_age [0:3];
    logic [3:0] unused_post_age [0:3];
    logic [3:0] unused_positive [0:3];
    logic [3:0] unused_negative [0:3];
    logic signed [7:0] unused_direction [0:3];
    logic [1:0] unused_mode [0:3];

    genvar g;
    generate
        for (g = 0; g < 4; g = g + 1) begin : gen_core
            pulse_mini_core core (
                .clk, .rst,
                .cmd_valid(core_cmd_valid[g]), .cmd_ready(core_cmd_ready[g]),
                .cmd_opcode(core_cmd_opcode[g]), .cmd_arg0(core_cmd_arg0[g]),
                .cmd_arg1(core_cmd_arg1[g]),
                .rsp_valid(core_rsp_valid[g]), .rsp_ready(core_rsp_ready[g]),
                .rsp_status(core_rsp_status[g]), .rsp_data(core_rsp_data[g]),
                .spike(core_spike[g]), .pending_valid(core_pending[g]),
                .protocol_error(core_protocol_error[g]), .mode_state(unused_mode[g]),
                .weight0(unused_w0[g]), .weight1(unused_w1[g]),
                .weight2(unused_w2[g]), .weight3(unused_w3[g]),
                .soma_state(unused_soma[g]), .refractory_state(unused_refractory[g]),
                .leak_timer_state(unused_leak_timer[g]),
                .pre_age_flat(unused_pre_age[g]), .post_age_state(unused_post_age[g]),
                .positive_evidence(unused_positive[g]), .negative_evidence(unused_negative[g]),
                .captured_direction_flat(unused_direction[g])
            );
        end
    endgenerate

    assign cmd_ready = (state == S_IDLE);
    assign rsp_valid = (state == S_RSP);
    assign rsp_status = response_status_reg;
    assign rsp_data = response_data_reg;
    assign hidden_spikes = hidden_spikes_reg;
    assign output_spikes = output_spikes_reg;
    assign pending_hidden_state = pending_hidden_reg;
    assign protocol_error = response_error_reg;

    integer i;
    always_comb begin
        core_cmd_valid = '0;
        core_rsp_ready = '0;
        for (i = 0; i < 4; i = i + 1) begin
            core_cmd_opcode[i] = active_opcode;
            core_cmd_arg0[i] = '0;
            core_cmd_arg1[i] = '0;
        end

        if (state == S_SEND) begin
            core_cmd_valid[target_index] = 1'b1;
            if (active_opcode == OP_TICK) begin
                core_cmd_opcode[target_index] = OP_TICK;
                core_cmd_arg0[target_index] = tick_output_phase ? {6'b0, pending_hidden_reg} : active_arg0;
                if (tick_output_phase)
                    core_cmd_arg1[target_index] = {7'b0, active_arg1[target_index]};
                else
                    core_cmd_arg1[target_index] = {7'b0, active_arg1[target_index]};
            end else if (active_opcode == OP_CAPTURE) begin
                core_cmd_opcode[target_index] = OP_CAPTURE;
            end else if (active_opcode == OP_FEEDBACK) begin
                core_cmd_opcode[target_index] = OP_FEEDBACK;
                core_cmd_arg0[target_index] = active_arg1;
            end else if (active_opcode == OP_WEIGHT_READ) begin
                core_cmd_opcode[target_index] = OP_WEIGHT_READ;
                core_cmd_arg0[target_index] = {6'b0, active_arg0[1:0]};
            end else if (active_opcode == OP_WEIGHT_WRITE) begin
                core_cmd_opcode[target_index] = OP_WEIGHT_WRITE;
                core_cmd_arg0[target_index] = {6'b0, active_arg0[1:0]};
                core_cmd_arg1[target_index] = active_arg1;
            end else begin
                core_cmd_opcode[target_index] = active_opcode;
                core_cmd_arg0[target_index] = active_arg0;
                core_cmd_arg1[target_index] = active_arg1;
            end
        end else if (state == S_WAIT) begin
            core_rsp_ready[target_index] = 1'b1;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= S_IDLE;
            active_opcode <= '0;
            active_arg0 <= '0;
            active_arg1 <= '0;
            target_index <= '0;
            target_last <= '0;
            tick_output_phase <= 1'b0;
            pending_hidden_reg <= '0;
            hidden_spikes_reg <= '0;
            output_spikes_reg <= '0;
            tick_hidden_accum <= '0;
            response_status_reg <= ST_OK;
            response_data_reg <= '0;
            response_error_reg <= 1'b0;
        end else begin
            if (state == S_RSP && rsp_ready)
                state <= S_IDLE;

            if (state == S_IDLE && cmd_valid && cmd_ready) begin
                active_opcode <= cmd_opcode;
                active_arg0 <= cmd_arg0;
                active_arg1 <= cmd_arg1;
                response_status_reg <= ST_OK;
                response_data_reg <= '0;
                response_error_reg <= 1'b0;
                if (cmd_opcode == OP_TICK) begin
                    tick_output_phase <= 1'b0;
                    target_index <= 2'd0;
                    target_last <= 2'd3;
                    tick_hidden_accum <= '0;
                    hidden_spikes_reg <= '0;
                    output_spikes_reg <= '0;
                    state <= S_SEND;
                end else if (cmd_opcode == OP_MODE_SET || cmd_opcode == OP_STATE_CLEAR) begin
                    target_index <= 2'd0;
                    target_last <= 2'd3;
                    state <= S_SEND;
                end else if (cmd_opcode == OP_CAPTURE || cmd_opcode == OP_FEEDBACK
                         || cmd_opcode == OP_WEIGHT_READ || cmd_opcode == OP_WEIGHT_WRITE) begin
                    target_index <= cmd_arg0[7:6];
                    target_last <= cmd_arg0[7:6];
                    state <= S_SEND;
                end else begin
                    response_status_reg <= 3'd1;
                    response_error_reg <= 1'b1;
                    state <= S_RSP;
                end
            end

            if (state == S_SEND && core_cmd_ready[target_index])
                state <= S_WAIT;

            if (state == S_WAIT && core_rsp_valid[target_index]) begin
                response_status_reg <= core_rsp_status[target_index];
                response_data_reg <= core_rsp_data[target_index];
                response_error_reg <= (core_rsp_status[target_index] != ST_OK)
                    || core_protocol_error[target_index];
                if (active_opcode == OP_TICK) begin
                    if (!tick_output_phase) begin
                        tick_hidden_accum[target_index] <= core_spike[target_index];
                        if (target_index == 2'd1) begin
                            tick_output_phase <= 1'b1;
                            target_index <= 2'd2;
                            state <= S_SEND;
                        end else begin
                            target_index <= target_index + 1'b1;
                            state <= S_SEND;
                        end
                    end else begin
                        if (target_index == 2'd2)
                            output_spikes_reg[0] <= core_spike[target_index];
                        else
                            output_spikes_reg[1] <= core_spike[target_index];
                        if (target_index == 2'd3) begin
                            hidden_spikes_reg <= tick_hidden_accum;
                            pending_hidden_reg <= tick_hidden_accum;
                            state <= S_RSP;
                        end else begin
                            target_index <= 2'd3;
                            state <= S_SEND;
                        end
                    end
                end else if (target_index == target_last) begin
                    if (active_opcode == OP_STATE_CLEAR) begin
                        pending_hidden_reg <= '0;
                        hidden_spikes_reg <= '0;
                        output_spikes_reg <= '0;
                    end
                    state <= S_RSP;
                end else begin
                    target_index <= target_index + 1'b1;
                    state <= S_SEND;
                end
            end
        end
    end
endmodule
