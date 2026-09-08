// Pulse-Mini-L2 固定四输入脉冲神经元。
//
// 这是 Pulse-Mini-L 的最小 RTL：输入脉冲直接选择有符号连接强度，胞体做一次
// 饱和累加；TRAIN 保存输入/输出先后证据，CAPTURE 锁存单槽方向，
// FEEDBACK 以一步数值更新连接。膜电位泄放由固定周期计时器驱动，所有状态只由 clk/rst 驱动。
module pulse_mini_l2_core #(
    parameter int THRESHOLD = 6,
    parameter int WINDOW = 3,
    parameter int REFRACTORY_LENGTH = 1,
    parameter int LEAK_PERIOD = 8
) (
    input  logic                         clk,
    input  logic                         rst,
    input  logic                         cmd_valid,
    output logic                         cmd_ready,
    input  logic [2:0]                   cmd_opcode,
    input  logic [7:0]                   cmd_arg0,
    input  logic [7:0]                   cmd_arg1,
    output logic                         rsp_valid,
    input  logic                         rsp_ready,
    output logic [2:0]                   rsp_status,
    output logic signed [7:0]            rsp_data,
    output logic                         spike,
    output logic                         pending_valid,
    output logic                         protocol_error,
    output logic [1:0]                   mode_state,
    output logic signed [3:0]            weight0,
    output logic signed [3:0]            weight1,
    output logic signed [3:0]            weight2,
    output logic signed [3:0]            weight3,
    output logic signed [7:0]            soma_state,
    output logic [3:0]                   refractory_state,
    output logic [3:0]                   leak_timer_state,
    output logic [15:0]                  pre_age_flat,
    output logic [3:0]                   post_age_state,
    // 每条输入使用 2 位正证据和 2 位负证据；四路打包为 8 位。
    output logic [7:0]                   positive_evidence,
    output logic [7:0]                   negative_evidence,
    // 每路捕获方向为 3 位有符号数，范围 -2..+2；四路打包为 12 位。
    output logic signed [11:0]           captured_direction_flat
);

    localparam logic [2:0] ST_OK = 3'd0;
    localparam logic [2:0] ST_BAD_OPCODE = 3'd1;
    localparam logic [2:0] ST_BAD_ARG = 3'd2;
    localparam logic [2:0] ST_BAD_MODE = 3'd3;
    localparam logic [2:0] ST_BUSY_PENDING = 3'd4;
    localparam logic [2:0] ST_NO_PENDING = 3'd5;

    localparam logic [2:0] OP_MODE_SET = 3'd0;
    localparam logic [2:0] OP_STATE_CLEAR = 3'd1;
    localparam logic [2:0] OP_TICK = 3'd2;
    localparam logic [2:0] OP_CAPTURE = 3'd3;
    localparam logic [2:0] OP_FEEDBACK = 3'd4;
    localparam logic [2:0] OP_WEIGHT_WRITE = 3'd5;
    localparam logic [2:0] OP_WEIGHT_READ = 3'd6;

    localparam logic [1:0] MODE_CONFIG = 2'd0;
    localparam logic [1:0] MODE_TRAIN = 2'd1;
    localparam logic [1:0] MODE_INFER = 2'd2;

    logic signed [3:0] weights [0:3];
    logic [3:0] pre_age [0:3];
    logic [1:0] positive_evidence_reg [0:3];
    logic [1:0] negative_evidence_reg [0:3];
    logic signed [2:0] captured_direction [0:3];
    logic [1:0] mode_reg;
    logic signed [7:0] soma_reg;
    logic [3:0] refractory_reg;
    logic [3:0] leak_timer_reg;
    logic [3:0] post_age_reg;
    logic pending_reg;
    logic response_valid_reg;
    logic [2:0] response_status_reg;
    logic signed [7:0] response_data_reg;
    logic spike_reg;
    logic protocol_error_reg;
    integer i;
    integer j;
    integer total_value;
    integer candidate_value;
    integer feedback_value;
    integer direction_value;
    integer next_weight_value;
    integer natural_spike_value;

    assign cmd_ready = !response_valid_reg;
    assign rsp_valid = response_valid_reg;
    assign rsp_status = response_status_reg;
    assign rsp_data = response_data_reg;
    assign spike = spike_reg;
    assign pending_valid = pending_reg;
    assign protocol_error = protocol_error_reg;
    assign mode_state = mode_reg;
    assign weight0 = weights[0];
    assign weight1 = weights[1];
    assign weight2 = weights[2];
    assign weight3 = weights[3];
    assign soma_state = soma_reg;
    assign refractory_state = refractory_reg;
    assign leak_timer_state = leak_timer_reg;
    assign pre_age_flat[3:0] = pre_age[0];
    assign pre_age_flat[7:4] = pre_age[1];
    assign pre_age_flat[11:8] = pre_age[2];
    assign pre_age_flat[15:12] = pre_age[3];
    assign post_age_state = post_age_reg;
    assign positive_evidence = {
        positive_evidence_reg[3], positive_evidence_reg[2],
        positive_evidence_reg[1], positive_evidence_reg[0]
    };
    assign negative_evidence = {
        negative_evidence_reg[3], negative_evidence_reg[2],
        negative_evidence_reg[1], negative_evidence_reg[0]
    };
    assign captured_direction_flat = {
        captured_direction[3], captured_direction[2],
        captured_direction[1], captured_direction[0]
    };

    function automatic integer sat_soma(input integer value);
        begin
            if (value > 127) sat_soma = 127;
            else if (value < -128) sat_soma = -128;
            else sat_soma = value;
        end
    endfunction

    function automatic integer sat_weight(input integer value);
        begin
            if (value > 7) sat_weight = 7;
            else if (value < -7) sat_weight = -7;
            else sat_weight = value;
        end
    endfunction

    function automatic integer decode_weight4(input logic [3:0] value);
        begin
            if (value == 4'b1000)
                decode_weight4 = 99;
            else if (value[3])
                decode_weight4 = $signed({1'b1, value});
            else
                decode_weight4 = value;
        end
    endfunction

    always_ff @(posedge clk) begin
        if (rst) begin
            mode_reg <= MODE_CONFIG;
            soma_reg <= '0;
            refractory_reg <= '0;
            leak_timer_reg <= '0;
            post_age_reg <= '0;
            pending_reg <= 1'b0;
            response_valid_reg <= 1'b0;
            response_status_reg <= ST_OK;
            response_data_reg <= '0;
            spike_reg <= 1'b0;
            protocol_error_reg <= 1'b0;
            for (i = 0; i < 4; i = i + 1) begin
                weights[i] <= '0;
                pre_age[i] <= '0;
                positive_evidence_reg[i] <= 2'd0;
                negative_evidence_reg[i] <= 2'd0;
                captured_direction[i] <= '0;
            end
        end else begin
            // spike 是命令完成脉冲；response 背压期间保持响应及其 spike。
            if (response_valid_reg && rsp_ready) begin
                response_valid_reg <= 1'b0;
                spike_reg <= 1'b0;
            end
            if (cmd_valid && cmd_ready) begin
                response_valid_reg <= 1'b1;
                response_status_reg <= ST_OK;
                response_data_reg <= '0;
                spike_reg <= 1'b0;
                protocol_error_reg <= 1'b0;

                case (cmd_opcode)
                    OP_MODE_SET: begin
                        if (cmd_arg1 != 0 || cmd_arg0 > 2) begin
                            response_status_reg <= ST_BAD_ARG;
                            protocol_error_reg <= 1'b1;
                        end else if (pending_reg) begin
                            response_status_reg <= ST_BUSY_PENDING;
                            protocol_error_reg <= 1'b1;
                        end else begin
                            mode_reg <= cmd_arg0[1:0];
                        end
                    end

                    OP_STATE_CLEAR: begin
                        if (cmd_arg0 != 0 || cmd_arg1 != 0) begin
                            response_status_reg <= ST_BAD_ARG;
                            protocol_error_reg <= 1'b1;
                        end else if (pending_reg) begin
                            response_status_reg <= ST_BUSY_PENDING;
                            protocol_error_reg <= 1'b1;
                        end else begin
                            soma_reg <= '0;
                            refractory_reg <= '0;
                            leak_timer_reg <= '0;
                            post_age_reg <= '0;
                            for (i = 0; i < 4; i = i + 1) begin
                                pre_age[i] <= '0;
                                positive_evidence_reg[i] <= 2'd0;
                                negative_evidence_reg[i] <= 2'd0;
                                captured_direction[i] <= '0;
                            end
                        end
                    end

                    OP_TICK: begin
                        if (cmd_arg0[7:4] != 0 || cmd_arg1[7:1] != 0) begin
                            response_status_reg <= ST_BAD_ARG;
                            protocol_error_reg <= 1'b1;
                        end else if (mode_reg == MODE_CONFIG) begin
                            response_status_reg <= ST_BAD_MODE;
                            protocol_error_reg <= 1'b1;
                        end else if (pending_reg) begin
                            response_status_reg <= ST_BUSY_PENDING;
                            protocol_error_reg <= 1'b1;
                        end else if (mode_reg == MODE_INFER && cmd_arg1[0]) begin
                            response_status_reg <= ST_BAD_MODE;
                            protocol_error_reg <= 1'b1;
                        end else begin
                            total_value = 0;
                            natural_spike_value = 0;
                            for (i = 0; i < 4; i = i + 1)
                                if (cmd_arg0[i]) total_value = total_value + $signed(weights[i]);

                            if (refractory_reg != 0) begin
                                soma_reg <= '0;
                                refractory_reg <= refractory_reg - 1'b1;
                            end else begin
                                if ((LEAK_PERIOD != 0) &&
                                    (leak_timer_reg == LEAK_PERIOD - 1)) begin
                                    if ($signed(soma_reg) > 0)
                                        candidate_value = sat_soma($signed(soma_reg) - 1 + total_value);
                                    else if ($signed(soma_reg) < 0)
                                        candidate_value = sat_soma($signed(soma_reg) + 1 + total_value);
                                    else
                                        candidate_value = sat_soma($signed(soma_reg) + total_value);
                                    leak_timer_reg <= '0;
                                end else begin
                                    candidate_value = sat_soma($signed(soma_reg) + total_value);
                                    if (LEAK_PERIOD != 0)
                                        leak_timer_reg <= leak_timer_reg + 1'b1;
                                    else
                                        leak_timer_reg <= '0;
                                end
                                if (candidate_value >= THRESHOLD) begin
                                    natural_spike_value = 1;
                                    spike_reg <= 1'b1;
                                    soma_reg <= '0;
                                    refractory_reg <= REFRACTORY_LENGTH[3:0];
                                    leak_timer_reg <= '0;
                                end else begin
                                    soma_reg <= candidate_value[7:0];
                                end
                            end

                            if (mode_reg == MODE_TRAIN) begin
                                // old ages are read before this tick changes them.
                                for (i = 0; i < 4; i = i + 1) begin
                                    if (refractory_reg == 0) begin
                                        if (cmd_arg0[i] && (cmd_arg1[0] ||
                                            natural_spike_value)) begin
                                            if (positive_evidence_reg[i] < 2'd2)
                                                positive_evidence_reg[i] <= positive_evidence_reg[i] + 1'b1;
                                        end
                                        if (cmd_arg0[i] && (post_age_reg > 0)) begin
                                            if (negative_evidence_reg[i] < 2'd2)
                                                negative_evidence_reg[i] <= negative_evidence_reg[i] + 1'b1;
                                        end
                                    end
                                    if ((pre_age[i] > 0) &&
                                        (cmd_arg1[0] || natural_spike_value))
                                        if (positive_evidence_reg[i] < 2'd2)
                                            positive_evidence_reg[i] <= positive_evidence_reg[i] + 1'b1;

                                    if (refractory_reg == 0) begin
                                        if (cmd_arg0[i]) pre_age[i] <= WINDOW[3:0];
                                        else if (pre_age[i] > 0) pre_age[i] <= pre_age[i] - 1'b1;
                                    end
                                end
                                if (cmd_arg1[0] || natural_spike_value)
                                    post_age_reg <= WINDOW[3:0];
                                else if (post_age_reg > 0)
                                    post_age_reg <= post_age_reg - 1'b1;
                            end
                        end
                    end

                    OP_CAPTURE: begin
                        if (cmd_arg0 != 0 || cmd_arg1 != 0) begin
                            response_status_reg <= ST_BAD_ARG;
                            protocol_error_reg <= 1'b1;
                        end else if (mode_reg != MODE_TRAIN) begin
                            response_status_reg <= ST_BAD_MODE;
                            protocol_error_reg <= 1'b1;
                        end else if (pending_reg) begin
                            response_status_reg <= ST_BUSY_PENDING;
                            protocol_error_reg <= 1'b1;
                        end else begin
                            for (i = 0; i < 4; i = i + 1) begin
                                direction_value = $signed({1'b0, positive_evidence_reg[i]}) -
                                    $signed({1'b0, negative_evidence_reg[i]});
                                if (direction_value > 2)
                                    captured_direction[i] <= 3'sd2;
                                else if (direction_value < -2)
                                    captured_direction[i] <= -3'sd2;
                                else
                                    captured_direction[i] <= direction_value[2:0];
                            end
                            pending_reg <= 1'b1;
                        end
                    end

                    OP_FEEDBACK: begin
                        if (cmd_arg1 != 0 || (cmd_arg0 != 0 && cmd_arg0 != 1 && cmd_arg0 != 3)) begin
                            response_status_reg <= ST_BAD_ARG;
                            protocol_error_reg <= 1'b1;
                        end else if (mode_reg != MODE_TRAIN) begin
                            response_status_reg <= ST_BAD_MODE;
                            protocol_error_reg <= 1'b1;
                        end else if (!pending_reg) begin
                            response_status_reg <= ST_NO_PENDING;
                            protocol_error_reg <= 1'b1;
                        end else begin
                            feedback_value = (cmd_arg0 == 0) ? 0 : ((cmd_arg0 == 1) ? 1 : -1);
                            for (i = 0; i < 4; i = i + 1) begin
                                direction_value = $signed(captured_direction[i]);
                                next_weight_value = sat_weight($signed(weights[i]) + feedback_value * direction_value);
                                weights[i] <= next_weight_value[3:0];
                                positive_evidence_reg[i] <= 2'd0;
                                negative_evidence_reg[i] <= 2'd0;
                                captured_direction[i] <= '0;
                            end
                            pending_reg <= 1'b0;
                        end
                    end

                    OP_WEIGHT_WRITE: begin
                        if (cmd_arg0 > 3 || cmd_arg1[7:4] != 0) begin
                            response_status_reg <= ST_BAD_ARG;
                            protocol_error_reg <= 1'b1;
                        end else if (decode_weight4(cmd_arg1[3:0]) == 99) begin
                            response_status_reg <= ST_BAD_ARG;
                            protocol_error_reg <= 1'b1;
                        end else if (mode_reg != MODE_CONFIG) begin
                            response_status_reg <= ST_BAD_MODE;
                            protocol_error_reg <= 1'b1;
                        end else begin
                            weights[cmd_arg0[1:0]] <= decode_weight4(cmd_arg1[3:0]);
                        end
                    end

                    OP_WEIGHT_READ: begin
                        if (cmd_arg1 != 0 || cmd_arg0 > 3) begin
                            response_status_reg <= ST_BAD_ARG;
                            protocol_error_reg <= 1'b1;
                        end else begin
                            response_data_reg <= $signed(weights[cmd_arg0[1:0]]);
                        end
                    end

                    default: begin
                        response_status_reg <= ST_BAD_OPCODE;
                        protocol_error_reg <= 1'b1;
                    end
                endcase
            end
        end
    end
endmodule
