// B2 packet-NPU 计数器只读 AXI-Lite 状态块。
// 该模块不参与数据通路，只把同一 FCLK0 域的计数器和 fence 快照提供给 PS/JTAG。
module b2_npu_status_probe (
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AXI, DATA_WIDTH 32, PROTOCOL AXI4LITE, FREQ_HZ 200000000, ADDR_WIDTH 12, ID_WIDTH 0, NUM_READ_OUTSTANDING 1, NUM_WRITE_OUTSTANDING 1" *)
    input wire        s_axi_aclk,
    input wire        s_axi_aresetn,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWADDR" *)
    input wire [11:0] s_axi_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWVALID" *)
    input wire        s_axi_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *)
    output wire       s_axi_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WDATA" *)
    input wire [31:0] s_axi_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *)
    input wire [3:0]  s_axi_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WVALID" *)
    input wire        s_axi_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WREADY" *)
    output wire       s_axi_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BRESP" *)
    output reg [1:0]  s_axi_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BVALID" *)
    output reg        s_axi_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BREADY" *)
    input wire        s_axi_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *)
    input wire [11:0] s_axi_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *)
    input wire        s_axi_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *)
    output wire       s_axi_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RDATA" *)
    output reg [31:0] s_axi_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RRESP" *)
    output reg [1:0]  s_axi_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RVALID" *)
    output reg        s_axi_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RREADY" *)
    input wire        s_axi_rready,

    input wire [31:0] command_accept_count,
    input wire [31:0] command_complete_count,
    input wire [31:0] sample_accept_count,
    input wire [31:0] sample_complete_count,
    input wire [31:0] response_accept_count,
    input wire [31:0] response_complete_count,
    input wire [31:0] result_accept_count,
    input wire [31:0] result_complete_count,
    input wire [31:0] execute_group_count,
    input wire [31:0] skip_group_count,
    input wire [31:0] runtime_status,
    input wire [31:0] active_mask_epoch,
    input wire [31:0] pending_mask_epoch,
    input wire [31:0] last_compute_cycles,
    input wire [31:0] protocol_error_count,
    input wire        fence_snapshot_valid,
    input wire [255:0] fence_snapshot_counts
);
    localparam [11:0] STATUS_ADDR = 12'h000;
    localparam [11:0] COMMAND_ACCEPT_ADDR = 12'h004;
    localparam [11:0] COMMAND_COMPLETE_ADDR = 12'h008;
    localparam [11:0] SAMPLE_ACCEPT_ADDR = 12'h00C;
    localparam [11:0] SAMPLE_COMPLETE_ADDR = 12'h010;
    localparam [11:0] RESPONSE_ACCEPT_ADDR = 12'h014;
    localparam [11:0] RESPONSE_COMPLETE_ADDR = 12'h018;
    localparam [11:0] RESULT_ACCEPT_ADDR = 12'h01C;
    localparam [11:0] RESULT_COMPLETE_ADDR = 12'h020;
    localparam [11:0] EXECUTE_GROUP_ADDR = 12'h048;
    localparam [11:0] SKIP_GROUP_ADDR = 12'h04C;
    localparam [11:0] RUNTIME_STATUS_ADDR = 12'h050;
    localparam [11:0] ACTIVE_MASK_EPOCH_ADDR = 12'h054;
    localparam [11:0] PENDING_MASK_EPOCH_ADDR = 12'h058;
    localparam [11:0] LAST_COMPUTE_CYCLES_ADDR = 12'h05C;
    localparam [11:0] PROTOCOL_ERROR_COUNT_ADDR = 12'h060;
    localparam [11:0] FENCE_SNAPSHOT_VALID_ADDR = 12'h024;
    localparam [11:0] FENCE_SNAPSHOT_BASE_ADDR = 12'h028;

    reg aw_pending;
    reg w_pending;
    reg read_pending;
    reg [11:0] read_addr;
    wire write_fire;

    assign s_axi_awready = s_axi_aresetn && !aw_pending && !s_axi_bvalid;
    assign s_axi_wready = s_axi_aresetn && !w_pending && !s_axi_bvalid;
    assign s_axi_arready = s_axi_aresetn && !read_pending && !s_axi_rvalid;
    assign write_fire = aw_pending && w_pending && !s_axi_bvalid;

    function [31:0] read_value;
        input [11:0] address;
        begin
            case (address)
                STATUS_ADDR: read_value = {31'd0, s_axi_aresetn};
                COMMAND_ACCEPT_ADDR: read_value = command_accept_count;
                COMMAND_COMPLETE_ADDR: read_value = command_complete_count;
                SAMPLE_ACCEPT_ADDR: read_value = sample_accept_count;
                SAMPLE_COMPLETE_ADDR: read_value = sample_complete_count;
                RESPONSE_ACCEPT_ADDR: read_value = response_accept_count;
                RESPONSE_COMPLETE_ADDR: read_value = response_complete_count;
                RESULT_ACCEPT_ADDR: read_value = result_accept_count;
                RESULT_COMPLETE_ADDR: read_value = result_complete_count;
                EXECUTE_GROUP_ADDR: read_value = execute_group_count;
                SKIP_GROUP_ADDR: read_value = skip_group_count;
                RUNTIME_STATUS_ADDR: read_value = runtime_status;
                ACTIVE_MASK_EPOCH_ADDR: read_value = active_mask_epoch;
                PENDING_MASK_EPOCH_ADDR: read_value = pending_mask_epoch;
                LAST_COMPUTE_CYCLES_ADDR: read_value = last_compute_cycles;
                PROTOCOL_ERROR_COUNT_ADDR: read_value = protocol_error_count;
                FENCE_SNAPSHOT_VALID_ADDR: read_value = {31'd0, fence_snapshot_valid};
                FENCE_SNAPSHOT_BASE_ADDR + 12'h000: read_value = fence_snapshot_counts[31:0];
                FENCE_SNAPSHOT_BASE_ADDR + 12'h004: read_value = fence_snapshot_counts[63:32];
                FENCE_SNAPSHOT_BASE_ADDR + 12'h008: read_value = fence_snapshot_counts[95:64];
                FENCE_SNAPSHOT_BASE_ADDR + 12'h00C: read_value = fence_snapshot_counts[127:96];
                FENCE_SNAPSHOT_BASE_ADDR + 12'h010: read_value = fence_snapshot_counts[159:128];
                FENCE_SNAPSHOT_BASE_ADDR + 12'h014: read_value = fence_snapshot_counts[191:160];
                FENCE_SNAPSHOT_BASE_ADDR + 12'h018: read_value = fence_snapshot_counts[223:192];
                FENCE_SNAPSHOT_BASE_ADDR + 12'h01C: read_value = fence_snapshot_counts[255:224];
                default: read_value = 32'd0;
            endcase
        end
    endfunction

    always @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            s_axi_bresp <= 2'b00;
            s_axi_bvalid <= 1'b0;
            s_axi_rdata <= 32'd0;
            s_axi_rresp <= 2'b00;
            s_axi_rvalid <= 1'b0;
            aw_pending <= 1'b0;
            w_pending <= 1'b0;
            read_pending <= 1'b0;
            read_addr <= 12'd0;
        end else begin
            if (s_axi_awvalid && s_axi_awready) begin
                aw_pending <= 1'b1;
            end
            if (s_axi_wvalid && s_axi_wready) begin
                w_pending <= 1'b1;
            end
            if (write_fire) begin
                aw_pending <= 1'b0;
                w_pending <= 1'b0;
                // 状态块没有可写寄存器；完成握手并返回 SLVERR，避免 Host 误以为写入生效。
                s_axi_bresp <= 2'b10;
                s_axi_bvalid <= 1'b1;
            end
            if (s_axi_bvalid && s_axi_bready)
                s_axi_bvalid <= 1'b0;

            if (s_axi_arvalid && s_axi_arready) begin
                read_pending <= 1'b1;
                read_addr <= s_axi_araddr;
            end
            if (read_pending && !s_axi_rvalid) begin
                read_pending <= 1'b0;
                s_axi_rdata <= read_value(read_addr);
                s_axi_rresp <= 2'b00;
                s_axi_rvalid <= 1'b1;
            end
            if (s_axi_rvalid && s_axi_rready)
                s_axi_rvalid <= 1'b0;
        end
    end
endmodule
