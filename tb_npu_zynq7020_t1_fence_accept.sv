`timescale 1ns/1ps

// T1-06 独立验收：只验证 SAMPLE_FENCE 的拒绝/接受条件和样本窗口开放。
// TLAST、非整数频比和随机相位分别属于外层 packetizer 与 T2。
module tb_npu_zynq7020_t1_fence_accept;
    localparam logic [3:0] OP_MODEL_BEGIN  = 4'h1;
    localparam logic [3:0] OP_MODEL_DATA   = 4'h2;
    localparam logic [3:0] OP_MODEL_COMMIT = 4'h3;
    localparam logic [3:0] OP_MASK_BEGIN   = 4'h4;
    localparam logic [3:0] OP_MASK_DATA    = 4'h5;
    localparam logic [3:0] OP_MASK_COMMIT  = 4'h6;
    localparam logic [3:0] OP_MASK_ABORT   = 4'h7;
    localparam logic [3:0] OP_SAMPLE_FENCE = 4'hA;
    localparam logic [3:0] RSP_FENCE       = 4'hD;
    localparam logic [3:0] RSP_ERROR       = 4'hE;

    logic host_clk = 1'b0;
    logic npu_clk = 1'b0;
    logic bridge_rst = 1'b1;
    logic host_cmd_valid = 1'b0;
    logic [127:0] host_cmd_data = '0;
    wire host_cmd_ready;
    wire host_rsp_valid;
    logic host_rsp_ready = 1'b0;
    wire [127:0] host_rsp_data;
    logic host_sample_valid = 1'b0;
    logic [31:0] host_sample_data = '0;
    logic [31:0] host_sample_id = '0;
    wire host_sample_ready;
    wire host_result_valid;
    logic host_result_ready = 1'b0;
    wire [31:0] host_result_data;
    wire [31:0] host_result_sample_id;
    wire [31:0] host_result_mask_epoch;
    wire host_model_valid;
    wire host_mask_valid;
    wire host_infer_frozen;
    wire host_status_irq;
    wire host_error;

    always #5 host_clk = ~host_clk;
    always #5 npu_clk = ~npu_clk;

    npu_zynq7020_t1_wrapper dut (
        .host_clk(host_clk), .npu_clk(npu_clk), .bridge_rst(bridge_rst),
        .host_cmd_valid(host_cmd_valid), .host_cmd_ready(host_cmd_ready),
        .host_cmd_data(host_cmd_data), .host_rsp_valid(host_rsp_valid),
        .host_rsp_ready(host_rsp_ready), .host_rsp_data(host_rsp_data),
        .host_sample_valid(host_sample_valid), .host_sample_ready(host_sample_ready),
        .host_sample_data(host_sample_data), .host_sample_id(host_sample_id),
        .host_result_valid(host_result_valid), .host_result_ready(host_result_ready),
        .host_result_data(host_result_data), .host_result_sample_id(host_result_sample_id),
        .host_result_mask_epoch(host_result_mask_epoch), .host_model_valid(host_model_valid),
        .host_mask_valid(host_mask_valid), .host_infer_frozen(host_infer_frozen),
        .host_status_irq(host_status_irq), .host_error(host_error)
    );

    task automatic wait_cmd_ready;
        integer timeout;
        begin
            timeout = 0;
            while (!host_cmd_ready && timeout < 300) begin
                @(posedge host_clk);
                timeout = timeout + 1;
            end
            if (!host_cmd_ready) $fatal(1, "timeout waiting host_cmd_ready");
        end
    endtask

    task automatic send_cmd(
        input logic [3:0] opcode,
        input logic [3:0] flags,
        input logic [31:0] epoch,
        input logic [55:0] reserved,
        input logic [31:0] word
    );
        begin
            @(negedge host_clk);
            wait_cmd_ready();
            host_cmd_data = {opcode, flags, epoch, reserved, word};
            host_cmd_valid = 1'b1;
            do @(posedge host_clk); while (!host_cmd_ready);
            @(negedge host_clk);
            host_cmd_valid = 1'b0;
            host_cmd_data = '0;
        end
    endtask

    task automatic expect_response(input logic [3:0] category, input logic [31:0] id);
        logic [127:0] observed;
        integer timeout;
        begin
            host_rsp_ready = 1'b1;
            timeout = 0;
            while (!host_rsp_valid && timeout < 300) begin
                @(posedge host_clk);
                timeout = timeout + 1;
            end
            if (!host_rsp_valid) $fatal(1, "timeout waiting response");
            observed = host_rsp_data;
            if (observed[127:124] !== category)
                $fatal(1, "response category=%h expected=%h", observed[127:124], category);
            if (category == RSP_FENCE && observed[111:80] !== id)
                $fatal(1, "fence id=%h expected=%h", observed[111:80], id);
            if (category == RSP_ERROR && observed[47:0] !== 48'd0)
                $fatal(1, "error reserved bits are nonzero: %h", observed[47:0]);
            @(negedge host_clk);
            host_rsp_ready = 1'b0;
        end
    endtask

    task automatic expect_fence_response(input logic [31:0] id, input logic [31:0] epoch);
        logic [127:0] observed;
        integer timeout;
        begin
            host_rsp_ready = 1'b1;
            timeout = 0;
            while (!host_rsp_valid && timeout < 300) begin
                @(posedge host_clk);
                timeout = timeout + 1;
            end
            if (!host_rsp_valid) $fatal(1, "timeout waiting fence response");
            observed = host_rsp_data;
            if (observed[127:124] !== RSP_FENCE || observed[119:116] !== OP_SAMPLE_FENCE)
                $fatal(1, "invalid fence response header: %h", observed);
            if (observed[111:80] !== id)
                $fatal(1, "fence id=%h expected=%h", observed[111:80], id);
            if (observed[79:48] !== epoch)
                $fatal(1, "fence epoch=%h expected=%h", observed[79:48], epoch);
            if (observed[47:0] !== 48'd0)
                $fatal(1, "fence reserved bits are nonzero: %h", observed[47:0]);
            @(negedge host_clk);
            host_rsp_ready = 1'b0;
        end
    endtask

    task automatic expect_no_sample_ready(input integer cycles);
        integer i;
        begin
            for (i = 0; i < cycles; i = i + 1) begin
                @(posedge host_clk);
                if (host_sample_ready) $fatal(1, "sample_ready opened before accepted fence");
            end
        end
    endtask

    integer i;
    integer wait_cycles;
    initial begin
        // 复位后等待 Host/NPU 两域的 rst_busy 汇合。
        repeat (8) @(posedge host_clk);
        if (host_cmd_ready || host_sample_ready)
            $fatal(1, "ready leaked during reset");
        bridge_rst = 1'b0;
        repeat (8) @(posedge host_clk);
        wait_cmd_ready();

        // 准备一个最小合法模型；模型数值不属于本测试的验收范围。
        send_cmd(OP_MODEL_BEGIN, 4'h0, 32'd0, 56'd0, 32'd0);
        for (i = 0; i < 634; i = i + 1)
            send_cmd(OP_MODEL_DATA, 4'h0, 32'd0, 56'd0, 32'd0);
        send_cmd(OP_MODEL_COMMIT, 4'h0, 32'd0, 56'd0, 32'd0);
        wait_cycles = 0;
        while (!host_model_valid && wait_cycles < 40) begin
            @(posedge host_clk);
            wait_cycles = wait_cycles + 1;
        end
        if (!host_model_valid) $fatal(1, "model_valid did not assert");

        // staging 尚未闭合时，fence 必须产生一个错误且不开放窗口。
        send_cmd(OP_MASK_BEGIN, 4'h0, 32'd1, 56'd0, 32'd0);
        send_cmd(OP_MASK_DATA, 4'h0, 32'd0, 56'd0, 32'h0000_0001);
        send_cmd(OP_SAMPLE_FENCE, 4'h0, 32'd0, 56'd0, 32'hF00D_BAD);
        expect_response(RSP_ERROR, 32'd0);
        expect_no_sample_ready(6);
        send_cmd(OP_MASK_ABORT, 4'h0, 32'd0, 56'd0, 32'd0);

        // 完整发布 next epoch 后，fence 才能返回 0xD 并打开一个样本窗口。
        send_cmd(OP_MASK_BEGIN, 4'h0, 32'd1, 56'd0, 32'd0);
        for (i = 0; i < 19; i = i + 1)
            send_cmd(OP_MASK_DATA, 4'h0, 32'd0, 56'd0,
                     (i == 18) ? 32'h0000_ffff : 32'hffff_ffff);
        send_cmd(OP_MASK_COMMIT, 4'h0, 32'd1, 56'd0, 32'd0);
        expect_no_sample_ready(6);
        send_cmd(OP_SAMPLE_FENCE, 4'h0, 32'd0, 56'd0, 32'hF00D_0A00);
        expect_fence_response(32'hF00D_0A00, 32'd0);

        wait_cycles = 0;
        while (!host_sample_ready && wait_cycles < 40) begin
            @(posedge host_clk);
            wait_cycles = wait_cycles + 1;
        end
        if (!host_sample_ready) $fatal(1, "sample window did not open after accepted fence");
        if (host_mask_valid) $display("T1_FENCE_ACCEPT_INFO mask_valid already synchronized");
        $display("T1_FENCE_ACCEPT_PASS");
        $finish;
    end
endmodule
