`timescale 1ns/1ps

// Vivado 2024.1 实际 XPM FIFO 的双时钟 transport/reset 验收。
module tb_vivado_xpm_wrapper;
    localparam logic [127:0] CMD_BASE =
        128'h1000_0000_0000_0000_0000_0000_0000_0000;
    localparam logic [127:0] RSP_BASE =
        128'h9000_0000_0000_0000_0000_0000_0000_0000;

    logic host_clk = 1'b0;
    logic tile_clk = 1'b0;
    logic bridge_rst = 1'b1;

    logic host_cmd_valid = 1'b0;
    wire host_cmd_ready;
    logic [127:0] host_cmd_data = '0;
    wire host_rsp_valid;
    logic host_rsp_ready = 1'b0;
    wire [127:0] host_rsp_data;
    wire status_irq;

    wire tile_cmd_valid;
    logic tile_cmd_ready = 1'b0;
    wire [127:0] tile_cmd_data;
    logic tile_rsp_valid = 1'b0;
    wire tile_rsp_ready;
    logic [127:0] tile_rsp_data = '0;

    wire host_rst;
    wire tile_rst;
    wire tile_domain_up;
    wire cmd_wr_rst_busy;
    wire cmd_rd_rst_busy;
    wire rsp_wr_rst_busy;
    wire rsp_rd_rst_busy;

    logic test_passed = 1'b0;
    logic [127:0] stalled_tile_cmd;
    logic [127:0] stalled_host_rsp;
    logic tile_cmd_was_stalled = 1'b0;
    logic host_rsp_was_stalled = 1'b0;
    integer command_fill_count = 0;
    integer response_fill_count = 0;

    always #10 host_clk = ~host_clk;
    always #7 tile_clk = ~tile_clk;

    digital_snn_host_bridge dut (
        .host_clk(host_clk),
        .tile_clk(tile_clk),
        .bridge_rst(bridge_rst),
        .host_cmd_valid(host_cmd_valid),
        .host_cmd_ready(host_cmd_ready),
        .host_cmd_data(host_cmd_data),
        .host_rsp_valid(host_rsp_valid),
        .host_rsp_ready(host_rsp_ready),
        .host_rsp_data(host_rsp_data),
        .status_irq(status_irq),
        .tile_cmd_valid(tile_cmd_valid),
        .tile_cmd_ready(tile_cmd_ready),
        .tile_cmd_data(tile_cmd_data),
        .tile_rsp_valid(tile_rsp_valid),
        .tile_rsp_ready(tile_rsp_ready),
        .tile_rsp_data(tile_rsp_data),
        .host_rst(host_rst),
        .tile_rst(tile_rst),
        .tile_domain_up(tile_domain_up),
        .cmd_wr_rst_busy(cmd_wr_rst_busy),
        .cmd_rd_rst_busy(cmd_rd_rst_busy),
        .rsp_wr_rst_busy(rsp_wr_rst_busy),
        .rsp_rd_rst_busy(rsp_rd_rst_busy)
    );

    // 所有 reset-busy 窗口都必须封锁对应 valid/ready 接口。
    always @(posedge host_clk) begin
        if ((host_rst || cmd_wr_rst_busy) && host_cmd_ready)
            $fatal(1, "Host command handshake leaked during reset busy");
        if ((host_rst || rsp_rd_rst_busy) && host_rsp_valid)
            $fatal(1, "Host response valid leaked during reset busy");
        if (status_irq !== host_rsp_valid)
            $fatal(1, "status_irq differs from host_rsp_valid");

        if (host_rsp_valid && !host_rsp_ready) begin
            if (host_rsp_was_stalled && host_rsp_data !== stalled_host_rsp)
                $fatal(1, "Host response payload changed while stalled");
            stalled_host_rsp <= host_rsp_data;
            host_rsp_was_stalled <= 1'b1;
        end else begin
            host_rsp_was_stalled <= 1'b0;
        end
    end

    always @(posedge tile_clk) begin
        if ((tile_rst || cmd_rd_rst_busy || !tile_domain_up) && tile_cmd_valid)
            $fatal(1, "Tile command valid leaked during reset busy");
        if ((tile_rst || rsp_wr_rst_busy || !tile_domain_up) && tile_rsp_ready)
            $fatal(1, "Tile response ready leaked during reset busy");

        if (tile_cmd_valid && !tile_cmd_ready) begin
            if (tile_cmd_was_stalled && tile_cmd_data !== stalled_tile_cmd)
                $fatal(1, "Tile command payload changed while stalled");
            stalled_tile_cmd <= tile_cmd_data;
            tile_cmd_was_stalled <= 1'b1;
        end else begin
            tile_cmd_was_stalled <= 1'b0;
        end
    end

    task automatic host_send_command(input logic [127:0] value);
        begin
            @(negedge host_clk);
            host_cmd_data = value;
            host_cmd_valid = 1'b1;
            do @(posedge host_clk); while (!host_cmd_ready);
            @(negedge host_clk);
            host_cmd_valid = 1'b0;
        end
    endtask

    task automatic tile_receive_command(input logic [127:0] expected);
        logic [127:0] observed;
        begin
            @(negedge tile_clk);
            tile_cmd_ready = 1'b1;
            do @(posedge tile_clk); while (!tile_cmd_valid);
            observed = tile_cmd_data;
            if (observed !== expected)
                $fatal(1, "Command order mismatch: actual=%032h expected=%032h",
                    observed, expected);
            @(negedge tile_clk);
            tile_cmd_ready = 1'b0;
        end
    endtask

    task automatic tile_send_response(input logic [127:0] value);
        begin
            @(negedge tile_clk);
            tile_rsp_data = value;
            tile_rsp_valid = 1'b1;
            do @(posedge tile_clk); while (!tile_rsp_ready);
            @(negedge tile_clk);
            tile_rsp_valid = 1'b0;
        end
    endtask

    task automatic host_receive_response(input logic [127:0] expected);
        logic [127:0] observed;
        begin
            @(negedge host_clk);
            host_rsp_ready = 1'b1;
            do @(posedge host_clk); while (!host_rsp_valid);
            observed = host_rsp_data;
            if (observed !== expected)
                $fatal(1, "Response order mismatch: actual=%032h expected=%032h",
                    observed, expected);
            @(negedge host_clk);
            host_rsp_ready = 1'b0;
        end
    endtask

    task automatic fill_command_until_backpressure;
        integer accepted;
        begin
            accepted = 0;
            @(negedge host_clk);
            host_cmd_valid = 1'b1;
            host_cmd_data = CMD_BASE;
            while (host_cmd_ready) begin
                @(posedge host_clk);
                if (host_cmd_ready)
                    accepted = accepted + 1;
                @(negedge host_clk);
                host_cmd_data = CMD_BASE + accepted;
            end
            host_cmd_valid = 1'b0;
            command_fill_count = accepted;
            if (accepted == 0)
                $fatal(1, "XPM command FIFO accepted no data before backpressure");
        end
    endtask

    task automatic fill_response_until_backpressure;
        integer accepted;
        begin
            accepted = 0;
            @(negedge tile_clk);
            tile_rsp_valid = 1'b1;
            tile_rsp_data = RSP_BASE;
            while (tile_rsp_ready) begin
                @(posedge tile_clk);
                if (tile_rsp_ready)
                    accepted = accepted + 1;
                @(negedge tile_clk);
                tile_rsp_data = RSP_BASE + accepted;
            end
            tile_rsp_valid = 1'b0;
            response_fill_count = accepted;
            if (accepted == 0)
                $fatal(1, "XPM response FIFO accepted no data before backpressure");
        end
    endtask

    integer i;
    initial begin
        // bridge_rst 在两个域都保持超过四个上升沿。
        repeat (10) @(posedge host_clk);
        #3 bridge_rst = 1'b0;
        wait (host_cmd_ready && tile_rsp_ready && tile_domain_up);

        // 真实 XPM 的 FWFT 有效容量由仿真测得，随后验证长背压和完整排空。
        $display("XPM_PHASE command_fill_begin time=%0t", $time);
        fill_command_until_backpressure();
        $display("XPM_PHASE command_fill_end time=%0t count=%0d",
            $time, command_fill_count);
        repeat (12) @(posedge tile_clk);
        for (i = 0; i < command_fill_count; i = i + 1)
            tile_receive_command(CMD_BASE + i);
        $display("XPM_PHASE command_drain_end time=%0t", $time);

        // 多次指针回绕并保持两个非整数频比时钟并行运行。
        fork
            begin : command_producer
                integer j;
                for (j = 0; j < 64; j = j + 1)
                    host_send_command(CMD_BASE + 128 + j);
            end
            begin : command_consumer
                integer j;
                for (j = 0; j < 64; j = j + 1) begin
                    if ((j % 7) == 0)
                        repeat (3) @(posedge tile_clk);
                    tile_receive_command(CMD_BASE + 128 + j);
                end
            end
        join
        $display("XPM_PHASE command_wrap_end time=%0t", $time);

        $display("XPM_PHASE response_fill_begin time=%0t", $time);
        fill_response_until_backpressure();
        $display("XPM_PHASE response_fill_end time=%0t count=%0d",
            $time, response_fill_count);
        repeat (10) @(posedge host_clk);
        for (i = 0; i < response_fill_count; i = i + 1)
            host_receive_response(RSP_BASE + i);
        $display("XPM_PHASE response_drain_end time=%0t", $time);

        fork
            begin : response_producer
                integer j;
                for (j = 0; j < 64; j = j + 1)
                    tile_send_response(RSP_BASE + 128 + j);
            end
            begin : response_consumer
                integer j;
                for (j = 0; j < 64; j = j + 1) begin
                    if ((j % 5) == 0)
                        repeat (4) @(posedge host_clk);
                    host_receive_response(RSP_BASE + 128 + j);
                end
            end
        join
        $display("XPM_PHASE response_wrap_end time=%0t", $time);

        // 在两个 FIFO 各保留一个未消费 flit 时执行合法 hard reset。
        host_send_command(CMD_BASE + 16'h0bad);
        tile_send_response(RSP_BASE + 16'h0bad);
        wait (tile_cmd_valid && host_rsp_valid);
        wait (!cmd_wr_rst_busy && !rsp_wr_rst_busy);
        #3 bridge_rst = 1'b1;
        #220;
        if (host_cmd_ready || host_rsp_valid || tile_cmd_valid || tile_rsp_ready)
            $fatal(1, "Handshake leaked while hard reset was asserted");
        #3 bridge_rst = 1'b0;
        wait (host_cmd_ready && tile_rsp_ready && tile_domain_up);
        repeat (6) @(posedge host_clk);
        if (tile_cmd_valid || host_rsp_valid)
            $fatal(1, "Pre-reset flit survived hard reset");

        test_passed = 1'b1;
        $display(
            "VIVADO_XPM_WRAPPER_PASS command_capacity=%0d response_capacity=%0d",
            command_fill_count, response_fill_count
        );
        #20 $finish;
    end

    initial begin
        #500000;
        $fatal(1, "Vivado XPM wrapper test timeout");
    end
endmodule
