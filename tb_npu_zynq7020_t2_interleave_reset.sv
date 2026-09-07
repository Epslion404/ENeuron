`timescale 1ns/1ps

// T2 wrapper 交错/复位切片：两条 Host 输入流同时运行，并在命令、sample 和结果阶段注入 reset。
// 本测试使用 Icarus 等价 FIFO 模型，真实 AMD XPM/xsim 仍属 T3。
module tb_npu_zynq7020_t2_interleave_reset #(
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
    initial begin
        #NPU_PHASE;
        forever #(NPU_HALF) npu_clk = ~npu_clk;
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
            while (!host_cmd_ready && timeout < 1000) begin
                @(posedge host_clk);
                timeout = timeout + 1;
            end
            if (!host_cmd_ready) $fatal(1, "interleave timeout waiting host_cmd_ready");
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

    task automatic load_model;
        integer i;
        integer timeout;
        begin
            send_cmd(OP_MODEL_BEGIN, 4'h0, 32'd0, 56'd0, 32'd0);
            for (i = 0; i < 634; i = i + 1)
                send_cmd(OP_MODEL_DATA, 4'h0, 32'd0, 56'd0, 32'd0);
            send_cmd(OP_MODEL_COMMIT, 4'h0, 32'd0, 56'd0, 32'd0);
            timeout = 0;
            while (!host_model_valid && timeout < 100) begin
                @(posedge host_clk);
                timeout = timeout + 1;
            end
            if (!host_model_valid) $fatal(1, "interleave model_valid did not assert");
        end
    endtask

    task automatic load_mask(input logic [31:0] epoch);
        integer i;
        begin
            send_cmd(OP_MASK_BEGIN, 4'h0, epoch, 56'd0, 32'd0);
            for (i = 0; i < 19; i = i + 1)
                send_cmd(OP_MASK_DATA, 4'h0, 32'd0, 56'd0,
                         (i == 18) ? 32'h0000_ffff : 32'hffff_ffff);
            send_cmd(OP_MASK_COMMIT, 4'h0, epoch, 56'd0, 32'd0);
        end
    endtask

    task automatic expect_fence(input logic [31:0] id, input logic [31:0] epoch);
        logic [127:0] observed;
        integer timeout;
        begin
            host_rsp_ready = 1'b1;
            timeout = 0;
            while (!host_rsp_valid && timeout < 1000) begin
                @(posedge host_clk);
                timeout = timeout + 1;
            end
            if (!host_rsp_valid) $fatal(1, "interleave fence response timeout");
            observed = host_rsp_data;
            if (observed[127:124] !== RSP_FENCE || observed[111:80] !== id ||
                observed[79:48] !== epoch)
                $fatal(1, "interleave fence mismatch payload=%h", observed);
            @(negedge host_clk);
            host_rsp_ready = 1'b0;
        end
    endtask

    task automatic pulse_reset(input integer cycles);
        integer i;
        begin
            @(negedge host_clk);
            host_cmd_valid = 1'b0;
            host_sample_valid = 1'b0;
            host_rsp_ready = 1'b0;
            host_result_ready = 1'b0;
            bridge_rst = 1'b1;
            for (i = 0; i < cycles; i = i + 1) begin
                @(posedge host_clk);
                if (i >= 4 && (host_cmd_ready || host_sample_ready ||
                               host_rsp_valid || host_result_valid))
                    $fatal(1, "interleave ready/valid leaked during reset");
            end
            bridge_rst = 1'b0;
            repeat (24) @(posedge host_clk);
            if (host_rsp_valid || host_result_valid)
                $fatal(1, "interleave stale payload leaked after reset");
        end
    endtask

    integer i;
    integer timeout;
    logic [31:0] stalled_data;
    logic [31:0] stalled_sid;
    logic [31:0] stalled_epoch;
    initial begin
        // 初始复位后，先在模型装载中途复位，确认半条配置不会提交。
        repeat (20) @(posedge host_clk);
        bridge_rst = 1'b0;
        repeat (12) @(posedge host_clk);
        wait_cmd_ready();
        send_cmd(OP_MODEL_BEGIN, 4'h0, 32'd0, 56'd0, 32'd0);
        for (i = 0; i < 40; i = i + 1)
            send_cmd(OP_MODEL_DATA, 4'h0, 32'd0, 56'd0, 32'd0);
        pulse_reset(18);
        if (host_model_valid) $fatal(1, "partial model survived reset");

        // 重新装载后，在同一 Host 时间段交错发送 mask 命令和 sample beat。
        load_model();
        load_mask(32'd1);
        send_cmd(OP_SAMPLE_FENCE, 4'h0, 32'd0, 56'd0, 32'hF00D_3101);
        expect_fence(32'hF00D_3101, 32'd0);
        send_sample_beat(0, 32'hCAFE_3101);
        fork
            begin
                load_mask(32'd2);
            end
            begin
                for (i = 1; i < 8; i = i + 1)
                    send_sample_beat(i, 32'hCAFE_3101);
            end
        join
        if (host_sample_ready) $fatal(1, "sample window remained open after interleave");

        // 结果保持期间复位，必须丢弃整个未消费结果帧。
        host_result_ready = 1'b0;
        timeout = 0;
        while (!host_result_valid && timeout < 6000) begin
            @(posedge host_clk);
            timeout = timeout + 1;
        end
        if (!host_result_valid) $fatal(1, "interleave result did not arrive");
        stalled_data = host_result_data;
        stalled_sid = host_result_sample_id;
        stalled_epoch = host_result_mask_epoch;
        repeat (8) begin
            @(posedge host_clk);
            if (!host_result_valid || host_result_data !== stalled_data ||
                host_result_sample_id !== stalled_sid || host_result_mask_epoch !== stalled_epoch)
                $fatal(1, "interleave result changed under backpressure");
        end
        pulse_reset(18);

        // 第二次配置后在 sample 第 4 beat 前复位，确认半帧不会泄漏到下一次运行。
        load_model();
        load_mask(32'd1);
        send_cmd(OP_SAMPLE_FENCE, 4'h0, 32'd0, 56'd0, 32'hF00D_3102);
        expect_fence(32'hF00D_3102, 32'd0);
        for (i = 0; i < 3; i = i + 1)
            send_sample_beat(i, 32'hCAFE_3102);
        pulse_reset(18);

        $display("T2_INTERLEAVE_RESET_PASS NPU_HALF=%0d NPU_PHASE=%0d", NPU_HALF, NPU_PHASE);
        $finish;
    end
endmodule
