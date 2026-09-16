`timescale 1ns/1ps
module tb_b3_pl_replay_shim;
    logic clk = 1'b0;
    always #5 clk = ~clk;
    logic rst = 1'b1;

    logic [31:0] upstream_sample_data = 32'd0;
    logic [31:0] upstream_sample_id = 32'h5141_5400;
    logic upstream_sample_valid = 1'b0;
    wire upstream_sample_ready;

    wire [31:0] core_sample_data;
    wire [31:0] core_sample_id;
    wire core_sample_valid;
    logic core_sample_ready = 1'b1;

    logic [31:0] core_result_data = 32'd0;
    logic [31:0] core_result_sample_id = 32'd0;
    logic [31:0] core_result_mask_epoch = 32'd1;
    logic core_result_valid = 1'b0;
    wire core_result_ready;

    wire [31:0] downstream_result_data;
    wire [31:0] downstream_result_sample_id;
    wire [31:0] downstream_result_mask_epoch;
    wire downstream_result_valid;
    logic downstream_result_ready = 1'b1;

    wire [31:0] pl_replay_status;
    wire [31:0] pl_replay_completed_count;
    wire [31:0] pl_replay_measured_cycles;

    integer accepted_samples = 0;
    integer sample_beat = 0;
    integer result_beat = 0;
    integer forwarded_result_beats = 0;
    integer idle_cycles = 0;
    logic fake_result_active = 1'b0;

    b3_pl_replay_shim #(
        .WARMUP_SAMPLES(2),
        .MEASURE_SAMPLES(3)
    ) dut (
        .clk(clk), .rst(rst),
        .upstream_sample_data(upstream_sample_data),
        .upstream_sample_id(upstream_sample_id),
        .upstream_sample_valid(upstream_sample_valid),
        .upstream_sample_ready(upstream_sample_ready),
        .core_sample_data(core_sample_data),
        .core_sample_id(core_sample_id),
        .core_sample_valid(core_sample_valid),
        .core_sample_ready(core_sample_ready),
        .core_result_data(core_result_data),
        .core_result_sample_id(core_result_sample_id),
        .core_result_mask_epoch(core_result_mask_epoch),
        .core_result_valid(core_result_valid),
        .core_result_ready(core_result_ready),
        .downstream_result_data(downstream_result_data),
        .downstream_result_sample_id(downstream_result_sample_id),
        .downstream_result_mask_epoch(downstream_result_mask_epoch),
        .downstream_result_valid(downstream_result_valid),
        .downstream_result_ready(downstream_result_ready),
        .pl_replay_status(pl_replay_status),
        .pl_replay_completed_count(pl_replay_completed_count),
        .pl_replay_measured_cycles(pl_replay_measured_cycles)
    );

    always_ff @(posedge clk) begin
        if (rst) begin
            accepted_samples <= 0;
            sample_beat <= 0;
            result_beat <= 0;
            idle_cycles <= 0;
            fake_result_active <= 1'b0;
            core_result_valid <= 1'b0;
            forwarded_result_beats <= 0;
        end else begin
            if (core_sample_valid && core_sample_ready) begin
                if (core_sample_id != 32'h5141_5400)
                    $fatal(1, "sample id changed during replay");
                if (core_sample_data != (32'h1000_0000 + sample_beat))
                    $fatal(1, "sample beat mismatch beat=%0d data=%08x", sample_beat, core_sample_data);
                if (sample_beat == 7) begin
                    sample_beat <= 0;
                    accepted_samples <= accepted_samples + 1;
                    idle_cycles <= 2;
                end else begin
                    sample_beat <= sample_beat + 1;
                end
            end

            if (idle_cycles != 0) begin
                idle_cycles <= idle_cycles - 1;
                if (idle_cycles == 1) begin
                    fake_result_active <= 1'b1;
                    core_result_valid <= 1'b1;
                    result_beat <= 0;
                    core_result_sample_id <= 32'h5141_5400;
                    core_result_data <= 32'h2000_0000;
                end
            end

            if (core_result_valid && core_result_ready) begin
                if (result_beat == 9) begin
                    result_beat <= 0;
                    fake_result_active <= 1'b0;
                    core_result_valid <= 1'b0;
                end else begin
                    result_beat <= result_beat + 1;
                    core_result_data <= 32'h2000_0000 + result_beat + 1;
                end
            end

            if (downstream_result_valid && downstream_result_ready) begin
                if (downstream_result_data != (32'h2000_0000 + forwarded_result_beats))
                    $fatal(1, "forwarded result beat mismatch beat=%0d", forwarded_result_beats);
                forwarded_result_beats <= forwarded_result_beats + 1;
            end
        end
    end

    integer beat;
    initial begin
        repeat (5) @(posedge clk);
        rst = 1'b0;
        for (beat = 0; beat < 8; beat = beat + 1) begin
            @(negedge clk);
            upstream_sample_data = 32'h1000_0000 + beat;
            upstream_sample_valid = 1'b1;
            @(posedge clk);
            while (!upstream_sample_ready) @(posedge clk);
        end
        @(negedge clk);
        upstream_sample_valid = 1'b0;

        wait (pl_replay_status == 32'd4);
        repeat (3) @(posedge clk);
        if (accepted_samples != 6)
            $fatal(1, "expected initial + 2 warmup + 3 measured samples, got %0d", accepted_samples);
        if (pl_replay_completed_count != 3)
            $fatal(1, "measured completion mismatch: %0d", pl_replay_completed_count);
        if (pl_replay_measured_cycles == 0)
            $fatal(1, "measured cycle counter is zero");
        if (forwarded_result_beats != 10)
            $fatal(1, "only final result must escape replay shim, got %0d beats", forwarded_result_beats);
        $display("B3_PL_REPLAY_SHIM_PASS samples=%0d measured=%0d cycles=%0d",
                 accepted_samples, pl_replay_completed_count, pl_replay_measured_cycles);
        $finish;
    end

    initial begin
        #200000;
        $fatal(1, "timeout");
    end
endmodule
