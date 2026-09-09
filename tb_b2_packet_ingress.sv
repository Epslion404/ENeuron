module tb_b2_packet_ingress;
    logic clk = 1'b0;
    logic rst = 1'b1;
    logic s_valid = 1'b0;
    logic [31:0] s_data = '0;
    logic [3:0] s_keep = 4'hF;
    logic s_last = 1'b0;
    wire s_ready;

    wire cmd_valid;
    logic cmd_ready = 1'b0;
    wire [127:0] cmd_data;
    wire [31:0] cmd_sequence, cmd_model_id, cmd_mask_epoch;
    wire sample_valid;
    logic sample_ready = 1'b0;
    wire [31:0] sample_data, sample_id, sample_sequence, sample_model_id, sample_mask_epoch;
    wire error_valid;
    wire [3:0] error_code;
    wire busy;

    always #5 clk = ~clk;

    b2_packet_ingress dut (
        .clk(clk), .rst(rst),
        .s_valid(s_valid), .s_ready(s_ready), .s_data(s_data), .s_keep(s_keep), .s_last(s_last),
        .cmd_valid(cmd_valid), .cmd_ready(cmd_ready), .cmd_data(cmd_data),
        .cmd_sequence(cmd_sequence), .cmd_model_id(cmd_model_id), .cmd_mask_epoch(cmd_mask_epoch),
        .sample_valid(sample_valid), .sample_ready(sample_ready), .sample_data(sample_data),
        .sample_id(sample_id), .sample_sequence(sample_sequence), .sample_model_id(sample_model_id),
        .sample_mask_epoch(sample_mask_epoch), .error_valid(error_valid), .error_code(error_code), .busy(busy)
    );

    task automatic send_word(input logic [31:0] data, input logic last);
        begin
            @(negedge clk);
            while (!s_ready) @(negedge clk);
            s_data = data;
            s_last = last;
            s_valid = 1'b1;
            @(posedge clk);
            while (!s_ready) @(posedge clk);
            @(negedge clk);
            s_valid = 1'b0;
            s_last = 1'b0;
            s_data = '0;
        end
    endtask

    task automatic expect_error(input logic [3:0] expected);
        begin
            while (!error_valid) @(posedge clk);
            if (error_code !== expected)
                $fatal(1, "error code=%h expected=%h", error_code, expected);
            @(posedge clk);
        end
    endtask

    integer i;
    initial begin
        repeat (4) @(posedge clk);
        rst = 1'b0;
        repeat (3) @(posedge clk);

        // 单拍坏 magic 帧必须立即拒绝，且不能进入任何下游输出状态。
        send_word(32'h0000_0000, 1'b1);
        expect_error(4'h1);
        if (cmd_valid || sample_valid || busy) $fatal(1, "bad magic frame leaked state");

        // SAMPLE: sequence=7, sample_id=42, model_id=3, epoch=11.
        send_word(32'h3242_4e45, 1'b0);
        send_word(32'h0800_0201, 1'b0);
        send_word(32'h0000_0020, 1'b0);
        send_word(32'h0000_0007, 1'b0);
        send_word(32'h0000_002a, 1'b0);
        send_word(32'h0000_0003, 1'b0);
        send_word(32'h0000_000b, 1'b0);
        send_word(32'h0000_0000, 1'b0);
        for (i = 0; i < 8; i = i + 1) send_word(i, 1'b0);
        send_word(32'h4598_c638, 1'b1);

        sample_ready = 1'b1;
        for (i = 0; i < 8; i = i + 1) begin
            while (!sample_valid) @(posedge clk);
            #1;
            if (sample_data !== i || sample_id !== 32'd42 || sample_sequence !== 32'd7 ||
                sample_model_id !== 32'd3 || sample_mask_epoch !== 32'd11)
                $fatal(1, "sample beat %0d metadata/data mismatch", i);
            @(posedge clk);
        end
        sample_ready = 1'b0;

        // COMMAND: one 128-bit word, payload bytes are little-endian.
        send_word(32'h3242_4e45, 1'b0);
        send_word(32'h0800_0101, 1'b0);
        send_word(32'h0000_0010, 1'b0);
        send_word(32'h0000_0008, 1'b0);
        send_word(32'h0000_0000, 1'b0);
        send_word(32'h0000_0003, 1'b0);
        send_word(32'h0000_000b, 1'b0);
        send_word(32'h0000_0000, 1'b0);
        send_word(32'h0000_0001, 1'b0);
        send_word(32'h0000_0000, 1'b0);
        send_word(32'h0000_0000, 1'b0);
        send_word(32'h0000_0000, 1'b0);
        send_word(32'h6378_ccca, 1'b1);
        cmd_ready = 1'b1;
        while (!cmd_valid) @(posedge clk);
        #1;
        if (cmd_data !== 128'h0000_0000_0000_0000_0000_0000_0000_0001 ||
            cmd_sequence !== 32'd8 || cmd_model_id !== 32'd3 || cmd_mask_epoch !== 32'd11)
            $fatal(1, "command mapping mismatch");
        @(posedge clk);
        cmd_ready = 1'b0;

        // Bad CRC must not publish a sample.
        send_word(32'h3242_4e45, 1'b0);
        send_word(32'h0800_0201, 1'b0);
        send_word(32'h0000_0020, 1'b0);
        send_word(32'h0000_0001, 1'b0);
        send_word(32'h0000_0001, 1'b0);
        send_word(32'h0000_0001, 1'b0);
        send_word(32'h0000_0001, 1'b0);
        send_word(32'h0000_0000, 1'b0);
        for (i = 0; i < 8; i = i + 1) send_word(i, 1'b0);
        send_word(32'h4598_c639, 1'b1);
        expect_error(4'hA);
        if (sample_valid) $fatal(1, "bad CRC published sample");

        // Missing TLAST on the CRC word must be rejected at the frame boundary.
        send_word(32'h3242_4e45, 1'b0);
        send_word(32'h0800_0201, 1'b0);
        send_word(32'h0000_0020, 1'b0);
        send_word(32'h0000_0001, 1'b0);
        send_word(32'h0000_0001, 1'b0);
        send_word(32'h0000_0001, 1'b0);
        send_word(32'h0000_0001, 1'b0);
        send_word(32'h0000_0000, 1'b0);
        for (i = 0; i < 8; i = i + 1) send_word(i, 1'b0);
        send_word(32'hea4d_cce2, 1'b0);
        send_word(32'h0000_0000, 1'b1);
        expect_error(4'h9);

        $display("B2_PACKET_INGRESS_PASS");
        $finish;
    end
endmodule
