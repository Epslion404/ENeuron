// Host/Tile clock-domain transport for Host Bridge V1.
module digital_snn_host_bridge (
    input  logic         host_clk,
    input  logic         tile_clk,
    input  logic         bridge_rst,

    input  logic         host_cmd_valid,
    output logic         host_cmd_ready,
    input  logic [127:0] host_cmd_data,

    output logic         host_rsp_valid,
    input  logic         host_rsp_ready,
    output logic [127:0] host_rsp_data,
    output logic         status_irq,

    output logic         tile_cmd_valid,
    input  logic         tile_cmd_ready,
    output logic [127:0] tile_cmd_data,

    input  logic         tile_rsp_valid,
    output logic         tile_rsp_ready,
    input  logic [127:0] tile_rsp_data,

    output logic         host_rst,
    output logic         tile_rst,
    output logic         tile_domain_up,
    output logic         cmd_wr_rst_busy,
    output logic         cmd_rd_rst_busy,
    output logic         rsp_wr_rst_busy,
    output logic         rsp_rd_rst_busy
);

    // XPM rst is synchronous to the FIFO write clock. The external request is
    // therefore sampled independently in each write domain without async set.
    logic [1:0] host_rst_sync = 2'b11;
    logic [1:0] tile_rst_sync = 2'b11;

    always_ff @(posedge host_clk) begin
        host_rst_sync <= {host_rst_sync[0], bridge_rst};
    end

    always_ff @(posedge tile_clk) begin
        tile_rst_sync <= {tile_rst_sync[0], bridge_rst};
    end

    assign host_rst = host_rst_sync[1];
    assign tile_rst = tile_rst_sync[1];

    always_ff @(posedge tile_clk) begin
        if (tile_rst)
            tile_domain_up <= 1'b0;
        else
            tile_domain_up <= 1'b1;
    end

    logic cmd_full;
    logic cmd_empty;
    logic [127:0] cmd_dout;
    logic rsp_full;
    logic rsp_empty;
    logic [127:0] rsp_dout;
    logic cmd_wr_en;
    logic cmd_rd_en;
    logic rsp_wr_en;
    logic rsp_rd_en;

    assign host_cmd_ready = !host_rst && !cmd_wr_rst_busy && !cmd_full;
    assign cmd_wr_en = host_cmd_valid && host_cmd_ready;

    assign tile_cmd_valid = tile_domain_up && !tile_rst
        && !cmd_rd_rst_busy && !cmd_empty;
    assign tile_cmd_data = cmd_dout;
    assign cmd_rd_en = tile_cmd_valid && tile_cmd_ready;

    assign tile_rsp_ready = tile_domain_up && !tile_rst
        && !rsp_wr_rst_busy && !rsp_full;
    assign rsp_wr_en = tile_rsp_valid && tile_rsp_ready;

    assign host_rsp_valid = !host_rst && !rsp_rd_rst_busy && !rsp_empty;
    assign host_rsp_data = rsp_dout;
    assign rsp_rd_en = host_rsp_valid && host_rsp_ready;
    assign status_irq = host_rsp_valid;

    // Command FIFO: Host writes, Tile reads.
    xpm_fifo_async #(
        .FIFO_MEMORY_TYPE("auto"),
        .ECC_MODE("no_ecc"),
        .RELATED_CLOCKS(0),
        .SIM_ASSERT_CHK(1),
        .FIFO_WRITE_DEPTH(16),
        .WRITE_DATA_WIDTH(128),
        .WR_DATA_COUNT_WIDTH(5),
        .PROG_FULL_THRESH(10),
        .FULL_RESET_VALUE(0),
        .USE_ADV_FEATURES("0000"),
        .READ_MODE("fwft"),
        .FIFO_READ_LATENCY(0),
        .READ_DATA_WIDTH(128),
        .RD_DATA_COUNT_WIDTH(5),
        .PROG_EMPTY_THRESH(10),
        .DOUT_RESET_VALUE("0"),
        .CDC_SYNC_STAGES(2),
        .WAKEUP_TIME(0)
    ) command_fifo (
        .sleep(1'b0),
        .rst(host_rst),
        .wr_clk(host_clk),
        .wr_en(cmd_wr_en),
        .din(host_cmd_data),
        .full(cmd_full),
        .prog_full(),
        .wr_data_count(),
        .overflow(),
        .wr_rst_busy(cmd_wr_rst_busy),
        .almost_full(),
        .wr_ack(),
        .rd_clk(tile_clk),
        .rd_en(cmd_rd_en),
        .dout(cmd_dout),
        .empty(cmd_empty),
        .prog_empty(),
        .rd_data_count(),
        .underflow(),
        .rd_rst_busy(cmd_rd_rst_busy),
        .almost_empty(),
        .data_valid(),
        .injectsbiterr(1'b0),
        .injectdbiterr(1'b0),
        .sbiterr(),
        .dbiterr()
    );

    // Response FIFO: Tile writes, Host reads.
    xpm_fifo_async #(
        .FIFO_MEMORY_TYPE("auto"),
        .ECC_MODE("no_ecc"),
        .RELATED_CLOCKS(0),
        .SIM_ASSERT_CHK(1),
        .FIFO_WRITE_DEPTH(16),
        .WRITE_DATA_WIDTH(128),
        .WR_DATA_COUNT_WIDTH(5),
        .PROG_FULL_THRESH(10),
        .FULL_RESET_VALUE(0),
        .USE_ADV_FEATURES("0000"),
        .READ_MODE("fwft"),
        .FIFO_READ_LATENCY(0),
        .READ_DATA_WIDTH(128),
        .RD_DATA_COUNT_WIDTH(5),
        .PROG_EMPTY_THRESH(10),
        .DOUT_RESET_VALUE("0"),
        .CDC_SYNC_STAGES(2),
        .WAKEUP_TIME(0)
    ) response_fifo (
        .sleep(1'b0),
        .rst(tile_rst),
        .wr_clk(tile_clk),
        .wr_en(rsp_wr_en),
        .din(tile_rsp_data),
        .full(rsp_full),
        .prog_full(),
        .wr_data_count(),
        .overflow(),
        .wr_rst_busy(rsp_wr_rst_busy),
        .almost_full(),
        .wr_ack(),
        .rd_clk(host_clk),
        .rd_en(rsp_rd_en),
        .dout(rsp_dout),
        .empty(rsp_empty),
        .prog_empty(),
        .rd_data_count(),
        .underflow(),
        .rd_rst_busy(rsp_rd_rst_busy),
        .almost_empty(),
        .data_valid(),
        .injectsbiterr(1'b0),
        .injectdbiterr(1'b0),
        .sbiterr(),
        .dbiterr()
    );

`ifndef SYNTHESIS
    // V1 does not queue hard-reset requests. A new assertion before both
    // write-side busy sequences finish is an external protocol violation.
    logic reset_cycle_active = 1'b1;
    logic bridge_rst_seen_low = 1'b0;

    always @(negedge bridge_rst) begin
        bridge_rst_seen_low = 1'b1;
    end

    always @(posedge bridge_rst) begin
        // The initial high level is the power-on reset, not a re-entry edge.
        if (bridge_rst_seen_low && reset_cycle_active) begin
            $display("RESET_REENTRY_ERROR: bridge_rst asserted before write-side reset completion");
            $fatal(1, "RESET_REENTRY_ERROR");
        end
        reset_cycle_active = 1'b1;
    end

    always @(negedge cmd_wr_rst_busy or negedge rsp_wr_rst_busy
            or negedge bridge_rst) begin
        if (!bridge_rst && !cmd_wr_rst_busy && !rsp_wr_rst_busy)
            reset_cycle_active = 1'b0;
    end
`endif

endmodule
