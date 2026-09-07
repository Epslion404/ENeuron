// XC7Z020 T1 纯 RTL 适配器：四条异步 FIFO + SAMPLE_FENCE + 已签核 NPU 核。
// AXI、DMA、Ethernet 和 PS7 留在本模块之外；本模块只暴露稳定的流接口。
module npu_zynq7020_t1_wrapper #(
    parameter integer FIFO_DEPTH = 16
) (
    input  logic        host_clk,
    input  logic        npu_clk,
    input  logic        bridge_rst,

    input  logic        host_cmd_valid,
    output logic        host_cmd_ready,
    input  logic [127:0] host_cmd_data,
    output logic        host_rsp_valid,
    input  logic        host_rsp_ready,
    output logic [127:0] host_rsp_data,

    input  logic        host_sample_valid,
    output logic        host_sample_ready,
    input  logic [31:0] host_sample_data,
    input  logic [31:0] host_sample_id,
    output logic        host_result_valid,
    input  logic        host_result_ready,
    output logic [31:0] host_result_data,
    output logic [31:0] host_result_sample_id,
    output logic [31:0] host_result_mask_epoch,

    output logic        host_status_irq,
    output logic        host_model_valid,
    output logic        host_mask_valid,
    output logic        host_infer_frozen,
    output logic        host_error
);
    localparam logic [3:0] OP_SAMPLE_FENCE = 4'ha;
    localparam logic [3:0] RSP_FENCE       = 4'hd;

    (* ASYNC_REG = "TRUE" *) logic [1:0] host_rst_sync = 2'b11;
    (* ASYNC_REG = "TRUE" *) logic [1:0] npu_rst_sync = 2'b11;
    logic host_rst;
    logic npu_rst;

    always_ff @(posedge host_clk) begin
        host_rst_sync <= {host_rst_sync[0], bridge_rst};
    end
    always_ff @(posedge npu_clk) begin
        npu_rst_sync <= {npu_rst_sync[0], bridge_rst};
    end
    assign host_rst = host_rst_sync[1];
    assign npu_rst = npu_rst_sync[1];

    // command FIFO: Host -> NPU
    logic cmd_full, cmd_empty, cmd_wr_rst_busy, cmd_rd_rst_busy;
    logic [127:0] cmd_dout;
    logic cmd_wr_en, cmd_rd_en;
    // response FIFO: NPU -> Host
    logic rsp_full, rsp_empty, rsp_wr_rst_busy, rsp_rd_rst_busy;
    logic [127:0] rsp_dout;
    logic rsp_wr_en, rsp_rd_en;
    // sample FIFO: Host -> NPU, payload = {sample_id, sample_data}
    logic sample_full, sample_empty, sample_wr_rst_busy, sample_rd_rst_busy;
    logic [63:0] sample_dout;
    logic sample_wr_en, sample_rd_en;
    // result FIFO: NPU -> Host, payload = {mask_epoch, sample_id, result_data}
    logic result_full, result_empty, result_wr_rst_busy, result_rd_rst_busy;
    logic [95:0] result_dout;
    logic result_wr_en, result_rd_en;

    logic [4:0] unused_cmd_wr_count, unused_cmd_rd_count;
    logic [4:0] unused_rsp_wr_count, unused_rsp_rd_count;
    logic [4:0] unused_sample_wr_count, unused_sample_rd_count;
    logic [4:0] unused_result_wr_count, unused_result_rd_count;

    logic [127:0] core_rsp_payload_raw;
    logic [127:0] rsp_payload_mux;
    logic core_cmd_valid, core_cmd_ready_wire, core_rsp_valid, core_rsp_ready;
    logic [31:0] core_result_data, core_result_sample_id, core_result_mask_epoch;
    logic core_result_valid, core_result_ready;
    logic core_sample_valid, core_sample_ready;
    logic [31:0] core_sample_data, core_sample_id;
    logic core_runtime_idle, core_model_valid, core_mask_valid, core_infer_frozen;
    logic [31:0] core_state_clear_count;
    logic [31:0] core_active_mask_epoch;
    logic core_mask_staging_open;

    logic sample_window_open_npu;
    logic [3:0] sample_count_npu;
    logic sample_window_open_host;
    logic [3:0] sample_write_count_host;
    logic fence_response_pending;
    logic error_response_pending;
    logic [127:0] error_response_payload;
    logic error_sticky_npu;
    (* ASYNC_REG = "TRUE" *) logic [1:0] model_valid_host_sync, mask_valid_host_sync, infer_frozen_host_sync;
    (* ASYNC_REG = "TRUE" *) logic [1:0] error_host_sync;
    logic [31:0] fence_id_npu;
    // Host 窗口状态不能直接在 npu_clk 域采样；这里使用两级同步器。
    (* ASYNC_REG = "TRUE" *) logic sample_window_open_host_npu_d1, sample_window_open_host_npu_d2;
    // 每个时钟域先寄存本地四条 FIFO 的 busy 汇总，再只跨域同步一个 fail-closed bit。
    logic host_local_fifo_busy_reg = 1'b1;
    logic npu_local_fifo_busy_reg = 1'b1;
    (* ASYNC_REG = "TRUE" *) logic [1:0] host_busy_npu_sync = 2'b11;
    (* ASYNC_REG = "TRUE" *) logic [1:0] npu_busy_host_sync = 2'b11;
    wire npu_any_fifo_busy;
    wire error_rsp_valid;

    xpm_fifo_async #(
        .FIFO_MEMORY_TYPE("auto"), .ECC_MODE("no_ecc"), .RELATED_CLOCKS(0),
        .SIM_ASSERT_CHK(1), .FIFO_WRITE_DEPTH(FIFO_DEPTH),
        .WRITE_DATA_WIDTH(128), .WR_DATA_COUNT_WIDTH(5), .PROG_FULL_THRESH(10),
        .FULL_RESET_VALUE(0), .USE_ADV_FEATURES("0000"), .READ_MODE("fwft"),
        .FIFO_READ_LATENCY(0), .READ_DATA_WIDTH(128), .RD_DATA_COUNT_WIDTH(5),
        .PROG_EMPTY_THRESH(10), .DOUT_RESET_VALUE("0"), .CDC_SYNC_STAGES(2),
        .WAKEUP_TIME(0)
    ) command_fifo (
        .sleep(1'b0), .rst(host_rst), .wr_clk(host_clk), .wr_en(cmd_wr_en),
        .din(host_cmd_data), .full(cmd_full), .prog_full(),
        .wr_data_count(unused_cmd_wr_count), .overflow(), .wr_rst_busy(cmd_wr_rst_busy),
        .almost_full(), .wr_ack(), .rd_clk(npu_clk), .rd_en(cmd_rd_en),
        .dout(cmd_dout), .empty(cmd_empty), .prog_empty(),
        .rd_data_count(unused_cmd_rd_count), .underflow(), .rd_rst_busy(cmd_rd_rst_busy),
        .almost_empty(), .data_valid(), .injectsbiterr(1'b0), .injectdbiterr(1'b0),
        .sbiterr(), .dbiterr()
    );

    xpm_fifo_async #(
        .FIFO_MEMORY_TYPE("auto"), .ECC_MODE("no_ecc"), .RELATED_CLOCKS(0),
        .SIM_ASSERT_CHK(1), .FIFO_WRITE_DEPTH(FIFO_DEPTH),
        .WRITE_DATA_WIDTH(128), .WR_DATA_COUNT_WIDTH(5), .PROG_FULL_THRESH(10),
        .FULL_RESET_VALUE(0), .USE_ADV_FEATURES("0000"), .READ_MODE("fwft"),
        .FIFO_READ_LATENCY(0), .READ_DATA_WIDTH(128), .RD_DATA_COUNT_WIDTH(5),
        .PROG_EMPTY_THRESH(10), .DOUT_RESET_VALUE("0"), .CDC_SYNC_STAGES(2),
        .WAKEUP_TIME(0)
    ) response_fifo (
        .sleep(1'b0), .rst(npu_rst), .wr_clk(npu_clk), .wr_en(rsp_wr_en),
        .din(rsp_payload_mux), .full(rsp_full), .prog_full(),
        .wr_data_count(unused_rsp_wr_count), .overflow(), .wr_rst_busy(rsp_wr_rst_busy),
        .almost_full(), .wr_ack(), .rd_clk(host_clk), .rd_en(rsp_rd_en),
        .dout(rsp_dout), .empty(rsp_empty), .prog_empty(),
        .rd_data_count(unused_rsp_rd_count), .underflow(), .rd_rst_busy(rsp_rd_rst_busy),
        .almost_empty(), .data_valid(), .injectsbiterr(1'b0), .injectdbiterr(1'b0),
        .sbiterr(), .dbiterr()
    );

    xpm_fifo_async #(
        .FIFO_MEMORY_TYPE("auto"), .ECC_MODE("no_ecc"), .RELATED_CLOCKS(0),
        .SIM_ASSERT_CHK(1), .FIFO_WRITE_DEPTH(FIFO_DEPTH),
        .WRITE_DATA_WIDTH(64), .WR_DATA_COUNT_WIDTH(5), .PROG_FULL_THRESH(10),
        .FULL_RESET_VALUE(0), .USE_ADV_FEATURES("0000"), .READ_MODE("fwft"),
        .FIFO_READ_LATENCY(0), .READ_DATA_WIDTH(64), .RD_DATA_COUNT_WIDTH(5),
        .PROG_EMPTY_THRESH(10), .DOUT_RESET_VALUE("0"), .CDC_SYNC_STAGES(2),
        .WAKEUP_TIME(0)
    ) sample_fifo (
        .sleep(1'b0), .rst(host_rst), .wr_clk(host_clk), .wr_en(sample_wr_en),
        .din({host_sample_id, host_sample_data}), .full(sample_full), .prog_full(),
        .wr_data_count(unused_sample_wr_count), .overflow(), .wr_rst_busy(sample_wr_rst_busy),
        .almost_full(), .wr_ack(), .rd_clk(npu_clk), .rd_en(sample_rd_en),
        .dout(sample_dout), .empty(sample_empty), .prog_empty(),
        .rd_data_count(unused_sample_rd_count), .underflow(), .rd_rst_busy(sample_rd_rst_busy),
        .almost_empty(), .data_valid(), .injectsbiterr(1'b0), .injectdbiterr(1'b0),
        .sbiterr(), .dbiterr()
    );

    xpm_fifo_async #(
        .FIFO_MEMORY_TYPE("auto"), .ECC_MODE("no_ecc"), .RELATED_CLOCKS(0),
        .SIM_ASSERT_CHK(1), .FIFO_WRITE_DEPTH(FIFO_DEPTH),
        .WRITE_DATA_WIDTH(96), .WR_DATA_COUNT_WIDTH(5), .PROG_FULL_THRESH(10),
        .FULL_RESET_VALUE(0), .USE_ADV_FEATURES("0000"), .READ_MODE("fwft"),
        .FIFO_READ_LATENCY(0), .READ_DATA_WIDTH(96), .RD_DATA_COUNT_WIDTH(5),
        .PROG_EMPTY_THRESH(10), .DOUT_RESET_VALUE("0"), .CDC_SYNC_STAGES(2),
        .WAKEUP_TIME(0)
    ) result_fifo (
        .sleep(1'b0), .rst(npu_rst), .wr_clk(npu_clk), .wr_en(result_wr_en),
        .din({core_result_mask_epoch, core_result_sample_id, core_result_data}),
        .full(result_full), .prog_full(), .wr_data_count(unused_result_wr_count),
        .overflow(), .wr_rst_busy(result_wr_rst_busy), .almost_full(), .wr_ack(),
        .rd_clk(host_clk), .rd_en(result_rd_en), .dout(result_dout),
        .empty(result_empty), .prog_empty(), .rd_data_count(unused_result_rd_count),
        .underflow(), .rd_rst_busy(result_rd_rst_busy), .almost_empty(), .data_valid(),
        .injectsbiterr(1'b0), .injectdbiterr(1'b0), .sbiterr(), .dbiterr()
    );

    wire [3:0] command_opcode = cmd_dout[127:124];
    wire command_is_fence = command_opcode == OP_SAMPLE_FENCE;
    wire command_fields_bad =
        |cmd_dout[87:32] ||
        ((command_opcode != 4'h9) && (|cmd_dout[123:120])) ||
        ((command_opcode == 4'h9) && (|cmd_dout[123:121])) ||
        (command_is_fence && (|cmd_dout[119:88]));
    wire command_fifo_ready_npu = !npu_rst && !npu_any_fifo_busy;
    wire response_fifo_ready_npu = !npu_rst && !npu_any_fifo_busy && !rsp_full;
    wire result_fifo_ready_npu = !npu_rst && !npu_any_fifo_busy && !result_full;
    wire fence_staging_blocked = command_is_fence && core_mask_staging_open;
    wire host_local_fifo_busy = cmd_wr_rst_busy || sample_wr_rst_busy ||
        rsp_rd_rst_busy || result_rd_rst_busy;
    wire npu_local_fifo_busy = cmd_rd_rst_busy || sample_rd_rst_busy ||
        rsp_wr_rst_busy || result_wr_rst_busy;
    wire host_any_fifo_busy = host_local_fifo_busy_reg || npu_busy_host_sync[1];
    assign npu_any_fifo_busy = npu_local_fifo_busy_reg || host_busy_npu_sync[1];

    always_ff @(posedge host_clk) begin
        if (host_rst) begin
            host_local_fifo_busy_reg <= 1'b1;
            npu_busy_host_sync <= 2'b11;
        end else begin
            host_local_fifo_busy_reg <= host_local_fifo_busy;
            npu_busy_host_sync <= {npu_busy_host_sync[0], npu_local_fifo_busy_reg};
        end
    end

    always_ff @(posedge npu_clk) begin
        if (npu_rst) begin
            npu_local_fifo_busy_reg <= 1'b1;
            host_busy_npu_sync <= 2'b11;
        end else begin
            npu_local_fifo_busy_reg <= npu_local_fifo_busy;
            host_busy_npu_sync <= {host_busy_npu_sync[0], host_local_fifo_busy_reg};
        end
    end

    assign host_cmd_ready = !host_rst && !host_any_fifo_busy && !cmd_full;
    assign cmd_wr_en = host_cmd_valid && host_cmd_ready;
    assign host_rsp_valid = !host_rst && !host_any_fifo_busy && !rsp_empty;
    assign host_rsp_data = rsp_dout;
    assign rsp_rd_en = host_rsp_valid && host_rsp_ready;
    assign host_status_irq = host_rsp_valid;

    // Host 只在实际消费 fence 响应后打开一个样本写入窗口。
    always_ff @(posedge host_clk) begin
        if (host_rst) begin
            sample_window_open_host <= 1'b0;
            sample_write_count_host <= '0;
        end else begin
            // 以 Host 域实际消费的 fence 响应作为窗口授权，避免额外的手写 toggle CDC。
            if (rsp_rd_en && rsp_dout[127:124] == RSP_FENCE) begin
                sample_window_open_host <= 1'b1;
                sample_write_count_host <= '0;
            end else if (sample_window_open_host && sample_wr_en) begin
                if (sample_write_count_host == 4'd7) begin
                    sample_window_open_host <= 1'b0;
                    sample_write_count_host <= '0;
                end else begin
                    sample_write_count_host <= sample_write_count_host + 1'b1;
                end
            end
        end
    end

    assign host_sample_ready = !host_rst && !host_any_fifo_busy && !sample_full
        && sample_window_open_host && (sample_write_count_host < 4'd8);
    assign sample_wr_en = host_sample_valid && host_sample_ready;

    assign host_result_valid = !host_rst && !host_any_fifo_busy && !result_empty;
    assign host_result_data = result_dout[31:0];
    assign host_result_sample_id = result_dout[63:32];
    assign host_result_mask_epoch = result_dout[95:64];
    assign result_rd_en = host_result_valid && host_result_ready;

    assign host_model_valid = model_valid_host_sync[1];
    assign host_mask_valid = mask_valid_host_sync[1];
    assign host_infer_frozen = infer_frozen_host_sync[1];
    assign host_error = error_host_sync[1];

    // 命令 FIFO 只有在核心能够接收、或 fence 能够原子地产生确认时才出队。
    assign core_cmd_valid = command_fifo_ready_npu && !cmd_empty && !command_is_fence &&
        !command_fields_bad && !error_response_pending;
    assign cmd_rd_en = command_fifo_ready_npu && !cmd_empty &&
        ((command_is_fence && !fence_response_pending && response_fifo_ready_npu &&
          core_sample_ready && !core_result_valid && !core_rsp_valid &&
          !sample_window_open_npu && !sample_window_open_host_npu_d2 &&
          !core_mask_staging_open) ||
         ((command_fields_bad || fence_staging_blocked) &&
          !fence_response_pending && !error_response_pending &&
          response_fifo_ready_npu && !core_rsp_valid) ||
         (!command_is_fence && !command_fields_bad && !error_response_pending &&
          core_cmd_ready_wire));

    assign core_rsp_ready = response_fifo_ready_npu && !fence_response_pending &&
        !error_response_pending;

    assign core_sample_valid = sample_window_open_npu && !sample_empty &&
        !sample_rd_rst_busy && !npu_rst;
    assign core_sample_data = sample_dout[31:0];
    assign core_sample_id = sample_dout[63:32];
    assign sample_rd_en = core_sample_valid && core_sample_ready;

    assign core_result_ready = result_fifo_ready_npu;
    assign result_wr_en = core_result_valid && core_result_ready;

    npu_eneuron_single_clock_skeleton core (
        .clk(npu_clk), .rst(npu_rst),
        .cmd_payload(cmd_dout), .cmd_valid(core_cmd_valid), .cmd_ready(core_cmd_ready_wire),
        .rsp_payload(core_rsp_payload_raw), .rsp_valid(core_rsp_valid), .rsp_ready(core_rsp_ready),
        .sample_data(core_sample_data), .sample_id(core_sample_id),
        .sample_valid(core_sample_valid), .sample_ready(core_sample_ready),
        .result_data(core_result_data), .result_sample_id(core_result_sample_id),
        .result_mask_epoch(core_result_mask_epoch), .result_valid(core_result_valid),
        .result_ready(core_result_ready), .runtime_idle(core_runtime_idle),
        .model_valid(core_model_valid), .mask_valid(core_mask_valid),
        .infer_frozen(core_infer_frozen), .state_clear_count(core_state_clear_count),
        .active_mask_epoch(core_active_mask_epoch), .mask_staging_open(core_mask_staging_open)
    );

    always_ff @(posedge npu_clk) begin
        if (npu_rst) begin
            sample_window_open_npu <= 1'b0;
            sample_count_npu <= '0;
            fence_response_pending <= 1'b0;
            error_response_pending <= 1'b0;
            error_response_payload <= '0;
            fence_id_npu <= '0;
            error_sticky_npu <= 1'b0;
            sample_window_open_host_npu_d1 <= 1'b0;
            sample_window_open_host_npu_d2 <= 1'b0;
        end else begin
            sample_window_open_host_npu_d1 <= sample_window_open_host;
            sample_window_open_host_npu_d2 <= sample_window_open_host_npu_d1;
            if (cmd_rd_en && command_is_fence && !command_fields_bad && !core_mask_staging_open) begin
                sample_window_open_npu <= 1'b1;
                sample_count_npu <= '0;
                fence_response_pending <= 1'b1;
                fence_id_npu <= cmd_dout[31:0];
            end
            if (cmd_rd_en && (command_fields_bad || fence_staging_blocked)) begin
                error_response_pending <= 1'b1;
                error_response_payload <= {
                    RSP_FENCE + 1'b1, 4'h1, command_opcode, 4'hf,
                    cmd_dout[31:0], cmd_dout[119:88], 48'd0
                };
            end
            if (sample_rd_en) begin
                if (sample_count_npu == 4'd7) begin
                    sample_window_open_npu <= 1'b0;
                    sample_count_npu <= '0;
                end else begin
                    sample_count_npu <= sample_count_npu + 1'b1;
                end
            end
            if (fence_response_pending && response_fifo_ready_npu) begin
                fence_response_pending <= 1'b0;
            end
            if (error_rsp_valid) begin
                error_response_pending <= 1'b0;
                error_sticky_npu <= 1'b1;
            end
            if (core_rsp_valid && core_rsp_ready && core_rsp_payload_raw[127:124] == 4'he)
                error_sticky_npu <= 1'b1;
        end
    end

    wire fence_rsp_valid = fence_response_pending && response_fifo_ready_npu;
    assign error_rsp_valid = error_response_pending && !fence_response_pending && response_fifo_ready_npu;
    assign rsp_wr_en = fence_rsp_valid || error_rsp_valid || (core_rsp_valid && core_rsp_ready);
    assign rsp_payload_mux = fence_response_pending ?
        {RSP_FENCE, 4'd0, OP_SAMPLE_FENCE, 4'd0, fence_id_npu,
         core_active_mask_epoch, 48'd0} :
        error_response_pending ? error_response_payload : core_rsp_payload_raw;

    // 状态摘要在 Host 域同步，避免把 NPU 域状态直接组合跨域。
    always_ff @(posedge host_clk) begin
        if (host_rst) begin
            model_valid_host_sync <= '0;
            mask_valid_host_sync <= '0;
            infer_frozen_host_sync <= '0;
            error_host_sync <= '0;
        end else begin
            model_valid_host_sync <= {model_valid_host_sync[0], core_model_valid};
            mask_valid_host_sync <= {mask_valid_host_sync[0], core_mask_valid};
            infer_frozen_host_sync <= {infer_frozen_host_sync[0], core_infer_frozen};
            error_host_sync <= {error_host_sync[0], error_sticky_npu};
        end
    end

`ifndef SYNTHESIS
    always @(posedge npu_clk) begin
        if (cmd_rd_en)
            $display("NPU_T1 CMD_DEQUEUE op=%h empty=%0d core_valid=%0d core_ready=%0d", command_opcode, cmd_empty, core_cmd_valid, core_cmd_ready_wire);
        if (core_cmd_valid && core_cmd_ready_wire)
            $display("NPU_T1 CORE_CMD_ACCEPT op=%h", command_opcode);
        if (core_rsp_valid)
            $display("NPU_T1 CORE_RSP valid=%0d ready=%0d payload=%h", core_rsp_valid, core_rsp_ready, core_rsp_payload_raw);
        if (rsp_wr_en)
            $display("NPU_T1 RSP_FIFO_WRITE fence=%0d payload=%h", fence_rsp_valid, rsp_payload_mux);
        if (cmd_rd_en && command_is_fence)
            $display("NPU_T1 FENCE_ACCEPT id=%08x", cmd_dout[31:0]);
        if (sample_rd_en && sample_count_npu == 4'd7)
            $display("NPU_T1 SAMPLE_WINDOW_COMPLETE");
        if (result_wr_en && core_result_sample_id == 32'd0)
            $display("NPU_T1 RESULT_PUSH");
    end
    always @(posedge host_clk) begin
        if (host_rsp_valid || rsp_rd_en)
            $display("NPU_T1 HOST_RSP valid=%0d ready=%0d data=%h", host_rsp_valid, host_rsp_ready, host_rsp_data);
    end
`endif
endmodule
