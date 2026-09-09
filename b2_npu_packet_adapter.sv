// B2 外层 packet 与 T1 wrapper 的最小集成适配器。
// ingress/egress 在 Host 域运行；T1 wrapper 内部保留 Host/NPU 双时钟和四条异步 FIFO。
// 当前 wrapper 没有 packet 边界 sideband，因此每个 response word 独立封装为一帧，
// 并在单个 outstanding packet 场景下回显最近一次命令/样本元数据。
module b2_npu_packet_adapter #(
    parameter integer FIFO_DEPTH = 16
) (
    input  logic host_clk,
    input  logic npu_clk,
    input  logic bridge_rst,

    input  logic s_valid,
    output logic s_ready,
    input  logic [31:0] s_data,
    input  logic [3:0] s_keep,
    input  logic s_last,

    output logic m_valid,
    input  logic m_ready,
    output logic [31:0] m_data,
    output logic [3:0] m_keep,
    output logic m_last,

    output logic error_valid,
    output logic [3:0] error_code,
    output logic busy,
    output logic host_error,
    output logic host_model_valid,
    output logic host_mask_valid,
    output logic host_infer_frozen,
    output logic host_status_irq
);
    logic ingress_cmd_valid;
    logic ingress_cmd_ready;
    logic [127:0] ingress_cmd_data;
    logic [31:0] ingress_cmd_sequence;
    logic [31:0] ingress_cmd_model_id;
    logic [31:0] ingress_cmd_mask_epoch;
    logic ingress_sample_valid;
    logic ingress_sample_ready;
    logic [31:0] ingress_sample_data;
    logic [31:0] ingress_sample_id;
    logic [31:0] ingress_sample_sequence;
    logic [31:0] ingress_sample_model_id;
    logic [31:0] ingress_sample_mask_epoch;
    logic ingress_error_valid;
    logic [3:0] ingress_error_code;
    logic ingress_busy;

    logic wrapper_cmd_valid;
    logic wrapper_cmd_ready;
    logic wrapper_rsp_valid;
    logic wrapper_rsp_ready;
    logic [127:0] wrapper_rsp_data;
    logic wrapper_sample_valid;
    logic wrapper_sample_ready;
    logic wrapper_result_valid;
    logic wrapper_result_ready;
    logic [31:0] wrapper_result_data;
    logic [31:0] wrapper_result_sample_id;
    logic [31:0] wrapper_result_mask_epoch;
    logic wrapper_status_irq;
    logic wrapper_model_valid;
    logic wrapper_mask_valid;
    logic wrapper_infer_frozen;
    logic wrapper_error;

    logic egress_rsp_valid;
    logic egress_rsp_ready;
    logic egress_result_valid;
    logic egress_result_ready;
    logic egress_error_valid;
    logic [3:0] egress_error_code;
    logic egress_busy;

    logic [31:0] cmd_sequence_reg;
    logic [31:0] cmd_model_id_reg;
    logic [31:0] cmd_mask_epoch_reg;
    logic [31:0] sample_sequence_reg;
    logic [31:0] sample_model_id_reg;

    b2_packet_ingress ingress (
        .clk(host_clk), .rst(bridge_rst),
        .s_valid(s_valid), .s_ready(s_ready), .s_data(s_data),
        .s_keep(s_keep), .s_last(s_last),
        .cmd_valid(ingress_cmd_valid), .cmd_ready(ingress_cmd_ready),
        .cmd_data(ingress_cmd_data), .cmd_sequence(ingress_cmd_sequence),
        .cmd_model_id(ingress_cmd_model_id), .cmd_mask_epoch(ingress_cmd_mask_epoch),
        .sample_valid(ingress_sample_valid), .sample_ready(ingress_sample_ready),
        .sample_data(ingress_sample_data), .sample_id(ingress_sample_id),
        .sample_sequence(ingress_sample_sequence), .sample_model_id(ingress_sample_model_id),
        .sample_mask_epoch(ingress_sample_mask_epoch),
        .error_valid(ingress_error_valid), .error_code(ingress_error_code),
        .busy(ingress_busy)
    );

    assign wrapper_cmd_valid = ingress_cmd_valid;
    assign ingress_cmd_ready = wrapper_cmd_ready;
    assign wrapper_sample_valid = ingress_sample_valid;
    assign ingress_sample_ready = wrapper_sample_ready;

    npu_zynq7020_t1_wrapper #(.FIFO_DEPTH(FIFO_DEPTH)) wrapper (
        .host_clk(host_clk), .npu_clk(npu_clk), .bridge_rst(bridge_rst),
        .host_cmd_valid(wrapper_cmd_valid), .host_cmd_ready(wrapper_cmd_ready),
        .host_cmd_data(ingress_cmd_data),
        .host_rsp_valid(wrapper_rsp_valid), .host_rsp_ready(wrapper_rsp_ready),
        .host_rsp_data(wrapper_rsp_data),
        .host_sample_valid(wrapper_sample_valid), .host_sample_ready(wrapper_sample_ready),
        .host_sample_data(ingress_sample_data), .host_sample_id(ingress_sample_id),
        .host_result_valid(wrapper_result_valid), .host_result_ready(wrapper_result_ready),
        .host_result_data(wrapper_result_data),
        .host_result_sample_id(wrapper_result_sample_id),
        .host_result_mask_epoch(wrapper_result_mask_epoch),
        .host_status_irq(wrapper_status_irq), .host_model_valid(wrapper_model_valid),
        .host_mask_valid(wrapper_mask_valid), .host_infer_frozen(wrapper_infer_frozen),
        .host_error(wrapper_error)
    );

    // wrapper 的公开 response 没有 last；每个 response word 独立成为一帧，
    // 避免猜测核心内部命令完成边界。
    assign egress_rsp_valid = wrapper_rsp_valid;
    assign wrapper_rsp_ready = egress_rsp_ready;
    assign egress_result_valid = wrapper_result_valid;
    assign wrapper_result_ready = egress_result_ready;

    b2_packet_egress egress (
        .clk(host_clk), .rst(bridge_rst),
        .rsp_valid(egress_rsp_valid), .rsp_ready(egress_rsp_ready),
        .rsp_data(wrapper_rsp_data), .rsp_last(1'b1),
        .rsp_sequence(cmd_sequence_reg), .rsp_model_id(cmd_model_id_reg),
        .rsp_mask_epoch(cmd_mask_epoch_reg), .rsp_status(32'd0),
        .result_valid(egress_result_valid), .result_ready(egress_result_ready),
        .result_data(wrapper_result_data), .result_sample_id(wrapper_result_sample_id),
        .result_model_id(sample_model_id_reg), .result_mask_epoch(wrapper_result_mask_epoch),
        .result_sequence(sample_sequence_reg), .result_status(32'd0),
        .m_valid(m_valid), .m_ready(m_ready), .m_data(m_data), .m_keep(m_keep),
        .m_last(m_last), .error_valid(egress_error_valid), .error_code(egress_error_code),
        .busy(egress_busy)
    );

    always_ff @(posedge host_clk) begin
        if (bridge_rst) begin
            cmd_sequence_reg <= '0;
            cmd_model_id_reg <= '0;
            cmd_mask_epoch_reg <= '0;
            sample_sequence_reg <= '0;
            sample_model_id_reg <= '0;
        end else begin
            if (ingress_cmd_valid && ingress_cmd_ready) begin
                cmd_sequence_reg <= ingress_cmd_sequence;
                cmd_model_id_reg <= ingress_cmd_model_id;
                cmd_mask_epoch_reg <= ingress_cmd_mask_epoch;
            end
            if (ingress_sample_valid && ingress_sample_ready) begin
                sample_sequence_reg <= ingress_sample_sequence;
                sample_model_id_reg <= ingress_sample_model_id;
            end
        end
    end

    assign error_valid = ingress_error_valid || egress_error_valid;
    assign error_code = ingress_error_valid ? ingress_error_code : egress_error_code;
    assign busy = ingress_busy || egress_busy || wrapper_status_irq;
    assign host_error = wrapper_error;
    assign host_model_valid = wrapper_model_valid;
    assign host_mask_valid = wrapper_mask_valid;
    assign host_infer_frozen = wrapper_infer_frozen;
    assign host_status_irq = wrapper_status_irq;
endmodule
