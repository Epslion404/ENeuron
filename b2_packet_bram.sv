// B2 packet 缓存的单写单读 BRAM 封装。
// Icarus 使用行为模型；Vivado 综合使用 XPM simple-dual-port block RAM。
module b2_packet_bram #(
    parameter integer DATA_WIDTH = 32,
    parameter integer DEPTH = 16,
    parameter integer ADDR_WIDTH = $clog2(DEPTH)
) (
    input  logic                  clk,
    input  logic                  rst,
    input  logic                  wr_en,
    input  logic [ADDR_WIDTH-1:0] wr_addr,
    input  logic [DATA_WIDTH-1:0] wr_data,
    input  logic                  rd_en,
    input  logic [ADDR_WIDTH-1:0] rd_addr,
    output logic [DATA_WIDTH-1:0] rd_data
);
`ifdef SYNTHESIS
    xpm_memory_sdpram #(
        .MEMORY_SIZE(DATA_WIDTH * DEPTH),
        .MEMORY_PRIMITIVE("block"),
        .CLOCKING_MODE("common_clock"),
        .ECC_MODE("no_ecc"),
        .MEMORY_INIT_FILE("none"),
        .USE_MEM_INIT(0),
        .SIM_ASSERT_CHK(0),
        .WRITE_DATA_WIDTH_A(DATA_WIDTH),
        .BYTE_WRITE_WIDTH_A(DATA_WIDTH),
        .ADDR_WIDTH_A(ADDR_WIDTH),
        .RST_MODE_A("SYNC"),
        .READ_DATA_WIDTH_B(DATA_WIDTH),
        .ADDR_WIDTH_B(ADDR_WIDTH),
        .READ_RESET_VALUE_B("0"),
        .READ_LATENCY_B(1),
        .WRITE_MODE_B("no_change"),
        .RST_MODE_B("SYNC")
    ) mem (
        .sleep(1'b0),
        .clka(clk), .ena(wr_en), .wea(wr_en), .addra(wr_addr), .dina(wr_data),
        .injectsbiterra(1'b0), .injectdbiterra(1'b0),
        .clkb(clk), .rstb(rst), .enb(rd_en), .regceb(1'b1), .addrb(rd_addr),
        .doutb(rd_data), .sbiterrb(), .dbiterrb()
    );
`else
    logic [DATA_WIDTH-1:0] mem [0:DEPTH-1];

    always_ff @(posedge clk) begin
        if (rst) begin
            rd_data <= '0;
        end else begin
            if (wr_en)
                mem[wr_addr] <= wr_data;
            if (rd_en)
                rd_data <= mem[rd_addr];
        end
    end
`endif
endmodule
