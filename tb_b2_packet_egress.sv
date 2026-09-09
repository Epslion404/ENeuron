module tb_b2_packet_egress;
    logic clk = 1'b0;
    logic rst = 1'b1;
    logic rsp_valid = 1'b0;
    wire rsp_ready;
    logic [127:0] rsp_data = '0;
    logic rsp_last = 1'b0;
    logic [31:0] rsp_sequence = 8;
    logic [31:0] rsp_model_id = 3;
    logic [31:0] rsp_mask_epoch = 11;
    logic [31:0] rsp_status = 5;
    logic result_valid = 1'b0;
    wire result_ready;
    logic [31:0] result_data = '0;
    logic [31:0] result_sample_id = 42;
    logic [31:0] result_model_id = 3;
    logic [31:0] result_mask_epoch = 11;
    logic [31:0] result_sequence = 9;
    logic [31:0] result_status = 0;
    wire m_valid;
    logic m_ready = 1'b0;
    wire [31:0] m_data;
    wire [3:0] m_keep;
    wire m_last;
    wire error_valid;
    wire [3:0] error_code;
    wire busy;

    always #5 clk = ~clk;
    b2_packet_egress dut (
        .clk(clk), .rst(rst),
        .rsp_valid(rsp_valid), .rsp_ready(rsp_ready), .rsp_data(rsp_data), .rsp_last(rsp_last),
        .rsp_sequence(rsp_sequence), .rsp_model_id(rsp_model_id), .rsp_mask_epoch(rsp_mask_epoch),
        .rsp_status(rsp_status), .result_valid(result_valid), .result_ready(result_ready),
        .result_data(result_data), .result_sample_id(result_sample_id), .result_model_id(result_model_id),
        .result_mask_epoch(result_mask_epoch), .result_sequence(result_sequence), .result_status(result_status),
        .m_valid(m_valid), .m_ready(m_ready), .m_data(m_data), .m_keep(m_keep), .m_last(m_last),
        .error_valid(error_valid), .error_code(error_code), .busy(busy)
    );

    task automatic send_rsp(input logic [127:0] data, input logic last);
        begin
            @(negedge clk);
            while (!rsp_ready) @(negedge clk);
            rsp_data = data;
            rsp_last = last;
            rsp_valid = 1'b1;
            @(posedge clk);
            @(negedge clk);
            rsp_valid = 1'b0;
            rsp_last = 1'b0;
        end
    endtask

    task automatic send_result(input logic [31:0] data, input logic [31:0] sid);
        begin
            @(negedge clk);
            while (!result_ready) @(negedge clk);
            result_data = data;
            result_sample_id = sid;
            result_valid = 1'b1;
            @(posedge clk);
            @(negedge clk);
            result_valid = 1'b0;
        end
    endtask

    task automatic expect_word(input logic [31:0] expected, input logic last);
        begin
            // egress 的 CRC 状态机允许内部气泡；在负边沿等待，避免跨 NBA 竞态。
            #1;
            while (!m_valid) @(negedge clk);
            #1;
            if (m_data !== expected || m_keep !== 4'hF || m_last !== last)
                $fatal(1, "egress word=%h keep=%h last=%b expected=%h/%b", m_data, m_keep, m_last, expected, last);
            @(posedge clk);
            #1;
        end
    endtask

    integer i;
    initial begin
        repeat (4) @(posedge clk);
        rst = 1'b0;
        repeat (3) @(posedge clk);
        m_ready = 1'b1;

        // One response word.
        send_rsp(128'h0000_0000_0000_0000_0000_0000_0000_0001, 1'b1);
        expect_word(32'h3242_4e45, 1'b0);
        expect_word(32'h0800_0301, 1'b0);
        expect_word(32'h0000_0010, 1'b0);
        expect_word(32'h0000_0008, 1'b0);
        expect_word(32'h0000_0000, 1'b0);
        expect_word(32'h0000_0003, 1'b0);
        expect_word(32'h0000_000b, 1'b0);
        expect_word(32'h0000_0005, 1'b0);
        expect_word(32'h0000_0001, 1'b0);
        expect_word(32'h0000_0000, 1'b0);
        expect_word(32'h0000_0000, 1'b0);
        expect_word(32'h0000_0000, 1'b0);
        expect_word(32'hc6d5_f123, 1'b1);

        // Ten result beats.
        for (i = 0; i < 10; i = i + 1) send_result(i, 32'd42);
        expect_word(32'h3242_4e45, 1'b0);
        expect_word(32'h0800_0401, 1'b0);
        expect_word(32'h0000_0028, 1'b0);
        expect_word(32'h0000_0009, 1'b0);
        expect_word(32'h0000_002a, 1'b0);
        expect_word(32'h0000_0003, 1'b0);
        expect_word(32'h0000_000b, 1'b0);
        expect_word(32'h0000_0000, 1'b0);
        for (i = 0; i < 10; i = i + 1) expect_word(i, i == 9 ? 1'b0 : 1'b0);
        expect_word(32'h5bb6_4098, 1'b1);

        // Metadata change inside a result is rejected before any frame is emitted.
        for (i = 0; i < 2; i = i + 1) send_result(i, i == 0 ? 32'd42 : 32'd43);
        while (!error_valid) @(posedge clk);
        if (error_code !== 4'h2 || m_valid) $fatal(1, "bad result metadata was not rejected");

        $display("B2_PACKET_EGRESS_PASS");
        $finish;
    end
endmodule
