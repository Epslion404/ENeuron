// Pulse-Mini-L2 有限时域协议/不变量证明 harness。
module formal_pulse_mini_l2(input logic clk);
    (* anyseq *) logic rst;
    (* anyseq *) logic cmd_valid;
    (* anyseq *) logic [2:0] cmd_opcode;
    (* anyseq *) logic [7:0] cmd_arg0;
    (* anyseq *) logic [7:0] cmd_arg1;
    (* anyseq *) logic rsp_ready;
    logic cmd_ready, rsp_valid;
    logic [2:0] rsp_status;
    logic signed [7:0] rsp_data;
    logic spike, pending_valid, protocol_error;
    logic [1:0] mode_state;
    logic signed [3:0] weight0, weight1, weight2, weight3;
    logic signed [7:0] soma_state;
    logic [3:0] refractory_state, leak_timer_state;
    logic [15:0] pre_age_flat;
    logic [3:0] post_age_state;
    logic [7:0] positive_evidence, negative_evidence;
    logic signed [11:0] captured_direction_flat;
    logic past_valid;
    logic [2:0] accepted_opcode;
    logic capture_completed;
    (* keep *) logic reached_tick_ok;
    (* keep *) logic reached_capture_ok;
    (* keep *) logic reached_feedback_ok;
    (* keep *) logic reached_capture_then_feedback_ok;

    pulse_mini_l2_core dut (.*);

    always_ff @(posedge clk) begin
        // set-init-zero 令第一拍必须复位，之后复位必须持续释放。
        past_valid <= 1'b1;
        if (!past_valid)
            assume(rst);
        else
            assume(!rst);

        if (rst) begin
            accepted_opcode <= 3'd0;
            capture_completed <= 1'b0;
            reached_tick_ok <= 1'b0;
            reached_capture_ok <= 1'b0;
            reached_feedback_ok <= 1'b0;
            reached_capture_then_feedback_ok <= 1'b0;
        end else begin
            if (cmd_valid && cmd_ready)
                accepted_opcode <= cmd_opcode;

            // 可达性标记只认核心返回的成功响应，不把命令接受误当成功。
            if (rsp_valid && rsp_status == 3'd0) begin
                case (accepted_opcode)
                    3'd2: reached_tick_ok <= 1'b1;
                    3'd3: begin
                        reached_capture_ok <= 1'b1;
                        capture_completed <= 1'b1;
                    end
                    3'd4: begin
                        reached_feedback_ok <= 1'b1;
                        if (capture_completed)
                            reached_capture_then_feedback_ok <= 1'b1;
                        capture_completed <= 1'b0;
                    end
                    default: begin end
                endcase
            end

            assert(cmd_ready == !rsp_valid);
            if (past_valid && !$past(rst))
                assert(rsp_valid == ($past(cmd_valid && cmd_ready) ||
                    ($past(rsp_valid) && !$past(rsp_ready))));

            if (past_valid && $past(rsp_valid && !rsp_ready)) begin
                assert(rsp_valid);
                assert(rsp_status == $past(rsp_status));
                assert(rsp_data == $past(rsp_data));
                assert(weight0 == $past(weight0));
                assert(weight1 == $past(weight1));
                assert(weight2 == $past(weight2));
                assert(weight3 == $past(weight3));
                assert(soma_state == $past(soma_state));
                assert(pending_valid == $past(pending_valid));
                assert(positive_evidence == $past(positive_evidence));
                assert(negative_evidence == $past(negative_evidence));
            end

            assert(weight0 != -8);
            assert(weight1 != -8);
            assert(weight2 != -8);
            assert(weight3 != -8);
            assert(refractory_state <= 1);
            assert(leak_timer_state <= 7);
            assert(post_age_state <= 3);

            if (past_valid && $past(cmd_valid && cmd_ready && cmd_opcode == 3'd2
                    && mode_state == 2'd2 && cmd_arg1[0] == 1'b0
                    && !pending_valid)) begin
                assert(weight0 == $past(weight0));
                assert(weight1 == $past(weight1));
                assert(weight2 == $past(weight2));
                assert(weight3 == $past(weight3));
                assert(pre_age_flat == $past(pre_age_flat));
                assert(post_age_state == $past(post_age_state));
                assert(positive_evidence == $past(positive_evidence));
                assert(negative_evidence == $past(negative_evidence));
                assert(captured_direction_flat == $past(captured_direction_flat));
                assert(pending_valid == $past(pending_valid));
            end

            for (integer index = 0; index < 4; index = index + 1) begin
                assert(positive_evidence[2*index +: 2] <= 2);
                assert(negative_evidence[2*index +: 2] <= 2);
                assert($signed(captured_direction_flat[3*index +: 3]) <= 2);
                assert($signed(captured_direction_flat[3*index +: 3]) >= -2);
            end
        end
    end
endmodule
