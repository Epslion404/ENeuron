// B2 外层帧 ingress：先完整缓存并校验 DMA 帧，再向 NPU 命令/样本流发布。
// 该切片只负责 Host -> NPU；response/result 的反向封装由后续 egress 实现。
module b2_packet_ingress #(
    parameter integer PAYLOAD_WORD_CAPACITY = 1015
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        s_valid,
    output logic        s_ready,
    input  logic [31:0] s_data,
    input  logic [3:0]  s_keep,
    input  logic        s_last,

    output logic        cmd_valid,
    input  logic        cmd_ready,
    output logic [127:0] cmd_data,
    output logic [31:0] cmd_sequence,
    output logic [31:0] cmd_model_id,
    output logic [31:0] cmd_mask_epoch,

    output logic        sample_valid,
    input  logic        sample_ready,
    output logic [31:0] sample_data,
    output logic [31:0] sample_id,
    output logic [31:0] sample_sequence,
    output logic [31:0] sample_model_id,
    output logic [31:0] sample_mask_epoch,

    output logic        error_valid,
    output logic [3:0]  error_code,
    output logic        busy
);
    localparam logic [31:0] MAGIC = 32'h3242_4e45;
    localparam integer HEADER_WORDS = 8;
    localparam integer HEADER_BYTES = 32;
    localparam integer CRC_BYTES = 4;
    localparam integer MAX_PAYLOAD_BYTES = 4096 - HEADER_BYTES - CRC_BYTES;

    localparam logic [3:0] ERR_BAD_MAGIC     = 4'h1;
    localparam logic [3:0] ERR_BAD_VERSION   = 4'h2;
    localparam logic [3:0] ERR_BAD_TYPE      = 4'h3;
    localparam logic [3:0] ERR_BAD_FLAGS     = 4'h4;
    localparam logic [3:0] ERR_BAD_HEADER    = 4'h5;
    localparam logic [3:0] ERR_BAD_LENGTH    = 4'h6;
    localparam logic [3:0] ERR_BAD_KEEP      = 4'h7;
    localparam logic [3:0] ERR_TLAST_EARLY   = 4'h8;
    localparam logic [3:0] ERR_TLAST_LATE    = 4'h9;
    localparam logic [3:0] ERR_BAD_CRC       = 4'hA;
    localparam logic [3:0] ERR_BAD_DIRECTION = 4'hB;

    localparam logic [7:0] TYPE_COMMAND = 8'd1;
    localparam logic [7:0] TYPE_SAMPLE  = 8'd2;

    typedef enum logic [2:0] {
        ST_IDLE,
        ST_HEADER,
        ST_PAYLOAD,
        ST_CRC,
        ST_DROP,
        ST_CMD_OUT,
        ST_SAMPLE_OUT
    } state_t;

    state_t state;
    // 四个 bank 让 command 四字并行读；同步读端口可稳定推断为 BRAM。
    localparam integer PAYLOAD_BANK_CAPACITY = (PAYLOAD_WORD_CAPACITY + 3) / 4;
    (* ram_style = "block" *) logic [31:0] payload_mem_bank0 [0:PAYLOAD_BANK_CAPACITY-1];
    (* ram_style = "block" *) logic [31:0] payload_mem_bank1 [0:PAYLOAD_BANK_CAPACITY-1];
    (* ram_style = "block" *) logic [31:0] payload_mem_bank2 [0:PAYLOAD_BANK_CAPACITY-1];
    (* ram_style = "block" *) logic [31:0] payload_mem_bank3 [0:PAYLOAD_BANK_CAPACITY-1];
    logic [31:0] crc_state;
    logic [3:0]  header_index;
    logic [7:0]  message_type;
    logic [31:0] payload_length;
    logic [31:0] sequence_reg;
    logic [31:0] sample_id_reg;
    logic [31:0] model_id_reg;
    logic [31:0] mask_epoch_reg;
    logic [31:0] status_reg;
    logic [10:0] payload_word_index;
    logic [10:0] payload_word_expected;
    logic [9:0]  output_index;
    logic [9:0]  output_count;
    logic [31:0] sample_data_reg;
    logic [127:0] cmd_data_reg;
    logic        output_data_valid;
    logic        frame_error;
    logic [3:0]  frame_error_code;

    wire s_fire = s_valid && s_ready;
    wire cmd_fire = cmd_valid && cmd_ready;
    wire sample_fire = sample_valid && sample_ready;

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

    assign s_ready = (state != ST_CMD_OUT) && (state != ST_SAMPLE_OUT);
    assign busy = (state != ST_IDLE);

    always_comb begin
        cmd_valid = (state == ST_CMD_OUT) && output_data_valid;
        cmd_data = cmd_data_reg;
        cmd_sequence = sequence_reg;
        cmd_model_id = model_id_reg;
        cmd_mask_epoch = mask_epoch_reg;

        sample_valid = (state == ST_SAMPLE_OUT) && output_data_valid;
        sample_data = sample_data_reg;
        sample_id = sample_id_reg;
        sample_sequence = sequence_reg;
        sample_model_id = model_id_reg;
        sample_mask_epoch = mask_epoch_reg;
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= ST_IDLE;
            crc_state <= 32'hFFFF_FFFF;
            header_index <= '0;
            message_type <= '0;
            payload_length <= '0;
            sequence_reg <= '0;
            sample_id_reg <= '0;
            model_id_reg <= '0;
            mask_epoch_reg <= '0;
            status_reg <= '0;
            payload_word_index <= '0;
            payload_word_expected <= '0;
            output_index <= '0;
            output_count <= '0;
            sample_data_reg <= '0;
            cmd_data_reg <= '0;
            output_data_valid <= 1'b0;
            frame_error <= 1'b0;
            frame_error_code <= '0;
            error_valid <= 1'b0;
            error_code <= '0;
        end else begin
            error_valid <= 1'b0;

            if ((state == ST_CMD_OUT || state == ST_SAMPLE_OUT) && !output_data_valid) begin
                if (state == ST_CMD_OUT) begin
                    cmd_data_reg <= {
                        payload_mem_bank3[output_index],
                        payload_mem_bank2[output_index],
                        payload_mem_bank1[output_index],
                        payload_mem_bank0[output_index]
                    };
                end else begin
                    case (output_index[1:0])
                        2'd0: sample_data_reg <= payload_mem_bank0[output_index >> 2];
                        2'd1: sample_data_reg <= payload_mem_bank1[output_index >> 2];
                        2'd2: sample_data_reg <= payload_mem_bank2[output_index >> 2];
                        default: sample_data_reg <= payload_mem_bank3[output_index >> 2];
                    endcase
                end
                output_data_valid <= 1'b1;
            end else if (cmd_fire) begin
                output_data_valid <= 1'b0;
                if (output_index + 1'b1 >= output_count) begin
                    state <= ST_IDLE;
                    output_index <= '0;
                end else begin
                    output_index <= output_index + 1'b1;
                end
            end else if (sample_fire) begin
                output_data_valid <= 1'b0;
                if (output_index + 1'b1 >= output_count) begin
                    state <= ST_IDLE;
                    output_index <= '0;
                end else begin
                    output_index <= output_index + 1'b1;
                end
            end else if (s_fire) begin
                case (state)
                    ST_IDLE: begin
                        frame_error <= 1'b0;
                        if (s_keep != 4'hF) begin
                            error_code <= ERR_BAD_KEEP;
                            if (s_last) begin
                                error_valid <= 1'b1;
                                state <= ST_IDLE;
                            end else begin
                                frame_error <= 1'b1;
                                frame_error_code <= ERR_BAD_KEEP;
                                state <= ST_DROP;
                            end
                        end else if (s_data != MAGIC) begin
                            error_code <= ERR_BAD_MAGIC;
                            if (s_last) begin
                                error_valid <= 1'b1;
                                state <= ST_IDLE;
                            end else begin
                                frame_error <= 1'b1;
                                frame_error_code <= ERR_BAD_MAGIC;
                                state <= ST_DROP;
                            end
                        end else begin
                            crc_state <= crc32_word(32'hFFFF_FFFF, s_data);
                            header_index <= 4'd1;
                            state <= ST_HEADER;
                        end
                    end

                    ST_HEADER: begin
                        if (s_keep != 4'hF) begin
                            frame_error <= 1'b1;
                            frame_error_code <= ERR_BAD_KEEP;
                            if (s_last) begin
                                error_valid <= 1'b1;
                                error_code <= ERR_BAD_KEEP;
                                state <= ST_IDLE;
                            end else state <= ST_DROP;
                        end else if (s_last) begin
                            error_valid <= 1'b1;
                            error_code <= ERR_TLAST_EARLY;
                            state <= ST_IDLE;
                        end else begin
                            crc_state <= crc32_word(crc_state, s_data);
                            case (header_index)
                                4'd1: begin
                                    if (s_data[7:0] != 8'd1) begin
                                        frame_error <= 1'b1;
                                        frame_error_code <= ERR_BAD_VERSION;
                                    end else if ((s_data[23:16] != 8'd0) ||
                                                 (s_data[31:24] != HEADER_WORDS)) begin
                                        frame_error <= 1'b1;
                                        frame_error_code <= (s_data[23:16] != 8'd0) ? ERR_BAD_FLAGS : ERR_BAD_HEADER;
                                    end
                                    message_type <= s_data[15:8];
                                end
                                4'd2: begin
                                    payload_length <= s_data;
                                    if ((s_data == 0) || (s_data > MAX_PAYLOAD_BYTES) || (s_data[1:0] != 0)) begin
                                        frame_error <= 1'b1;
                                        frame_error_code <= ERR_BAD_LENGTH;
                                    end
                                end
                                4'd3: sequence_reg <= s_data;
                                4'd4: sample_id_reg <= s_data;
                                4'd5: model_id_reg <= s_data;
                                4'd6: mask_epoch_reg <= s_data;
                                4'd7: begin
                                    status_reg <= s_data;
                                    if (frame_error) begin
                                        state <= ST_DROP;
                                    end else if (message_type == TYPE_COMMAND) begin
                                        if ((payload_length[3:0] != 0) || (payload_length > MAX_PAYLOAD_BYTES)) begin
                                            frame_error <= 1'b1;
                                            frame_error_code <= ERR_BAD_LENGTH;
                                            state <= ST_DROP;
                                        end else begin
                                            payload_word_expected <= payload_length >> 2;
                                            payload_word_index <= '0;
                                            state <= ST_PAYLOAD;
                                        end
                                    end else if (message_type == TYPE_SAMPLE) begin
                                        if (payload_length != 32) begin
                                            frame_error <= 1'b1;
                                            frame_error_code <= ERR_BAD_LENGTH;
                                            state <= ST_DROP;
                                        end else begin
                                            payload_word_expected <= 11'd8;
                                            payload_word_index <= '0;
                                            state <= ST_PAYLOAD;
                                        end
                                    end else begin
                                        frame_error <= 1'b1;
                                        frame_error_code <= (message_type == 8'd3 || message_type == 8'd4)
                                            ? ERR_BAD_DIRECTION : ERR_BAD_TYPE;
                                        state <= ST_DROP;
                                    end
                                end
                                default: begin
                                    frame_error <= 1'b1;
                                    frame_error_code <= ERR_BAD_HEADER;
                                end
                            endcase
                            if (header_index != 4'd7) header_index <= header_index + 1'b1;
                        end
                    end

                    ST_PAYLOAD: begin
                        if (s_keep != 4'hF) begin
                            frame_error <= 1'b1;
                            frame_error_code <= ERR_BAD_KEEP;
                            if (s_last) begin
                                error_valid <= 1'b1;
                                error_code <= ERR_BAD_KEEP;
                                state <= ST_IDLE;
                            end else state <= ST_DROP;
                        end else if (s_last) begin
                            error_valid <= 1'b1;
                            error_code <= ERR_TLAST_EARLY;
                            state <= ST_IDLE;
                        end else if (payload_word_index >= PAYLOAD_WORD_CAPACITY) begin
                            frame_error <= 1'b1;
                            frame_error_code <= ERR_BAD_LENGTH;
                            state <= ST_DROP;
                        end else begin
                            case (payload_word_index[1:0])
                                2'd0: payload_mem_bank0[payload_word_index >> 2] <= s_data;
                                2'd1: payload_mem_bank1[payload_word_index >> 2] <= s_data;
                                2'd2: payload_mem_bank2[payload_word_index >> 2] <= s_data;
                                default: payload_mem_bank3[payload_word_index >> 2] <= s_data;
                            endcase
                            crc_state <= crc32_word(crc_state, s_data);
                            if (payload_word_index + 1'b1 >= payload_word_expected) begin
                                state <= ST_CRC;
                            end else begin
                                payload_word_index <= payload_word_index + 1'b1;
                            end
                        end
                    end

                    ST_CRC: begin
                        if (s_keep != 4'hF) begin
                            error_valid <= 1'b1;
                            error_code <= ERR_BAD_KEEP;
                            state <= s_last ? ST_IDLE : ST_DROP;
                            frame_error <= 1'b1;
                            frame_error_code <= ERR_BAD_KEEP;
                        end else if (s_data != ~crc_state) begin
                            error_valid <= 1'b1;
                            error_code <= ERR_BAD_CRC;
                            state <= s_last ? ST_IDLE : ST_DROP;
                            frame_error <= 1'b1;
                            frame_error_code <= ERR_BAD_CRC;
                        end else if (!s_last) begin
                            error_valid <= 1'b1;
                            error_code <= ERR_TLAST_LATE;
                            state <= ST_DROP;
                            frame_error <= 1'b1;
                            frame_error_code <= ERR_TLAST_LATE;
                        end else if (frame_error) begin
                            error_valid <= 1'b1;
                            error_code <= frame_error_code;
                            state <= ST_IDLE;
                        end else if (message_type == TYPE_COMMAND) begin
                            output_index <= '0;
                            output_count <= payload_length >> 4;
                            output_data_valid <= 1'b0;
                            state <= ST_CMD_OUT;
                        end else begin
                            output_index <= '0;
                            output_count <= 10'd8;
                            output_data_valid <= 1'b0;
                            state <= ST_SAMPLE_OUT;
                        end
                    end

                    ST_DROP: begin
                        if (s_last) begin
                            error_valid <= 1'b1;
                            error_code <= frame_error_code;
                            state <= ST_IDLE;
                            frame_error <= 1'b0;
                        end
                    end

                    default: state <= ST_IDLE;
                endcase
            end
        end
    end
endmodule
