// Pulse-Mini-L2 剪枝 wrapper 的有限深度协议检查。
module formal_pulse_mini_l2_prune_wrapper(input logic clk);
    (* anyseq *) logic rst;
    (* anyseq *) logic cmd_valid;
    (* anyseq *) logic [2:0] cmd_opcode;
    (* anyseq *) logic [7:0] cmd_arg0;
    (* anyseq *) logic [7:0] cmd_arg1;
    (* anyseq *) logic rsp_ready;
    (* anyseq *) logic prune_cmd_valid;
    (* anyseq *) logic [2:0] prune_cmd_opcode;
    (* anyseq *) logic [15:0] prune_cmd_id;
    (* anyseq *) logic prune_rsp_ready;

    logic cmd_ready, rsp_valid, spike, prune_cmd_ready, prune_rsp_valid;
    logic [2:0] rsp_status, prune_rsp_status;
    logic signed [7:0] rsp_data;
    logic [15:0] prune_rsp_id;
    logic [3:0] prune_rsp_mask;
    logic pending_valid, protocol_error;
    logic [1:0] mode_state;
    logic signed [3:0] weight0, weight1, weight2, weight3;
    logic signed [7:0] soma_state;
    logic [3:0] refractory_state, leak_timer_state;
    logic [15:0] pre_age_flat;
    logic [3:0] post_age_state;
    logic [7:0] positive_evidence, negative_evidence;
    logic signed [11:0] captured_direction_flat;
    logic [15:0] prune_utility_state;
    logic [3:0] prune_structural_mask_state;
    logic prune_mask_valid_state;
    logic [31:0] prune_observe_count_state;
    logic [31:0] prune_refractory_skips_state;
    logic prune_sticky_halt_state;
    logic [7:0] prune_latched_evidence_state;
    logic [3:0] prune_issue_mask_state;
    logic [31:0] prune_dense_reads_state;
    logic [31:0] prune_reads_issued_state;
    logic [31:0] prune_reads_saved_state;

    logic past_valid;
    logic feedback_active;
    logic feedback_observed;
    logic [31:0] feedback_observe_before;
    logic [15:0] feedback_utility_after_observe;
    (* keep *) logic reached_successful_nonzero_feedback;

    wire accepted_nonzero_feedback = cmd_valid && cmd_ready
        && cmd_opcode == 3'd4 && (cmd_arg0 == 8'd1 || cmd_arg0 == 8'd3);
    wire observe_completed = feedback_observed
        || (prune_observe_count_state == feedback_observe_before + 1'b1);

    pulse_mini_l2_prune_wrapper dut (.*);

    always_ff @(posedge clk) begin
        past_valid <= 1'b1;
        if (!past_valid)
            assume(rst);
        else
            assume(!rst);

        // 本证明只检查运行 FEEDBACK 合同，不允许独立 sideband 干扰。
        assume(!prune_cmd_valid);

        if (rst) begin
            feedback_active <= 1'b0;
            feedback_observed <= 1'b0;
            feedback_observe_before <= '0;
            feedback_utility_after_observe <= '0;
            reached_successful_nonzero_feedback <= 1'b0;
        end else begin
            if (accepted_nonzero_feedback) begin
                assert(!feedback_active);
                feedback_active <= 1'b1;
                feedback_observed <= 1'b0;
                feedback_observe_before <= prune_observe_count_state;
            end

            if (feedback_active) begin
                assert(prune_observe_count_state == feedback_observe_before
                    || prune_observe_count_state == feedback_observe_before + 1'b1);

                if (!feedback_observed
                        && prune_observe_count_state == feedback_observe_before + 1'b1) begin
                    feedback_observed <= 1'b1;
                    feedback_utility_after_observe <= prune_utility_state;
                end

                if (rsp_valid) begin
                    if (rsp_status == 3'd0) begin
                        // 成功响应公开前 OBSERVE 与 utility 更新必须均已完成。
                        assert(prune_observe_count_state
                            == feedback_observe_before + 1'b1);
                        assert(observe_completed);
                        if (feedback_observed)
                            assert(prune_utility_state == feedback_utility_after_observe);
                        if (prune_latched_evidence_state != 0)
                            reached_successful_nonzero_feedback <= 1'b1;
                    end else begin
                        assert(prune_observe_count_state == feedback_observe_before);
                        assert(!feedback_observed);
                    end
                end
                if (rsp_valid && rsp_ready)
                    feedback_active <= 1'b0;
            end

            if (past_valid && prune_observe_count_state
                    != $past(prune_observe_count_state)) begin
                assert($past(feedback_active));
                assert(prune_observe_count_state
                    == $past(prune_observe_count_state) + 1'b1);
            end

            if (past_valid && $past(rsp_valid && !rsp_ready)) begin
                assert(rsp_valid);
                assert(rsp_status == $past(rsp_status));
                assert(rsp_data == $past(rsp_data));
                assert(spike == $past(spike));
                assert(prune_observe_count_state == $past(prune_observe_count_state));
                assert(prune_utility_state == $past(prune_utility_state));
            end
            if (past_valid && $past(prune_rsp_valid && !prune_rsp_ready)) begin
                assert(prune_rsp_valid);
                assert(prune_rsp_status == $past(prune_rsp_status));
                assert(prune_rsp_id == $past(prune_rsp_id));
                assert(prune_rsp_mask == $past(prune_rsp_mask));
            end
        end
    end
endmodule
