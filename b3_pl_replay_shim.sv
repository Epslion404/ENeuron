// 纯 PL 吞吐微基准：缓存一个已通过 packet 合同的 8-beat 样本，
// 在 NPU 时钟域内完成预热和计量，只把最后一次结果送回既有结果 FIFO。
`timescale 1ns/1ps
module b3_pl_replay_shim #(
    parameter integer WARMUP_SAMPLES = 1000,
    parameter integer MEASURE_SAMPLES = 10000
) (
    input  logic        clk,
    input  logic        rst,

    input  logic [31:0] upstream_sample_data,
    input  logic [31:0] upstream_sample_id,
    input  logic        upstream_sample_valid,
    output logic        upstream_sample_ready,

    output logic [31:0] core_sample_data,
    output logic [31:0] core_sample_id,
    output logic        core_sample_valid,
    input  logic        core_sample_ready,

    input  logic [31:0] core_result_data,
    input  logic [31:0] core_result_sample_id,
    input  logic [31:0] core_result_mask_epoch,
    input  logic        core_result_valid,
    output logic        core_result_ready,

    output logic [31:0] downstream_result_data,
    output logic [31:0] downstream_result_sample_id,
    output logic [31:0] downstream_result_mask_epoch,
    output logic        downstream_result_valid,
    input  logic        downstream_result_ready,

    output logic [31:0] pl_replay_status,
    output logic [31:0] pl_replay_completed_count,
    output logic [31:0] pl_replay_measured_cycles
);
    localparam logic [2:0] STATE_CAPTURE = 3'd0;
    localparam logic [2:0] STATE_WAIT_RESULT = 3'd1;
    localparam logic [2:0] STATE_FEED_REPLAY = 3'd2;
    localparam logic [2:0] STATE_DONE = 3'd3;

    localparam logic [1:0] RUN_INITIAL = 2'd0;
    localparam logic [1:0] RUN_WARMUP = 2'd1;
    localparam logic [1:0] RUN_MEASURE = 2'd2;

    localparam logic [31:0] STATUS_CAPTURE = 32'd1;
    localparam logic [31:0] STATUS_WARMUP = 32'd2;
    localparam logic [31:0] STATUS_MEASURE = 32'd3;
    localparam logic [31:0] STATUS_PASS = 32'd4;

    logic [2:0] state;
    logic [1:0] run_kind;
    logic [3:0] capture_beat;
    logic [3:0] replay_beat;
    logic [3:0] result_beat;
    logic [31:0] cached_sample_data [0:7];
    logic [31:0] cached_sample_id;
    logic [31:0] warmup_completed_count;
    logic [31:0] measured_cycle_counter;
    logic measuring;
    logic forward_current_result;

    wire upstream_fire = upstream_sample_valid && upstream_sample_ready;
    wire replay_fire = core_sample_valid && core_sample_ready;
    wire result_fire = core_result_valid && core_result_ready;

    always_comb begin
        upstream_sample_ready = 1'b0;
        core_sample_data = 32'd0;
        core_sample_id = cached_sample_id;
        core_sample_valid = 1'b0;
        core_result_ready = 1'b0;
        downstream_result_data = core_result_data;
        downstream_result_sample_id = core_result_sample_id;
        downstream_result_mask_epoch = core_result_mask_epoch;
        downstream_result_valid = 1'b0;

        case (state)
            STATE_CAPTURE: begin
                upstream_sample_ready = core_sample_ready;
                core_sample_data = upstream_sample_data;
                core_sample_id = upstream_sample_id;
                core_sample_valid = upstream_sample_valid;
            end
            STATE_FEED_REPLAY: begin
                core_sample_data = cached_sample_data[replay_beat];
                core_sample_valid = 1'b1;
            end
            STATE_WAIT_RESULT: begin
                core_result_ready = forward_current_result ? downstream_result_ready : 1'b1;
                downstream_result_valid = core_result_valid && forward_current_result;
            end
            default: begin
            end
        endcase
    end

    integer reset_index;
    always_ff @(posedge clk) begin
        if (rst) begin
            state <= STATE_CAPTURE;
            run_kind <= RUN_INITIAL;
            capture_beat <= 4'd0;
            replay_beat <= 4'd0;
            result_beat <= 4'd0;
            cached_sample_id <= 32'd0;
            warmup_completed_count <= 32'd0;
            pl_replay_completed_count <= 32'd0;
            measured_cycle_counter <= 32'd0;
            pl_replay_measured_cycles <= 32'd0;
            pl_replay_status <= STATUS_CAPTURE;
            measuring <= 1'b0;
            forward_current_result <= 1'b0;
            for (reset_index = 0; reset_index < 8; reset_index = reset_index + 1)
                cached_sample_data[reset_index] <= 32'd0;
        end else begin
            if (measuring)
                measured_cycle_counter <= measured_cycle_counter + 32'd1;

            if (state == STATE_CAPTURE && upstream_fire) begin
                cached_sample_data[capture_beat] <= upstream_sample_data;
                if (capture_beat == 4'd0)
                    cached_sample_id <= upstream_sample_id;
                if (capture_beat == 4'd7) begin
                    capture_beat <= 4'd0;
                    result_beat <= 4'd0;
                    run_kind <= RUN_INITIAL;
                    forward_current_result <= 1'b0;
                    state <= STATE_WAIT_RESULT;
                end else begin
                    capture_beat <= capture_beat + 4'd1;
                end
            end

            if (state == STATE_FEED_REPLAY && replay_fire) begin
                if (run_kind == RUN_MEASURE && pl_replay_completed_count == 32'd0 &&
                    replay_beat == 4'd0) begin
                    measuring <= 1'b1;
                    measured_cycle_counter <= 32'd1;
                    pl_replay_status <= STATUS_MEASURE;
                end
                if (replay_beat == 4'd7) begin
                    replay_beat <= 4'd0;
                    result_beat <= 4'd0;
                    state <= STATE_WAIT_RESULT;
                end else begin
                    replay_beat <= replay_beat + 4'd1;
                end
            end

            if (state == STATE_WAIT_RESULT && result_fire) begin
                if (result_beat == 4'd9) begin
                    result_beat <= 4'd0;
                    if (run_kind == RUN_INITIAL) begin
                        replay_beat <= 4'd0;
                        if (WARMUP_SAMPLES != 0) begin
                            run_kind <= RUN_WARMUP;
                            pl_replay_status <= STATUS_WARMUP;
                            forward_current_result <= 1'b0;
                        end else begin
                            run_kind <= RUN_MEASURE;
                            pl_replay_status <= STATUS_MEASURE;
                            forward_current_result <= (MEASURE_SAMPLES == 1);
                        end
                        state <= STATE_FEED_REPLAY;
                    end else if (run_kind == RUN_WARMUP) begin
                        warmup_completed_count <= warmup_completed_count + 32'd1;
                        replay_beat <= 4'd0;
                        if ((warmup_completed_count + 32'd1) < WARMUP_SAMPLES) begin
                            run_kind <= RUN_WARMUP;
                            forward_current_result <= 1'b0;
                        end else begin
                            run_kind <= RUN_MEASURE;
                            pl_replay_status <= STATUS_MEASURE;
                            forward_current_result <= (MEASURE_SAMPLES == 1);
                        end
                        state <= STATE_FEED_REPLAY;
                    end else begin
                        pl_replay_completed_count <= pl_replay_completed_count + 32'd1;
                        if ((pl_replay_completed_count + 32'd1) >= MEASURE_SAMPLES) begin
                            measuring <= 1'b0;
                            pl_replay_measured_cycles <= measured_cycle_counter + 32'd1;
                            pl_replay_status <= STATUS_PASS;
                            state <= STATE_DONE;
                        end else begin
                            replay_beat <= 4'd0;
                            forward_current_result <=
                                ((pl_replay_completed_count + 32'd2) >= MEASURE_SAMPLES);
                            state <= STATE_FEED_REPLAY;
                        end
                    end
                end else begin
                    result_beat <= result_beat + 4'd1;
                end
            end
        end
    end
endmodule
