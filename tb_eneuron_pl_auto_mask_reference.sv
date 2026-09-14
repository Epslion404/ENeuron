`timescale 1ns/1ps
module tb_eneuron_pl_auto_mask_reference;
    logic clk = 1'b0;
    logic rst = 1'b1;
    logic start = 1'b0;
    logic enable = 1'b1;
    logic [3:0] input_pixels [0:63];
    logic [31:0] model_words [0:633];
    logic busy;
    logic valid;
    wire [31:0] mask_words [0:18];
    integer i;

    always #5 clk = ~clk;

    eneuron_pl_auto_mask_reference dut (
        .clk(clk), .rst(rst), .start(start), .enable(enable),
        .input_pixels(input_pixels), .model_words(model_words),
        .busy(busy), .valid(valid), .mask_words(mask_words)
    );

    initial begin
        for (i = 0; i < 64; i = i + 1)
            input_pixels[i] = 4'd0;
        for (i = 0; i < 634; i = i + 1)
            model_words[i] = 32'd0;
        repeat (2) @(posedge clk);
        rst <= 1'b0;
        @(posedge clk);
        start <= 1'b1;
        @(posedge clk);
        start <= 1'b0;
        @(posedge clk);
        if (!busy) $fatal(1, "auto-mask engine did not enter busy");
        @(posedge clk);
        if (!valid) $fatal(1, "auto-mask engine did not publish result");
        // 全零 evidence 的稳定 top-2 是每组 bit0/bit1（0b0011），最后一个 word 仅低 16 bit 有效。
        for (i = 0; i < 18; i = i + 1)
            if (mask_words[i] !== 32'h33333333)
                $fatal(1, "mask word %0d mismatch: %08x", i, mask_words[i]);
        if (mask_words[18] !== 32'h00003333)
            $fatal(1, "mask word 18 mismatch: %08x", mask_words[18]);
        $display("B3_PL_AUTO_MASK_REFERENCE_PASS");
        $finish;
    end
endmodule
