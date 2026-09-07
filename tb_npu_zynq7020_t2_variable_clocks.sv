`timescale 1ns/1ps

// T2 首个协同切片：Host=100 MHz，NPU 使用参数化非整数频比和相位偏移。
// 本测试只证明跨 FIFO 的事务完整性，不替代全矩阵随机 CDC 签核。
module tb_npu_zynq7020_t2_variable_clocks #(
    parameter integer NPU_HALF = 7,
    parameter integer NPU_PHASE = 2
);
    localparam logic [3:0] OP_MODEL_BEGIN  = 4'h1;
    localparam logic [3:0] OP_MODEL_DATA   = 4'h2;
    localparam logic [3:0] OP_MODEL_COMMIT = 4'h3;
    localparam logic [3:0] OP_MASK_BEGIN   = 4'h4;
    localparam logic [3:0] OP_MASK_DATA    = 4'h5;
    localparam logic [3:0] OP_MASK_COMMIT  = 4'h6;
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

    initial begin
        forever #5 host_clk = ~host_clk;
    end
    initial begin
        #NPU_PHASE;
        forever #NPU_HALF npu_clk = ~npu_clk;
    end

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
            while (!host_cmd_ready && timeout < 600) begin
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

    task automatic expect_stable_error;
        logic [127:0] observed;
        integer timeout;
        integer i;
        begin
            host_rsp_ready = 1'b0;
            timeout = 0;
            while (!host_rsp_valid && timeout < 600) begin
                @(posedge host_clk);
                timeout = timeout + 1;
            end
            if (!host_rsp_valid) $fatal(1, "timeout waiting CDC error response");
            observed = host_rsp_data;
            if (observed[127:124] !== RSP_ERROR)
                $fatal(1, "unexpected CDC error category=%h", observed[127:124]);
            for (i = 0; i < 10; i = i + 1) begin
                @(posedge host_clk);
                if (!host_rsp_valid || host_rsp_data !== observed)
                    $fatal(1, "CDC error response changed under backpressure");
            end
            @(negedge host_clk);
            host_rsp_ready = 1'b1;
            @(posedge host_clk);
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
            while (!host_rsp_valid && timeout < 600) begin
                @(posedge host_clk);
                timeout = timeout + 1;
            end
            if (!host_rsp_valid) $fatal(1, "timeout waiting CDC fence response");
            observed = host_rsp_data;
            if (observed[127:124] !== RSP_FENCE || observed[119:116] !== OP_SAMPLE_FENCE)
                $fatal(1, "invalid CDC fence header=%h", observed);
            if (observed[111:80] !== id || observed[79:48] !== epoch)
                $fatal(1, "CDC fence fields id=%h epoch=%h", observed[111:80], observed[79:48]);
            if (observed[47:0] !== 48'd0)
                $fatal(1, "CDC fence reserved bits nonzero=%h", observed[47:0]);
            @(negedge host_clk);
            host_rsp_ready = 1'b0;
        end
    endtask

    task automatic send_sample_beat(input integer beat, input logic [31:0] sid);
        begin
            @(negedge host_clk);
            host_sample_data = {24'd0, beat[7:0]};
            host_sample_id = sid;
            host_sample_valid = 1'b1;
            do @(posedge host_clk); while (!host_sample_ready);
            @(negedge host_clk);
            host_sample_valid = 1'b0;
        end
    endtask

    integer i;
    integer wait_cycles;
    initial begin
        // 复位覆盖多个 Host/NPU 边沿，并确认 ready 不提前泄漏。
        repeat (24) @(posedge host_clk);
        if (host_cmd_ready || host_sample_ready)
            $fatal(1, "T2 ready leaked during reset");
        bridge_rst = 1'b0;
        repeat (10) @(posedge host_clk);
        wait_cmd_ready();

        // 先走一条跨域错误响应并施加 Host 侧背压。
        send_cmd(4'hF, 4'h0, 32'd0, 56'd0, 32'd0);
        expect_stable_error();

        // 模型装载跨越多个非整数时钟周期，检查命令 FIFO 顺序和 exactly-once。
        send_cmd(OP_MODEL_BEGIN, 4'h0, 32'd0, 56'd0, 32'd0);
        for (i = 0; i < 634; i = i + 1)
            send_cmd(OP_MODEL_DATA, 4'h0, 32'd0, 56'd0, 32'd0);
        send_cmd(OP_MODEL_COMMIT, 4'h0, 32'd0, 56'd0, 32'd0);
        wait_cycles = 0;
        while (!host_model_valid && wait_cycles < 100) begin
            @(posedge host_clk);
            wait_cycles = wait_cycles + 1;
        end
        if (!host_model_valid) $fatal(1, "T2 model_valid did not assert");

        // 发布 mask，fence 前持续确认样本 FIFO 没有被预填。
        send_cmd(OP_MASK_BEGIN, 4'h0, 32'd1, 56'd0, 32'd0);
        for (i = 0; i < 19; i = i + 1)
            send_cmd(OP_MASK_DATA, 4'h0, 32'd0, 56'd0,
                     (i == 18) ? 32'h0000_ffff : 32'hffff_ffff);
        send_cmd(OP_MASK_COMMIT, 4'h0, 32'd1, 56'd0, 32'd0);
        for (i = 0; i < 12; i = i + 1) begin
            @(posedge host_clk);
            if (host_sample_ready) $fatal(1, "T2 sample_ready leaked before fence");
        end
        send_cmd(OP_SAMPLE_FENCE, 4'h0, 32'd0, 56'd0, 32'hF00D_0201);
        expect_fence_response(32'hF00D_0201, 32'd0);

        // 一个完整样本跨域传输；结果先背压，再按 10 beat 排空。
        for (i = 0; i < 8; i = i + 1)
            send_sample_beat(i, 32'hCAFE_0001);
        host_result_ready = 1'b0;
        wait_cycles = 0;
        // 核心固定计算最坏约 1900 个 NPU 周期；慢时钟比下不能用 600 个 Host 周期误报超时。
        while (!host_result_valid && wait_cycles < 5000) begin
            @(posedge host_clk);
            wait_cycles = wait_cycles + 1;
        end
        if (!host_result_valid) $fatal(1, "T2 result did not arrive");
        begin : result_stall
            logic [31:0] stalled_data;
            logic [31:0] stalled_sid;
            logic [31:0] stalled_epoch;
            stalled_data = host_result_data;
            stalled_sid = host_result_sample_id;
            stalled_epoch = host_result_mask_epoch;
            repeat (9) begin
                @(posedge host_clk);
                if (!host_result_valid || host_result_data !== stalled_data ||
                    host_result_sample_id !== stalled_sid || host_result_mask_epoch !== stalled_epoch)
                    $fatal(1, "T2 result changed under CDC backpressure");
            end
        end
        @(negedge host_clk);
        host_result_ready = 1'b1;
        for (i = 0; i < 10; i = i + 1) begin
            while (!host_result_valid) @(posedge host_clk);
            if (host_result_sample_id !== 32'hCAFE_0001 || host_result_mask_epoch !== 32'd1)
                $fatal(1, "T2 result sideband mismatch sid=%h epoch=%h",
                       host_result_sample_id, host_result_mask_epoch);
            @(posedge host_clk);
        end

        // 一个 fence 只授权一个样本窗口；结果排空后不得自动接受第二个样本。
        repeat (12) begin
            @(posedge host_clk);
            if (host_sample_ready) $fatal(1, "T2 sample window reopened without fence");
        end

        // 复位重入跨越两个时钟域，旧结果/响应不得泄漏。
        bridge_rst = 1'b1;
        repeat (12) @(posedge host_clk);
        if (host_cmd_ready || host_sample_ready || host_rsp_valid || host_result_valid)
            $fatal(1, "T2 ready/valid leaked during reset re-entry");
        bridge_rst = 1'b0;
        repeat (12) @(posedge host_clk);
        if (host_rsp_valid || host_result_valid)
            $fatal(1, "T2 stale payload leaked after reset re-entry");

        $display("T2_VARIABLE_CLOCKS_PASS NPU_HALF=%0d NPU_PHASE=%0d", NPU_HALF, NPU_PHASE);
        $finish;
    end
endmodule
