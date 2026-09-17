// B3 路线一：PL auto-mask 参考引擎与 PS 黄金 mask 的逐输入逐 bit 对照。
//
// 输入文件由 test_b3_pl_auto_mask_contract.py 从共享 manifest 生成：
//   +MODEL=<file>     634 个 32-bit 模型 word，每行 8 位十六进制
//   +PIXELS=<file>    SAMPLE_COUNT 样本 × 64 个 4-bit 像素，每行一个十六进制 nibble
//   +EXPECTED=<file>  SAMPLE_COUNT 样本 × 19 个 32-bit mask word，每行 8 位十六进制
`timescale 1ns/1ps
module tb_b3_pl_auto_mask_golden;
    parameter integer SAMPLE_COUNT = 64;
    localparam integer PIXEL_COUNT = 64;
    localparam integer MODEL_WORD_COUNT = 634;
    localparam integer MASK_WORD_COUNT = 19;

    logic clk = 1'b0;
    logic rst = 1'b1;
    logic start = 1'b0;
    logic enable = 1'b1;
    logic [3:0] input_pixels [0:PIXEL_COUNT-1];
    logic [31:0] model_words [0:MODEL_WORD_COUNT-1];
    wire busy;
    wire valid;
    wire [31:0] mask_words [0:MASK_WORD_COUNT-1];

    logic [3:0] pixel_mem [0:SAMPLE_COUNT*PIXEL_COUNT-1];
    logic [31:0] expected_mem [0:SAMPLE_COUNT*MASK_WORD_COUNT-1];

    string model_file;
    string pixel_file;
    string expected_file;

    integer sample_index;
    integer word_index;
    integer timeout;
    integer errors;
    logic [31:0] engine_cycles;

`ifdef PL_AUTO_MASK_ENGINE
    eneuron_pl_auto_mask_engine dut (
        .clk(clk),
        .rst(rst),
        .start(start),
        .enable(enable),
        .input_pixels(input_pixels),
        .model_words(model_words),
        .busy(busy),
        .valid(valid),
        .mask_words(mask_words),
        .cycle_count(engine_cycles)
    );
`else
    eneuron_pl_auto_mask_reference dut (
        .clk(clk),
        .rst(rst),
        .start(start),
        .enable(enable),
        .input_pixels(input_pixels),
        .model_words(model_words),
        .busy(busy),
        .valid(valid),
        .mask_words(mask_words)
    );
`endif

    always #5 clk = ~clk;

    initial begin
        if (!$value$plusargs("MODEL=%s", model_file))
            $fatal(1, "missing +MODEL");
        if (!$value$plusargs("PIXELS=%s", pixel_file))
            $fatal(1, "missing +PIXELS");
        if (!$value$plusargs("EXPECTED=%s", expected_file))
            $fatal(1, "missing +EXPECTED");
        $readmemh(model_file, model_words);
        $readmemh(pixel_file, pixel_mem);
        $readmemh(expected_file, expected_mem);
        for (word_index = 0; word_index < PIXEL_COUNT; word_index = word_index + 1)
            input_pixels[word_index] = 4'd0;

        repeat (2) @(posedge clk);
        rst <= 1'b0;
        @(posedge clk);

        errors = 0;
        for (sample_index = 0; sample_index < SAMPLE_COUNT; sample_index = sample_index + 1) begin
            for (word_index = 0; word_index < PIXEL_COUNT; word_index = word_index + 1)
                input_pixels[word_index] = pixel_mem[sample_index * PIXEL_COUNT + word_index];

            start <= 1'b1;
            @(posedge clk);
            start <= 1'b0;
            @(posedge clk);
            timeout = 0;
            while (valid !== 1'b1 && timeout < 4096) begin
                @(posedge clk);
                timeout = timeout + 1;
            end
            if (valid !== 1'b1) begin
                $display("B3_PL_AUTO_MASK_GOLDEN_FAIL sample=%0d reason=no_valid", sample_index);
                $fatal(1, "auto-mask engine did not publish sample %0d", sample_index);
            end

            for (word_index = 0; word_index < MASK_WORD_COUNT; word_index = word_index + 1) begin
                if (mask_words[word_index] !== expected_mem[sample_index * MASK_WORD_COUNT + word_index]) begin
                    errors = errors + 1;
                    if (errors <= 8)
                        $display(
                            "B3_PL_AUTO_MASK_GOLDEN_FAIL sample=%0d word=%0d actual=%08x expected=%08x",
                            sample_index, word_index,
                            mask_words[word_index],
                            expected_mem[sample_index * MASK_WORD_COUNT + word_index]);
                end
            end
        end

        if (errors != 0) begin
            $display("B3_PL_AUTO_MASK_GOLDEN_FAIL mismatches=%0d", errors);
            $fatal(1, "golden comparison failed");
        end
        $display("B3_PL_AUTO_MASK_GOLDEN_PASS samples=%0d", SAMPLE_COUNT);
`ifdef PL_AUTO_MASK_ENGINE
        $display("B3_PL_AUTO_MASK_ENGINE_CYCLES=%0d", engine_cycles);
`endif
        $finish;
    end
endmodule
