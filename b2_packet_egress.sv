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
    logic [31:0] payload_mem [0:PAYLOAD_WORD_CAPACITY-1];
    logic [10:0] payload_word_count;
    logic [10:0] response_word_count;
    logic [10:0] result_word_count;
    logic [10:0] output_index;
    logic [10:0] output_frame_words;
    logic [31:0] sequence_reg, sample_id_reg, model_id_reg, mask_epoch_reg, status_reg;
    logic [7:0] message_type_reg;
    logic [31:0] crc_state;

    wire rsp_fire = rsp_valid && rsp_ready;
    wire result_fire = result_valid && result_ready;
    wire m_fire = m_valid && m_ready;

    function automatic [31:0] crc32_word(input [31:0] crc, input [31:0] data);
        integer byte_index;
        integer bit_index;
        reg [31:0] value;
        reg [7:0] byte_value;
        begin
            value = crc;
            for (byte_index = 0; byte_index < 4; byte_index = byte_index + 1) begin
                byte_value = data[byte_index * 8 +: 8];
                value = value ^ byte_value;
                for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1) begin
                    if (value[0]) value = (value >> 1) ^ 32'hEDB8_8320;
                    else value = value >> 1;
                end
            end
            crc32_word = value;
        end
    endfunction

    assign rsp_ready = (state == ST_RSP_COLLECT) || ((state == ST_IDLE) && !result_valid);
    assign result_ready = (state == ST_RESULT_COLLECT) || ((state == ST_IDLE) && !rsp_valid);
    assign busy = (state != ST_IDLE);
    assign m_valid = (state == ST_OUTPUT);
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
        else if (output_index < output_frame_words)
            m_data = payload_mem[output_index - HEADER_WORDS];
        else m_data = ~crc_state;
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= ST_IDLE;
            payload_word_count <= '0;
            response_word_count <= '0;
            result_word_count <= '0;
            output_index <= '0;
            output_frame_words <= '0;
            sequence_reg <= '0;
            sample_id_reg <= '0;
            model_id_reg <= '0;
            mask_epoch_reg <= '0;
            status_reg <= '0;
            message_type_reg <= '0;
            crc_state <= 32'hFFFF_FFFF;
            error_valid <= 1'b0;
            error_code <= '0;
        end else begin
            error_valid <= 1'b0;

            if (m_fire) begin
                if (output_index == output_frame_words) begin
                    state <= ST_IDLE;
                    output_index <= '0;
                end else begin
                    if (output_index < output_frame_words)
                        crc_state <= crc32_word(crc_state, m_data);
                    output_index <= output_index + 1'b1;
                end
            end else if (rsp_fire) begin
                if ((state == ST_IDLE) || (response_word_count * 4 + 4 > PAYLOAD_WORD_CAPACITY)) begin
                    if (response_word_count * 4 + 4 > PAYLOAD_WORD_CAPACITY) begin
                        error_valid <= 1'b1;
                        error_code <= ERR_OVERFLOW;
                        state <= ST_IDLE;
                    end else begin
                        payload_mem[0] <= rsp_data[31:0];
                        payload_mem[1] <= rsp_data[63:32];
                        payload_mem[2] <= rsp_data[95:64];
                        payload_mem[3] <= rsp_data[127:96];
                        response_word_count <= 1;
                        sequence_reg <= rsp_sequence;
                        model_id_reg <= rsp_model_id;
                        mask_epoch_reg <= rsp_mask_epoch;
                        status_reg <= rsp_status;
                        message_type_reg <= TYPE_RESPONSE;
                        if (rsp_last) begin
                            payload_word_count <= 4;
                            output_frame_words <= HEADER_WORDS + 4;
                            output_index <= '0;
                            crc_state <= 32'hFFFF_FFFF;
                            state <= ST_OUTPUT;
                        end else state <= ST_RSP_COLLECT;
                    end
                end else begin
                    payload_mem[response_word_count * 4] <= rsp_data[31:0];
                    payload_mem[response_word_count * 4 + 1] <= rsp_data[63:32];
                    payload_mem[response_word_count * 4 + 2] <= rsp_data[95:64];
                    payload_mem[response_word_count * 4 + 3] <= rsp_data[127:96];
                    response_word_count <= response_word_count + 1'b1;
                    if (rsp_last) begin
                        payload_word_count <= (response_word_count + 1'b1) * 4;
                        output_frame_words <= HEADER_WORDS + (response_word_count + 1'b1) * 4;
                        output_index <= '0;
                        crc_state <= 32'hFFFF_FFFF;
                        state <= ST_OUTPUT;
                    end
                end
            end else if (result_fire) begin
                if (state == ST_IDLE) begin
                    payload_mem[0] <= result_data;
                    result_word_count <= 1;
                    sequence_reg <= result_sequence;
                    sample_id_reg <= result_sample_id;
                    model_id_reg <= result_model_id;
                    mask_epoch_reg <= result_mask_epoch;
                    status_reg <= result_status;
                    message_type_reg <= TYPE_RESULT;
                    state <= ST_RESULT_COLLECT;
                end else if ((result_sample_id != sample_id_reg) ||
                             (result_model_id != model_id_reg) ||
                             (result_mask_epoch != mask_epoch_reg) ||
                             (result_sequence != sequence_reg)) begin
                    error_valid <= 1'b1;
                    error_code <= ERR_RESULT_METADATA;
                    state <= ST_IDLE;
                end else begin
                    payload_mem[result_word_count] <= result_data;
                    if (result_word_count == 9) begin
                        payload_word_count <= 10;
                        output_frame_words <= HEADER_WORDS + 10;
                        output_index <= '0;
                        crc_state <= 32'hFFFF_FFFF;
                        state <= ST_OUTPUT;
                    end else result_word_count <= result_word_count + 1'b1;
                end
            end
        end
    end
endmodule
