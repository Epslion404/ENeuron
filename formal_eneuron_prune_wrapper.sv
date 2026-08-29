// ENeuron 剪枝 wrapper 的有限深度事务原子性 harness。
//
// 环境只通过公开输入产生 eligibility、提交 snapshot 和执行 MOD；内部接受沿
// 的同拍原子性由 wrapper 的 FORMAL 条件断言直接检查。
module formal_eneuron_prune_wrapper(input logic clk);
    (* anyseq *) logic rst;
    (* anyseq *) logic [1:0] mode_state;
    (* anyseq *) logic state_clear;
    (* anyseq *) logic tick_valid;
    (* anyseq *) logic [3:0] input_spikes;
    (* anyseq *) logic snapshot_we;
    (* anyseq *) logic [15:0] snapshot_commit_id;
    (* anyseq *) logic mod_valid;
    (* anyseq *) logic [15:0] mod_commit_id;
    (* anyseq *) logic signed [1:0] modulator;
    (* anyseq *) logic weight_we;
    (* anyseq *) logic [1:0] weight_addr;
    (* anyseq *) logic signed [7:0] weight_wdata;
    (* anyseq *) logic prune_cmd_valid;
    (* anyseq *) logic [2:0] prune_cmd_opcode;
    (* anyseq *) logic [15:0] prune_cmd_id;
    (* anyseq *) logic prune_rsp_ready;
    (* anyseq *) logic cfg_mask_valid;
    (* anyseq *) logic [3:0] cfg_mask_data;

    logic signed [7:0] weight_rdata;
    logic ready, busy, done, protocol_error, spike;
    logic signed [15:0] membrane;
    logic [7:0] threshold_state;
    logic snapshot_valid_state;
    logic [47:0] eligibility_snapshot_flat_state;
    logic pending_snapshot_valid_state;
    logic [15:0] pending_snapshot_id_state;
    logic prune_cmd_ready;
    logic prune_rsp_valid;
    logic [2:0] prune_rsp_status;
    logic [15:0] prune_rsp_id;
    logic [3:0] prune_rsp_mask;
    logic cfg_mask_ready, cfg_mask_done, cfg_mask_error;
    logic [3:0] issue_mask;
    logic [15:0] utility_flat;
    logic [3:0] structural_mask_state;
    logic mask_valid_state;
    logic last_observation_valid_state;
    logic [15:0] last_observation_id_state;
    logic last_commit_valid_state;
    logic [15:0] last_commit_id_state;
    logic [31:0] hidden_dense_reads_state;
    logic [31:0] hidden_reads_issued_state;
    logic [31:0] hidden_reads_saved_state;
    logic [31:0] output_dense_reads_state;
    logic [31:0] output_reads_issued_state;
    logic [31:0] output_reads_saved_state;

    logic past_valid;
    logic tick_active;
    logic snapshot_active;
    logic mod_active;
    logic invalid_mod_check;
    logic invalid_wrong_mode;
    logic invalid_wrong_id;
    logic invalid_repeat_id;
    logic [15:0] expected_utility_after_mod;
    logic [15:0] utility_before_mod;
    logic [15:0] active_mod_id;
    logic [15:0] invalid_utility_before;
    logic invalid_observation_valid_before;
    logic [15:0] invalid_observation_id_before;
    logic invalid_pending_valid_before;
    logic [15:0] invalid_pending_id_before;
    logic seen_train_tick_done;
    logic seen_nonzero_snapshot;
    (* keep *) logic reached_public_nonzero_mod_success;
    (* keep *) logic reached_wrong_mode_reject;
    (* keep *) logic reached_wrong_id_reject;
    (* keep *) logic reached_repeat_id_reject;

    wire selected_public_mod = !state_clear && !snapshot_we && !weight_we
        && mod_valid;
    wire public_mod_metadata_valid = (mode_state == 2'd1)
        && pending_snapshot_valid_state
        && (mod_commit_id == pending_snapshot_id_state);
    wire public_mod_id_fresh = !last_observation_valid_state
        || (mod_commit_id > last_observation_id_state);
    wire accepted_valid_nonzero_mod = ready && selected_public_mod
        && (modulator != 0) && public_mod_metadata_valid && public_mod_id_fresh;
    wire accepted_invalid_nonzero_mod = ready && selected_public_mod
        && (modulator != 0)
        && (!public_mod_metadata_valid || !public_mod_id_fresh);
    wire accepted_tick = ready && !state_clear && !snapshot_we && !weight_we
        && !mod_valid && tick_valid && (mode_state == 2'd1);
    wire accepted_snapshot = ready && !state_clear && snapshot_we
        && (mode_state == 2'd1) && !pending_snapshot_valid_state;

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

    function automatic [15:0] utility_after_observe(
        input logic [15:0] before,
        input logic [47:0] snapshot
    );
        integer lane;
        logic [1:0] level;
        logic [4:0] sum;
        logic [15:0] result;
        begin
            result = before;
            for (lane = 0; lane < 4; lane = lane + 1) begin
                level = quantize_snapshot(
                    $signed(snapshot[lane*12 +: 12])
                );
                sum = {1'b0, before[lane*4 +: 4]} + level;
                result[lane*4 +: 4] = sum > 15 ? 4'd15 : sum[3:0];
            end
            utility_after_observe = result;
        end
    endfunction

    eneuron_local_prune_wrapper dut (.*);

    always_ff @(posedge clk) begin
        past_valid <= 1'b1;
        if (!past_valid)
            assume(rst);
        else
            assume(!rst);

        // P1 只研究 TICK/SNAPSHOT/MOD 与剪枝响应；排除无关配置写入。
        assume(mode_state != 2'd3);
        assume(!state_clear);
        assume(!weight_we);
        assume(!cfg_mask_valid);
        assume(!(prune_cmd_valid && (tick_valid || snapshot_we || mod_valid)));
        if (past_valid && $past(busy))
            assume(mode_state == $past(mode_state));

        if (rst) begin
            tick_active <= 1'b0;
            snapshot_active <= 1'b0;
            mod_active <= 1'b0;
            invalid_mod_check <= 1'b0;
            seen_train_tick_done <= 1'b0;
            seen_nonzero_snapshot <= 1'b0;
            reached_public_nonzero_mod_success <= 1'b0;
            reached_wrong_mode_reject <= 1'b0;
            reached_wrong_id_reject <= 1'b0;
            reached_repeat_id_reject <= 1'b0;
        end else begin
            invalid_mod_check <= 1'b0;

            if (accepted_tick)
                tick_active <= 1'b1;
            if (tick_active && done) begin
                tick_active <= 1'b0;
                seen_train_tick_done <= 1'b1;
            end

            if (accepted_snapshot && seen_train_tick_done)
                snapshot_active <= 1'b1;
            if (snapshot_active && done) begin
                snapshot_active <= 1'b0;
                if (snapshot_valid_state
                        && eligibility_snapshot_flat_state != 0
                        && pending_snapshot_valid_state)
                    seen_nonzero_snapshot <= 1'b1;
            end

            if (accepted_valid_nonzero_mod) begin
                assert(!mod_active);
                mod_active <= 1'b1;
                utility_before_mod <= utility_flat;
                expected_utility_after_mod <= utility_after_observe(
                    utility_flat,
                    eligibility_snapshot_flat_state
                );
                active_mod_id <= mod_commit_id;
            end

            if (mod_active) begin
                // gate OBSERVE 在核心多周期 MOD 完成之前已经公开原子结果。
                assert(last_observation_valid_state);
                assert(last_observation_id_state == active_mod_id);
                assert(utility_flat == expected_utility_after_mod);
                if (!done)
                    assert(pending_snapshot_valid_state);
                if (done) begin
                    assert(!protocol_error);
                    assert(!pending_snapshot_valid_state);
                    mod_active <= 1'b0;
                    if (seen_nonzero_snapshot
                            && (eligibility_snapshot_flat_state != 0)
                            && (utility_flat != utility_before_mod))
                        reached_public_nonzero_mod_success <= 1'b1;
                end
            end

            if (accepted_invalid_nonzero_mod) begin
                invalid_mod_check <= 1'b1;
                invalid_wrong_mode <= mode_state != 2'd1;
                invalid_wrong_id <= (mode_state == 2'd1)
                    && (!pending_snapshot_valid_state
                        || (mod_commit_id != pending_snapshot_id_state));
                invalid_repeat_id <= public_mod_metadata_valid
                    && !public_mod_id_fresh;
                invalid_utility_before <= utility_flat;
                invalid_observation_valid_before <= last_observation_valid_state;
                invalid_observation_id_before <= last_observation_id_state;
                invalid_pending_valid_before <= pending_snapshot_valid_state;
                invalid_pending_id_before <= pending_snapshot_id_state;
            end

            if (invalid_mod_check) begin
                assert(done);
                assert(protocol_error);
                assert(utility_flat == invalid_utility_before);
                assert(last_observation_valid_state
                    == invalid_observation_valid_before);
                assert(last_observation_id_state
                    == invalid_observation_id_before);
                assert(pending_snapshot_valid_state == invalid_pending_valid_before);
                assert(pending_snapshot_id_state == invalid_pending_id_before);
                if (invalid_wrong_mode)
                    reached_wrong_mode_reject <= 1'b1;
                if (invalid_wrong_id)
                    reached_wrong_id_reject <= 1'b1;
                if (invalid_repeat_id)
                    reached_repeat_id_reject <= 1'b1;
            end

            // 剪枝响应受背压时，响应和 MOD 相关公开状态必须完全稳定。
            if (past_valid && $past(prune_rsp_valid && !prune_rsp_ready)) begin
                assert(prune_rsp_valid);
                assert(prune_rsp_status == $past(prune_rsp_status));
                assert(prune_rsp_id == $past(prune_rsp_id));
                assert(prune_rsp_mask == $past(prune_rsp_mask));
                assert(!ready);
                assert(utility_flat == $past(utility_flat));
                assert(last_observation_valid_state
                    == $past(last_observation_valid_state));
                assert(last_observation_id_state
                    == $past(last_observation_id_state));
                assert(pending_snapshot_valid_state
                    == $past(pending_snapshot_valid_state));
                assert(pending_snapshot_id_state == $past(pending_snapshot_id_state));
            end
        end
    end
endmodule
