// 单时钟 NPU+ENeuron 第一条协议垂直切片的公开接口测试台。
// 只验证 ready/valid、固定 beat 计数、模型提交和结果背压；不窥探 DUT 内部状态。
`timescale 1ns/1ps
module tb_npu_eneuron_single_clock_skeleton;
    localparam logic [3:0] OP_MODEL_BEGIN  = 4'h1;
    localparam logic [3:0] OP_MODEL_DATA   = 4'h2;
    localparam logic [3:0] OP_MODEL_COMMIT = 4'h3;
    localparam logic [3:0] RSP_OK           = 4'h0;

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
        .sample_data(sample_data), .sample_id(sample_id),
        .sample_valid(sample_valid), .sample_ready(sample_ready),
        .result_data(result_data), .result_sample_id(result_sample_id),
        .result_mask_epoch(result_mask_epoch),
        .result_valid(result_valid), .result_ready(result_ready),
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

    task automatic send_sample_beat(input int index);
        begin
            @(negedge clk);
            sample_data = {24'd0, index[7:0]};
            sample_id = 32'h0000_0042;
            sample_valid = 1'b1;
            while (!sample_ready) @(negedge clk);
            @(negedge clk);
            sample_valid = 1'b0;
            sample_data = '0;
        end
    endtask

    integer i;
    integer result_beats;
    logic [31:0] held_result;

    // 防止 ready/valid 回归在工具中无限等待，失败时给出明确阶段边界。
    initial begin
        repeat (5000) @(posedge clk);
        $fatal(1, "watchdog: protocol test did not finish");
    end

    initial begin
        repeat (3) @(negedge clk);
        rst = 1'b0;

        // 未提交模型时必须 fail-closed：样本不能握手。
        @(negedge clk);
        if (model_valid !== 1'b0) $fatal(1, "model_valid must be 0 after reset");
        if (sample_ready !== 1'b0) $fatal(1, "sample_ready must be 0 before model commit");
        sample_valid = 1'b1;
        sample_data = 32'h1234_5678;
        repeat (3) begin
            @(negedge clk);
            if (sample_ready !== 1'b0) $fatal(1, "sample accepted before model commit");
        end
        sample_valid = 1'b0;
        sample_data = '0;

        // 634-word 模型镜像：第一片只验证顺序计数和原子提交，数据本身不参与计算。
        $display("PHASE model_load");
        send_cmd(OP_MODEL_BEGIN, 32'd0);
        for (i = 0; i < 634; i = i + 1) send_cmd(OP_MODEL_DATA, i[31:0]);
        send_cmd(OP_MODEL_COMMIT, 32'd0);
        repeat (2) @(negedge clk);
        if (model_valid !== 1'b1) $fatal(1, "model_valid did not assert after commit");
        if (rsp_valid !== 1'b0) $fatal(1, "successful commands must not leave a response pending");

        // 非法命令必须握手后进入单槽错误响应；响应背压期间命令口停住且 payload 稳定。
        rsp_ready = 1'b0;
        @(negedge clk);
        cmd_payload = '0;
        cmd_payload[127:124] = 4'hf;
        cmd_valid = 1'b1;
        while (!cmd_ready) @(negedge clk);
        @(negedge clk);
        cmd_valid = 1'b0;
        if (!rsp_valid) $fatal(1, "illegal command must produce an error response");
        held_result = rsp_payload[31:0];
        repeat (2) begin
            @(negedge clk);
            if (!rsp_valid || rsp_payload[31:0] !== held_result) $fatal(1, "error response changed under backpressure");
            if (cmd_ready) $fatal(1, "command port must stall behind pending error response");
        end
        rsp_ready = 1'b1;
        @(negedge clk);
        if (rsp_valid) $fatal(1, "error response was not consumed");

        // 配置命令与样本首拍同拍时，配置优先，sample_ready 必须为 0。
        @(negedge clk);
        cmd_payload = '0;
        cmd_payload[127:124] = 4'hf;
        sample_data = 32'hcafebabe;
        sample_id = 32'h0000_0042;
        cmd_valid = 1'b1;
        sample_valid = 1'b1;
        @(negedge clk);
        if (sample_ready) $fatal(1, "config must beat sample first beat");
        cmd_valid = 1'b0;
        sample_valid = 1'b0;
        sample_data = '0;
        while (rsp_valid) @(negedge clk);

        // 固定 8 拍样本输入。
        $display("PHASE sample_load");
        for (i = 0; i < 8; i = i + 1) send_sample_beat(i);

        // 结果槽在背压时必须保持 beat 和 metadata。
        $display("PHASE result_hold");
        while (!result_valid) @(negedge clk);
        held_result = result_data;
        if (result_sample_id !== 32'h0000_0042) $fatal(1, "sample id mismatch");
        if (result_mask_epoch !== 32'd0) $fatal(1, "reset mask epoch mismatch");
        repeat (2) begin
            @(negedge clk);
            if (!result_valid || result_data !== held_result) $fatal(1, "result changed under backpressure");
        end

        result_ready = 1'b1;
        result_beats = 0;
        while (result_beats < 10) begin
            // 在 posedge 观察握手，避免最后一个 beat 清除 valid 后在 negedge 被漏计。
            @(posedge clk);
            if (result_valid && result_ready) begin
                if (result_data !== 32'd0) $fatal(1, "skeleton result must be zero placeholder");
                result_beats = result_beats + 1;
            end
        end
        @(negedge clk);
        if (!runtime_idle) $fatal(1, "runtime_idle must assert after result drain");
        $display("PASS npu single-clock skeleton protocol");
        $finish;
    end
endmodule
