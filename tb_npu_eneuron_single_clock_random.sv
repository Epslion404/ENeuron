// 单时钟 NPU 随机 bit-exact 协同仿真。
// 数据由 Python 生成并通过 $readmemh 提供；testbench 只验证公开端口合同。
`timescale 1ns/1ps
module tb_npu_eneuron_single_clock_random;
    localparam logic [3:0] OP_MODEL_BEGIN  = 4'h1;
    localparam logic [3:0] OP_MODEL_DATA   = 4'h2;
    localparam logic [3:0] OP_MODEL_COMMIT = 4'h3;
    localparam logic [3:0] OP_MASK_BEGIN   = 4'h4;
    localparam logic [3:0] OP_MASK_DATA    = 4'h5;
    localparam logic [3:0] OP_MASK_COMMIT  = 4'h6;
    localparam integer SAMPLE_COUNT = 100;

    logic clk = 1'b0;
    always #5 clk = ~clk;
    logic rst = 1'b1;
    logic [127:0] cmd_payload = '0;
    logic cmd_valid = 1'b0;
    wire cmd_ready;
    wire [127:0] rsp_payload;
    wire rsp_valid;
    logic rsp_ready;
    logic [31:0] sample_data = '0;
    logic [31:0] sample_id = '0;
    logic sample_valid = 1'b0;
    wire sample_ready;
    wire [31:0] result_data;
    wire [31:0] result_sample_id;
    wire [31:0] result_mask_epoch;
    wire result_valid;
    logic result_ready;
    wire runtime_idle, model_valid, mask_valid, infer_frozen;
    wire [31:0] state_clear_count;

    logic [31:0] model_words [0:633];
    logic [31:0] sample_words [0:799];
    logic [31:0] mask_words [0:1899];
    logic [31:0] expected_words [0:999];
    string model_path;
    string samples_path;
    string masks_path;
    string expected_path;
    integer seed_value;
    integer i;
    integer sample_index;
    integer hold_cycles;
    logic [31:0] held_result_data;
    logic [31:0] held_result_id;
    logic [31:0] held_result_epoch;

    npu_eneuron_single_clock_skeleton dut (
        .clk(clk), .rst(rst), .cmd_payload(cmd_payload), .cmd_valid(cmd_valid), .cmd_ready(cmd_ready),
        .rsp_payload(rsp_payload), .rsp_valid(rsp_valid), .rsp_ready(rsp_ready),
        .sample_data(sample_data), .sample_id(sample_id), .sample_valid(sample_valid), .sample_ready(sample_ready),
        .result_data(result_data), .result_sample_id(result_sample_id), .result_mask_epoch(result_mask_epoch),
        .result_valid(result_valid), .result_ready(result_ready), .runtime_idle(runtime_idle),
        .model_valid(model_valid), .mask_valid(mask_valid), .infer_frozen(infer_frozen),
        .state_clear_count(state_clear_count)
    );

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

    task automatic send_sample(input integer index);
        integer beat;
        begin
            for (beat = 0; beat < 8; beat = beat + 1) begin
                @(negedge clk);
                sample_id = 32'ha500_0000 | index;
                sample_data = sample_words[index * 8 + beat];
                sample_valid = 1'b1;
                while (!sample_ready) @(negedge clk);
                @(negedge clk);
                sample_valid = 1'b0;
            end
        end
    endtask

    task automatic send_mask(input integer index);
        integer word_index;
        begin
            send_cmd(OP_MASK_BEGIN, index, 32'd0);
            for (word_index = 0; word_index < 19; word_index = word_index + 1)
                send_cmd(OP_MASK_DATA, 32'd0, mask_words[index * 19 + word_index]);
            send_cmd(OP_MASK_COMMIT, index, 32'd0);
        end
    endtask

    task automatic check_result(input integer index);
        integer beat;
        begin
            wait (result_valid);
            held_result_data = result_data;
            held_result_id = result_sample_id;
            held_result_epoch = result_mask_epoch;
            hold_cycles = (index % 5) + 1;
            repeat (hold_cycles) begin
                @(negedge clk);
                if (!result_valid || result_data !== held_result_data ||
                    result_sample_id !== held_result_id || result_mask_epoch !== held_result_epoch)
                    $fatal(1, "result changed under random backpressure sample=%0d", index);
            end
            if (held_result_data !== expected_words[index * 10])
                $fatal(1, "logit mismatch sample=%0d beat=0 got=%08x expected=%08x",
                       index, held_result_data, expected_words[index * 10]);

            // 结果在下降沿稳定观察；对应上升沿只完成这一 beat 的握手。
            @(negedge clk);
            result_ready = 1'b1;
            for (beat = 0; beat < 10; beat = beat + 1) begin
                if (!result_valid)
                    $fatal(1, "result disappeared before beat=%0d sample=%0d", beat, index);
                if (result_sample_id !== (32'ha500_0000 | index))
                    $fatal(1, "sample id mismatch sample=%0d got=%08x", index, result_sample_id);
                if (result_mask_epoch !== index)
                    $fatal(1, "mask epoch mismatch sample=%0d got=%0d", index, result_mask_epoch);
                if (result_data !== expected_words[index * 10 + beat])
                    $fatal(1, "logit mismatch sample=%0d beat=%0d got=%08x expected=%08x",
                           index, beat, result_data, expected_words[index * 10 + beat]);
                @(posedge clk);
                if (beat < 9)
                    @(negedge clk);
            end
            @(negedge clk);
            if (result_valid)
                $fatal(1, "result did not clear after final handshake sample=%0d", index);
            result_ready = 1'b0;
        end
    endtask

    initial begin
        result_ready = 1'b0;
        rsp_ready = 1'b1;
        cmd_valid = 1'b0;
        sample_valid = 1'b0;
        if (!$value$plusargs("MODEL=%s", model_path)) $fatal(1, "MODEL plusarg missing");
        if (!$value$plusargs("SAMPLES=%s", samples_path)) $fatal(1, "SAMPLES plusarg missing");
        if (!$value$plusargs("MASKS=%s", masks_path)) $fatal(1, "MASKS plusarg missing");
        if (!$value$plusargs("EXPECTED=%s", expected_path)) $fatal(1, "EXPECTED plusarg missing");
        if (!$value$plusargs("SEED=%d", seed_value)) seed_value = -1;
        $readmemh(model_path, model_words);
        $readmemh(samples_path, sample_words);
        $readmemh(masks_path, mask_words);
        $readmemh(expected_path, expected_words);

        repeat (3) @(negedge clk);
        rst = 1'b0;
        send_cmd(OP_MODEL_BEGIN, 32'd0, 32'd0);
        for (i = 0; i < 634; i = i + 1)
            send_cmd(OP_MODEL_DATA, 32'd0, model_words[i]);
        send_cmd(OP_MODEL_COMMIT, 32'd0, 32'd0);
        if (!model_valid) $fatal(1, "model did not commit seed=%0d", seed_value);

        for (sample_index = 0; sample_index < SAMPLE_COUNT; sample_index = sample_index + 1) begin
            send_sample(sample_index);
            check_result(sample_index);
            // 在本样本结果消费完成后准备下一版 mask；不会污染已完成结果。
            if (sample_index + 1 < SAMPLE_COUNT)
                send_mask(sample_index + 1);
        end

        if (!runtime_idle) $fatal(1, "runtime_idle not restored seed=%0d", seed_value);
        $display("PASS random bit-exact seed=%0d samples=%0d", seed_value, SAMPLE_COUNT);
        $finish;
    end

    initial begin
        repeat (3000000) @(posedge clk);
        $fatal(1, "watchdog random seed=%0d", seed_value);
    end
endmodule
