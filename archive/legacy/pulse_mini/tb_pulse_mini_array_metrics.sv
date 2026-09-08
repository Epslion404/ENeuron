`timescale 1ns/1ps
module tb_pulse_mini_array_metrics #(
    parameter integer N_CORES = 32
);
    logic clk = 1'b0;
    logic rst = 1'b1;
    logic cmd_valid = 1'b0;
    logic cmd_ready;
    logic [2:0] cmd_opcode;
    logic [7:0] cmd_arg0;
    logic [7:0] cmd_arg1;
    logic rsp_valid;
    logic rsp_ready = 1'b0;
    logic [2:0] rsp_status;
    logic signed [7:0] rsp_data;
    logic [N_CORES-1:0] spike_vector;
    logic [N_CORES-1:0] pending_vector;
    logic [N_CORES-1:0] protocol_error_vector;
    integer cycle_count = 0;
    integer start_cycle;
    integer command_latency;
    integer tick_latency_sum = 0;
    integer feedback_latency_sum = 0;
    integer spike_count;
    integer last_spike_count = 0;
    integer burst_accepts = 0;
    integer burst_cycles = 64;
    integer i;

    pulse_mini_array #(.N_CORES(N_CORES)) dut (.*);
    always #5 clk = ~clk;
    always @(posedge clk) cycle_count = cycle_count + 1;

    task automatic issue(input integer in_op, input integer in_a0, input integer in_a1);
        begin
            @(negedge clk);
            while (!cmd_ready) @(negedge clk);
            start_cycle = cycle_count;
            cmd_opcode = in_op[2:0];
            cmd_arg0 = in_a0[7:0];
            cmd_arg1 = in_a1[7:0];
            cmd_valid = 1'b1;
            @(posedge clk);
            #1 cmd_valid = 1'b0;
            @(negedge clk);
            while (!rsp_valid) @(negedge clk);
            command_latency = cycle_count - start_cycle;
            if (in_op == 2) tick_latency_sum = tick_latency_sum + command_latency;
            if (in_op == 4) feedback_latency_sum = feedback_latency_sum + command_latency;
            if (rsp_status != 0) $fatal(1, "unexpected status %0d for op %0d", rsp_status, in_op);
            if (in_op == 2) begin
                last_spike_count = 0;
                for (i = 0; i < N_CORES; i = i + 1)
                    last_spike_count = last_spike_count + spike_vector[i];
            end
            rsp_ready = 1'b1;
            @(posedge clk);
            #1 rsp_ready = 1'b0;
        end
    endtask

    initial begin
        repeat (3) @(posedge clk);
        rst = 1'b0;
        issue(5, 0, 6); // CONFIG: all cores get weight0=+6.
        issue(6, 0, 0);
        issue(0, 2, 0); // INFER.
        issue(1, 0, 0);
        issue(2, 1, 0);
        spike_count = last_spike_count;
        $display("METRIC N=%0d TICK_LATENCY=%0d SPIKES=%0d", N_CORES, command_latency, spike_count);
        issue(1, 0, 0);
        issue(0, 1, 0); // TRAIN.
        issue(3, 0, 0);
        issue(4, 0, 0);
        $display("METRIC N=%0d TICK_TOTAL=%0d FEEDBACK_LATENCY=%0d", N_CORES,
            tick_latency_sum, feedback_latency_sum);
        // Keep response ready high and hold a valid TICK to expose the actual
        // one-slot protocol throughput, including the no-same-cycle-replace gap.
        rsp_ready = 1'b1;
        cmd_opcode = 2;
        cmd_arg0 = 0;
        cmd_arg1 = 0;
        cmd_valid = 1'b1;
        burst_accepts = 0;
        repeat (burst_cycles) begin
            @(posedge clk);
            if (cmd_ready)
                burst_accepts = burst_accepts + 1;
        end
        cmd_valid = 1'b0;
        rsp_ready = 1'b0;
        $display("METRIC N=%0d BURST_CYCLES=%0d BURST_ACCEPTS=%0d", N_CORES,
            burst_cycles, burst_accepts);
        $display("PULSE_MINI_ARRAY_METRICS_PASS N=%0d", N_CORES);
        $finish;
    end
endmodule
