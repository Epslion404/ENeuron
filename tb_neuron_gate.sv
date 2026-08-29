// NeuronGate V1 最小定向测试台。
//
// 该测试台只验证复位、训练 tick、image_end 和 epoch_end 的可见状态更新。
// 更完整的随机/形式验证应沿用 ENeuron 现有 pulse_mini_cosim.py 的模型，
// 用 iverilog + vvp 与 neuron_gate_reference.py 逐拍对拍。

`timescale 1ns/1ps

module tb_neuron_gate;
    logic        clk = 0;
    logic        rst = 1;
    logic        train_mode = 1;
    logic        tick_valid = 0;
    logic [3:0]  pre_mask = 4'b0000;
    logic        post_event = 0;
    logic        feedback_valid = 0;
    logic        feedback_correct = 0;
    logic        image_end = 0;
    logic        epoch_end = 0;

    logic [3:0]  keep_mask;
    logic [3:0]  candidate_mask;
    logic        candidate_valid;
    logic [31:0] score_flat;
    logic [15:0] cooldown_flat;
    logic [2:0]  keep_count;

    neuron_gate_core dut (
        .clk(clk),
        .rst(rst),
        .train_mode(train_mode),
        .tick_valid(tick_valid),
        .pre_mask(pre_mask),
        .post_event(post_event),
        .feedback_valid(feedback_valid),
        .feedback_correct(feedback_correct),
        .image_end(image_end),
        .epoch_end(epoch_end),
        .keep_mask(keep_mask),
        .candidate_mask(candidate_mask),
        .candidate_valid(candidate_valid),
        .score_flat(score_flat),
        .cooldown_flat(cooldown_flat),
        .keep_count(keep_count)
    );

    always #5 clk = ~clk;

    initial begin
        repeat (2) @(posedge clk);
        @(negedge clk);
        rst = 1'b0;
        @(posedge clk);

        for (int t = 0; t < 8; t = t + 1) begin
            @(negedge clk);
            tick_valid = 1'b1;
            pre_mask = 4'b0001;
            @(posedge clk);
            @(negedge clk);
            tick_valid = 1'b0;
            pre_mask = 4'b0000;
            @(posedge clk);
        end

        @(negedge clk);
        image_end = 1'b1;
        @(posedge clk);
        @(negedge clk);
        image_end = 1'b0;
        @(posedge clk);

        @(negedge clk);
        epoch_end = 1'b1;
        @(posedge clk);
        @(negedge clk);
        epoch_end = 1'b0;
        @(posedge clk);

        $display("GATE_TB keep=%b candidate=%b scores=%08x cooldown=%04x count=%0d",
                 keep_mask, candidate_mask, score_flat, cooldown_flat, keep_count);
        if (keep_mask !== 4'b0011 || score_flat[7:0] !== 8'd136 || score_flat[15:8] !== 8'd127) begin
            $display("GATE_TB_FAIL");
            $fatal(1, "unexpected gate state");
        end
        $display("GATE_TB_PASS");
        $finish;
    end
endmodule
