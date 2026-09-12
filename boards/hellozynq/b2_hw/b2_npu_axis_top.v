// Vivado BD ?????? AXI-Stream ????? B2 packet/NPU ????
// ??????? Host/NPU ?? FCLK0???????????????
module b2_npu_axis_top (
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME axis_aclk, ASSOCIATED_BUSIF S_AXIS:M_AXIS, ASSOCIATED_RESET axis_aresetn, FREQ_HZ 200000000" *)
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 axis_aclk CLK" *)
    input  wire        axis_aclk,
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME axis_aresetn, POLARITY ACTIVE_LOW" *)
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 axis_aresetn RST" *)
    input  wire        axis_aresetn,

    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AXIS, TDATA_NUM_BYTES 4, FREQ_HZ 200000000, ASSOCIATED_CLK axis_aclk, TDEST_WIDTH 0, TID_WIDTH 0, TUSER_WIDTH 0" *)
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TDATA" *)
    input  wire [31:0] s_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TKEEP" *)
    input  wire [3:0]  s_axis_tkeep,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TLAST" *)
    input  wire        s_axis_tlast,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TVALID" *)
    input  wire        s_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TREADY" *)
    output wire        s_axis_tready,

    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME M_AXIS, TDATA_NUM_BYTES 4, FREQ_HZ 200000000, ASSOCIATED_CLK axis_aclk, TDEST_WIDTH 0, TID_WIDTH 0, TUSER_WIDTH 0" *)
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TDATA" *)
    output wire [31:0] m_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TKEEP" *)
    output wire [3:0]  m_axis_tkeep,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TLAST" *)
    output wire        m_axis_tlast,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TVALID" *)
    output wire        m_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TREADY" *)
    input  wire        m_axis_tready,

    output wire        packet_error_valid,
    output wire [3:0]  packet_error_code,
    output wire        packet_busy,
    output wire        npu_error,
    output wire        npu_model_valid,
    output wire        npu_mask_valid,
    output wire        npu_infer_frozen,
    output wire        npu_status_irq,
    output wire [31:0] command_accept_count,
    output wire [31:0] command_complete_count,
    output wire [31:0] sample_accept_count,
    output wire [31:0] sample_complete_count,
    output wire [31:0] response_accept_count,
    output wire [31:0] response_complete_count,
    output wire [31:0] result_accept_count,
    output wire [31:0] result_complete_count,
    output wire [31:0] execute_group_count,
    output wire [31:0] skip_group_count,
    output wire [31:0] runtime_status,
    output wire [31:0] active_mask_epoch,
    output wire [31:0] pending_mask_epoch,
    output wire [31:0] last_compute_cycles,
    output wire [31:0] protocol_error_count,
    output wire        fence_snapshot_valid,
    output wire [255:0] fence_snapshot_counts
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
         .host_infer_frozen(npu_infer_frozen), .host_status_irq(npu_status_irq),
         .command_accept_count(command_accept_count),
         .command_complete_count(command_complete_count),
         .sample_accept_count(sample_accept_count),
         .sample_complete_count(sample_complete_count),
         .response_accept_count(response_accept_count),
         .response_complete_count(response_complete_count),
         .result_accept_count(result_accept_count),
         .result_complete_count(result_complete_count),
         .execute_group_count(execute_group_count),
         .skip_group_count(skip_group_count),
         .runtime_status(runtime_status),
         .active_mask_epoch(active_mask_epoch),
         .pending_mask_epoch(pending_mask_epoch),
         .last_compute_cycles(last_compute_cycles),
         .protocol_error_count(protocol_error_count),
         .fence_snapshot_valid(fence_snapshot_valid),
         .fence_snapshot_counts(fence_snapshot_counts)
     );
endmodule
