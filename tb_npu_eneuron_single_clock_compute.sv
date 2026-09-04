// 真实计算 tracer：手算模型验证 uint4×INT8、hidden 饱和、INT32 logit 与 mask 门控。
`timescale 1ns/1ps
module tb_npu_eneuron_single_clock_compute;
    localparam logic [3:0] OP_MODEL_BEGIN  = 4'h1;
    localparam logic [3:0] OP_MODEL_DATA   = 4'h2;
    localparam logic [3:0] OP_MODEL_COMMIT = 4'h3;
    localparam logic [3:0] OP_MASK_BEGIN   = 4'h4;
    localparam logic [3:0] OP_MASK_DATA    = 4'h5;
    localparam logic [3:0] OP_MASK_COMMIT  = 4'h6;

    logic clk = 1'b0;
    always #5 clk = ~clk;
    logic rst = 1'b1;
    logic [127:0] cmd_payload = '0;
    logic cmd_valid = 1'b0;
    wire cmd_ready;
    wire [127:0] rsp_payload;
    wire rsp_valid;
    logic rsp_ready = 1'b1;
    logic [31:0] sample_data = '0;
    logic [31:0] sample_id = '0;
    logic sample_valid = 1'b0;
    wire sample_ready;
    wire [31:0] result_data;
    wire [31:0] result_sample_id;
    wire [31:0] result_mask_epoch;
    wire result_valid;
    logic result_ready = 1'b1;
    wire runtime_idle, model_valid, mask_valid, infer_frozen;
    wire [31:0] state_clear_count;

    npu_eneuron_single_clock_skeleton dut (
        .clk(clk), .rst(rst), .cmd_payload(cmd_payload), .cmd_valid(cmd_valid), .cmd_ready(cmd_ready),
        .rsp_payload(rsp_payload), .rsp_valid(rsp_valid), .rsp_ready(rsp_ready),
        .sample_data(sample_data), .sample_id(sample_id), .sample_valid(sample_valid), .sample_ready(sample_ready),
        .result_data(result_data), .result_sample_id(result_sample_id), .result_mask_epoch(result_mask_epoch),
        .result_valid(result_valid), .result_ready(result_ready), .runtime_idle(runtime_idle),
        .model_valid(model_valid), .mask_valid(mask_valid), .infer_frozen(infer_frozen),
        .state_clear_count(state_clear_count)
    );

    function automatic logic [31:0] model_word(input integer index);
        begin
            case (index)
                0:   model_word = 32'h0a0a_0a0a; // hidden0: 4×(+10)
                16:  model_word = 32'hffff_ffff; // hidden1: 4×(-1)
                511: model_word = 32'h0101_0101; // hidden31 最后一组：4×(+1)
                513: model_word = 32'd100;       // hidden1 bias
                544: model_word = 32'h0000_fd02; // output0: hidden0×2 + hidden1×(-3)
                623: model_word = 32'h0100_0000; // output9 最后一组：hidden31×(+1)
                624: model_word = 32'd3;         // output0 bias
                625: model_word = 32'hffff_fffb; // output1 bias = -5
                633: model_word = 32'hffff_ffff; // output9 bias = -1
                default: model_word = 32'd0;
            endcase
        end
    endfunction

    task automatic send_cmd(input logic [3:0] opcode, input logic [31:0] epoch, input logic [31:0] word);
        begin
            @(negedge clk);
            cmd_payload = '0;
            cmd_payload[127:124] = opcode;
            cmd_payload[119:88] = epoch;
            cmd_payload[31:0] = word;
            cmd_valid = 1'b1;
            while (!cmd_ready) @(negedge clk);
            @(negedge clk);
            cmd_valid = 1'b0;
            cmd_payload = '0;
        end
    endtask

    task automatic send_sample(input logic [31:0] id);
        integer beat;
        begin
            for (beat = 0; beat < 8; beat = beat + 1) begin
                @(negedge clk);
                sample_id = id;
                if (beat == 0) sample_data = 32'h0000_ffff;
                else if (beat == 7) sample_data = 32'hffff_0000;
                else sample_data = 32'd0;
                sample_valid = 1'b1;
                while (!sample_ready) @(negedge clk);
                @(negedge clk);
                sample_valid = 1'b0;
            end
        end
    endtask

    task automatic check_result(
        input logic [31:0] id,
        input logic [31:0] epoch,
        input logic signed [31:0] expected0,
        input logic signed [31:0] expected9
    );
        integer beat;
        begin
            beat = 0;
            while (beat < 10) begin
                @(posedge clk);
                if (result_valid && result_ready) begin
                    if (result_sample_id !== id || result_mask_epoch !== epoch)
                        $fatal(1, "result metadata mismatch beat=%0d", beat);
                    if (beat == 0 && $signed(result_data) !== expected0)
                        $fatal(1, "logit0 mismatch got=%0d expected=%0d", $signed(result_data), expected0);
                    if (beat == 1 && $signed(result_data) !== -32'sd5)
                        $fatal(1, "logit1 mismatch got=%0d", $signed(result_data));
                    if (beat >= 2 && beat <= 8 && result_data !== 32'd0)
                        $fatal(1, "unexpected nonzero logit beat=%0d value=%0d", beat, $signed(result_data));
                    if (beat == 9 && $signed(result_data) !== expected9)
                        $fatal(1, "logit9 mismatch got=%0d expected=%0d", $signed(result_data), expected9);
                    beat = beat + 1;
                end
            end
        end
    endtask

    integer i;
    initial begin
        repeat (3) @(negedge clk);
        rst = 1'b0;
        send_cmd(OP_MODEL_BEGIN, 32'd0, 32'd0);
        for (i = 0; i < 634; i = i + 1) send_cmd(OP_MODEL_DATA, 32'd0, model_word(i));
        send_cmd(OP_MODEL_COMMIT, 32'd0, 32'd0);

        // hidden0=600→127，hidden1=-60+100=40，logit0=137；
        // hidden31 的最后一组为 60，output9 最后一组得到 60-1=59。
        send_sample(32'h101);
        if (sample_ready || cmd_ready || runtime_idle)
            $fatal(1, "ready/idle asserted while compute is active");
        // 当前样本计算期间并发发布下一 mask；它只能影响下一样本。
        send_cmd(OP_MASK_BEGIN, 32'd1, 32'd0);
        for (i = 0; i < 19; i = i + 1) begin
            if (i == 0) send_cmd(OP_MASK_DATA, 32'd0, 32'hffff_fffe);
            else if (i == 18) send_cmd(OP_MASK_DATA, 32'd0, 32'h0000_7fff);
            else send_cmd(OP_MASK_DATA, 32'd0, 32'hffff_ffff);
        end
        send_cmd(OP_MASK_COMMIT, 32'd1, 32'd0);
        check_result(32'h101, 32'd0, 32'sd137, 32'sd59);

        // 下一样本首 beat 激活新版本：logit0=-117，output9 只剩 bias=-1。
        send_sample(32'h102);
        check_result(32'h102, 32'd1, -32'sd117, -32'sd1);

        $display("PASS npu single-clock real compute tracer");
        $finish;
    end

    initial begin
        repeat (9000) @(posedge clk);
        $fatal(1, "watchdog: compute tracer did not finish");
    end
endmodule
