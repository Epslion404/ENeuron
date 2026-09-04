// 单时钟控制切片：MASK_ABORT、STATE_CLEAR 与 FREEZE_SET 的公开行为。
`timescale 1ns/1ps
module tb_npu_eneuron_single_clock_control;
    localparam logic [3:0] OP_MODEL_BEGIN  = 4'h1;
    localparam logic [3:0] OP_MODEL_DATA   = 4'h2;
    localparam logic [3:0] OP_MODEL_COMMIT = 4'h3;
    localparam logic [3:0] OP_MASK_BEGIN   = 4'h4;
    localparam logic [3:0] OP_MASK_DATA    = 4'h5;
    localparam logic [3:0] OP_MASK_ABORT   = 4'h7;
    localparam logic [3:0] OP_STATE_CLEAR  = 4'h8;
    localparam logic [3:0] OP_FREEZE_SET   = 4'h9;

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
    logic [31:0] sample_id = 32'h71;
    logic sample_valid = 1'b0;
    wire sample_ready;
    wire [31:0] result_data;
    wire [31:0] result_sample_id;
    wire [31:0] result_mask_epoch;
    wire result_valid;
    logic result_ready = 1'b0;
    wire runtime_idle;
    wire model_valid;
    wire mask_valid;
    wire infer_frozen;
    wire [31:0] state_clear_count;

    npu_eneuron_single_clock_skeleton dut (
        .clk(clk), .rst(rst),
        .cmd_payload(cmd_payload), .cmd_valid(cmd_valid), .cmd_ready(cmd_ready),
        .rsp_payload(rsp_payload), .rsp_valid(rsp_valid), .rsp_ready(rsp_ready),
        .sample_data(sample_data), .sample_id(sample_id), .sample_valid(sample_valid), .sample_ready(sample_ready),
        .result_data(result_data), .result_sample_id(result_sample_id), .result_mask_epoch(result_mask_epoch),
        .result_valid(result_valid), .result_ready(result_ready),
        .runtime_idle(runtime_idle), .model_valid(model_valid), .mask_valid(mask_valid),
        .infer_frozen(infer_frozen), .state_clear_count(state_clear_count)
    );

    task automatic send_cmd(input logic [3:0] opcode, input logic flag, input logic [31:0] epoch, input logic [31:0] word);
        begin
            @(negedge clk);
            while (!cmd_ready) @(negedge clk);
            cmd_payload = '0;
            cmd_payload[127:124] = opcode;
            cmd_payload[120] = flag;
            cmd_payload[119:88] = epoch;
            cmd_payload[31:0] = word;
            cmd_valid = 1'b1;
            @(negedge clk);
            cmd_valid = 1'b0;
            cmd_payload = '0;
        end
    endtask

    task automatic drain_error;
        begin
            if (!rsp_valid) $fatal(1, "expected error response");
            @(negedge clk);
            while (rsp_valid) @(negedge clk);
        end
    endtask

    task automatic send_sample;
        integer beat;
        begin
            for (beat = 0; beat < 8; beat = beat + 1) begin
                @(negedge clk);
                sample_data = beat;
                sample_valid = 1'b1;
                while (!sample_ready) @(negedge clk);
                @(negedge clk);
                sample_valid = 1'b0;
            end
        end
    endtask

    integer i;
    initial begin
        repeat (3) @(negedge clk);
        rst = 1'b0;
        send_cmd(OP_MODEL_BEGIN, 1'b0, 32'd0, 32'd0);
        for (i = 0; i < 634; i = i + 1) send_cmd(OP_MODEL_DATA, 1'b0, 32'd0, i);
        send_cmd(OP_MODEL_COMMIT, 1'b0, 32'd0, 32'd0);

        // 部分 mask 可由 MASK_ABORT 原子丢弃，之后回到严格 idle。
        send_cmd(OP_MASK_BEGIN, 1'b0, 32'd1, 32'd0);
        send_cmd(OP_MASK_DATA, 1'b0, 32'd0, 32'h1234);
        send_cmd(OP_MASK_ABORT, 1'b0, 32'd0, 32'd0);
        @(negedge clk);
        if (!runtime_idle) $fatal(1, "MASK_ABORT did not return runtime to idle");

        // STATE_CLEAR 只清动态计数，不破坏已提交模型。
        send_cmd(OP_STATE_CLEAR, 1'b0, 32'd0, 32'd0);
        if (state_clear_count !== 32'd1 || !model_valid) $fatal(1, "STATE_CLEAR contract mismatch");

        // freeze 只能从 idle 切换；冻结后仍允许推理，但拒绝配置和 STATE_CLEAR。
        send_cmd(OP_FREEZE_SET, 1'b1, 32'd0, 32'd0);
        if (!infer_frozen) $fatal(1, "freeze did not assert");
        send_cmd(OP_MODEL_BEGIN, 1'b0, 32'd0, 32'd0);
        drain_error();
        send_cmd(OP_STATE_CLEAR, 1'b0, 32'd0, 32'd0);
        drain_error();
        if (state_clear_count !== 32'd1) $fatal(1, "frozen clear changed state");

        send_sample();
        while (!result_valid) @(negedge clk);
        // 结果占用期间 freeze 切换必须被 ready 层阻塞；Host 维持 valid，排空后才接受。
        @(negedge clk);
        cmd_payload = '0;
        cmd_payload[127:124] = OP_FREEZE_SET;
        cmd_payload[120] = 1'b0;
        cmd_valid = 1'b1;
        if (cmd_ready) $fatal(1, "freeze command accepted while result occupied");
        result_ready = 1'b1;
        repeat (10) @(posedge clk);
        @(negedge clk);
        while (!cmd_ready) @(negedge clk);
        @(negedge clk);
        cmd_valid = 1'b0;
        if (infer_frozen) $fatal(1, "freeze did not clear after runtime became idle");

        $display("PASS npu single-clock control slice");
        $finish;
    end

    initial begin
        repeat (6000) @(posedge clk);
        $fatal(1, "watchdog: control test did not finish");
    end
endmodule
