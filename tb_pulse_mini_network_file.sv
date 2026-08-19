`timescale 1ns/1ps
module tb_pulse_mini_network_file;
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
    integer fh, op, a0, a1, seq;
    string cmdfile;

    pulse_mini_network_4x2x2 dut (.*);
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
            $display("R %0d %0d %0d %0d %0d %0d %0d %0d",
                seq, rsp_status, rsp_data, hidden_spikes, output_spikes,
                pending_hidden_state, protocol_error, rsp_valid);
            seq = seq + 1;
            rsp_ready = 1'b1;
            @(posedge clk);
            #1 rsp_ready = 1'b0;
        end
    endtask

    initial begin
        if (!$value$plusargs("CMDFILE=%s", cmdfile)) $finish(2);
        fh = $fopen(cmdfile, "r");
        if (!fh) $finish(2);
        seq = 0;
        repeat (3) @(posedge clk);
        rst = 1'b0;
        while (!$feof(fh)) begin
            if ($fscanf(fh, "%d %d %d\n", op, a0, a1) == 3)
                issue(op, a0, a1);
        end
        $display("PULSE_MINI_NETWORK_FILE_TB_PASS commands=%0d", seq);
        $fclose(fh);
        $finish;
    end
endmodule
