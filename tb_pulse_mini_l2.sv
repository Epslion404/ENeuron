module tb_pulse_mini_l2;
    logic clk = 0;
    logic rst = 1;
    logic cmd_valid = 0;
    logic cmd_ready;
    logic [2:0] cmd_opcode;
    logic [7:0] cmd_arg0;
    logic [7:0] cmd_arg1;
    logic rsp_valid;
    logic rsp_ready = 0;
    logic [2:0] rsp_status;
    logic signed [7:0] rsp_data;
    logic spike;
    logic pending_valid;
    logic protocol_error;
    logic [1:0] mode_state;
    logic signed [3:0] weight0, weight1, weight2, weight3;
    logic signed [7:0] soma_state;
    logic [3:0] refractory_state, leak_timer_state;
    logic [15:0] pre_age_flat;
    logic [3:0] post_age_state;
    logic [7:0] positive_evidence;
    logic [7:0] negative_evidence;
    logic signed [11:0] captured_direction_flat;

    pulse_mini_l2_core dut (.*);

    always #5 clk = ~clk;

    task automatic command(input logic [2:0] opcode, input logic [7:0] arg0, input logic [7:0] arg1);
        begin
            @(negedge clk);
            while (!cmd_ready) @(negedge clk);
            cmd_opcode <= opcode;
            cmd_arg0 <= arg0;
            cmd_arg1 <= arg1;
            cmd_valid <= 1'b1;
            @(negedge clk);
            cmd_valid <= 1'b0;
            while (!rsp_valid) @(negedge clk);
            rsp_ready <= 1'b1;
            @(negedge clk);
            rsp_ready <= 1'b0;
        end
    endtask

    initial begin
        repeat (2) @(negedge clk);
        rst <= 1'b0;
        command(3'd0, 8'd1, 8'd0); // TRAIN
        command(3'd1, 8'd0, 8'd0); // CLEAR
        repeat (4) begin
            command(3'd2, 8'd1, 8'd0); // input
            command(3'd2, 8'd0, 8'd1); // teacher post
            command(3'd2, 8'd0, 8'd0);
            command(3'd2, 8'd0, 8'd0);
            command(3'd2, 8'd0, 8'd0);
        end
        $display("L2_EVIDENCE pos=%0d neg=%0d", positive_evidence[1:0], negative_evidence[1:0]);
        command(3'd3, 8'd0, 8'd0);
        $display("L2_CAPTURE dir=%0d", $signed(captured_direction_flat[2:0]));
        command(3'd4, 8'd1, 8'd0);
        $display("L2_WEIGHT weight0=%0d status=%0d", weight0, rsp_status);
        $finish;
    end
endmodule
