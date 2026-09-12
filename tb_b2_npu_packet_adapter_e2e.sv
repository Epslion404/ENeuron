`timescale 1ns/1ps

module tb_b2_npu_packet_adapter_e2e;
    logic host_clk = 1'b0;
    logic npu_clk = 1'b0;
    logic rst = 1'b1;
    logic s_valid = 1'b0;
    logic [31:0] s_data = '0;
    logic [3:0] s_keep = 4'hf;
    logic s_last = 1'b0;
    wire s_ready;
    wire m_valid;
    logic m_ready = 1'b1;
    wire [31:0] m_data;
    wire [3:0] m_keep;
    wire m_last;
    wire error_valid;
    wire [3:0] error_code;
    wire busy;
    wire host_error;
    wire host_model_valid;
    wire host_mask_valid;
    wire host_infer_frozen;
    wire host_status_irq;

    always #5 host_clk = ~host_clk;
    always #7 npu_clk = ~npu_clk;

    b2_npu_packet_adapter dut (
        .host_clk(host_clk), .npu_clk(npu_clk), .bridge_rst(rst),
        .s_valid(s_valid), .s_ready(s_ready), .s_data(s_data),
        .s_keep(s_keep), .s_last(s_last), .m_valid(m_valid),
        .m_ready(m_ready), .m_data(m_data), .m_keep(m_keep),
        .m_last(m_last), .error_valid(error_valid), .error_code(error_code),
        .busy(busy), .host_error(host_error), .host_model_valid(host_model_valid),
        .host_mask_valid(host_mask_valid), .host_infer_frozen(host_infer_frozen),
        .host_status_irq(host_status_irq)
    );

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
                for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1)
                    value = value[0] ? ((value >> 1) ^ 32'hEDB8_8320) : (value >> 1);
            end
            crc32_word = value;
        end
    endfunction

    task automatic send_word(input logic [31:0] data, input logic last);
        begin
            @(negedge host_clk);
            while (!s_ready) @(negedge host_clk);
            s_data = data;
            s_last = last;
            s_valid = 1'b1;
            @(posedge host_clk);
            while (!s_ready) @(posedge host_clk);
            @(negedge host_clk);
            s_valid = 1'b0;
            s_last = 1'b0;
            s_data = '0;
        end
    endtask

    task automatic send_command_frame(
        input integer count,
        input logic [3:0] opcode,
        input logic [31:0] epoch,
        input logic [31:0] seq,
        input logic [31:0] model_id,
        input logic [31:0] fence_id
    );
        integer i;
        logic [31:0] crc;
        logic [127:0] command_word;
        logic [31:0] low_word;
        begin
            crc = 32'hffff_ffff;
            send_word(32'h3242_4e45, 1'b0); crc = crc32_word(crc, 32'h3242_4e45);
            send_word({8'd8, 8'd0, 8'd1, 8'd1}, 1'b0); crc = crc32_word(crc, {8'd8, 8'd0, 8'd1, 8'd1});
            send_word(count * 16, 1'b0); crc = crc32_word(crc, count * 16);
            send_word(seq, 1'b0); crc = crc32_word(crc, seq);
            send_word(32'd0, 1'b0); crc = crc32_word(crc, 32'd0);
            send_word(model_id, 1'b0); crc = crc32_word(crc, model_id);
            send_word(epoch, 1'b0); crc = crc32_word(crc, epoch);
            send_word(32'd0, 1'b0); crc = crc32_word(crc, 32'd0);
            for (i = 0; i < count; i = i + 1) begin
                if (opcode == 4'ha)
                    low_word = fence_id;
                else if (opcode == 4'h5)
                    low_word = (i == 18) ? 32'h0000_ffff : 32'hffff_ffff;
                else
                    low_word = 32'd0;
                command_word = {opcode, 4'd0,
                    ((opcode == 4'h4 || opcode == 4'h6) ? epoch : 32'd0),
                    56'd0, low_word};
                send_word(command_word[31:0], 1'b0); crc = crc32_word(crc, command_word[31:0]);
                send_word(command_word[63:32], 1'b0); crc = crc32_word(crc, command_word[63:32]);
                send_word(command_word[95:64], 1'b0); crc = crc32_word(crc, command_word[95:64]);
                send_word(command_word[127:96], 1'b0); crc = crc32_word(crc, command_word[127:96]);
            end
            send_word(~crc, 1'b1);
        end
    endtask

    task automatic send_sample_frame(
        input logic [31:0] seq,
        input logic [31:0] sample_id,
        input logic [31:0] model_id,
        input logic [31:0] epoch
    );
        integer i;
        logic [31:0] crc;
        begin
            crc = 32'hffff_ffff;
            send_word(32'h3242_4e45, 1'b0); crc = crc32_word(crc, 32'h3242_4e45);
            send_word({8'd8, 8'd0, 8'd2, 8'd1}, 1'b0); crc = crc32_word(crc, {8'd8, 8'd0, 8'd2, 8'd1});
            send_word(32'd32, 1'b0); crc = crc32_word(crc, 32'd32);
            send_word(seq, 1'b0); crc = crc32_word(crc, seq);
            send_word(sample_id, 1'b0); crc = crc32_word(crc, sample_id);
            send_word(model_id, 1'b0); crc = crc32_word(crc, model_id);
            send_word(epoch, 1'b0); crc = crc32_word(crc, epoch);
            send_word(32'd0, 1'b0); crc = crc32_word(crc, 32'd0);
            for (i = 0; i < 8; i = i + 1) begin
                send_word(i, 1'b0);
                crc = crc32_word(crc, i);
            end
            send_word(~crc, 1'b1);
        end
    endtask

    task automatic expect_frame_header(
        input integer total_words,
        input logic [31:0] message_word,
        input logic [31:0] payload_length,
        input logic [31:0] seq,
        input logic [31:0] sample_id,
        input logic [31:0] model_id,
        input logic [31:0] epoch
    );
        integer i;
        logic [31:0] observed [0:18];
        begin
            for (i = 0; i < total_words; i = i + 1) begin
                while (!m_valid) @(posedge host_clk);
                observed[i] = m_data;
                if (m_keep !== 4'hf) $fatal(1, "egress keep changed");
                if (i == total_words - 1 && !m_last) $fatal(1, "egress missed TLAST");
                if (i != total_words - 1 && m_last) $fatal(1, "egress asserted TLAST early");
                @(posedge host_clk);
            end
            if (observed[0] !== 32'h3242_4e45 || observed[1] !== message_word)
                $fatal(1, "bad packet header");
            if (observed[2] !== payload_length || observed[3] !== seq)
                $fatal(1, "sequence or length metadata mismatch");
            if (observed[4] !== sample_id || observed[5] !== model_id || observed[6] !== epoch)
                $fatal(1, "sideband metadata mismatch");
            if (payload_length == 32'd40)
                for (i = 8; i < 18; i = i + 1)
                    if (observed[i] !== 32'd0) $fatal(1, "expected zero result beat %0d", i - 8);
        end
    endtask

    integer i;
    initial begin
        repeat (8) @(posedge host_clk);
        rst = 1'b0;
        repeat (8) @(posedge host_clk);

        // 634 个模型 word 的装载已由 T1 wrapper 回归覆盖；本切片只预装
        // 零模型并把时间集中在 packet mask/fence/sample/result 端到端路径。
        dut.wrapper.core.model_state = 2'd3;
        dut.wrapper.core.model_valid = 1'b1;
        for (i = 0; i < 634; i = i + 1)
            dut.wrapper.core.model_staging[i] = 32'd0;
        @(posedge host_clk);

        // 合法 2:4 mask 同样拆帧；前 18 个 word 全开，末 word 仅低 16 位有效。
        send_command_frame(1,  4'h4, 32'd1, 32'd200, 32'd3, 32'd0);
        send_command_frame(19, 4'h5, 32'd1, 32'd201, 32'd3, 32'd0);
        send_command_frame(1,  4'h6, 32'd1, 32'd202, 32'd3, 32'd0);

        // fence 成功后才允许 sample frame；响应 header 必须使用 fence packet 元数据。
        send_command_frame(1, 4'ha, 32'd0, 32'd300, 32'd3, 32'h0000_0f00);
        expect_frame_header(13, 32'h0800_0301, 32'd16, 32'd300, 32'd0, 32'd3, 32'd0);

        send_sample_frame(32'd301, 32'h1234_5678, 32'd3, 32'd1);
        expect_frame_header(19, 32'h0800_0401, 32'd40, 32'd301,
                            32'h1234_5678, 32'd3, 32'd1);
        $display("B2_NPU_PACKET_ADAPTER_E2E_PASS");
        $finish;
    end
endmodule
