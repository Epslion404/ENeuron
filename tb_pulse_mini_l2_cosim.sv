`timescale 1ns/1ps
module tb_pulse_mini_l2_cosim;
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
    logic spike;
    logic pending_valid;
    logic protocol_error;
    logic [1:0] mode_state;
    logic signed [3:0] weight0, weight1, weight2, weight3;
    logic signed [7:0] soma_state;
    logic [3:0] refractory_state;
    logic [3:0] leak_timer_state;
    logic [15:0] pre_age_flat;
    logic [3:0] post_age_state;
    logic [7:0] positive_evidence;
    logic [7:0] negative_evidence;
    logic signed [11:0] captured_direction_flat;
    integer fh;
    integer op;
    integer a0;
    integer a1;
    integer seq;
    string cmdfile;

    pulse_mini_l2_core dut (.*);
    always #5 clk = ~clk;

    task automatic issue(input integer in_op, input integer in_a0, input integer in_a1);
        begin
            @(negedge clk);
            while (!cmd_ready) @(negedge clk);
            cmd_opcode = in_op[2:0];
            cmd_arg0 = in_a0[7:0];
            cmd_arg1 = in_a1[7:0];
            cmd_valid = 1'b1;
            @(posedge clk);
            #1 cmd_valid = 1'b0;
            @(negedge clk);
            while (!rsp_valid) @(negedge clk);
            $display("R %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d",
                seq, rsp_status, rsp_data, spike, mode_state, pending_valid,
                protocol_error, weight0, weight1, weight2, weight3, soma_state,
                refractory_state, leak_timer_state, pre_age_flat, post_age_state,
                positive_evidence, negative_evidence, captured_direction_flat, rsp_valid);
            seq = seq + 1;
            rsp_ready = 1'b1;
            @(posedge clk);
            #1 rsp_ready = 1'b0;
        end
    endtask

    initial begin
        if (!$value$plusargs("CMDFILE=%s", cmdfile)) begin
            $display("missing +CMDFILE");
            $finish(2);
        end
        fh = $fopen(cmdfile, "r");
        if (!fh) begin
            $display("cannot open command file");
            $finish(2);
        end
        seq = 0;
        repeat (3) @(posedge clk);
        rst = 1'b0;
        while (!$feof(fh)) begin
            if ($fscanf(fh, "%d %d %d\n", op, a0, a1) == 3)
                issue(op, a0, a1);
        end
        $display("PULSE_MINI_L2_TB_PASS commands=%0d", seq);
        $fclose(fh);
        $finish;
    end
endmodule
