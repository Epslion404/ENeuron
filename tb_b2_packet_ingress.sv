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

    task automatic send_word_keep(input logic [31:0] data, input logic [3:0] keep, input logic last);
        begin
            @(negedge clk);
            while (!s_ready) @(negedge clk);
            s_data = data;
            s_keep = keep;
            s_last = last;
            s_valid = 1'b1;
            @(posedge clk);
            while (!s_ready) @(posedge clk);
            @(negedge clk);
            s_valid = 1'b0;
            s_last = 1'b0;
            s_keep = 4'hF;
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

        // 首拍 TKEEP 非法必须拒绝，不能把部分字节当作 magic/header。
        send_word_keep(32'h3242_4e45, 4'h7, 1'b1);
        expect_error(4'h7);
        if (cmd_valid || sample_valid || busy) $fatal(1, "bad keep frame leaked state");

        // 错误版本必须等到帧边界后整体拒绝，不得提前释放 payload。
        send_word(32'h3242_4e45, 1'b0);
        send_word(32'h0800_0202, 1'b0);
        send_word(32'h0000_0020, 1'b0);
        for (i = 0; i < 13; i = i + 1) send_word(32'h0000_0000, 1'b0);
        send_word(32'h0000_0000, 1'b1);
        expect_error(4'h2);
        if (cmd_valid || sample_valid || busy) $fatal(1, "bad version frame leaked state");

        // 未知消息类型必须明确拒绝，不能解释为 command 或 sample。
        send_word(32'h3242_4e45, 1'b0);
        send_word(32'h0800_7f01, 1'b0);
        send_word(32'h0000_0010, 1'b0);
        for (i = 0; i < 5; i = i + 1) send_word(32'h0000_0000, 1'b0);
        send_word(32'h0000_0000, 1'b1);
        expect_error(4'h3);
        if (cmd_valid || sample_valid || busy) $fatal(1, "unknown type frame leaked state");

        // 保留 flags 非零必须明确拒绝，不能继续解释帧类型。
        send_word(32'h3242_4e45, 1'b0);
        send_word(32'h0801_0201, 1'b0);
        send_word(32'h0000_0010, 1'b0);
        for (i = 0; i < 5; i = i + 1) send_word(32'h0000_0000, 1'b0);
        send_word(32'h0000_0000, 1'b1);
        expect_error(4'h4);
        if (cmd_valid || sample_valid || busy) $fatal(1, "bad flags frame leaked state");

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

        // Batch command：21 个 128-bit command word 共用一次 DMA frame，
        // ingress 必须逐 word 顺序发布，并保持 PL staging 所需的 epoch 字段。
        send_word(32'h3242_4e45, 1'b0);
        send_word(32'h0800_0101, 1'b0);
        send_word(32'h0000_0150, 1'b0);
        send_word(32'h0000_0009, 1'b0);
        send_word(32'h0000_0000, 1'b0);
        send_word(32'h0000_0003, 1'b0);
        send_word(32'h0000_0001, 1'b0);
        send_word(32'h0000_0000, 1'b0);
        for (i = 0; i < 21; i = i + 1) begin
            send_word((i == 0 || i == 20) ? 32'h0000_0000 : (32'h0000_0100 + i), 1'b0);
            send_word(32'h0000_0000, 1'b0);
            send_word((i == 0 || i == 20) ? 32'h0100_0000 : 32'h0000_0000, 1'b0);
            send_word((i == 0) ? 32'h4000_0000 : (i == 20) ? 32'h6000_0000 : 32'h5000_0000,
                      1'b0);
        end
        send_word(32'h5f58_430d, 1'b1);
        cmd_ready = 1'b1;
        for (i = 0; i < 21; i = i + 1) begin
            while (!cmd_valid) @(posedge clk);
            #1;
            if (cmd_sequence !== 32'd9 || cmd_model_id !== 32'd3 ||
                cmd_data[127:124] !== ((i == 0) ? 4'h4 : (i == 20) ? 4'h6 : 4'h5) ||
                cmd_data[31:0] !== ((i == 0 || i == 20) ? 32'd0 : (32'h100 + i)))
                $fatal(1, "batch command mapping mismatch index=%0d data=%h", i, cmd_data);
            @(posedge clk);
        end
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
