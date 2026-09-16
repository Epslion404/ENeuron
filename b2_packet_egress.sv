// B2 外层帧 egress：缓存 NPU response/result，再按冻结字节合同输出 32-bit AXI 帧。
module b2_packet_egress #(
    parameter integer PAYLOAD_WORD_CAPACITY = 1015
) (
    input  logic        clk,
    input  logic        rst,

    input  logic        rsp_valid,
    output logic        rsp_ready,
    input  logic [127:0] rsp_data,
    input  logic        rsp_last,
    input  logic [31:0] rsp_sequence,
    input  logic [31:0] rsp_model_id,
    input  logic [31:0] rsp_mask_epoch,
    input  logic [31:0] rsp_status,

    input  logic        result_valid,
    output logic        result_ready,
    input  logic [31:0] result_data,
    input  logic [31:0] result_sample_id,
    input  logic [31:0] result_model_id,
    input  logic [31:0] result_mask_epoch,
    input  logic [31:0] result_sequence,
    input  logic [31:0] result_status,

    output logic        m_valid,
    input  logic        m_ready,
    output logic [31:0] m_data,
    output logic [3:0]  m_keep,
    output logic        m_last,
    output logic        error_valid,
    output logic [3:0]  error_code,
    output logic        busy
);
    localparam logic [31:0] MAGIC = 32'h3242_4e45;
    localparam integer HEADER_WORDS = 8;
    localparam logic [7:0] TYPE_RESPONSE = 8'd3;
    localparam logic [7:0] TYPE_RESULT = 8'd4;
    localparam logic [3:0] ERR_OVERFLOW = 4'h1;
    localparam logic [3:0] ERR_RESULT_METADATA = 4'h2;

    typedef enum logic [2:0] {ST_IDLE, ST_RSP_COLLECT, ST_RESULT_COLLECT, ST_OUTPUT} state_t;
    state_t state;
    // response 以 128-bit word 写入、按 32-bit lane 读出；同步读端口避免大范围 LUT mux。
    localparam integer RESPONSE_WORD_CAPACITY = (PAYLOAD_WORD_CAPACITY + 3) / 4;
    localparam integer RESPONSE_COUNT_WIDTH = $clog2(RESPONSE_WORD_CAPACITY + 1);
    logic [127:0] response_mem_rd_data;
    logic [31:0] result_mem_rd_data;
    logic response_mem_wr_en, response_mem_rd_en;
    logic result_mem_wr_en, result_mem_rd_en;
    logic [$clog2(RESPONSE_WORD_CAPACITY)-1:0] response_mem_wr_addr, response_mem_rd_addr;
    logic [3:0] result_mem_wr_addr, result_mem_rd_addr;
    assign response_mem_wr_en = rsp_fire && ((state == ST_IDLE) ||
        (response_word_count + 1'b1 <= RESPONSE_WORD_CAPACITY));
    assign response_mem_wr_addr = (state == ST_IDLE) ? '0 : response_word_count[$clog2(RESPONSE_WORD_CAPACITY)-1:0];
    assign result_mem_wr_en = result_fire && ((state == ST_IDLE) || (result_word_count < 10));
    assign result_mem_wr_addr = (state == ST_IDLE) ? '0 : result_word_count[3:0];

    b2_packet_bram #(.DATA_WIDTH(128), .DEPTH(RESPONSE_WORD_CAPACITY)) response_mem (
        .clk(clk), .rst(rst), .wr_en(response_mem_wr_en), .wr_addr(response_mem_wr_addr),
        .wr_data(rsp_data), .rd_en(response_mem_rd_en), .rd_addr(response_mem_rd_addr),
        .rd_data(response_mem_rd_data)
    );
    b2_packet_bram #(.DATA_WIDTH(32), .DEPTH(10), .ADDR_WIDTH(4)) result_mem (
        .clk(clk), .rst(rst), .wr_en(result_mem_wr_en), .wr_addr(result_mem_wr_addr),
        .wr_data(result_data), .rd_en(result_mem_rd_en), .rd_addr(result_mem_rd_addr),
        .rd_data(result_mem_rd_data)
    );
    logic [10:0] payload_word_count;
    logic [RESPONSE_COUNT_WIDTH-1:0] response_word_count;
    logic [10:0] result_word_count;
    logic [10:0] output_index;
    logic [10:0] output_frame_words;
    logic [31:0] sequence_reg, sample_id_reg, model_id_reg, mask_epoch_reg, status_reg;
    logic [7:0] message_type_reg;
    logic [31:0] crc_state;
    logic [31:0] crc_word_data;
    logic [1:0]  crc_byte_index;
    logic        crc_busy;
    logic        output_data_valid;

    wire rsp_fire = rsp_valid && rsp_ready;
    wire result_fire = result_valid && result_ready;
    wire m_fire = m_valid && m_ready;
    // 元数据只在新帧首拍更新，避免输出索引/下游 READY 参与寄存器 CE 组合链。
    wire rsp_metadata_fire = rsp_fire && (state == ST_IDLE) &&
        (response_word_count + 1'b1 <= RESPONSE_WORD_CAPACITY);
    wire result_metadata_fire = result_fire && (state == ST_IDLE);

    function automatic [31:0] crc32_byte(input [31:0] crc, input [7:0] data);
        integer bit_index;
        reg [31:0] value;
        begin
            value = crc ^ data;
            for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1) begin
                if (value[0]) value = (value >> 1) ^ 32'hEDB8_8320;
                else value = value >> 1;
            end
            crc32_byte = value;
        end
    endfunction

    // 保留字级参考函数，供静态合同和离线交叉核对使用；硬件路径按字节分拍执行。
    function automatic [31:0] crc32_word(input [31:0] crc, input [31:0] data);
        integer byte_index;
        reg [31:0] value;
        begin
            value = crc;
            for (byte_index = 0; byte_index < 4; byte_index = byte_index + 1)
                value = crc32_byte(value, data[byte_index * 8 +: 8]);
            crc32_word = value;
        end
    endfunction

    assign rsp_ready = (state == ST_RSP_COLLECT) || ((state == ST_IDLE) && !result_valid);
    assign result_ready = (state == ST_RESULT_COLLECT) || ((state == ST_IDLE) && !rsp_valid);
    assign busy = (state != ST_IDLE);
    assign m_valid = (state == ST_OUTPUT) &&
        !crc_busy &&
        ((output_index < HEADER_WORDS) || (output_index == output_frame_words) || output_data_valid);
    assign m_keep = 4'hF;
    assign m_last = (output_index == output_frame_words);

    always_comb begin
        if (output_index == 0) m_data = MAGIC;
        else if (output_index == 1)
            m_data = {8'd8, 8'd0, message_type_reg, 8'd1};
        else if (output_index == 2) m_data = payload_word_count * 4;
        else if (output_index == 3) m_data = sequence_reg;
        else if (output_index == 4) m_data = sample_id_reg;
        else if (output_index == 5) m_data = model_id_reg;
        else if (output_index == 6) m_data = mask_epoch_reg;
        else if (output_index == 7) m_data = status_reg;
        else if (output_index < output_frame_words) begin
            if (message_type_reg == TYPE_RESPONSE)
                m_data = response_mem_rd_data[(output_index[1:0]) * 32 +: 32];
            else
                m_data = result_mem_rd_data;
        end else m_data = ~crc_state;
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            sequence_reg <= '0;
            sample_id_reg <= '0;
            model_id_reg <= '0;
            mask_epoch_reg <= '0;
            status_reg <= '0;
            message_type_reg <= '0;
        end else if (rsp_metadata_fire) begin
            sequence_reg <= rsp_sequence;
            model_id_reg <= rsp_model_id;
            mask_epoch_reg <= rsp_mask_epoch;
            status_reg <= rsp_status;
            message_type_reg <= TYPE_RESPONSE;
        end else if (result_metadata_fire) begin
            sequence_reg <= result_sequence;
            sample_id_reg <= result_sample_id;
            model_id_reg <= result_model_id;
            mask_epoch_reg <= result_mask_epoch;
            status_reg <= result_status;
            message_type_reg <= TYPE_RESULT;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= ST_IDLE;
            payload_word_count <= '0;
            response_word_count <= '0;
            result_word_count <= '0;
            output_index <= '0;
            output_frame_words <= '0;
            crc_state <= 32'hFFFF_FFFF;
            crc_word_data <= '0;
            crc_byte_index <= '0;
            crc_busy <= 1'b0;
            output_data_valid <= 1'b0;
            response_mem_rd_en <= 1'b0;
            response_mem_rd_addr <= '0;
            result_mem_rd_en <= 1'b0;
            result_mem_rd_addr <= '0;
            error_valid <= 1'b0;
            error_code <= '0;
        end else begin
            error_valid <= 1'b0;
            // CRC 分拍期间完成下一 payload word 的同步 BRAM 预取。
            response_mem_rd_en <= 1'b0;
            result_mem_rd_en <= 1'b0;

            if (crc_busy) begin
                // 每拍只展开一个字节，切断 BRAM 输出到 CRC 状态寄存器的长组合路径。
                crc_state <= crc32_byte(crc_state,
                    crc_word_data[crc_byte_index * 8 +: 8]);
                if (crc_byte_index == 2'd3) begin
                    crc_byte_index <= '0;
                    crc_busy <= 1'b0;
                    output_index <= output_index + 1'b1;
                end else begin
                    crc_byte_index <= crc_byte_index + 1'b1;
                end
            end else if ((state == ST_OUTPUT) && (output_index >= HEADER_WORDS) &&
                (output_index < output_frame_words) && !output_data_valid) begin
                output_data_valid <= 1'b1;
            end else if (m_fire) begin
                if (output_index == HEADER_WORDS - 1) begin
                    if (message_type_reg == TYPE_RESPONSE) begin
                        response_mem_rd_en <= 1'b1;
                        response_mem_rd_addr <= '0;
                    end else begin
                        result_mem_rd_en <= 1'b1;
                        result_mem_rd_addr <= '0;
                    end
                end else if ((output_index >= HEADER_WORDS) &&
                             (output_index < output_frame_words - 1)) begin
                    if ((message_type_reg == TYPE_RESPONSE) &&
                        (((output_index - HEADER_WORDS) & 3) == 3)) begin
                        response_mem_rd_en <= 1'b1;
                        response_mem_rd_addr <=
                            ((output_index - HEADER_WORDS) >> 2) + 1'b1;
                    end else if (message_type_reg == TYPE_RESULT) begin
                        result_mem_rd_en <= 1'b1;
                        result_mem_rd_addr <= output_index - HEADER_WORDS + 1'b1;
                    end
                end
                if (output_index == output_frame_words) begin
                    state <= ST_IDLE;
                    output_index <= '0;
                    output_data_valid <= 1'b0;
                end else begin
                    crc_word_data <= m_data;
                    crc_byte_index <= '0;
                    crc_busy <= 1'b1;
                    output_data_valid <= 1'b0;
                end
            end else if (rsp_fire) begin
                if ((state == ST_IDLE) || (response_word_count + 1'b1 > RESPONSE_WORD_CAPACITY)) begin
                    if (response_word_count + 1'b1 > RESPONSE_WORD_CAPACITY) begin
                        error_valid <= 1'b1;
                        error_code <= ERR_OVERFLOW;
                        state <= ST_IDLE;
                    end else begin
                        response_word_count <= 1;
                        if (rsp_last) begin
                            payload_word_count <= 4;
                            output_frame_words <= HEADER_WORDS + 4;
                            output_index <= '0;
                            crc_state <= 32'hFFFF_FFFF;
                            output_data_valid <= 1'b0;
                            state <= ST_OUTPUT;
                        end else state <= ST_RSP_COLLECT;
                    end
                end else begin
                    response_word_count <= response_word_count + 1'b1;
                    if (rsp_last) begin
                        payload_word_count <= (response_word_count + 1'b1) * 4;
                        output_frame_words <= HEADER_WORDS + (response_word_count + 1'b1) * 4;
                        output_index <= '0;
                        crc_state <= 32'hFFFF_FFFF;
                        output_data_valid <= 1'b0;
                        state <= ST_OUTPUT;
                    end
                end
            end else if (result_fire) begin
                if (state == ST_IDLE) begin
                    result_word_count <= 1;
                    state <= ST_RESULT_COLLECT;
                end else if ((result_sample_id != sample_id_reg) ||
                             (result_model_id != model_id_reg) ||
                             (result_mask_epoch != mask_epoch_reg) ||
                             (result_sequence != sequence_reg)) begin
                    error_valid <= 1'b1;
                    error_code <= ERR_RESULT_METADATA;
                    state <= ST_IDLE;
                end else begin
                    if (result_word_count == 9) begin
                        payload_word_count <= 10;
                        output_frame_words <= HEADER_WORDS + 10;
                        output_index <= '0;
                        crc_state <= 32'hFFFF_FFFF;
                        output_data_valid <= 1'b0;
                        state <= ST_OUTPUT;
                    end else result_word_count <= result_word_count + 1'b1;
                end
            end
        end
    end
endmodule
