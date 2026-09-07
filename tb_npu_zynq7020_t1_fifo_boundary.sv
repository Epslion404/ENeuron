`timescale 1ns/1ps

    // T1-12 的 FIFO 边界切片：覆盖四种 payload 宽度的空/满、回绕、溢出和背压。
// 双时钟只用于让读写事件错开；完整频比/随机相位矩阵仍属于 T2。
module fifo_boundary_case #(
    parameter integer WIDTH = 128
) (
    output logic done
);
    logic wr_clk = 1'b0;
    logic rd_clk = 1'b0;
    logic rst = 1'b1;
    logic wr_en = 1'b0;
    logic rd_en = 1'b0;
    logic [WIDTH-1:0] din = '0;
    wire [WIDTH-1:0] dout;
    wire full, empty, wr_ack, overflow, underflow, wr_rst_busy, rd_rst_busy;
    wire [4:0] wr_count, rd_count;
    integer head = 0;
    integer tail = 0;
    integer i;
    logic [WIDTH-1:0] expected [0:63];
    logic [WIDTH-1:0] stalled_value;

    always #5 wr_clk = ~wr_clk;
    always #7 rd_clk = ~rd_clk;

    xpm_fifo_async #(
        .FIFO_MEMORY_TYPE("auto"), .ECC_MODE("no_ecc"), .RELATED_CLOCKS(0),
        .SIM_ASSERT_CHK(1), .FIFO_WRITE_DEPTH(16),
        .WRITE_DATA_WIDTH(WIDTH), .WR_DATA_COUNT_WIDTH(5), .PROG_FULL_THRESH(10),
        .FULL_RESET_VALUE(0), .USE_ADV_FEATURES("0000"), .READ_MODE("fwft"),
        .FIFO_READ_LATENCY(0), .READ_DATA_WIDTH(WIDTH), .RD_DATA_COUNT_WIDTH(5),
        .PROG_EMPTY_THRESH(10), .DOUT_RESET_VALUE("0"), .CDC_SYNC_STAGES(2),
        .WAKEUP_TIME(0)
    ) fifo (
        .sleep(1'b0), .rst(rst), .wr_clk(wr_clk), .wr_en(wr_en), .din(din),
        .full(full), .prog_full(), .wr_data_count(wr_count), .overflow(overflow),
        .wr_rst_busy(wr_rst_busy), .almost_full(), .wr_ack(wr_ack),
        .rd_clk(rd_clk), .rd_en(rd_en), .dout(dout), .empty(empty), .prog_empty(),
        .rd_data_count(rd_count), .underflow(underflow), .rd_rst_busy(rd_rst_busy),
        .almost_empty(), .data_valid(), .injectsbiterr(1'b0), .injectdbiterr(1'b0),
        .sbiterr(), .dbiterr()
    );

    task automatic write_word(input integer value);
        logic [WIDTH-1:0] payload;
        begin
            payload = '0;
            payload[31:0] = value;
            @(negedge wr_clk);
            while (wr_rst_busy || full) @(negedge wr_clk);
            din = payload;
            wr_en = 1'b1;
            @(posedge wr_clk);
            #1;
            if (!wr_ack) $fatal(1, "FIFO width=%0d write not acknowledged", WIDTH);
            wr_en = 1'b0;
            expected[tail] = payload;
            tail = tail + 1;
        end
    endtask

    task automatic read_word;
        logic [WIDTH-1:0] observed;
        begin
            @(negedge rd_clk);
            while (rd_rst_busy || empty) @(negedge rd_clk);
            observed = dout;
            rd_en = 1'b1;
            @(posedge rd_clk);
            #1;
            rd_en = 1'b0;
            if (observed !== expected[head])
                $fatal(1, "FIFO width=%0d order mismatch index=%0d got=%h expected=%h",
                       WIDTH, head, observed, expected[head]);
            head = head + 1;
        end
    endtask

    initial begin
        done = 1'b0;
        repeat (8) @(posedge wr_clk);
        rst = 1'b0;
        while (wr_rst_busy || rd_rst_busy) @(posedge wr_clk);

        // 空读必须产生 underflow，且不能制造可见数据。
        @(negedge rd_clk);
        rd_en = 1'b1;
        @(posedge rd_clk);
        #1;
        rd_en = 1'b0;
        if (!underflow) $fatal(1, "FIFO width=%0d empty read did not flag underflow", WIDTH);

        // depth=16 的 RAM 加 1 个 FWFT 预取槽，外部可见容量为 17。
        for (i = 0; i < 17; i = i + 1) write_word(i);
        @(posedge wr_clk);
        if (!full) $fatal(1, "FIFO width=%0d did not become full", WIDTH);
        @(negedge wr_clk);
        din = '1;
        wr_en = 1'b1;
        @(posedge wr_clk);
        #1;
        wr_en = 1'b0;
        if (!overflow) $fatal(1, "FIFO width=%0d full write did not flag overflow", WIDTH);

        // 读出一半，再写入一半，强制读写指针回绕并保持顺序。
        for (i = 0; i < 8; i = i + 1) read_word();
        for (i = 17; i < 25; i = i + 1) write_word(i);

        // 长背压期间 FWFT 输出必须稳定，解除后仍按账本消费。
        @(negedge rd_clk);
        while (rd_rst_busy || empty) @(negedge rd_clk);
        stalled_value = dout;
        repeat (5) begin
            @(posedge rd_clk);
            if (empty || dout !== stalled_value)
                $fatal(1, "FIFO width=%0d payload changed under backpressure", WIDTH);
        end
        read_word();
        for (i = 0; i < 16; i = i + 1) read_word();

        // 再做一轮小事务，覆盖回绕后的空/非空转换。
        for (i = 25; i < 29; i = i + 1) write_word(i);
        repeat (5) @(posedge rd_clk);
        for (i = 0; i < 4; i = i + 1) read_word();
        if (head !== tail) $fatal(1, "FIFO width=%0d scoreboard not empty", WIDTH);
        done = 1'b1;
    end
endmodule

module tb_npu_zynq7020_t1_fifo_boundary;
    wire done_cmd, done_rsp, done_sample, done_result;

    fifo_boundary_case #(.WIDTH(128)) command_case (.done(done_cmd));
    fifo_boundary_case #(.WIDTH(128)) response_case (.done(done_rsp));
    fifo_boundary_case #(.WIDTH(64)) sample_case (.done(done_sample));
    fifo_boundary_case #(.WIDTH(96)) result_case (.done(done_result));

    initial begin
        wait (done_cmd && done_rsp && done_sample && done_result);
        $display("T1_FIFO_BOUNDARY_PASS");
        $finish;
    end
endmodule
