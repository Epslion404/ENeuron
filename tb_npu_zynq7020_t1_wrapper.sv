`timescale 1ns/1ps

// P15 T1 协议切片。当前覆盖复位、非法字段、模型装载、fence、
// 单样本窗口和结果背压；尚未声称 T1-01..T1-12 全部通过。
// 仅使用同频 100 MHz；非整数频比和随机相位属于 T2。
module tb_npu_zynq7020_t1_wrapper;
    localparam logic [3:0] OP_MODEL_BEGIN  = 4'h1;
    localparam logic [3:0] OP_MODEL_DATA   = 4'h2;
    localparam logic [3:0] OP_MODEL_COMMIT = 4'h3;
    localparam logic [3:0] OP_MASK_BEGIN   = 4'h4;
    localparam logic [3:0] OP_MASK_DATA    = 4'h5;
    localparam logic [3:0] OP_MASK_COMMIT  = 4'h6;
    localparam logic [3:0] OP_MASK_ABORT   = 4'h7;
    localparam logic [3:0] OP_STATE_CLEAR  = 4'h8;
    localparam logic [3:0] OP_FREEZE_SET   = 4'h9;
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

    // 待接入生产 DUT。端口表和位宽必须与文档保持一致。
    npu_zynq7020_t1_wrapper dut (
        .host_clk(host_clk), .npu_clk(npu_clk), .bridge_rst(bridge_rst),
        .host_cmd_valid(host_cmd_valid), .host_cmd_ready(host_cmd_ready),
        .host_cmd_data(host_cmd_data),
        .host_rsp_valid(host_rsp_valid), .host_rsp_ready(host_rsp_ready),
        .host_rsp_data(host_rsp_data),
        .host_sample_valid(host_sample_valid), .host_sample_ready(host_sample_ready),
        .host_sample_data(host_sample_data), .host_sample_id(host_sample_id),
        .host_result_valid(host_result_valid), .host_result_ready(host_result_ready),
        .host_result_data(host_result_data), .host_result_sample_id(host_result_sample_id),
        .host_result_mask_epoch(host_result_mask_epoch),
        .host_model_valid(host_model_valid), .host_mask_valid(host_mask_valid),
        .host_infer_frozen(host_infer_frozen), .host_status_irq(host_status_irq), .host_error(host_error)
    );

    task automatic wait_host_ready;
        integer timeout;
        begin
            timeout = 0;
            while (!host_cmd_ready && timeout < 200) begin @(posedge host_clk); timeout = timeout + 1; end
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
            wait_host_ready();
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

    task automatic expect_response(input logic [3:0] category, input logic [31:0] id);
        logic [127:0] observed;
        integer timeout;
        begin
            host_rsp_ready = 1'b1;
            timeout = 0;
            while (!host_rsp_valid && timeout < 200) begin @(posedge host_clk); timeout = timeout + 1; end
            if (!host_rsp_valid) $fatal(1, "timeout waiting response");
            observed = host_rsp_data;
            if (observed[127:124] !== category) $fatal(1, "response category=%h expected=%h", observed[127:124], category);
            if (category == RSP_FENCE && observed[111:80] !== id)
                $fatal(1, "fence id=%h expected=%h", observed[111:80], id);
            if (category == RSP_ERROR && observed[47:0] !== 48'd0)
                $fatal(1, "error reserved bits are nonzero: %h", observed[47:0]);
            // 当前上升沿已经完成响应握手；在下降沿撤销 ready，
            // 避免未来背靠背响应在下一上升沿被这个 task 额外消费。
            @(negedge host_clk);
            host_rsp_ready = 1'b0;
        end
    endtask

    task automatic expect_stalled_error_response;
        logic [127:0] observed;
        integer stall_cycle;
        begin
            host_rsp_ready = 1'b0;
            while (!host_rsp_valid) @(posedge host_clk);
            observed = host_rsp_data;
            if (observed[127:124] !== RSP_ERROR)
                $fatal(1, "stalled response category=%h", observed[127:124]);
            if (observed[47:0] !== 48'd0)
                $fatal(1, "stalled error reserved bits are nonzero: %h", observed[47:0]);
            for (stall_cycle = 0; stall_cycle < 5; stall_cycle = stall_cycle + 1) begin
                @(posedge host_clk);
                if (!host_rsp_valid || host_rsp_data !== observed)
                    $fatal(1, "response changed under backpressure");
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
            while (!host_rsp_valid && timeout < 200) begin @(posedge host_clk); timeout = timeout + 1; end
            if (!host_rsp_valid) $fatal(1, "timeout waiting fence response");
            observed = host_rsp_data;
            if (observed[127:124] !== RSP_FENCE) $fatal(1, "fence response category=%h", observed[127:124]);
            if (observed[111:80] !== id) $fatal(1, "fence id=%h expected=%h", observed[111:80], id);
            if (observed[79:48] !== epoch) $fatal(1, "fence epoch=%h expected=%h", observed[79:48], epoch);
            @(negedge host_clk);
            host_rsp_ready = 1'b0;
        end
    endtask

    task automatic expect_no_sample_ready(input integer cycles);
        integer i;
        begin
            for (i = 0; i < cycles; i = i + 1) begin
                @(posedge host_clk);
                if (host_sample_ready) $fatal(1, "sample_ready leaked before fence");
            end
        end
    endtask

    integer i;
    integer clear_wait_cycles;
    logic [31:0] clear_count_before;
    initial begin
        // T1-01：复位期间禁止新握手，释放后等待两域稳定。
        repeat (8) @(posedge host_clk);
        if (host_cmd_ready || host_sample_ready) $fatal(1, "ready leaked during reset");
        bridge_rst = 1'b0;
        repeat (8) @(posedge host_clk);
        wait_host_ready();

        // T1-02：合法控制命令各只消费一次；冻结期间配置命令必须被拒绝。
        clear_count_before = dut.core.state_clear_count;
        send_cmd(OP_STATE_CLEAR, 4'h0, 32'd0, 56'd0, 32'd0);
        clear_wait_cycles = 0;
        while (dut.core.state_clear_count === clear_count_before && clear_wait_cycles < 100) begin
            @(posedge npu_clk);
            clear_wait_cycles = clear_wait_cycles + 1;
        end
        if (dut.core.state_clear_count !== clear_count_before + 32'd1)
            $fatal(1, "STATE_CLEAR count mismatch: before=%0d after=%0d",
                   clear_count_before, dut.core.state_clear_count);
        send_cmd(OP_FREEZE_SET, 4'h1, 32'd0, 56'd0, 32'd0);
        clear_wait_cycles = 0;
        while (!host_infer_frozen && clear_wait_cycles < 100) begin
            @(posedge host_clk);
            clear_wait_cycles = clear_wait_cycles + 1;
        end
        if (!host_infer_frozen) $fatal(1, "FREEZE_SET did not assert");
        send_cmd(OP_MODEL_BEGIN, 4'h0, 32'd0, 56'd0, 32'd0);
        expect_response(RSP_ERROR, 32'd0);
        send_cmd(OP_FREEZE_SET, 4'h0, 32'd0, 56'd0, 32'd0);
        clear_wait_cycles = 0;
        while (host_infer_frozen && clear_wait_cycles < 100) begin
            @(posedge host_clk);
            clear_wait_cycles = clear_wait_cycles + 1;
        end
        if (host_infer_frozen) $fatal(1, "FREEZE_SET did not release");

        // T1-03：保留位和未知 opcode 必须握手后产生一个错误，无副作用。
        send_cmd(4'hF, 4'h0, 32'd0, 56'd0, 32'd0);
        // T1-04：响应未被消费时 valid/payload 必须保持稳定。
        expect_stalled_error_response();
        // 非法 fence 必须只产生错误响应，不能同时打开样本窗口或产生 0xD。
        send_cmd(OP_SAMPLE_FENCE, 4'h1, 32'd0, 56'd0, 32'h0000_00F1);
        expect_response(RSP_ERROR, 32'd0);
        expect_no_sample_ready(4);
        send_cmd(OP_MODEL_BEGIN, 4'h1, 32'd0, 56'd0, 32'd0);
        expect_response(RSP_ERROR, 32'd0);
        send_cmd(OP_MODEL_BEGIN, 4'h0, 32'd0, 56'd1, 32'd0);
        expect_response(RSP_ERROR, 32'd0);

        // 合法最小模型镜像；数值内容由核心单时钟回归负责，T1 只验证传输。
        send_cmd(OP_MODEL_BEGIN, 4'h0, 32'd0, 56'd0, 32'd0);
        for (i = 0; i < 634; i = i + 1)
            send_cmd(OP_MODEL_DATA, 4'h0, 32'd0, 56'd0, 32'd0);
        send_cmd(OP_MODEL_COMMIT, 4'h0, 32'd0, 56'd0, 32'd0);
        begin : model_sync_wait
            integer sync_cycles;
            sync_cycles = 0;
        while (!host_model_valid && sync_cycles < 16) begin
                @(posedge host_clk);
                sync_cycles = sync_cycles + 1;
        end
            if (!host_model_valid) $fatal(1, "model_valid did not assert after commit");

        // T1-06：mask staging 未闭合时 fence 必须拒绝且不得开放样本窗口。
        send_cmd(OP_MASK_BEGIN, 4'h0, 32'd1, 56'd0, 32'd0);
        send_cmd(OP_MASK_DATA, 4'h0, 32'd0, 56'd0, 32'h0000_0001);
        send_cmd(OP_SAMPLE_FENCE, 4'h0, 32'd0, 56'd0, 32'h0000_00F2);
        expect_response(RSP_ERROR, 32'd0);
        expect_no_sample_ready(4);
        send_cmd(OP_MASK_ABORT, 4'h0, 32'd0, 56'd0, 32'd0);

        // 发布 epoch=1 mask，首个样本激活后，后续 fence 必须回显 active epoch=1。
        send_cmd(OP_MASK_BEGIN, 4'h0, 32'd1, 56'd0, 32'd0);
        for (i = 0; i < 19; i = i + 1)
            send_cmd(OP_MASK_DATA, 4'h0, 32'd0, 56'd0,
                     (i == 18) ? 32'h0000_ffff : 32'hffff_ffff);
        send_cmd(OP_MASK_COMMIT, 4'h0, 32'd1, 56'd0, 32'd0);
        end

        // T1-05：fence 前禁止样本握手，不能预填 sample FIFO。
        expect_no_sample_ready(8);
        send_cmd(OP_SAMPLE_FENCE, 4'h0, 32'd0, 56'd0, 32'h0000_00A5);
        expect_fence_response(32'h0000_00A5, 32'd0);

        // T1-07/T1-10：首 beat 锁存 epoch=1；样本进行中发布 epoch=2，
        // 当前结果仍必须回显 epoch=1，不能被后续 mask 污染。
        send_sample_beat(0, 32'h1234_5678);
        send_cmd(OP_MASK_BEGIN, 4'h0, 32'd2, 56'd0, 32'd0);
        for (i = 0; i < 19; i = i + 1)
            send_cmd(OP_MASK_DATA, 4'h0, 32'd0, 56'd0,
                     (i == 18) ? 32'h0000_ffff : 32'hffff_ffff);
        send_cmd(OP_MASK_COMMIT, 4'h0, 32'd2, 56'd0, 32'd0);
        for (i = 1; i < 8; i = i + 1) send_sample_beat(i, 32'h1234_5678);
        @(posedge host_clk);
        if (host_sample_ready) $fatal(1, "sample window remained open after 8 beats");

        // T1-08：结果背压期间所有结果字段必须稳定，随后恰好消费 10 beat。
        host_result_ready = 1'b0;
        wait (host_result_valid);
        begin : result_stall_check
            logic [31:0] stalled_data;
            logic [31:0] stalled_sample_id;
            logic [31:0] stalled_epoch;
            integer stall_cycle;
            stalled_data = host_result_data;
            stalled_sample_id = host_result_sample_id;
            stalled_epoch = host_result_mask_epoch;
            for (stall_cycle = 0; stall_cycle < 5; stall_cycle = stall_cycle + 1) begin
                @(posedge host_clk);
                if (!host_result_valid || host_result_data !== stalled_data ||
                    host_result_sample_id !== stalled_sample_id ||
                    host_result_mask_epoch !== stalled_epoch)
                    $fatal(1, "result payload changed while stalled");
            end
        end
        @(negedge host_clk);
        host_result_ready = 1'b1;
        for (i = 0; i < 10; i = i + 1) begin
            while (!host_result_valid) @(posedge host_clk);
            if (host_result_sample_id !== 32'h1234_5678)
                $fatal(1, "result sample id changed");
            if (host_result_mask_epoch !== 32'd1)
                $fatal(1, "result mask epoch changed: %h", host_result_mask_epoch);
            @(posedge host_clk);
        end

        send_cmd(OP_SAMPLE_FENCE, 4'h0, 32'd0, 56'd0, 32'h0000_00A6);
        expect_fence_response(32'h0000_00A6, 32'd1);

        // 下一样本首 beat 才激活 epoch=2；验证新结果使用新 epoch。
        for (i = 0; i < 8; i = i + 1) send_sample_beat(i, 32'h8765_4321);
        host_result_ready = 1'b1;
        for (i = 0; i < 10; i = i + 1) begin
            while (!host_result_valid) @(posedge host_clk);
            if (host_result_sample_id !== 32'h8765_4321)
                $fatal(1, "second result sample id changed");
            if (host_result_mask_epoch !== 32'd2)
                $fatal(1, "second result mask epoch changed: %h", host_result_mask_epoch);
            @(posedge host_clk);
        end

        // T1-11：复位重入后不得泄漏旧响应或旧结果。
        bridge_rst = 1'b1;
        repeat (8) @(posedge host_clk);
        if (host_cmd_ready || host_sample_ready || host_rsp_valid || host_result_valid)
            $fatal(1, "ready/valid leaked during reset re-entry");
        bridge_rst = 1'b0;
        repeat (8) @(posedge host_clk);
        if (host_rsp_valid || host_result_valid)
            $fatal(1, "stale payload leaked after reset re-entry");

        $display("T1_PROTOCOL_SKELETON_PASS");
        $finish;
    end
endmodule
