// 单时钟 mask 双阶段切片测试台：验证 19-word staging、epoch 和样本边界激活。
`timescale 1ns/1ps
module tb_npu_eneuron_single_clock_mask;
    localparam logic [3:0] OP_MODEL_BEGIN  = 4'h1;
    localparam logic [3:0] OP_MODEL_DATA   = 4'h2;
    localparam logic [3:0] OP_MODEL_COMMIT = 4'h3;
    localparam logic [3:0] OP_MASK_BEGIN   = 4'h4;
    localparam logic [3:0] OP_MASK_DATA    = 4'h5;
    localparam logic [3:0] OP_MASK_COMMIT  = 4'h6;

    logic clk = 1'b0;
    always #5 clk = ~clk;
    logic rst = 1'b1;
    logic [127:0] cmd_payload = '0;
    logic cmd_valid = 1'b0;
    wire cmd_ready;
    wire [127:0] rsp_payload;
    wire rsp_valid;
    logic rsp_ready = 1'b1;
    logic [31:0] sample_data = '0;
    logic [31:0] sample_id = '0;
    logic sample_valid = 1'b0;
    wire sample_ready;
    wire [31:0] result_data;
    wire [31:0] result_sample_id;
    wire [31:0] result_mask_epoch;
    wire result_valid;
    logic result_ready = 1'b1;
    wire runtime_idle;
    wire model_valid;
    wire mask_valid;
    wire infer_frozen;
    wire [31:0] state_clear_count;

    npu_eneuron_single_clock_skeleton dut (
        .clk(clk), .rst(rst),
        .cmd_payload(cmd_payload), .cmd_valid(cmd_valid), .cmd_ready(cmd_ready),
        .rsp_payload(rsp_payload), .rsp_valid(rsp_valid), .rsp_ready(rsp_ready),
        .sample_data(sample_data), .sample_id(sample_id),
        .sample_valid(sample_valid), .sample_ready(sample_ready),
        .result_data(result_data), .result_sample_id(result_sample_id),
        .result_mask_epoch(result_mask_epoch), .result_valid(result_valid), .result_ready(result_ready),
        .runtime_idle(runtime_idle), .model_valid(model_valid), .mask_valid(mask_valid),
        .infer_frozen(infer_frozen), .state_clear_count(state_clear_count)
    );

    task automatic send_cmd(input logic [3:0] opcode, input logic [31:0] word);
        begin
            @(negedge clk);
            while (!cmd_ready) @(negedge clk);
            cmd_payload = '0;
            cmd_payload[127:124] = opcode;
            cmd_payload[31:0] = word;
            cmd_valid = 1'b1;
            @(negedge clk);
            cmd_valid = 1'b0;
            cmd_payload = '0;
        end
    endtask

    task automatic send_mask_cmd(input logic [3:0] opcode, input logic [31:0] epoch, input logic [31:0] word);
        begin
            @(negedge clk);
            while (!cmd_ready) @(negedge clk);
            cmd_payload = '0;
            cmd_payload[127:124] = opcode;
            cmd_payload[119:88] = epoch;
            cmd_payload[31:0] = word;
            cmd_valid = 1'b1;
            @(negedge clk);
            cmd_valid = 1'b0;
            cmd_payload = '0;
        end
    endtask

    task automatic send_sample_beat(input int index);
        begin
            @(negedge clk);
            sample_data = {24'd0, index[7:0]};
            sample_id = 32'h0000_0051;
            sample_valid = 1'b1;
            while (!sample_ready) @(negedge clk);
            @(negedge clk);
            sample_valid = 1'b0;
            sample_data = '0;
        end
    endtask

    integer i;
    initial begin
        repeat (3) @(negedge clk);
        rst = 1'b0;
        if (mask_valid !== 1'b0) $fatal(1, "mask_valid must be 0 after reset");

        send_cmd(OP_MODEL_BEGIN, 32'd0);
        for (i = 0; i < 634; i = i + 1) send_cmd(OP_MODEL_DATA, 32'd0);
        send_cmd(OP_MODEL_COMMIT, 32'd0);
        repeat (2) @(negedge clk);
        if (!model_valid) $fatal(1, "model commit failed");

        send_mask_cmd(OP_MASK_BEGIN, 32'd1, 32'd0);
        for (i = 0; i < 18; i = i + 1) send_mask_cmd(OP_MASK_DATA, 32'd0, (i == 0) ? 32'h0000_0001 : 32'd0);

        // word18 高 16 位保留；非法字必须零副作用，并在响应消费后同索引重试。
        rsp_ready = 1'b0;
        send_mask_cmd(OP_MASK_DATA, 32'd0, 32'hffff_0000);
        if (!rsp_valid) $fatal(1, "reserved mask bits must produce an error response");
        if (rsp_payload[127:124] !== 4'he || rsp_payload[119:116] !== OP_MASK_DATA)
            $fatal(1, "mask error response header mismatch");
        if (rsp_payload[111:80] !== 32'd18)
            $fatal(1, "invalid mask word advanced implicit index");
        repeat (2) @(negedge clk);
        if (!rsp_valid || cmd_ready) $fatal(1, "mask error response backpressure broken");
        rsp_ready = 1'b1;
        @(negedge clk);
        while (rsp_valid) @(negedge clk);
        send_mask_cmd(OP_MASK_DATA, 32'd0, 32'd0);
        send_mask_cmd(OP_MASK_COMMIT, 32'd1, 32'd0);
        repeat (2) @(negedge clk);
        if (mask_valid !== 1'b0) $fatal(1, "published mask must wait for sample boundary");

        send_sample_beat(0);
        if (mask_valid !== 1'b1) $fatal(1, "mask_valid must assert at first sample beat");
        for (i = 1; i < 8; i = i + 1) send_sample_beat(i);
        while (!result_valid) @(negedge clk);
        if (result_mask_epoch !== 32'd1) $fatal(1, "result did not latch mask epoch 1");
        repeat (10) @(posedge clk);
        @(negedge clk);
        if (!runtime_idle) $fatal(1, "runtime_idle must return after result drain");

        // 第二个样本必须重新接收完整 8 beat，并继续使用已激活 epoch。
        for (i = 0; i < 8; i = i + 1) send_sample_beat(i);
        while (!result_valid) @(negedge clk);
        if (result_mask_epoch !== 32'd1) $fatal(1, "active epoch changed on second sample");
        $display("PASS npu single-clock mask epoch slice");
        $finish;
    end

    initial begin
        repeat (5000) @(posedge clk);
        $fatal(1, "watchdog: mask test did not finish");
    end
endmodule
