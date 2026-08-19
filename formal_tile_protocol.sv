// 4->2->2 Tile 接口安全性质：使用真实四核实现，不抽象神经元算术。
module formal_tile_protocol (
    input logic clk
);

    (* anyseq *) logic rst;
    (* anyseq *) logic state_clear;
    (* anyseq *) logic tick_valid;
    (* anyseq *) logic route_flush_valid;
    (* anyseq *) logic [3:0] input_spikes;
    (* anyseq *) logic learn_enable;
    (* anyseq *) logic snapshot_we;
    (* anyseq *) logic [15:0] snapshot_commit_id;
    (* anyseq *) logic [15:0] snapshot_episode_id;
    (* anyseq *) logic mod_valid;
    (* anyseq *) logic [15:0] mod_commit_id;
    (* anyseq *) logic signed [1:0] hidden0_modulator;
    (* anyseq *) logic signed [1:0] hidden1_modulator;
    (* anyseq *) logic signed [1:0] output0_modulator;
    (* anyseq *) logic signed [1:0] output1_modulator;
    (* anyseq *) logic weight_we;
    (* anyseq *) logic [1:0] neuron_addr;
    (* anyseq *) logic [1:0] weight_addr;
    (* anyseq *) logic signed [7:0] weight_wdata;

    logic signed [7:0] weight_rdata;
    logic ready;
    logic busy;
    logic done;
    logic protocol_error;
    logic [1:0] hidden_spikes;
    logic [1:0] output_spikes;
    logic [1:0] pending_hidden_state;
    logic snapshot_valid_state;
    logic [15:0] pending_commit_id_state;
    logic [15:0] pending_episode_id_state;
    logic last_commit_valid_state;
    logic [15:0] last_commit_id_state;
    logic [31:0] weight_epoch_state;

    logic past_valid = 1'b0;
    logic clear_inflight = 1'b0;
    logic route_flush_inflight = 1'b0;
    logic saved_snapshot_valid;
    logic [15:0] saved_pending_commit_id;
    logic [15:0] saved_pending_episode_id;
    logic saved_last_commit_valid;
    logic [15:0] saved_last_commit_id;
    logic [31:0] saved_weight_epoch;

    digital_snn_tile_4x2x2 dut (.*);

    // 只约束同步复位序列；其余命令和数据保持完全任意。
    always_ff @(posedge clk) begin
        past_valid <= 1'b1;
        if (!past_valid) begin
            assume(rst);
            clear_inflight <= 1'b0;
            route_flush_inflight <= 1'b0;
        end else begin
            assume(!rst);

            // 先结算旧事务，再捕获同周期被接受的新事务，覆盖 done/ready 背靠背场景。
            if (done && clear_inflight) begin
                assert(pending_hidden_state == 0);
                assert(snapshot_valid_state == saved_snapshot_valid);
                assert(pending_commit_id_state == saved_pending_commit_id);
                assert(pending_episode_id_state == saved_pending_episode_id);
                assert(last_commit_valid_state == saved_last_commit_valid);
                assert(last_commit_id_state == saved_last_commit_id);
                assert(weight_epoch_state == saved_weight_epoch);
                clear_inflight <= 1'b0;
            end
            if (done && route_flush_inflight) begin
                assert(pending_hidden_state == 0);
                assert(hidden_spikes == 0);
                assert(snapshot_valid_state == saved_snapshot_valid);
                assert(pending_commit_id_state == saved_pending_commit_id);
                assert(pending_episode_id_state == saved_pending_episode_id);
                assert(last_commit_valid_state == saved_last_commit_valid);
                assert(last_commit_id_state == saved_last_commit_id);
                assert(weight_epoch_state == saved_weight_epoch);
                route_flush_inflight <= 1'b0;
            end

            if (ready && state_clear) begin
                clear_inflight <= 1'b1;
                saved_snapshot_valid <= snapshot_valid_state;
                saved_pending_commit_id <= pending_commit_id_state;
                saved_pending_episode_id <= pending_episode_id_state;
                saved_last_commit_valid <= last_commit_valid_state;
                saved_last_commit_id <= last_commit_id_state;
                saved_weight_epoch <= weight_epoch_state;
            end else if (ready && !snapshot_we && !weight_we && !mod_valid
                    && route_flush_valid) begin
                route_flush_inflight <= 1'b1;
                saved_snapshot_valid <= snapshot_valid_state;
                saved_pending_commit_id <= pending_commit_id_state;
                saved_pending_episode_id <= pending_episode_id_state;
                saved_last_commit_valid <= last_commit_valid_state;
                saved_last_commit_id <= last_commit_id_state;
                saved_weight_epoch <= weight_epoch_state;
            end
        end
    end

    always_ff @(posedge clk) begin
        if (past_valid && !rst) begin
            // Tile 对外只暴露 IDLE 或 BUSY，不允许第三种握手状态。
            assert(ready == !busy);

            // 事务进行中不得提前泄露完成、错误、spike 或权重读数据。
            if (busy) begin
                assert(!done);
                assert(!protocol_error);
                assert(hidden_spikes == 0);
                assert(output_spikes == 0);
                assert(weight_rdata == 0);
            end

            // 所有脉冲和协议错误只能出现在事务完成周期。
            if ((hidden_spikes != 0) || (output_spikes != 0))
                assert(done);
            if (protocol_error)
                assert(done);
            if (done)
                assert(ready && !busy);

            // all-done barrier 前，Tile 级元数据必须保持原子不可见。
            if (busy && !$past(rst)) begin
                assert(pending_hidden_state == $past(pending_hidden_state));
                assert(snapshot_valid_state == $past(snapshot_valid_state));
                assert(pending_commit_id_state == $past(pending_commit_id_state));
                assert(pending_episode_id_state == $past(pending_episode_id_state));
                assert(last_commit_valid_state == $past(last_commit_valid_state));
                assert(last_commit_id_state == $past(last_commit_id_state));
                assert(weight_epoch_state == $past(weight_epoch_state));
            end

        end
    end

endmodule
