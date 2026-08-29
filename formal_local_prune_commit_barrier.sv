// 十参与者小状态环境；只抽象参与者，不替换被证明的真实 barrier。
module formal_local_prune_commit_barrier(
    input logic clk,
    output logic reached_success,
    output logic saw_gate_stagger,
    output logic saw_rsp_backpressure,
    output logic saw_unblock
);
    localparam integer N = 10;
    (* anyseq *) logic rst, commit_valid, safe_boundary, rsp_ready;
    (* anyseq *) logic [15:0] commit_id;
    (* anyseq *) logic [N-1:0] gate_cmd_ready, clear_cmd_ready;
    (* anyseq *) logic [N-1:0] gate_rsp_valid, clear_rsp_valid;
    (* anyseq *) logic runtime_cmd_valid;
    logic commit_ready, rsp_valid, runtime_blocked, internal_error;
    logic [2:0] rsp_status; logic [15:0] rsp_id;
    logic [39:0] rsp_masks_flat, gate_rsp_masks_flat;
    logic [N-1:0] gate_cmd_valid, gate_rsp_ready;
    logic [N-1:0] clear_cmd_valid, clear_rsp_ready;
    logic [15:0] gate_cmd_id; logic [29:0] gate_rsp_status_flat;
    logic [29:0] clear_rsp_status_flat; logic [31:0] commit_epoch_state;
    logic [N-1:0] gate_started, gate_replied, clear_started, clear_replied;
    logic past_valid;
    logic epoch_changed_for_commit;
    wire runtime_cmd_ready = !runtime_blocked;

    assign gate_rsp_status_flat = '0; // ST_OK；exact-two 由 gate 合同环境保证。
    assign clear_rsp_status_flat = '0;
    assign gate_rsp_masks_flat = {N{4'b0011}};

    local_prune_commit_barrier #(.N_GATES(N)) dut (.*);

    integer i;
    always_ff @(posedge clk) begin
        past_valid <= 1'b1;
        if (!past_valid) assume(rst);
        else assume(!rst);
        if (rst) begin
            gate_started <= 0; gate_replied <= 0;
            clear_started <= 0; clear_replied <= 0; reached_success <= 0;
            saw_gate_stagger <= 0; saw_rsp_backpressure <= 0; saw_unblock <= 0;
            epoch_changed_for_commit <= 0;
        end else begin
            // 小状态参与者只能在被启动后响应，每路最多一次。
            for (i=0; i<N; i=i+1) begin
                assume(!gate_rsp_valid[i] || (gate_started[i] && !gate_replied[i]));
                assume(!clear_rsp_valid[i] || (clear_started[i] && !clear_replied[i]));
            end
            if (|gate_cmd_valid) begin
                gate_started <= gate_cmd_valid;
                gate_replied <= 0;
                clear_started <= 0;
                clear_replied <= 0;
            end else begin
                gate_started <= gate_started | gate_cmd_valid;
                gate_replied <= gate_replied | (gate_rsp_valid & gate_rsp_ready);
                clear_started <= clear_started | clear_cmd_valid;
                clear_replied <= clear_replied | (clear_rsp_valid & clear_rsp_ready);
            end
            if (gate_replied != 0 && gate_replied != {N{1'b1}})
                saw_gate_stagger <= 1;
            if (rsp_valid && !rsp_ready) saw_rsp_backpressure <= 1;
            if (past_valid && $past(runtime_blocked) && !runtime_blocked)
                saw_unblock <= 1;
            if (saw_gate_stagger && saw_rsp_backpressure && saw_unblock)
                reached_success <= 1;
            if (|gate_cmd_valid) epoch_changed_for_commit <= 0;

            assert(gate_cmd_valid == 0 || gate_cmd_valid == {N{1'b1}});
            if (|gate_cmd_valid) begin
                assert(&gate_cmd_ready); assert(safe_boundary);
                assert(gate_cmd_id == commit_id);
            end
            if (|clear_cmd_valid) begin
                assert(clear_cmd_valid == {N{1'b1}});
                assert(gate_replied == {N{1'b1}});
                assert(&clear_cmd_ready);
            end
            if (rsp_valid && rsp_status == 0) assert(clear_replied == {N{1'b1}});
            for (i=0; i<N; i=i+1) begin
                if (gate_replied[i]) assert(!gate_rsp_ready[i]);
                if (clear_replied[i]) assert(!clear_rsp_ready[i]);
            end
            assert(runtime_blocked == !commit_ready);
            if (runtime_blocked && runtime_cmd_valid) assert(!runtime_cmd_ready);
            if (past_valid && $past(rsp_valid && !rsp_ready)) begin
                assert(rsp_valid); assert(rsp_status == $past(rsp_status));
                assert(rsp_id == $past(rsp_id));
                assert(rsp_masks_flat == $past(rsp_masks_flat));
            end
            if (past_valid && commit_epoch_state != $past(commit_epoch_state)) begin
                assert(commit_epoch_state == $past(commit_epoch_state) + 1);
                assert(clear_replied == {N{1'b1}});
                assert(!epoch_changed_for_commit);
                epoch_changed_for_commit <= 1;
            end
        end
    end
endmodule
