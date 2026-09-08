`timescale 1ns/1ps
module tb_pulse_original;
    logic clk = 1'b0;
    logic rst = 1'b1;
    logic tick_valid = 1'b0;
    logic [3:0] input_spikes = 4'b0;
    logic [3:0] learn_pulse = 4'b0;
    logic spike;
    logic [3:0] dendrite_pulses;
    logic [11:0] learn_count_flat;
    logic [11:0] divider_progress_flat;
    logic signed [7:0] soma_state;
    logic [3:0] sleep_count;
    logic ready;

    pulse_original_core #(
        .N_INPUTS(4), .LEARN_BITS(3), .DIV_BITS(3), .SOMA_BITS(8),
        .SLEEP_BITS(4), .THRESHOLD(2), .SLEEP_LENGTH(2)
    ) dut (
        .clk, .rst, .tick_valid, .input_spikes, .learn_pulse,
        .spike, .dendrite_pulses, .learn_count_flat,
        .divider_progress_flat, .soma_state, .sleep_count, .ready
    );

    always #5 clk = ~clk;

    task automatic tick(input logic [3:0] inputs, input logic [3:0] learns);
        begin
            @(negedge clk);
            tick_valid = 1'b1;
            input_spikes = inputs;
            learn_pulse = learns;
            @(posedge clk);
            #1;
            $display("TICK in=%b learn=%b dend=%b spike=%b learn0=%0d prog0=%0d soma=%0d sleep=%0d",
                inputs, learns, dendrite_pulses, spike,
                learn_count_flat[2:0], divider_progress_flat[2:0], soma_state, sleep_count);
            tick_valid = 1'b0;
            input_spikes = 4'b0;
            learn_pulse = 4'b0;
        end
    endtask

    initial begin
        repeat (2) @(posedge clk);
        rst = 1'b0;
        tick(4'b0000, 4'b0001);
        tick(4'b0000, 4'b0001);
        tick(4'b0000, 4'b0001);
        tick(4'b0001, 4'b0000);
        dut.learn_count[0] = 3'b111;
        tick(4'b0001, 4'b0000);
        tick(4'b0011, 4'b0000);
        tick(4'b1111, 4'b0000);
        tick(4'b0000, 4'b0000);
        tick(4'b0000, 4'b0000);
        $display("PULSE_ORIGINAL_TB_PASS");
        $finish;
    end
endmodule
