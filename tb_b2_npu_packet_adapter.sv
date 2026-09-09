`timescale 1ns/1ps

module tb_b2_npu_packet_adapter;
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

    integer word_index;
    logic [31:0] observed [0:12];
    initial begin
        repeat (8) @(posedge host_clk);
        rst = 1'b0;
        repeat (8) @(posedge host_clk);

        // 一个未知 opcode 命令：必须完整进入核心并以单词响应返回，
        // egress 还要恢复 ingress 保存的 sequence/model/epoch。
        send_word(32'h3242_4e45, 1'b0);
        send_word(32'h0800_0101, 1'b0);
        send_word(32'h0000_0010, 1'b0);
        send_word(32'h1122_3344, 1'b0);
        send_word(32'h0000_0000, 1'b0);
        send_word(32'h5566_7788, 1'b0);
        send_word(32'h99aa_bbcc, 1'b0);
        send_word(32'h0000_0000, 1'b0);
        send_word(32'h0000_0001, 1'b0);
        send_word(32'h0000_0000, 1'b0);
        send_word(32'h0000_0000, 1'b0);
        send_word(32'hf000_0000, 1'b0);
        send_word(32'h2adb_7c7c, 1'b1);

        word_index = 0;
        while (word_index < 13) begin
            @(posedge host_clk);
            if (m_valid) begin
                observed[word_index] = m_data;
                if (m_keep !== 4'hf) $fatal(1, "adapter changed keep");
                if (word_index == 12 && !m_last) $fatal(1, "adapter missed response TLAST");
                if (word_index != 12 && m_last) $fatal(1, "adapter asserted early TLAST");
                word_index = word_index + 1;
            end
        end
        if (observed[0] !== 32'h3242_4e45) $fatal(1, "bad response magic");
        if (observed[1] !== 32'h0800_0301) $fatal(1, "bad response type/version");
        if (observed[2] !== 32'h0000_0010) $fatal(1, "bad response payload length");
        if (observed[3] !== 32'h1122_3344) $fatal(1, "sequence metadata was lost");
        if (observed[5] !== 32'h5566_7788) $fatal(1, "model metadata was lost");
        if (observed[6] !== 32'h99aa_bbcc) $fatal(1, "mask metadata was lost");
        if (observed[11][31:28] !== 4'he) $fatal(1, "core error response was not framed");
        $display("B2_NPU_PACKET_ADAPTER_PASS");
        $finish;
    end
endmodule
