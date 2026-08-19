// Interface-equivalent XPM async FIFO model for Icarus regression only.
// Vivado synthesis and xsim use AMD's xpm_fifo_async implementation instead.
module xpm_fifo_async #(
    parameter FIFO_MEMORY_TYPE = "auto",
    parameter ECC_MODE = "no_ecc",
    parameter integer RELATED_CLOCKS = 0,
    parameter integer SIM_ASSERT_CHK = 0,
    parameter EN_SIM_ASSERT_ERR = "warning",
    parameter integer CASCADE_HEIGHT = 0,
    parameter integer FIFO_WRITE_DEPTH = 16,
    parameter integer WRITE_DATA_WIDTH = 128,
    parameter integer WR_DATA_COUNT_WIDTH = 5,
    parameter integer PROG_FULL_THRESH = 10,
    parameter integer FULL_RESET_VALUE = 0,
    parameter USE_ADV_FEATURES = "0000",
    parameter READ_MODE = "fwft",
    parameter integer FIFO_READ_LATENCY = 0,
    parameter integer READ_DATA_WIDTH = WRITE_DATA_WIDTH,
    parameter integer RD_DATA_COUNT_WIDTH = 5,
    parameter integer PROG_EMPTY_THRESH = 10,
    parameter DOUT_RESET_VALUE = "0",
    parameter integer CDC_SYNC_STAGES = 2,
    parameter WAKEUP_TIME = 0
) (
    input  wire sleep,
    input  wire rst,
    input  wire wr_clk,
    input  wire wr_en,
    input  wire [WRITE_DATA_WIDTH-1:0] din,
    output wire full,
    output wire prog_full,
    output wire [WR_DATA_COUNT_WIDTH-1:0] wr_data_count,
    output reg overflow,
    output reg wr_rst_busy,
    output wire almost_full,
    output reg wr_ack,
    input  wire rd_clk,
    input  wire rd_en,
    output wire [READ_DATA_WIDTH-1:0] dout,
    output wire empty,
    output wire prog_empty,
    output wire [RD_DATA_COUNT_WIDTH-1:0] rd_data_count,
    output reg underflow,
    output reg rd_rst_busy,
    output wire almost_empty,
    output wire data_valid,
    input  wire injectsbiterr,
    input  wire injectdbiterr,
    output wire sbiterr,
    output wire dbiterr
);

    localparam integer ADDR_BITS = $clog2(FIFO_WRITE_DEPTH);
    localparam integer PTR_BITS = ADDR_BITS + 1;

    reg [WRITE_DATA_WIDTH-1:0] memory [0:FIFO_WRITE_DEPTH-1];
    reg [PTR_BITS-1:0] wr_binary = '0;
    reg [PTR_BITS-1:0] wr_gray = '0;
    reg [PTR_BITS-1:0] rd_binary = '0;
    reg [PTR_BITS-1:0] rd_gray = '0;
    reg [PTR_BITS-1:0] rd_gray_sync1 = '0;
    reg [PTR_BITS-1:0] rd_gray_sync2 = '0;
    reg [PTR_BITS-1:0] wr_gray_sync1 = '0;
    reg [PTR_BITS-1:0] wr_gray_sync2 = '0;
    reg full_reg = 1'b0;
    reg [READ_DATA_WIDTH-1:0] fwft_data = '0;
    reg fwft_valid = 1'b0;
    reg [1:0] rd_reset_sync = 2'b11;
    reg [1:0] wr_busy_count = 2'd3;
    reg [1:0] rd_busy_count = 2'd3;

    wire write_accept = wr_en && !full && !wr_rst_busy;
    wire read_accept = rd_en && fwft_valid && !rd_rst_busy;
    wire [PTR_BITS-1:0] wr_binary_next = wr_binary + write_accept;
    // The RAM read pointer advances when a word moves into the FWFT slot.
    // That move is distinct from the external valid/ready consumption event.
    wire ram_read_advance = !rd_rst_busy && !ram_empty
        && (!fwft_valid || read_accept);
    wire [PTR_BITS-1:0] rd_binary_next = rd_binary + ram_read_advance;
    wire [PTR_BITS-1:0] wr_gray_next = (wr_binary_next >> 1) ^ wr_binary_next;
    wire [PTR_BITS-1:0] rd_gray_next = (rd_binary_next >> 1) ^ rd_binary_next;
    wire [PTR_BITS-1:0] full_compare = {
        ~rd_gray_sync2[PTR_BITS-1:PTR_BITS-2],
        rd_gray_sync2[PTR_BITS-3:0]
    };

    assign full = full_reg;
    wire ram_empty = rd_gray == wr_gray_sync2;
    assign empty = !fwft_valid;
    assign dout = fwft_valid ? fwft_data : {READ_DATA_WIDTH{1'b0}};
    assign data_valid = fwft_valid && !rd_rst_busy;
    assign prog_full = 1'b0;
    assign prog_empty = 1'b0;
    assign almost_full = full;
    assign almost_empty = empty;
    assign wr_data_count = '0;
    assign rd_data_count = '0;
    assign sbiterr = 1'b0;
    assign dbiterr = 1'b0;

    always @(posedge wr_clk) begin
        rd_gray_sync1 <= rd_gray;
        rd_gray_sync2 <= rd_gray_sync1;
        overflow <= 1'b0;
        wr_ack <= 1'b0;
        if (rst) begin
            wr_binary <= '0;
            wr_gray <= '0;
            full_reg <= 1'b0;
            wr_rst_busy <= 1'b1;
            wr_busy_count <= 2'd3;
        end else if (wr_busy_count != 0) begin
            wr_binary <= '0;
            wr_gray <= '0;
            full_reg <= 1'b0;
            wr_busy_count <= wr_busy_count - 1'b1;
            wr_rst_busy <= 1'b1;
        end else begin
            wr_rst_busy <= 1'b0;
            full_reg <= wr_gray_next == full_compare;
            if (write_accept) begin
                memory[wr_binary[ADDR_BITS-1:0]] <= din;
                wr_binary <= wr_binary_next;
                wr_gray <= wr_gray_next;
                wr_ack <= 1'b1;
            end else if (wr_en && full) begin
                overflow <= 1'b1;
            end
        end
    end

    always @(posedge rd_clk) begin
        rd_reset_sync <= {rd_reset_sync[0], rst};
        wr_gray_sync1 <= wr_gray;
        wr_gray_sync2 <= wr_gray_sync1;
        underflow <= 1'b0;
        if (rd_reset_sync[1]) begin
            rd_binary <= '0;
            rd_gray <= '0;
            fwft_data <= '0;
            fwft_valid <= 1'b0;
            rd_rst_busy <= 1'b1;
            rd_busy_count <= 2'd3;
        end else if (rd_busy_count != 0) begin
            rd_binary <= '0;
            rd_gray <= '0;
            fwft_data <= '0;
            fwft_valid <= 1'b0;
            rd_busy_count <= rd_busy_count - 1'b1;
            rd_rst_busy <= 1'b1;
        end else begin
            rd_rst_busy <= 1'b0;
            // FWFT owns one read-domain prefetch slot. Moving a RAM word into
            // this slot advances the internal read pointer without consuming
            // the externally visible word, matching the real XPM capacity.
            if (!fwft_valid && !ram_empty) begin
                fwft_data <= memory[rd_binary[ADDR_BITS-1:0]];
                fwft_valid <= 1'b1;
                rd_binary <= rd_binary_next;
                rd_gray <= rd_gray_next;
            end else if (read_accept && !ram_empty) begin
                fwft_data <= memory[rd_binary[ADDR_BITS-1:0]];
                fwft_valid <= 1'b1;
                rd_binary <= rd_binary_next;
                rd_gray <= rd_gray_next;
            end else if (read_accept) begin
                fwft_valid <= 1'b0;
            end else if (rd_en && !fwft_valid) begin
                underflow <= 1'b1;
            end
        end
    end

    initial begin
        overflow = 1'b0;
        underflow = 1'b0;
        wr_ack = 1'b0;
        wr_rst_busy = 1'b1;
        rd_rst_busy = 1'b1;
        if (FIFO_WRITE_DEPTH != 16 || WRITE_DATA_WIDTH != 128
                || READ_DATA_WIDTH != 128 || READ_MODE != "fwft"
                || FIFO_READ_LATENCY != 0 || CDC_SYNC_STAGES != 2)
            $fatal(1, "xpm_fifo_async_sim parameter mismatch");
    end

endmodule
