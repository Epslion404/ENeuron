// Vivado BD 入口：将标准 AXI-Stream 接口映射到 B2 packet/NPU 适配器。
// 首个物理切片让 Host/NPU 共用 FCLK0，后续再单独验证异步时钟部署。
module b2_npu_axis_top (
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME axis_aclk, ASSOCIATED_BUSIF S_AXIS:M_AXIS, ASSOCIATED_RESET axis_aresetn, FREQ_HZ 200000000" *)
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 axis_aclk CLK" *)
    input  logic        axis_aclk,
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME axis_aresetn, POLARITY ACTIVE_LOW" *)
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 axis_aresetn RST" *)
    input  logic        axis_aresetn,

    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AXIS, TDATA_NUM_BYTES 4, FREQ_HZ 200000000, ASSOCIATED_CLK axis_aclk, TDEST_WIDTH 0, TID_WIDTH 0, TUSER_WIDTH 0" *)
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TDATA" *)
    input  logic [31:0] s_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TKEEP" *)
    input  logic [3:0]  s_axis_tkeep,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TLAST" *)
    input  logic        s_axis_tlast,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TVALID" *)
    input  logic        s_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TREADY" *)
    output logic        s_axis_tready,

    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME M_AXIS, TDATA_NUM_BYTES 4, FREQ_HZ 200000000, ASSOCIATED_CLK axis_aclk, TDEST_WIDTH 0, TID_WIDTH 0, TUSER_WIDTH 0" *)
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TDATA" *)
    output logic [31:0] m_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TKEEP" *)
    output logic [3:0]  m_axis_tkeep,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TLAST" *)
    output logic        m_axis_tlast,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TVALID" *)
    output logic        m_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TREADY" *)
    input  logic        m_axis_tready,

    output logic        packet_error_valid,
    output logic [3:0]  packet_error_code,
    output logic        packet_busy,
    output logic        npu_error,
    output logic        npu_model_valid,
    output logic        npu_mask_valid,
    output logic        npu_infer_frozen,
    output logic        npu_status_irq
);
    b2_npu_packet_adapter adapter (
        .host_clk(axis_aclk), .npu_clk(axis_aclk),
        .bridge_rst(!axis_aresetn),
        .s_valid(s_axis_tvalid), .s_ready(s_axis_tready),
        .s_data(s_axis_tdata), .s_keep(s_axis_tkeep), .s_last(s_axis_tlast),
        .m_valid(m_axis_tvalid), .m_ready(m_axis_tready),
        .m_data(m_axis_tdata), .m_keep(m_axis_tkeep), .m_last(m_axis_tlast),
        .error_valid(packet_error_valid), .error_code(packet_error_code),
        .busy(packet_busy), .host_error(npu_error),
        .host_model_valid(npu_model_valid), .host_mask_valid(npu_mask_valid),
        .host_infer_frozen(npu_infer_frozen), .host_status_irq(npu_status_irq)
    );
endmodule
