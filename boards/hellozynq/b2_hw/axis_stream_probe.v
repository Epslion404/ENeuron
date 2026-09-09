module axis_stream_probe #(
    parameter integer DATA_WIDTH = 32,
    parameter integer KEEP_WIDTH = DATA_WIDTH / 8
) (
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AXI, DATA_WIDTH 32, PROTOCOL AXI4LITE, FREQ_HZ 200000000, ADDR_WIDTH 12, ID_WIDTH 0, NUM_READ_OUTSTANDING 1, NUM_WRITE_OUTSTANDING 1" *)
    input wire                    s_axi_aclk,
    input wire                    s_axi_aresetn,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWADDR" *)
    input wire [11:0]             s_axi_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWVALID" *)
    input wire                    s_axi_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *)
    output wire                    s_axi_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WDATA" *)
    input wire [31:0]             s_axi_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *)
    input wire [3:0]              s_axi_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WVALID" *)
    input wire                    s_axi_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WREADY" *)
    output wire                    s_axi_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BRESP" *)
    output reg [1:0]              s_axi_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BVALID" *)
    output reg                    s_axi_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BREADY" *)
    input wire                    s_axi_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *)
    input wire [11:0]             s_axi_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *)
    input wire                    s_axi_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *)
    output wire                    s_axi_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RDATA" *)
    output reg [31:0]             s_axi_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RRESP" *)
    output reg [1:0]              s_axi_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RVALID" *)
    output reg                    s_axi_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RREADY" *)
    input wire                    s_axi_rready,

    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AXIS, TDATA_NUM_BYTES 4, FREQ_HZ 200000000, ASSOCIATED_CLK s_axi_aclk, TDEST_WIDTH 0, TID_WIDTH 0, TUSER_WIDTH 0" *)
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TDATA" *)
    input wire [DATA_WIDTH-1:0]   s_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TKEEP" *)
    input wire [KEEP_WIDTH-1:0]   s_axis_tkeep,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TLAST" *)
    input wire                    s_axis_tlast,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TVALID" *)
    input wire                    s_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TREADY" *)
    output wire                    s_axis_tready,
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME M_AXIS, TDATA_NUM_BYTES 4, FREQ_HZ 200000000, ASSOCIATED_CLK s_axi_aclk, TDEST_WIDTH 0, TID_WIDTH 0, TUSER_WIDTH 0" *)
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TDATA" *)
    output wire [DATA_WIDTH-1:0]   m_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TKEEP" *)
    output wire [KEEP_WIDTH-1:0]   m_axis_tkeep,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TLAST" *)
    output wire                    m_axis_tlast,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TVALID" *)
    output wire                    m_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TREADY" *)
    input wire                    m_axis_tready
);

    localparam [11:0] CONTROL_ADDR = 12'h000;
    localparam [11:0] BACKPRESSURE_ADDR = 12'h004;
    localparam [11:0] SAMPLE_ADDR = 12'h020;
    localparam [11:0] BEATS_ADDR = 12'h050;
    localparam [11:0] TLAST_ADDR = 12'h080;
    localparam [11:0] BYTES_ADDR = 12'h088;
    localparam [11:0] BUSY_ADDR = 12'h090;
    localparam [11:0] STALL_ADDR = 12'h098;
    localparam [11:0] STARVE_ADDR = 12'h0A0;
    localparam [11:0] LAST_KEEP_ADDR = 12'h0A8;
    reg [31:0] accepted_beats;
    reg [31:0] total_bytes;
    reg [31:0] tlast_count;
    reg [31:0] cycle_count;
    reg [31:0] stall_count;
    reg [31:0] starve_count;
    reg [31:0] backpressure_config;
    reg [7:0] backpressure_phase;
    reg backpressure_stall;
    reg fifo_valid;
    reg [DATA_WIDTH-1:0] fifo_tdata;
    reg [KEEP_WIDTH-1:0] fifo_tkeep;
    reg fifo_tlast;
    reg [KEEP_WIDTH-1:0] last_tkeep;
    reg active;
    reg aw_pending;
    reg w_pending;
    reg [11:0] write_addr;
    reg [31:0] write_data;
    reg [3:0] write_strb;
    wire write_fire;
    wire clear_now;
    wire stop_now;
    wire stream_fire;
    wire input_fire;

    function [31:0] keep_bytes;
        input [KEEP_WIDTH-1:0] keep;
        integer index;
        begin
            keep_bytes = 32'd0;
            for (index = 0; index < KEEP_WIDTH; index = index + 1) begin
                keep_bytes = keep_bytes + {{31{1'b0}}, keep[index]};
            end
        end
    endfunction

    /* 输出拍先锁存，再由寄存器化暂停状态插入气泡；暂停期间 payload 保持不变。 */
    assign m_axis_tdata = fifo_tdata;
    assign m_axis_tkeep = fifo_tkeep;
    assign m_axis_tlast = fifo_tlast;
    assign m_axis_tvalid = s_axi_aresetn && fifo_valid && !backpressure_stall;
    assign s_axis_tready = s_axi_aresetn && active && !fifo_valid;
    assign stream_fire = m_axis_tvalid && m_axis_tready;
    assign input_fire = s_axis_tvalid && s_axis_tready;

    assign s_axi_awready = s_axi_aresetn && !aw_pending && !s_axi_bvalid;
    assign s_axi_wready = s_axi_aresetn && !w_pending && !s_axi_bvalid;
    assign s_axi_arready = s_axi_aresetn && !s_axi_rvalid;
    assign write_fire = aw_pending && w_pending && !s_axi_bvalid;
    assign clear_now = write_fire && (write_addr == CONTROL_ADDR) && write_data[0];
    assign stop_now = write_fire && (write_addr == CONTROL_ADDR) && write_data[1];

    always @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            s_axi_bvalid <= 1'b0;
            s_axi_bresp <= 2'b00;
            s_axi_rvalid <= 1'b0;
            s_axi_rresp <= 2'b00;
            s_axi_rdata <= 32'd0;
            aw_pending <= 1'b0;
            w_pending <= 1'b0;
            write_addr <= 12'd0;
            write_data <= 32'd0;
            write_strb <= 4'd0;
            accepted_beats <= 32'd0;
            total_bytes <= 32'd0;
            tlast_count <= 32'd0;
            cycle_count <= 32'd0;
            stall_count <= 32'd0;
            starve_count <= 32'd0;
            backpressure_config <= 32'd0;
            backpressure_phase <= 8'd0;
            backpressure_stall <= 1'b0;
            fifo_valid <= 1'b0;
            fifo_tdata <= {DATA_WIDTH{1'b0}};
            fifo_tkeep <= {KEEP_WIDTH{1'b0}};
            fifo_tlast <= 1'b0;
            last_tkeep <= {KEEP_WIDTH{1'b0}};
            active <= 1'b0;
        end else begin
            if (s_axi_awvalid && s_axi_awready) begin
                aw_pending <= 1'b1;
                write_addr <= s_axi_awaddr;
            end
            if (s_axi_wvalid && s_axi_wready) begin
                w_pending <= 1'b1;
                write_data <= s_axi_wdata;
                write_strb <= s_axi_wstrb;
            end
            if (write_fire) begin
                aw_pending <= 1'b0;
                w_pending <= 1'b0;
                s_axi_bvalid <= 1'b1;
                s_axi_bresp <= 2'b00;
            end
            if (s_axi_bvalid && s_axi_bready) begin
                s_axi_bvalid <= 1'b0;
            end

            if (s_axi_arvalid && s_axi_arready) begin
                s_axi_rvalid <= 1'b1;
                s_axi_rresp <= 2'b00;
                case (s_axi_araddr)
                    BACKPRESSURE_ADDR: s_axi_rdata <= backpressure_config;
                    SAMPLE_ADDR: s_axi_rdata <= {31'd0, active};
                    BEATS_ADDR: s_axi_rdata <= accepted_beats;
                    TLAST_ADDR: s_axi_rdata <= tlast_count;
                    TLAST_ADDR + 12'd4: s_axi_rdata <= 32'd0;
                    BYTES_ADDR: s_axi_rdata <= total_bytes;
                    BYTES_ADDR + 12'd4: s_axi_rdata <= 32'd0;
                    BUSY_ADDR: s_axi_rdata <= cycle_count;
                    BUSY_ADDR + 12'd4: s_axi_rdata <= 32'd0;
                    STALL_ADDR: s_axi_rdata <= stall_count;
                    STALL_ADDR + 12'd4: s_axi_rdata <= 32'd0;
                    STARVE_ADDR: s_axi_rdata <= starve_count;
                    STARVE_ADDR + 12'd4: s_axi_rdata <= 32'd0;
                    LAST_KEEP_ADDR: s_axi_rdata <= {{(32-KEEP_WIDTH){1'b0}}, last_tkeep};
                    default: s_axi_rdata <= 32'd0;
                endcase
            end
            if (s_axi_rvalid && s_axi_rready) begin
                s_axi_rvalid <= 1'b0;
            end

            if (clear_now) begin
                accepted_beats <= 32'd0;
                total_bytes <= 32'd0;
                tlast_count <= 32'd0;
                cycle_count <= 32'd0;
                stall_count <= 32'd0;
                starve_count <= 32'd0;
                last_tkeep <= {KEEP_WIDTH{1'b0}};
                backpressure_phase <= 8'd0;
                backpressure_stall <= 1'b0;
                fifo_valid <= 1'b0;
                active <= 1'b1;
            end else begin
                if (stop_now) begin
                    active <= 1'b0;
                end
                if (active) begin
                    cycle_count <= cycle_count + 32'd1;
                    if (fifo_valid && (backpressure_stall || !m_axis_tready)) begin
                        stall_count <= stall_count + 32'd1;
                    end else if (!s_axis_tvalid) begin
                        starve_count <= starve_count + 32'd1;
                    end
                    if (input_fire) begin
                        fifo_valid <= 1'b1;
                        fifo_tdata <= s_axis_tdata;
                        fifo_tkeep <= s_axis_tkeep;
                        fifo_tlast <= s_axis_tlast;
                    end
                    if (stream_fire) begin
                        fifo_valid <= 1'b0;
                        accepted_beats <= accepted_beats + 32'd1;
                        total_bytes <= total_bytes + keep_bytes(fifo_tkeep);
                        last_tkeep <= fifo_tkeep;
                        if (fifo_tlast) begin
                            tlast_count <= tlast_count + 32'd1;
                            active <= 1'b0;
                        end
                    end
                    if (!backpressure_config[0] ||
                        (backpressure_config[15:8] == 8'd0) ||
                        (backpressure_config[23:16] == 8'd0)) begin
                        backpressure_phase <= 8'd0;
                        backpressure_stall <= 1'b0;
                    end else if (input_fire) begin
                        /* 每帧首个 beat 到达后才启动 phase，避免等待 DMA 首拍时相位漂移。 */
                        backpressure_phase <= 8'd0;
                        backpressure_stall <= 1'b1;
                    end else if (fifo_valid && !backpressure_stall && !m_axis_tready) begin
                        /* 已公开 VALID 的 beat 等待 READY 时冻结 phase，保持 VALID/payload。 */
                        backpressure_phase <= backpressure_phase;
                        backpressure_stall <= 1'b0;
                    end else if (!fifo_valid) begin
                        backpressure_phase <= 8'd0;
                        backpressure_stall <= 1'b0;
                    end else if (backpressure_phase < backpressure_config[15:8]) begin
                        backpressure_stall <= 1'b1;
                        backpressure_phase <= backpressure_phase + 8'd1;
                    end else if (backpressure_phase + 8'd1 >= backpressure_config[23:16]) begin
                        backpressure_phase <= 8'd0;
                        backpressure_stall <= 1'b0;
                    end else begin
                        backpressure_phase <= backpressure_phase + 8'd1;
                        backpressure_stall <= 1'b0;
                    end
                end
            end
            if (write_fire && (write_addr == BACKPRESSURE_ADDR)) begin
                backpressure_config <= write_data;
                backpressure_phase <= 8'd0;
                backpressure_stall <= 1'b0;
            end
        end
    end
endmodule

