// PL 侧 ENeuron group_4way 决策参考引擎。
//
// 该切片只冻结“输入/模型 -> 19 个 mask word”的硬件语义，便于先做
// PS/PL 逐 bit 对照。它是单次组合预计算模型，尚未接入主 NPU 的时序
// 状态机；接入前必须拆成可达 200 MHz 的顺序状态。
module eneuron_pl_auto_mask_reference (
    input  logic        clk,
    input  logic        rst,
    input  logic        start,
    input  logic        enable,
    input  logic [3:0]  input_pixels [0:63],
    input  logic [31:0] model_words [0:633],
    output logic        busy,
    output logic        valid,
    output [31:0]       mask_words [0:18]
);
    // 592 bit 有效（word18 只用低 16 bit）；补到 608 bit 让 word18
    // 的 32-bit 切片完整落在已定义范围内，保留位保持 0。
    logic [607:0] mask_calc;
    logic [6:0] hidden_calc [0:31];
    logic signed [31:0] hidden_sum_calc [0:31];
    logic signed [31:0] l0_contribution [0:31][0:15];
    // Icarus 12 不会把 always_ff 对 unpacked-array 变量输出端口的写入
    // 传回父层，因此这里写入内部数组，再用 net 输出端口连续赋值。
    logic [31:0] mask_words_q [0:18];
    integer i;
    integer j;
    integer w;
    genvar g;

    function automatic logic signed [7:0] decode_int8(
        input logic [31:0] word,
        input integer lane
    );
        decode_int8 = $signed(word[(lane * 8) +: 8]);
    endfunction

    function automatic logic signed [31:0] group_mac_pixels(
        input logic [31:0] word,
        input integer start_index
    );
        logic signed [31:0] acc;
        integer lane;
        begin
            acc = 32'sd0;
            for (lane = 0; lane < 4; lane = lane + 1)
                acc = acc + decode_int8(word, lane) * $signed({1'b0, input_pixels[start_index + lane]});
            group_mac_pixels = acc;
        end
    endfunction

    function automatic logic signed [31:0] group_mac_hidden(
        input logic [31:0] word,
        input integer start_index
    );
        logic signed [31:0] acc;
        integer lane;
        begin
            acc = 32'sd0;
            for (lane = 0; lane < 4; lane = lane + 1)
                acc = acc + decode_int8(word, lane) * $signed({1'b0, hidden_calc[start_index + lane]});
            group_mac_hidden = acc;
        end
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

    always_comb begin
        mask_calc = '0;
        for (i = 0; i < 32; i = i + 1) begin
            for (j = 0; j < 16; j = j + 1)
                l0_contribution[i][j] = group_mac_pixels(model_words[(i * 16) + j], j * 4);
            hidden_sum_calc[i] = $signed(model_words[512 + i]);
            for (j = 0; j < 16; j = j + 1)
                hidden_sum_calc[i] = hidden_sum_calc[i] + l0_contribution[i][j];
            if (hidden_sum_calc[i] < 0)
                hidden_calc[i] = 7'd0;
            else if (hidden_sum_calc[i] > 127)
                hidden_calc[i] = 7'd127;
            else
                hidden_calc[i] = hidden_sum_calc[i][6:0];
        end
        for (i = 0; i < 32; i = i + 1) begin
            for (j = 0; j < 4; j = j + 1)
                mask_calc[(i * 16) + (j * 4) +: 4] = top2_mask(
                    quantize_evidence(l0_contribution[i][j * 4 + 0]),
                    quantize_evidence(l0_contribution[i][j * 4 + 1]),
                    quantize_evidence(l0_contribution[i][j * 4 + 2]),
                    quantize_evidence(l0_contribution[i][j * 4 + 3]));
        end
        for (i = 0; i < 10; i = i + 1) begin
            for (j = 0; j < 2; j = j + 1)
                mask_calc[512 + (i * 8) + (j * 4) +: 4] = top2_mask(
                    quantize_evidence(group_mac_hidden(model_words[544 + (i * 8) + (j * 4) + 0], j * 16)),
                    quantize_evidence(group_mac_hidden(model_words[544 + (i * 8) + (j * 4) + 1], j * 16 + 4)),
                    quantize_evidence(group_mac_hidden(model_words[544 + (i * 8) + (j * 4) + 2], j * 16 + 8)),
                    quantize_evidence(group_mac_hidden(model_words[544 + (i * 8) + (j * 4) + 3], j * 16 + 12)));
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            busy <= 1'b0;
            valid <= 1'b0;
            for (w = 0; w < 19; w = w + 1)
                mask_words_q[w] <= 32'd0;
        end else begin
            valid <= 1'b0;
            if (start && enable && !busy) begin
                busy <= 1'b1;
                for (w = 0; w < 19; w = w + 1)
                    mask_words_q[w] <= mask_calc[w * 32 +: 32];
            end else if (busy) begin
                busy <= 1'b0;
                valid <= 1'b1;
            end
        end
    end

    generate
        for (g = 0; g < 19; g = g + 1) begin : mask_output
            assign mask_words[g] = mask_words_q[g];
        end
    endgenerate
endmodule
