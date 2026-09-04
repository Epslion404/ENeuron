// 传统 NPU + ENeuron 单时钟协议骨架。
//
// 这是第一条 RTL 垂直切片：它只冻结公开 ready/valid、模型顺序装载、
// 固定 8/10 beat 计数、结果背压和 fail-closed 行为。模型数据暂存但不参与
// 乘加，结果使用零占位；mask 只实现 staging/published/首拍激活账本，真正的
// 门控计算和计算调度器属于后续切片。
`timescale 1ns/1ps
module npu_eneuron_single_clock_skeleton (
    input  logic        clk,
    input  logic        rst,

    input  logic [127:0] cmd_payload,
    input  logic         cmd_valid,
    output logic         cmd_ready,
    output logic [127:0] rsp_payload,
    output logic         rsp_valid,
    input  logic         rsp_ready,

    input  logic [31:0] sample_data,
    input  logic [31:0] sample_id,
    input  logic        sample_valid,
    output logic        sample_ready,

    output logic [31:0] result_data,
    output logic [31:0] result_sample_id,
    output logic [31:0] result_mask_epoch,
    output logic        result_valid,
    input  logic        result_ready,

    output logic        runtime_idle,
    output logic        model_valid,
    output logic        mask_valid
);
    localparam logic [3:0] OP_MODEL_BEGIN  = 4'h1;
    localparam logic [3:0] OP_MODEL_DATA   = 4'h2;
    localparam logic [3:0] OP_MODEL_COMMIT = 4'h3;
    localparam logic [3:0] OP_MASK_BEGIN    = 4'h4;
    localparam logic [3:0] OP_MASK_DATA     = 4'h5;
    localparam logic [3:0] OP_MASK_COMMIT   = 4'h6;
    localparam logic [3:0] RSP_ERROR       = 4'he;

    localparam logic [1:0] MODEL_EMPTY     = 2'd0;
    localparam logic [1:0] MODEL_LOADING   = 2'd1;
    localparam logic [1:0] MODEL_COMPLETE  = 2'd2;
    localparam logic [1:0] MODEL_COMMITTED = 2'd3;

    localparam logic [1:0] MASK_EMPTY      = 2'd0;
    localparam logic [1:0] MASK_LOADING    = 2'd1;
    localparam logic [1:0] MASK_COMPLETE   = 2'd2;
    localparam logic [1:0] MASK_PUBLISHED  = 2'd3;

    logic [1:0]  model_state;
    logic [9:0]  model_word_index;
    logic        sample_active;
    logic [3:0]  sample_beat_index;
    logic [31:0] sample_id_reg;
    logic        result_active;
    logic [3:0]  result_beat_index;
    logic [31:0] result_sample_id_reg;
    logic [31:0] sample_mask_epoch_reg;
    logic [31:0] result_mask_epoch_reg;

    logic [1:0]  mask_state;
    logic [4:0]  mask_word_index;
    logic [31:0] mask_staging_epoch;
    logic [31:0] mask_published_epoch;
    logic [31:0] mask_active_epoch;

    // 634 words are deliberately represented by a small staging array in this
    // protocol slice. Later implementation may infer BRAM without changing the port contract.
    logic [31:0] model_staging [0:633];
    logic [31:0] mask_staging [0:18];

    wire [3:0]  cmd_opcode = cmd_payload[127:124];
    wire [31:0] cmd_word = cmd_payload[31:0];
    wire [31:0] cmd_epoch = cmd_payload[119:88];

    function automatic logic [127:0] make_error_response(
        input logic [3:0] error_code,
        input logic [3:0] rejected_opcode,
        input logic [3:0] state_code,
        input logic [31:0] word_index,
        input logic [31:0] epoch
    );
        begin
            make_error_response = {
                RSP_ERROR, error_code, rejected_opcode, state_code,
                word_index, epoch, 48'd0
            };
        end
    endfunction

    // 配置握手优先于样本首拍；响应槽背压期间整个命令口停住。
    always_comb begin
        cmd_ready = !rsp_valid && !sample_active && !result_active;
        // 输入流在首 beat 后仍需保持 ready，直到第 8 beat 完成；结果槽出现后才停止。
        sample_ready = model_valid && !result_active && !rsp_valid && !cmd_valid;
        result_valid = result_active;
        result_data = 32'd0;
        result_sample_id = result_sample_id_reg;
        result_mask_epoch = result_mask_epoch_reg;
        runtime_idle = !sample_active && !result_active && !rsp_valid &&
                       ((model_state == MODEL_EMPTY) || (model_state == MODEL_COMMITTED)) &&
                       (mask_state == MASK_EMPTY) &&
                       !cmd_valid;
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            model_state <= MODEL_EMPTY;
            model_word_index <= 10'd0;
            model_valid <= 1'b0;
            sample_active <= 1'b0;
            sample_beat_index <= 4'd0;
            sample_id_reg <= 32'd0;
            result_active <= 1'b0;
            result_beat_index <= 4'd0;
            result_sample_id_reg <= 32'd0;
            sample_mask_epoch_reg <= 32'd0;
            result_mask_epoch_reg <= 32'd0;
            mask_state <= MASK_EMPTY;
            mask_word_index <= 5'd0;
            mask_staging_epoch <= 32'd0;
            mask_published_epoch <= 32'd0;
            mask_active_epoch <= 32'd0;
            mask_valid <= 1'b0;
            rsp_valid <= 1'b0;
            rsp_payload <= 128'd0;
        end else begin
            // 单槽错误响应：消费前保持 payload/valid 稳定，消费拍不接受新命令。
            if (rsp_valid && rsp_ready) begin
                rsp_valid <= 1'b0;
            end

            if (cmd_valid && cmd_ready) begin
                if (cmd_opcode == OP_MODEL_BEGIN) begin
                    if (model_state == MODEL_EMPTY) begin
                        model_state <= MODEL_LOADING;
                        model_word_index <= 10'd0;
                        model_valid <= 1'b0;
                    end else begin
                        rsp_valid <= 1'b1;
                        rsp_payload <= make_error_response(
                            4'h1, cmd_opcode, {2'd0, model_state},
                            {22'd0, model_word_index}, 32'd0
                        );
                    end
                end else if (cmd_opcode == OP_MODEL_DATA) begin
                    if (model_state == MODEL_LOADING && model_word_index < 10'd634) begin
                        model_staging[model_word_index] <= cmd_word;
                        if (model_word_index == 10'd633) begin
                            model_state <= MODEL_COMPLETE;
                        end
                        model_word_index <= model_word_index + 10'd1;
                    end else begin
                        rsp_valid <= 1'b1;
                        rsp_payload <= make_error_response(
                            4'h2, cmd_opcode, {2'd0, model_state},
                            {22'd0, model_word_index}, 32'd0
                        );
                    end
                end else if (cmd_opcode == OP_MODEL_COMMIT) begin
                    if (model_state == MODEL_COMPLETE) begin
                        model_state <= MODEL_COMMITTED;
                        model_valid <= 1'b1;
                    end else begin
                        rsp_valid <= 1'b1;
                        rsp_payload <= make_error_response(
                            4'h3, cmd_opcode, {2'd0, model_state},
                            {22'd0, model_word_index}, 32'd0
                        );
                    end
                end else if (cmd_opcode == OP_MASK_BEGIN) begin
                    if (mask_state == MASK_EMPTY && cmd_epoch == (mask_active_epoch + 32'd1)) begin
                        mask_state <= MASK_LOADING;
                        mask_word_index <= 5'd0;
                        mask_staging_epoch <= cmd_epoch;
                    end else begin
                        rsp_valid <= 1'b1;
                        rsp_payload <= make_error_response(
                            4'h4, cmd_opcode, {2'd0, mask_state},
                            {27'd0, mask_word_index}, mask_active_epoch
                        );
                    end
                end else if (cmd_opcode == OP_MASK_DATA) begin
                    if (mask_state == MASK_LOADING && mask_word_index < 5'd19 &&
                        !(mask_word_index == 5'd18 && |cmd_word[31:16])) begin
                        mask_staging[mask_word_index] <= cmd_word;
                        if (mask_word_index == 5'd18) begin
                            mask_state <= MASK_COMPLETE;
                        end
                        mask_word_index <= mask_word_index + 5'd1;
                    end else begin
                        rsp_valid <= 1'b1;
                        rsp_payload <= make_error_response(
                            4'h5, cmd_opcode, {2'd0, mask_state},
                            {27'd0, mask_word_index}, mask_active_epoch
                        );
                    end
                end else if (cmd_opcode == OP_MASK_COMMIT) begin
                    if (mask_state == MASK_COMPLETE && cmd_epoch == mask_staging_epoch &&
                        cmd_epoch == (mask_active_epoch + 32'd1)) begin
                        mask_state <= MASK_PUBLISHED;
                        mask_published_epoch <= cmd_epoch;
                    end else begin
                        rsp_valid <= 1'b1;
                        rsp_payload <= make_error_response(
                            4'h6, cmd_opcode, {2'd0, mask_state},
                            {27'd0, mask_word_index}, mask_active_epoch
                        );
                    end
                end else begin
                    rsp_valid <= 1'b1;
                    rsp_payload <= make_error_response(
                        4'hf, cmd_opcode, {2'd0, model_state},
                        {22'd0, model_word_index}, 32'd0
                    );
                end
            end

            // 固定 8 beat 样本；首 beat 锁存 sample_id，payload 在背压期间由上游保持。
            if (sample_valid && sample_ready) begin
                if (sample_beat_index == 4'd0) begin
                    sample_id_reg <= sample_id;
                    if (mask_state == MASK_PUBLISHED) begin
                        mask_active_epoch <= mask_published_epoch;
                        sample_mask_epoch_reg <= mask_published_epoch;
                        mask_state <= MASK_EMPTY;
                        mask_word_index <= 5'd0;
                        mask_valid <= 1'b1;
                    end else begin
                        sample_mask_epoch_reg <= mask_active_epoch;
                    end
                end
                if (sample_beat_index == 4'd7) begin
                    sample_active <= 1'b0;
                    sample_beat_index <= 4'd0;
                    result_active <= 1'b1;
                    result_beat_index <= 4'd0;
                    result_sample_id_reg <= sample_id_reg;
                    result_mask_epoch_reg <= sample_mask_epoch_reg;
                end else begin
                    sample_active <= 1'b1;
                    sample_beat_index <= sample_beat_index + 4'd1;
                end
            end

            // 结果槽只有在 result_valid && result_ready 时前进；否则所有输出保持。
            if (result_active && result_ready) begin
                if (result_beat_index == 4'd9) begin
                    result_active <= 1'b0;
                    result_beat_index <= 4'd0;
                end else begin
                    result_beat_index <= result_beat_index + 4'd1;
                end
            end

`ifndef SYNTHESIS
            if (cmd_valid && cmd_ready && cmd_opcode == OP_MODEL_COMMIT && model_state == MODEL_COMPLETE)
                $display("NPU_SKELETON MODEL_COMMIT accepted");
            if (sample_valid && sample_ready && sample_beat_index == 4'd7)
                $display("NPU_SKELETON SAMPLE_COMPLETE id=%08x", sample_id_reg);
            if (result_active && result_ready && result_beat_index == 4'd9)
                $display("NPU_SKELETON RESULT_COMPLETE id=%08x", result_sample_id_reg);
`endif
        end
    end
endmodule
