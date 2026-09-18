// CP8 continuous replay RED 自校验 TB。
// 期望生产 shim 增加 CONTINUOUS_REPLAY 参数：为 1 时 warmup 后持续循环，
// 永不进入 PASS/DONE，completed_count 越过原 MEASURE_SAMPLES 仍增长，
// 且不再向下游输出 final 结果。当前生产代码未实现，编译应失败（RED）。
`timescale 1ns/1ps
module tb_b3_cp8_power_replay_shim;
    logic clk = 1'b0;
    always #5 clk = ~clk;
    logic rst = 1'b1;

    localparam integer INPUT_SAMPLES = 3;
    localparam integer WARMUP_SAMPLES = 2;
    localparam integer MEASURE_SAMPLES = 5;
    localparam integer CONTINUOUS = 1;
    localparam integer REQUIRED_MEASURES = MEASURE_SAMPLES + 5;

    logic [31:0] upstream_sample_data = 32'd0;
    logic [31:0] upstream_sample_id = 32'd0;
    logic upstream_sample_valid = 1'b0;
    wire upstream_sample_ready;
    wire [31:0] core_sample_data, core_sample_id;
    wire core_sample_valid;
    logic core_sample_ready = 1'b1;
    logic [31:0] core_result_data = 32'd0;
    logic [31:0] core_result_sample_id = 32'd0;
    logic [31:0] core_result_mask_epoch = 32'd1;
    logic core_result_valid = 1'b0;
    wire core_result_ready;
    wire [31:0] downstream_result_data, downstream_result_sample_id;
    wire [31:0] downstream_result_mask_epoch;
    wire downstream_result_valid;
    logic downstream_result_ready = 1'b1;
    wire [31:0] pl_replay_status, pl_replay_capture_count;
    wire [31:0] pl_replay_completed_count, pl_replay_measured_cycles;

    integer sample_beat = 0;
    integer result_beat = 0;
    integer core_samples = 0;
    integer result_delay = 0;
    logic [31:0] fake_id = 0;
    integer expected_slot;

    logic downstream_seen = 1'b0;
    logic pass_seen = 1'b0;
    logic fail_seen = 1'b0;
    logic measure_seen = 1'b0;

    b3_pl_distribution_replay_shim #(
        .INPUT_SAMPLES(INPUT_SAMPLES),
        .WARMUP_SAMPLES(WARMUP_SAMPLES),
        .MEASURE_SAMPLES(MEASURE_SAMPLES),
        .CONTINUOUS_REPLAY(CONTINUOUS)
    ) dut (
        .clk(clk), .rst(rst),
        .upstream_sample_data(upstream_sample_data),
        .upstream_sample_id(upstream_sample_id),
        .upstream_sample_valid(upstream_sample_valid),
        .upstream_sample_ready(upstream_sample_ready),
        .core_sample_data(core_sample_data), .core_sample_id(core_sample_id),
        .core_sample_valid(core_sample_valid), .core_sample_ready(core_sample_ready),
        .core_result_data(core_result_data), .core_result_sample_id(core_result_sample_id),
        .core_result_mask_epoch(core_result_mask_epoch), .core_result_valid(core_result_valid),
        .core_result_ready(core_result_ready),
        .downstream_result_data(downstream_result_data),
        .downstream_result_sample_id(downstream_result_sample_id),
        .downstream_result_mask_epoch(downstream_result_mask_epoch),
        .downstream_result_valid(downstream_result_valid),
        .downstream_result_ready(downstream_result_ready),
        .pl_replay_status(pl_replay_status),
        .pl_replay_capture_count(pl_replay_capture_count),
        .pl_replay_completed_count(pl_replay_completed_count),
        .pl_replay_measured_cycles(pl_replay_measured_cycles)
    );

    always_ff @(posedge clk) begin
        if (rst) begin
            sample_beat <= 0;
            result_beat <= 0;
            core_samples <= 0;
            result_delay <= 0;
            core_result_valid <= 1'b0;
            downstream_seen <= 1'b0;
            pass_seen <= 1'b0;
            fail_seen <= 1'b0;
            measure_seen <= 1'b0;
        end else begin
            if (core_sample_valid && core_sample_ready) begin
                if (core_samples < INPUT_SAMPLES)
                    expected_slot = core_samples;
                else if (core_samples < INPUT_SAMPLES + WARMUP_SAMPLES)
                    expected_slot = (core_samples - INPUT_SAMPLES) % INPUT_SAMPLES;
                else
                    expected_slot =
                        (core_samples - INPUT_SAMPLES - WARMUP_SAMPLES) % INPUT_SAMPLES;
                if (core_sample_data != 32'h1000_0000 + expected_slot * 32'h100 + sample_beat)
                    $fatal(1, "sample data mismatch samples=%0d beat=%0d data=%08x",
                           core_samples, sample_beat, core_sample_data);
                if (sample_beat == 0)
                    fake_id <= core_sample_id;
                if (sample_beat == 7) begin
                    sample_beat <= 0;
                    core_samples <= core_samples + 1;
                    result_delay <= 2;
                end else begin
                    sample_beat <= sample_beat + 1;
                end
            end
            if (result_delay != 0) begin
                result_delay <= result_delay - 1;
                if (result_delay == 1) begin
                    core_result_valid <= 1'b1;
                    result_beat <= 0;
                    core_result_sample_id <= fake_id;
                    core_result_data <= 32'h2000_0000;
                end
            end
            if (core_result_valid && core_result_ready) begin
                if (result_beat == 9) begin
                    result_beat <= 0;
                    core_result_valid <= 1'b0;
                end else begin
                    result_beat <= result_beat + 1;
                    core_result_data <= 32'h2000_0000 + result_beat + 1;
                end
            end
            if (downstream_result_valid)
                downstream_seen <= 1'b1;
            if (pl_replay_status == 32'd3)
                measure_seen <= 1'b1;
            if (pl_replay_status == 32'd4)
                pass_seen <= 1'b1;
            if (pl_replay_status == 32'd5)
                fail_seen <= 1'b1;
        end
    end

    integer sample;
    integer beat;
    initial begin
        repeat (5) @(posedge clk);
        rst = 1'b0;
        for (sample = 0; sample < INPUT_SAMPLES; sample = sample + 1) begin
            for (beat = 0; beat < 8; beat = beat + 1) begin
                @(negedge clk);
                upstream_sample_id = 32'h1000_0000 + sample * 32'h100;
                upstream_sample_data = upstream_sample_id + beat;
                upstream_sample_valid = 1'b1;
                @(posedge clk);
                while (!upstream_sample_ready) @(posedge clk);
            end
            @(negedge clk);
            upstream_sample_valid = 1'b0;
            wait (pl_replay_capture_count == sample + 1);
        end
        wait (pl_replay_completed_count >= REQUIRED_MEASURES);
        repeat (2) @(posedge clk);
        if (!measure_seen)
            $fatal(1, "continuous replay never entered STATUS_MEASURE");
        if (pass_seen || fail_seen)
            $fatal(1, "continuous replay reached terminal status pass=%0d fail=%0d",
                   pass_seen, fail_seen);
        if (pl_replay_status != 32'd3)
            $fatal(1, "continuous status must stay 3, got %0d", pl_replay_status);
        if (pl_replay_completed_count <= MEASURE_SAMPLES)
            $fatal(1, "completed did not exceed finite threshold: %0d",
                   pl_replay_completed_count);
        if (downstream_seen)
            $fatal(1, "continuous replay emitted a downstream final result");
        $display("B3_CP8_POWER_REPLAY_SHIM_PASS captures=%0d measures=%0d status=%0d",
                 pl_replay_capture_count, pl_replay_completed_count, pl_replay_status);
        $finish;
    end

    initial begin
        #500000;
        $fatal(1, "timeout");
    end
endmodule
