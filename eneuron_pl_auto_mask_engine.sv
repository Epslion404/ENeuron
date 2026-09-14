// PL 侧 ENeuron group_4way 决策顺序引擎。
//
// 与 eneuron_pl_auto_mask_reference.sv 的组合语义逐 bit 等价：
//   输入/模型 -> 19 个 mask word。
// 每个 group 用 FETCH/EXECUTE/ACCUM 三拍完成四 lane MAC；L0 累加 hidden
// 并饱和到 [0,127]，L1 只用于 evidence 与 top-2。top-2 使用与 PS
// live_top2_mask 相同的降序、低位 index 优先排序。
//
// 约束边界：本模块是独立参考引擎，尚未与主 NPU 共享四 DSP 数据通路；
// 接入前需要 Vivado 200 MHz 时序与资源评定（额外乘法器/DSP 成本）。
module eneuron_pl_auto_mask_engine (
    input  logic        clk,
    input  logic        rst,
    input  logic        start,
    input  logic        enable,
    input  logic [3:0]  input_pixels [0:63],
    input  logic [31:0] model_words [0:633],
    output logic        busy,
    output logic        valid,
    output [31:0]       mask_words [0:18],
    output logic [31:0] cycle_count
);
    typedef enum logic [3:0] {
        ST_IDLE,
        ST_L0_BIAS,
        ST_L0_FETCH,
        ST_L0_EXEC,
        ST_L0_ACCUM,
        ST_L0_WRITEBACK,
        ST_L1_BIAS,
        ST_L1_FETCH,
        ST_L1_EXEC,
        ST_L1_ACCUM,
        ST_L1_WRITEBACK,
        ST_DONE
    } state_t;

    state_t state;

    logic [607:0] mask_q;
    logic [6:0] hidden_values [0:31];
    logic [1:0] evidence_group [0:15];
    logic signed [31:0] unit_acc;
    logic signed [31:0] lane_term [0:3];
    logic signed [31:0] lane_sum;
    logic [31:0] model_word_latched;
    logic signed [31:0] activation_latched [0:3];
    logic signed [31:0] saturated_hidden;
    logic [5:0] unit_index;
    logic [4:0] group_index;
    integer i;
    genvar g;

    function automatic logic signed [7:0] decode_int8(
        input logic [31:0] word,
        input integer lane
    );
        decode_int8 = $signed(word[(lane * 8) +: 8]);
    endfunction

    function automatic logic [1:0] quantize_evidence(
        input logic signed [31:0] contribution
    );
        logic [31:0] magnitude;
        logic [31:0] level;
        begin
            magnitude = contribution < 0 ? -contribution : contribution;
            level = (magnitude + 32'd15) >> 4;
            quantize_evidence = level > 3 ? 2'd3 : level[1:0];
        end
    endfunction

    function automatic logic [3:0] top2_mask(
        input logic [1:0] e0,
        input logic [1:0] e1,
        input logic [1:0] e2,
        input logic [1:0] e3
    );
        logic [1:0] values [0:3];
        integer order [0:3];
        logic [1:0] value_tmp;
        integer index_tmp;
        integer first;
        integer second;
        begin
            values[0] = e0;
            values[1] = e1;
            values[2] = e2;
            values[3] = e3;
            for (first = 0; first < 4; first = first + 1)
                order[first] = first;
            for (first = 0; first < 3; first = first + 1) begin
                for (second = first + 1; second < 4; second = second + 1) begin
                    if ((values[order[second]] > values[order[first]]) ||
                        ((values[order[second]] == values[order[first]]) &&
                         (order[second] < order[first]))) begin
                        index_tmp = order[first];
                        order[first] = order[second];
                        order[second] = index_tmp;
                    end
                end
            end
            top2_mask = 4'b0000;
            top2_mask[order[0]] = 1'b1;
            top2_mask[order[1]] = 1'b1;
        end
    endfunction

    assign lane_sum = lane_term[0] + lane_term[1] + lane_term[2] + lane_term[3];

    always_comb begin
        if (unit_acc < 0)
            saturated_hidden = 32'sd0;
        else if (unit_acc > 127)
            saturated_hidden = 32'sd127;
        else
            saturated_hidden = unit_acc;
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            busy <= 1'b0;
            valid <= 1'b0;
            state <= ST_IDLE;
            cycle_count <= 32'd0;
            unit_index <= 6'd0;
            group_index <= 5'd0;
            unit_acc <= 32'sd0;
            mask_q <= 608'd0;
            for (i = 0; i < 32; i = i + 1)
                hidden_values[i] <= 7'd0;
            for (i = 0; i < 16; i = i + 1)
                evidence_group[i] <= 2'd0;
            for (i = 0; i < 4; i = i + 1)
                lane_term[i] <= 32'sd0;
        end else begin
            valid <= 1'b0;
            if (busy)
                cycle_count <= cycle_count + 32'd1;

            case (state)
                ST_IDLE: begin
                    if (start && enable && !busy) begin
                        busy <= 1'b1;
                        cycle_count <= 32'd0;
                        unit_index <= 6'd0;
                        group_index <= 5'd0;
                        mask_q <= 608'd0;
                        state <= ST_L0_BIAS;
                    end
                end

                ST_L0_BIAS: begin
                    unit_acc <= $signed(model_words[512 + unit_index]);
                    group_index <= 5'd0;
                    state <= ST_L0_FETCH;
                end

                ST_L0_FETCH: begin
                    model_word_latched <= model_words[{unit_index, 4'd0} + group_index];
                    activation_latched[0] <= $signed({28'd0, input_pixels[group_index * 4 + 0]});
                    activation_latched[1] <= $signed({28'd0, input_pixels[group_index * 4 + 1]});
                    activation_latched[2] <= $signed({28'd0, input_pixels[group_index * 4 + 2]});
                    activation_latched[3] <= $signed({28'd0, input_pixels[group_index * 4 + 3]});
                    state <= ST_L0_EXEC;
                end

                ST_L0_EXEC: begin
                    lane_term[0] <= $signed(decode_int8(model_word_latched, 0)) * activation_latched[0];
                    lane_term[1] <= $signed(decode_int8(model_word_latched, 1)) * activation_latched[1];
                    lane_term[2] <= $signed(decode_int8(model_word_latched, 2)) * activation_latched[2];
                    lane_term[3] <= $signed(decode_int8(model_word_latched, 3)) * activation_latched[3];
                    state <= ST_L0_ACCUM;
                end

                ST_L0_ACCUM: begin
                    unit_acc <= unit_acc + lane_sum;
                    evidence_group[group_index] <= quantize_evidence(lane_sum);
                    if (group_index == 5'd15) begin
                        group_index <= 5'd0;
                        state <= ST_L0_WRITEBACK;
                    end else begin
                        group_index <= group_index + 5'd1;
                        state <= ST_L0_FETCH;
                    end
                end

                ST_L0_WRITEBACK: begin
                    hidden_values[unit_index] <= saturated_hidden[6:0];
                    mask_q[unit_index * 16 + 0 +: 4] <= top2_mask(
                        evidence_group[0], evidence_group[1], evidence_group[2], evidence_group[3]);
                    mask_q[unit_index * 16 + 4 +: 4] <= top2_mask(
                        evidence_group[4], evidence_group[5], evidence_group[6], evidence_group[7]);
                    mask_q[unit_index * 16 + 8 +: 4] <= top2_mask(
                        evidence_group[8], evidence_group[9], evidence_group[10], evidence_group[11]);
                    mask_q[unit_index * 16 + 12 +: 4] <= top2_mask(
                        evidence_group[12], evidence_group[13], evidence_group[14], evidence_group[15]);
                    if (unit_index == 6'd31) begin
                        unit_index <= 6'd0;
                        state <= ST_L1_BIAS;
                    end else begin
                        unit_index <= unit_index + 6'd1;
                        state <= ST_L0_BIAS;
                    end
                end

                ST_L1_BIAS: begin
                    unit_acc <= $signed(model_words[624 + unit_index]);
                    group_index <= 5'd0;
                    state <= ST_L1_FETCH;
                end

                ST_L1_FETCH: begin
                    model_word_latched <= model_words[544 + {unit_index, 3'd0} + group_index];
                    activation_latched[0] <= $signed({25'd0, hidden_values[group_index * 4 + 0]});
                    activation_latched[1] <= $signed({25'd0, hidden_values[group_index * 4 + 1]});
                    activation_latched[2] <= $signed({25'd0, hidden_values[group_index * 4 + 2]});
                    activation_latched[3] <= $signed({25'd0, hidden_values[group_index * 4 + 3]});
                    state <= ST_L1_EXEC;
                end

                ST_L1_EXEC: begin
                    lane_term[0] <= $signed(decode_int8(model_word_latched, 0)) * activation_latched[0];
                    lane_term[1] <= $signed(decode_int8(model_word_latched, 1)) * activation_latched[1];
                    lane_term[2] <= $signed(decode_int8(model_word_latched, 2)) * activation_latched[2];
                    lane_term[3] <= $signed(decode_int8(model_word_latched, 3)) * activation_latched[3];
                    state <= ST_L1_ACCUM;
                end

                ST_L1_ACCUM: begin
                    unit_acc <= unit_acc + lane_sum;
                    evidence_group[group_index] <= quantize_evidence(lane_sum);
                    if (group_index == 5'd7) begin
                        group_index <= 5'd0;
                        state <= ST_L1_WRITEBACK;
                    end else begin
                        group_index <= group_index + 5'd1;
                        state <= ST_L1_FETCH;
                    end
                end

                ST_L1_WRITEBACK: begin
                    mask_q[512 + unit_index * 8 + 0 +: 4] <= top2_mask(
                        evidence_group[0], evidence_group[1], evidence_group[2], evidence_group[3]);
                    mask_q[512 + unit_index * 8 + 4 +: 4] <= top2_mask(
                        evidence_group[4], evidence_group[5], evidence_group[6], evidence_group[7]);
                    if (unit_index == 6'd9) begin
                        state <= ST_DONE;
                    end else begin
                        unit_index <= unit_index + 6'd1;
                        state <= ST_L1_BIAS;
                    end
                end

                ST_DONE: begin
                    state <= ST_IDLE;
                    busy <= 1'b0;
                    valid <= 1'b1;
                end

                default: state <= ST_IDLE;
            endcase
        end
    end

    generate
        for (g = 0; g < 19; g = g + 1) begin : mask_output
            assign mask_words[g] = mask_q[g * 32 +: 32];
        end
    endgenerate
endmodule
