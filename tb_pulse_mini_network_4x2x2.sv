`timescale 1ns/1ps
module tb_pulse_mini_network_4x2x2;
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
    logic [1:0] hidden_spikes;
    logic [1:0] output_spikes;
    logic [1:0] pending_hidden_state;
    logic protocol_error;

    pulse_mini_network_4x2x2 dut (.*);
    always #5 clk = ~clk;

    task automatic issue(input logic [2:0] op, input logic [7:0] a0, input logic [7:0] a1);
        begin
            @(negedge clk);
            while (!cmd_ready) @(negedge clk);
            cmd_opcode = op;
            cmd_arg0 = a0;
            cmd_arg1 = a1;
            cmd_valid = 1'b1;
            @(posedge clk);
            #1 cmd_valid = 1'b0;
            @(negedge clk);
            while (!rsp_valid) @(negedge clk);
            $display("R op=%0d status=%0d data=%0d hidden=%b output=%b pending=%b error=%b",
                op, rsp_status, rsp_data, hidden_spikes, output_spikes,
                pending_hidden_state, protocol_error);
            rsp_ready = 1'b1;
            @(posedge clk);
            #1 rsp_ready = 1'b0;
        end
    endtask

    initial begin
        repeat (3) @(posedge clk);
        rst = 1'b0;
        issue(3'd5, 8'h00, 8'd7); // hidden0 synapse0 = +7
        issue(3'd5, 8'h80, 8'd7); // output0 synapse0 = +7
        issue(3'd0, 8'd2, 8'd0);  // INFER
        issue(3'd1, 8'd0, 8'd0);
        issue(3'd2, 8'b0001, 8'b0);
        if (hidden_spikes !== 2'b01 || output_spikes !== 2'b00)
            $fatal(1, "tick 0 must expose hidden spike and no output spike");
        issue(3'd2, 8'b0000, 8'b0);
        if (output_spikes !== 2'b01 || pending_hidden_state !== 2'b00)
            $fatal(1, "tick 1 must consume prior hidden spike at output layer");
        $display("PULSE_MINI_NETWORK_TB_PASS one_tick_route=1");
        $finish;
    end
endmodule
