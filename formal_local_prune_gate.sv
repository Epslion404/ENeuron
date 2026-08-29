// 局部 2:4 剪枝控制器有限深度协议与原子性检查。
module formal_local_prune_gate(input logic clk);
    (* anyseq *) logic rst;
    (* anyseq *) logic [1:0] mode_state;
    (* anyseq *) logic cmd_valid;
    (* anyseq *) logic [2:0] cmd_opcode;
    (* anyseq *) logic [15:0] cmd_id;
    (* anyseq *) logic [7:0] evidence_levels_flat;
    (* anyseq *) logic modulator_nonzero;
    (* anyseq *) logic core_idle;
    (* anyseq *) logic pending_snapshot;
    (* anyseq *) logic pending_mod_commit;
    (* anyseq *) logic rsp_ready;
    (* anyseq *) logic cfg_mask_valid;
    (* anyseq *) logic [3:0] cfg_mask_data;
    (* anyseq *) logic [3:0] activity_mask;
    (* anyseq *) logic issue_layer_output;

    logic cmd_ready, rsp_valid;
    logic [2:0] rsp_status;
    logic [15:0] rsp_id;
    logic [3:0] rsp_mask;
    logic cfg_mask_ready, cfg_mask_done, cfg_mask_error;
    logic issue_valid;
    logic [3:0] issue_mask;
    logic busy, protocol_error, fsm_state;
    logic [1:0] scan_index_state;
    logic [15:0] utility_flat;
    logic [3:0] structural_mask_state;
    logic mask_valid_state;
    logic last_observation_valid_state;
    logic [15:0] last_observation_id_state;
    logic last_commit_valid_state;
    logic [15:0] last_commit_id_state;
    logic [31:0] mask_commits_state, illegal_commands_state;
    logic [31:0] hidden_dense_reads_state, hidden_reads_issued_state;
    logic [31:0] hidden_synapse_ops_state, hidden_reads_saved_state;
    logic [31:0] output_dense_reads_state, output_reads_issued_state;
    logic [31:0] output_synapse_ops_state, output_reads_saved_state;
    logic [31:0] inactive_groups_state, groups_skipped_state;

    logic past_valid;
    logic expected_commit_valid;
    logic [3:0] expected_commit_mask;
    logic expect_infer_reject;
    logic [15:0] infer_utility_snapshot;
    logic [3:0] infer_mask_snapshot;
    logic infer_mask_valid_snapshot;
    logic infer_observation_valid_snapshot;
    logic [15:0] infer_observation_id_snapshot;
    logic infer_commit_valid_snapshot;
    logic [15:0] infer_commit_id_snapshot;
    logic [31:0] infer_mask_commits_snapshot;

    local_prune_gate_2of4 dut(.*);

    function automatic logic exact_two(input logic [3:0] value);
        exact_two = (value == 4'b0011) || (value == 4'b0101)
            || (value == 4'b0110) || (value == 4'b1001)
            || (value == 4'b1010) || (value == 4'b1100);
    endfunction

    function automatic [3:0] top2_mask(input logic [15:0] values);
        integer i;
        integer j;
        integer outrank_count;
        logic [3:0] result;
        logic [3:0] value_i;
        logic [3:0] value_j;
        begin
            result = 4'b0000;
            for (i = 0; i < 4; i = i + 1) begin
                outrank_count = 0;
                value_i = values[i*4 +: 4];
                for (j = 0; j < 4; j = j + 1) begin
                    value_j = values[j*4 +: 4];
                    if ((value_j > value_i) || ((value_j == value_i) && (j < i)))
                        outrank_count = outrank_count + 1;
                end
                if (outrank_count < 2)
                    result[i] = 1'b1;
            end
            top2_mask = result;
        end
    endfunction

    // 形式检查聚焦控制器协议；工作量计数和 issue 组合关系由 cosim 穷举活动 mask。
    assign issue_valid = 1'b0;

    always_ff @(posedge clk) begin
        if (!past_valid)
            assume(rst);
        else
            assume(!rst);
        past_valid <= 1'b1;

        if (rst) begin
            expected_commit_valid <= 1'b0;
            expected_commit_mask <= 4'b1111;
            expect_infer_reject <= 1'b0;
            infer_utility_snapshot <= '0;
            infer_mask_snapshot <= 4'b1111;
            infer_mask_valid_snapshot <= 1'b0;
            infer_observation_valid_snapshot <= 1'b0;
            infer_observation_id_snapshot <= '0;
            infer_commit_valid_snapshot <= 1'b0;
            infer_commit_id_snapshot <= '0;
            infer_mask_commits_snapshot <= '0;
        end else begin
            if (cmd_valid && cmd_ready && cmd_opcode == 3'd2
                    && mode_state == 2'd1 && core_idle
                    && !pending_snapshot && !pending_mod_commit
                    && !mask_valid_state
                    && (!last_commit_valid_state || (cmd_id > last_commit_id_state))) begin
                expected_commit_valid <= 1'b1;
                expected_commit_mask <= top2_mask(utility_flat);
            end
            if (rsp_valid && rsp_status == 3'd0 && expected_commit_valid)
                expected_commit_valid <= 1'b0;

            expect_infer_reject <= cmd_valid && cmd_ready && mode_state == 2'd2
                && (cmd_opcode == 3'd0 || cmd_opcode == 3'd1 || cmd_opcode == 3'd2);
            if (cmd_valid && cmd_ready && mode_state == 2'd2
                    && (cmd_opcode == 3'd0 || cmd_opcode == 3'd1 || cmd_opcode == 3'd2)) begin
                infer_utility_snapshot <= utility_flat;
                infer_mask_snapshot <= structural_mask_state;
                infer_mask_valid_snapshot <= mask_valid_state;
                infer_observation_valid_snapshot <= last_observation_valid_state;
                infer_observation_id_snapshot <= last_observation_id_state;
                infer_commit_valid_snapshot <= last_commit_valid_state;
                infer_commit_id_snapshot <= last_commit_id_state;
                infer_mask_commits_snapshot <= mask_commits_state;
            end

            assert(cmd_ready == ((fsm_state == 1'b0) && !rsp_valid));
            assert(busy == ((fsm_state != 1'b0) || rsp_valid));
            assert(issue_mask == (activity_mask
                & (mask_valid_state ? structural_mask_state : 4'b1111)));
            if (mask_valid_state)
                assert(exact_two(structural_mask_state));

            // PRUNE_COMMIT 的四个扫描拍不得提前改变公开 mask。
            if (past_valid && (fsm_state == 1'b1)) begin
                assert(structural_mask_state == $past(structural_mask_state));
                assert(mask_valid_state == $past(mask_valid_state));
                assert(!cmd_ready);
            end

            // 响应背压时，控制响应和架构状态保持稳定。
            if (past_valid && $past(rsp_valid && !rsp_ready)) begin
                assert(rsp_valid);
                assert(rsp_status == $past(rsp_status));
                assert(rsp_id == $past(rsp_id));
                assert(rsp_mask == $past(rsp_mask));
                assert(utility_flat == $past(utility_flat));
                assert(structural_mask_state == $past(structural_mask_state));
                assert(mask_valid_state == $past(mask_valid_state));
                assert(last_observation_valid_state == $past(last_observation_valid_state));
                assert(last_observation_id_state == $past(last_observation_id_state));
                assert(last_commit_valid_state == $past(last_commit_valid_state));
                assert(last_commit_id_state == $past(last_commit_id_state));
                assert(mask_commits_state == $past(mask_commits_state));
            end

            // 已提交状态下的安全第二次提交必须被拒绝，结构不得改变。
            if (past_valid && $past(cmd_valid && cmd_ready && cmd_opcode == 3'd2
                    && mode_state == 2'd1 && core_idle
                    && !pending_snapshot && !pending_mod_commit
                    && mask_valid_state)) begin
                assert(rsp_valid);
                assert(rsp_status == 3'd5);
                assert(structural_mask_state == $past(structural_mask_state));
                assert(mask_valid_state == $past(mask_valid_state));
                assert(mask_commits_state == $past(mask_commits_state));
            end

            // 重复或倒退的 observation ID 不得重复累计 utility。
            if (past_valid && $past(cmd_valid && cmd_ready && cmd_opcode == 3'd0
                    && mode_state == 2'd1 && last_observation_valid_state
                    && (cmd_id <= last_observation_id_state))) begin
                assert(rsp_valid);
                assert(rsp_status == 3'd4);
                assert(utility_flat == $past(utility_flat));
                assert(last_observation_id_state == $past(last_observation_id_state));
            end

            // 第四个扫描拍后的公开结果必须是接受时 utility 的确定性 top-2。
            if (past_valid && $past(fsm_state == 1'b1 && scan_index_state == 2'd3)) begin
                assert(fsm_state == 1'b0);
                assert(rsp_valid);
                assert(rsp_status == 3'd0);
                assert(mask_valid_state);
                assert(structural_mask_state == expected_commit_mask);
                assert(exact_two(structural_mask_state));
            end

            // 独立监视寄存器验证 INFER 拒绝路径不会改写剪枝状态。
            if (expect_infer_reject) begin
                assert(rsp_valid);
                assert(rsp_status == 3'd2);
                assert(utility_flat == infer_utility_snapshot);
                assert(structural_mask_state == infer_mask_snapshot);
                assert(mask_valid_state == infer_mask_valid_snapshot);
                assert(last_observation_valid_state == infer_observation_valid_snapshot);
                assert(last_observation_id_state == infer_observation_id_snapshot);
                assert(last_commit_valid_state == infer_commit_valid_snapshot);
                assert(last_commit_id_state == infer_commit_id_snapshot);
                assert(mask_commits_state == infer_mask_commits_snapshot);
            end
        end
    end
endmodule
