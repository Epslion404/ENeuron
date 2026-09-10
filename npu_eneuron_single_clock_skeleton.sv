// 传统 NPU + ENeuron 单时钟协议骨架。
//
// 当前实现冻结公开 ready/valid、模型/掩码配置和固定 8/10 beat 协议，
// 并用一个四 lane 共享数据通路顺序完成 64→32→10 推理。每个模型 word
// 正好提供四个 INT8 权重；关闭的四权重组不读取模型 word，也不执行乘加。
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
    output logic        mask_valid,
    output logic        infer_frozen,
    output logic [31:0] state_clear_count,
    // 仅用于顶层 fence 判定和原子 epoch 回显，不改变计算数据路径。
    output logic [31:0] active_mask_epoch,
    output logic        mask_staging_open
);
    localparam logic [3:0] OP_MODEL_BEGIN  = 4'h1;
    localparam logic [3:0] OP_MODEL_DATA   = 4'h2;
    localparam logic [3:0] OP_MODEL_COMMIT = 4'h3;
    localparam logic [3:0] OP_MASK_BEGIN    = 4'h4;
    localparam logic [3:0] OP_MASK_DATA     = 4'h5;
    localparam logic [3:0] OP_MASK_COMMIT   = 4'h6;
    localparam logic [3:0] OP_MASK_ABORT    = 4'h7;
    localparam logic [3:0] OP_STATE_CLEAR   = 4'h8;
    localparam logic [3:0] OP_FREEZE_SET    = 4'h9;
    localparam logic [3:0] RSP_ERROR       = 4'he;

    localparam logic [1:0] MODEL_EMPTY     = 2'd0;
    localparam logic [1:0] MODEL_LOADING   = 2'd1;
    localparam logic [1:0] MODEL_COMPLETE  = 2'd2;
    localparam logic [1:0] MODEL_COMMITTED = 2'd3;

    localparam logic [1:0] MASK_EMPTY      = 2'd0;
    localparam logic [1:0] MASK_LOADING    = 2'd1;
    localparam logic [1:0] MASK_COMPLETE   = 2'd2;
    localparam logic [1:0] MASK_PUBLISHED  = 2'd3;

    localparam logic [3:0] COMPUTE_IDLE           = 4'd0;
    localparam logic [3:0] COMPUTE_L0_BIAS_FETCH  = 4'd1;
    localparam logic [3:0] COMPUTE_L0_BIAS_LOAD   = 4'd2;
    localparam logic [3:0] COMPUTE_L0_GROUP_FETCH = 4'd3;
    localparam logic [3:0] COMPUTE_L0_GROUP_EXECUTE = 4'd4;
    localparam logic [3:0] COMPUTE_L0_GROUP_COMMIT  = 4'd5;
    localparam logic [3:0] COMPUTE_L1_BIAS_FETCH  = 4'd6;
    localparam logic [3:0] COMPUTE_L1_BIAS_LOAD   = 4'd7;
    localparam logic [3:0] COMPUTE_L1_GROUP_FETCH = 4'd8;
    localparam logic [3:0] COMPUTE_L1_GROUP_EXECUTE = 4'd9;
    localparam logic [3:0] COMPUTE_L1_GROUP_COMMIT  = 4'd10;
    localparam logic [3:0] COMPUTE_L0_WRITEBACK      = 4'd11;
    localparam logic [3:0] COMPUTE_L1_WRITEBACK      = 4'd12;

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

    logic        compute_active;
    logic [3:0]  compute_state;
    logic [5:0]  compute_unit_index;
    logic [4:0]  compute_group_index;
    // 每个神经元进入 bias fetch 时锁存自己的组掩码，避免 group 循环反复
    // 通过 unit index 访问 592-bit mask 阵列，降低控制扇出与动态索引路径。
    logic [15:0] compute_unit_mask_latched;
    // 组权重地址提前一拍寄存，避免 unit/group 动态索引直达模型 RAM。
    logic [9:0] compute_model_addr;
    logic [31:0] model_word_latched;
    // 将累加器拆为两个 16-bit 段，保留 32-bit 二补码结果但缩短单段 carry 链。
    logic signed [15:0] mac_accumulator_lo;
    logic signed [15:0] mac_accumulator_hi;
    logic signed [31:0] mac_accumulator;
    logic [16:0] mac_low_sum_comb;
    logic [15:0] mac_high_sum_c0;
    logic [15:0] mac_high_sum_c1;
    logic [15:0] mac_high_sum_comb;
    logic signed [31:0] lane_sum_latched;
    logic signed [31:0] lane_sum_comb;
    logic signed [31:0] lane_pair_sum_01;
    logic signed [31:0] lane_pair_sum_23;
    logic signed [7:0] lane_activation_latched_0;
    logic signed [7:0] lane_activation_latched_1;
    logic signed [7:0] lane_activation_latched_2;
    logic signed [7:0] lane_activation_latched_3;
    logic signed [7:0] lane_activation_0;
    logic signed [7:0] lane_activation_1;
    logic signed [7:0] lane_activation_2;
    logic signed [7:0] lane_activation_3;
    logic signed [7:0] lane_weight_0;
    logic signed [7:0] lane_weight_1;
    logic signed [7:0] lane_weight_2;
    logic signed [7:0] lane_weight_3;
    (* use_dsp = "yes" *) logic signed [15:0] lane_product_0;
    (* use_dsp = "yes" *) logic signed [15:0] lane_product_1;
    (* use_dsp = "yes" *) logic signed [15:0] lane_product_2;
    (* use_dsp = "yes" *) logic signed [15:0] lane_product_3;

    logic [3:0]  input_pixels [0:63];
    logic [6:0]  hidden_values [0:31];
    logic [31:0] logit_values [0:9];

    // 634 words are deliberately represented by a small staging array in this
    // protocol slice. Later implementation may infer BRAM without changing the port contract.
    logic [31:0] model_staging [0:633];
    logic        model_write_pending;
    logic [9:0]  model_write_addr;
    logic [31:0] model_write_data;
    logic [31:0] mask_staging [0:18];
    logic [31:0] mask_active_words [0:18];

    wire [3:0]  cmd_opcode = cmd_payload[127:124];
    wire [31:0] cmd_word = cmd_payload[31:0];
    wire [31:0] cmd_epoch = cmd_payload[119:88];
    wire        cmd_is_mask = cmd_opcode >= OP_MASK_BEGIN && cmd_opcode <= OP_MASK_ABORT;

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

    function automatic logic model_word_payload_valid(
        input logic [9:0] word_index,
        input logic [31:0] word
    );
        logic signed [31:0] signed_word;
        begin
            signed_word = $signed(word);
            if (word_index >= 10'd512 && word_index <= 10'd543) begin
                model_word_payload_valid =
                    signed_word >= -32'sd2147360768 && signed_word <= 32'sd2147361727;
            end else if (word_index >= 10'd624 && word_index <= 10'd633) begin
                model_word_payload_valid =
                    signed_word >= -32'sd2146963456 && signed_word <= 32'sd2146967519;
            end else begin
                model_word_payload_valid = 1'b1;
            end
        end
    endfunction

    function automatic logic [6:0] relu_saturate_u7(
        input logic signed [31:0] value
    );
        begin
            if (value <= 0)
                relu_saturate_u7 = 7'd0;
            else if (value >= 127)
                relu_saturate_u7 = 7'd127;
            else
                relu_saturate_u7 = value[6:0];
        end
    endfunction

    function automatic logic active_mask_enabled(input integer bit_index);
        begin
            active_mask_enabled = mask_active_words[bit_index >> 5][bit_index & 31];
        end
    endfunction

    function automatic logic [15:0] l0_unit_mask(input logic [5:0] unit_index);
        integer mask_bit;
        begin
            for (mask_bit = 0; mask_bit < 16; mask_bit = mask_bit + 1)
                l0_unit_mask[mask_bit] =
                    mask_active_words[(unit_index * 16 + mask_bit) >> 5][(unit_index * 16 + mask_bit) & 31];
        end
    endfunction

    function automatic logic [15:0] l1_unit_mask(input logic [5:0] unit_index);
        integer mask_bit;
        begin
            l1_unit_mask = 16'd0;
            for (mask_bit = 0; mask_bit < 8; mask_bit = mask_bit + 1)
                l1_unit_mask[mask_bit] =
                    mask_active_words[(512 + unit_index * 8 + mask_bit) >> 5][(512 + unit_index * 8 + mask_bit) & 31];
        end
    endfunction

    // L0/L1 共用同一组四个 signed 8×8 乘法器。数组只在 FETCH 提供激活值，
    // EXECUTE 只使用稳定锁存器；每个乘积先符号扩展到 INT32 再求和。
    always_comb begin
        lane_activation_0 = lane_activation_latched_0;
        lane_activation_1 = lane_activation_latched_1;
        lane_activation_2 = lane_activation_latched_2;
        lane_activation_3 = lane_activation_latched_3;
        lane_weight_0 = $signed(model_word_latched[7:0]);
        lane_weight_1 = $signed(model_word_latched[15:8]);
        lane_weight_2 = $signed(model_word_latched[23:16]);
        lane_weight_3 = $signed(model_word_latched[31:24]);
    end

    always_comb begin
        mac_accumulator = {mac_accumulator_hi, mac_accumulator_lo};
        mac_low_sum_comb = {1'b0, mac_accumulator_lo} + {1'b0, lane_sum_comb[15:0]};
        // 高半字并行计算两种 carry 情况，避免低半字 carry 穿过整条 32-bit 加法链。
        mac_high_sum_c0 = mac_accumulator_hi + lane_sum_comb[31:16];
        mac_high_sum_c1 = mac_accumulator_hi + lane_sum_comb[31:16] + 16'd1;
        mac_high_sum_comb = mac_low_sum_comb[16] ? mac_high_sum_c1 : mac_high_sum_c0;
    end

    always_comb begin
        // 两级平衡加法树减少 DSP 输出后的串行 carry 深度。
        lane_pair_sum_01 =
            {{16{lane_product_0[15]}}, lane_product_0} +
            {{16{lane_product_1[15]}}, lane_product_1};
        lane_pair_sum_23 =
            {{16{lane_product_2[15]}}, lane_product_2} +
            {{16{lane_product_3[15]}}, lane_product_3};
        lane_sum_comb = lane_pair_sum_01 + lane_pair_sum_23;
    end

    // 配置握手优先于样本首拍；响应槽背压期间整个命令口停住。
    always_comb begin
        // mask staging/publish 可与部分输入、计算和结果输出并行；其它命令等待严格运行空闲。
        cmd_ready = !rsp_valid && !model_write_pending &&
                    (cmd_is_mask || (!sample_active && !compute_active && !result_active));
        // 配置只抢占样本首 beat；部分样本期间命令口被阻塞，输入必须继续前进。
        sample_ready = model_valid && !compute_active && !result_active && !rsp_valid &&
                       !(cmd_valid && !sample_active);
        result_valid = result_active;
        result_data = result_active ? logit_values[result_beat_index] : 32'd0;
        result_sample_id = result_sample_id_reg;
        result_mask_epoch = result_mask_epoch_reg;
        active_mask_epoch = mask_active_epoch;
        mask_staging_open = (mask_state == MASK_LOADING) || (mask_state == MASK_COMPLETE);
        runtime_idle = !sample_active && !compute_active && !result_active && !rsp_valid &&
                       ((model_state == MODEL_EMPTY) || (model_state == MODEL_COMMITTED)) &&
                       (mask_state == MASK_EMPTY) &&
                       !cmd_valid;
    end

    integer reset_mask_index;
    integer sample_pixel_index;
    integer activate_mask_index;

    always_ff @(posedge clk) begin
        if (rst) begin
            model_state <= MODEL_EMPTY;
            model_word_index <= 10'd0;
            model_valid <= 1'b0;
            model_write_pending <= 1'b0;
            model_write_addr <= 10'd0;
            model_write_data <= 32'd0;
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
            compute_active <= 1'b0;
            compute_state <= COMPUTE_IDLE;
            compute_unit_index <= 6'd0;
            compute_group_index <= 5'd0;
            compute_unit_mask_latched <= 16'd0;
            compute_model_addr <= 10'd0;
            model_word_latched <= 32'd0;
            mac_accumulator_lo <= 16'sd0;
            mac_accumulator_hi <= 16'sd0;
            lane_sum_latched <= 32'sd0;
            lane_activation_latched_0 <= 8'sd0;
            lane_activation_latched_1 <= 8'sd0;
            lane_activation_latched_2 <= 8'sd0;
            lane_activation_latched_3 <= 8'sd0;
            infer_frozen <= 1'b0;
            state_clear_count <= 32'd0;
            rsp_valid <= 1'b0;
            rsp_payload <= 128'd0;
            // 复位后的默认 mask 全开；word18 只有低 16 位属于 L1 mask。
            for (reset_mask_index = 0; reset_mask_index < 18; reset_mask_index = reset_mask_index + 1)
                mask_active_words[reset_mask_index] <= 32'hffff_ffff;
            mask_active_words[18] <= 32'h0000_ffff;
        end else begin
            if (model_write_pending) begin
                model_staging[model_write_addr] <= model_write_data;
                if (model_write_addr == 10'd633)
                    model_state <= MODEL_COMPLETE;
                model_word_index <= model_write_addr + 10'd1;
                model_write_pending <= 1'b0;
            end

            // 单槽错误响应：消费前保持 payload/valid 稳定，消费拍不接受新命令。
            if (rsp_valid && rsp_ready) begin
                rsp_valid <= 1'b0;
            end

            if (cmd_valid && cmd_ready) begin
                // 冻结只屏蔽配置/动态清除；FREEZE_SET 自身必须可用于退出冻结。
                if (infer_frozen && cmd_opcode != OP_FREEZE_SET) begin
                    rsp_valid <= 1'b1;
                    rsp_payload <= make_error_response(
                        4'h7, cmd_opcode, 4'hf,
                        (cmd_opcode >= OP_MASK_BEGIN && cmd_opcode <= OP_MASK_ABORT) ?
                            {27'd0, mask_word_index} : {22'd0, model_word_index},
                        mask_active_epoch
                    );
                end else if (cmd_opcode == OP_MODEL_BEGIN) begin
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
                    if (model_state == MODEL_LOADING && model_word_index < 10'd634 &&
                        model_word_payload_valid(model_word_index, cmd_word)) begin
                        model_write_addr <= model_word_index;
                        model_write_data <= cmd_word;
                        model_write_pending <= 1'b1;
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
                end else if (cmd_opcode == OP_MASK_ABORT) begin
                    if (mask_state == MASK_LOADING || mask_state == MASK_COMPLETE) begin
                        mask_state <= MASK_EMPTY;
                        mask_word_index <= 5'd0;
                        mask_staging_epoch <= 32'd0;
                    end else begin
                        rsp_valid <= 1'b1;
                        rsp_payload <= make_error_response(
                            4'h7, cmd_opcode, {2'd0, mask_state},
                            {27'd0, mask_word_index}, mask_active_epoch
                        );
                    end
                end else if (cmd_opcode == OP_STATE_CLEAR) begin
                    if ((model_state == MODEL_EMPTY || model_state == MODEL_COMMITTED) &&
                        mask_state == MASK_EMPTY) begin
                        state_clear_count <= state_clear_count + 32'd1;
                    end else begin
                        rsp_valid <= 1'b1;
                        rsp_payload <= make_error_response(
                            4'h8, cmd_opcode, {2'd0, mask_state},
                            {27'd0, mask_word_index}, mask_active_epoch
                        );
                    end
                end else if (cmd_opcode == OP_FREEZE_SET) begin
                    if ((model_state == MODEL_EMPTY || model_state == MODEL_COMMITTED) &&
                        mask_state == MASK_EMPTY) begin
                        infer_frozen <= cmd_payload[120];
                    end else begin
                        rsp_valid <= 1'b1;
                        rsp_payload <= make_error_response(
                            4'h9, cmd_opcode, {2'd0, mask_state},
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
                for (sample_pixel_index = 0; sample_pixel_index < 8; sample_pixel_index = sample_pixel_index + 1)
                    input_pixels[(sample_beat_index * 8) + sample_pixel_index] <=
                        sample_data[(sample_pixel_index * 4) +: 4];
                if (sample_beat_index == 4'd0) begin
                    sample_id_reg <= sample_id;
                    if (mask_state == MASK_PUBLISHED) begin
                        for (activate_mask_index = 0; activate_mask_index < 19; activate_mask_index = activate_mask_index + 1)
                            mask_active_words[activate_mask_index] <= mask_staging[activate_mask_index];
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
                    compute_active <= 1'b1;
                    compute_state <= COMPUTE_L0_BIAS_FETCH;
                    compute_unit_index <= 6'd0;
                    compute_group_index <= 5'd0;
                    result_sample_id_reg <= sample_id_reg;
                    result_mask_epoch_reg <= sample_mask_epoch_reg;
                end else begin
                    sample_active <= 1'b1;
                    sample_beat_index <= sample_beat_index + 4'd1;
                end
            end

            // 一个 32-bit 模型 word 提供四个权重，因此四 lane 每次处理一个 group。
            // bias 使用 FETCH/LOAD，启用权重组使用 FETCH/EXECUTE/COMMIT，
            // 给后续同步 RAM 映射和 DSP 数据通路保留清晰时序边界。
            if (compute_active) begin
                case (compute_state)
                    COMPUTE_L0_BIAS_FETCH: begin
                        model_word_latched <= model_staging[512 + compute_unit_index];
                        compute_unit_mask_latched <= l0_unit_mask(compute_unit_index);
                        compute_model_addr <= {compute_unit_index, 4'd0};
                        compute_state <= COMPUTE_L0_BIAS_LOAD;
                    end
                    COMPUTE_L0_BIAS_LOAD: begin
                        mac_accumulator_lo <= $signed(model_word_latched[15:0]);
                        mac_accumulator_hi <= $signed(model_word_latched[31:16]);
                        compute_group_index <= 5'd0;
                        compute_state <= COMPUTE_L0_GROUP_FETCH;
                    end
                    COMPUTE_L0_GROUP_FETCH: begin
                        if (compute_unit_mask_latched[compute_group_index[3:0]]) begin
                            model_word_latched <= model_staging[compute_model_addr];
                            lane_activation_latched_0 <=
                                $signed({4'b0000, input_pixels[(compute_group_index * 4) + 0]});
                            lane_activation_latched_1 <=
                                $signed({4'b0000, input_pixels[(compute_group_index * 4) + 1]});
                            lane_activation_latched_2 <=
                                $signed({4'b0000, input_pixels[(compute_group_index * 4) + 2]});
                            lane_activation_latched_3 <=
                                $signed({4'b0000, input_pixels[(compute_group_index * 4) + 3]});
                            compute_state <= COMPUTE_L0_GROUP_EXECUTE;
                        end else if (compute_group_index == 5'd15) begin
                            compute_group_index <= 5'd0;
                            compute_state <= COMPUTE_L0_WRITEBACK;
                        end else begin
                            compute_group_index <= compute_group_index + 5'd1;
                            compute_model_addr <= compute_model_addr + 10'd1;
                        end
                    end
                    COMPUTE_L0_GROUP_EXECUTE: begin
                        compute_state <= COMPUTE_L0_GROUP_COMMIT;
                        // 在 EXECUTE 边界寄存 DSP 输出，避免乘法器结果直达累加树。
                        lane_product_0 <= lane_activation_0 * lane_weight_0;
                        lane_product_1 <= lane_activation_1 * lane_weight_1;
                        lane_product_2 <= lane_activation_2 * lane_weight_2;
                        lane_product_3 <= lane_activation_3 * lane_weight_3;
                    end
                    COMPUTE_L0_GROUP_COMMIT: begin
                        lane_sum_latched <= lane_sum_comb;
                        // 最后一组必须使用 EXECUTE 已锁存的新组和，不能读取旧 accumulator。
                        if (compute_group_index == 5'd15) begin
                            mac_accumulator_lo <= mac_low_sum_comb[15:0];
                            mac_accumulator_hi <= mac_high_sum_comb;
                            compute_group_index <= 5'd0;
                            compute_state <= COMPUTE_L0_WRITEBACK;
                        end else begin
                            mac_accumulator_lo <= mac_low_sum_comb[15:0];
                            mac_accumulator_hi <= mac_high_sum_comb;
                            compute_group_index <= compute_group_index + 5'd1;
                            compute_model_addr <= compute_model_addr + 10'd1;
                            compute_state <= COMPUTE_L0_GROUP_FETCH;
                        end
                    end
                    COMPUTE_L0_WRITEBACK: begin
                        hidden_values[compute_unit_index] <= relu_saturate_u7(mac_accumulator);
                        compute_group_index <= 5'd0;
                        if (compute_unit_index == 6'd31) begin
                            compute_unit_index <= 6'd0;
                            compute_state <= COMPUTE_L1_BIAS_FETCH;
                        end else begin
                            compute_unit_index <= compute_unit_index + 6'd1;
                            compute_state <= COMPUTE_L0_BIAS_FETCH;
                        end
                    end
                    COMPUTE_L1_BIAS_FETCH: begin
                        model_word_latched <= model_staging[624 + compute_unit_index];
                        compute_unit_mask_latched <= l1_unit_mask(compute_unit_index);
                        compute_model_addr <= 10'd544 + {compute_unit_index, 3'd0};
                        compute_state <= COMPUTE_L1_BIAS_LOAD;
                    end
                    COMPUTE_L1_BIAS_LOAD: begin
                        mac_accumulator_lo <= $signed(model_word_latched[15:0]);
                        mac_accumulator_hi <= $signed(model_word_latched[31:16]);
                        compute_group_index <= 5'd0;
                        compute_state <= COMPUTE_L1_GROUP_FETCH;
                    end
                    COMPUTE_L1_GROUP_FETCH: begin
                        if (compute_unit_mask_latched[compute_group_index[2:0]]) begin
                            model_word_latched <= model_staging[compute_model_addr];
                            lane_activation_latched_0 <=
                                $signed({1'b0, hidden_values[(compute_group_index * 4) + 0]});
                            lane_activation_latched_1 <=
                                $signed({1'b0, hidden_values[(compute_group_index * 4) + 1]});
                            lane_activation_latched_2 <=
                                $signed({1'b0, hidden_values[(compute_group_index * 4) + 2]});
                            lane_activation_latched_3 <=
                                $signed({1'b0, hidden_values[(compute_group_index * 4) + 3]});
                            compute_state <= COMPUTE_L1_GROUP_EXECUTE;
                        end else if (compute_group_index == 5'd7) begin
                            compute_group_index <= 5'd0;
                            compute_state <= COMPUTE_L1_WRITEBACK;
                        end else begin
                            compute_group_index <= compute_group_index + 5'd1;
                            compute_model_addr <= compute_model_addr + 10'd1;
                        end
                    end
                    COMPUTE_L1_GROUP_EXECUTE: begin
                        compute_state <= COMPUTE_L1_GROUP_COMMIT;
                        lane_product_0 <= lane_activation_0 * lane_weight_0;
                        lane_product_1 <= lane_activation_1 * lane_weight_1;
                        lane_product_2 <= lane_activation_2 * lane_weight_2;
                        lane_product_3 <= lane_activation_3 * lane_weight_3;
                    end
                    COMPUTE_L1_GROUP_COMMIT: begin
                        lane_sum_latched <= lane_sum_comb;
                        if (compute_group_index == 5'd7) begin
                            mac_accumulator_lo <= mac_low_sum_comb[15:0];
                            mac_accumulator_hi <= mac_high_sum_comb;
                            compute_group_index <= 5'd0;
                            compute_state <= COMPUTE_L1_WRITEBACK;
                        end else begin
                            mac_accumulator_lo <= mac_low_sum_comb[15:0];
                            mac_accumulator_hi <= mac_high_sum_comb;
                            compute_group_index <= compute_group_index + 5'd1;
                            compute_model_addr <= compute_model_addr + 10'd1;
                            compute_state <= COMPUTE_L1_GROUP_FETCH;
                        end
                    end
                    COMPUTE_L1_WRITEBACK: begin
                        logit_values[compute_unit_index] <= mac_accumulator;
                        compute_group_index <= 5'd0;
                        if (compute_unit_index == 6'd9) begin
                            compute_active <= 1'b0;
                            compute_state <= COMPUTE_IDLE;
                            compute_unit_index <= 6'd0;
                            result_active <= 1'b1;
                            result_beat_index <= 4'd0;
                        end else begin
                            compute_unit_index <= compute_unit_index + 6'd1;
                            compute_state <= COMPUTE_L1_BIAS_FETCH;
                        end
                    end
                    default: begin
                        compute_active <= 1'b0;
                        compute_state <= COMPUTE_IDLE;
                    end
                endcase
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
            if (compute_active && compute_unit_index == 6'd9 &&
                compute_state == COMPUTE_L1_WRITEBACK)
                $display("NPU_SKELETON COMPUTE_COMPLETE id=%08x path=WRITEBACK", result_sample_id_reg);
            if (result_active && result_ready && result_beat_index == 4'd9)
                $display("NPU_SKELETON RESULT_COMPLETE id=%08x", result_sample_id_reg);
            if (cmd_valid && cmd_ready && cmd_opcode == OP_FREEZE_SET &&
                (model_state == MODEL_EMPTY || model_state == MODEL_COMMITTED) && mask_state == MASK_EMPTY)
                $display("NPU_SKELETON FREEZE_SET value=%0d", cmd_payload[120]);
`endif
        end
    end
endmodule
