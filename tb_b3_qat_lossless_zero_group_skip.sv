// QAT-v3 无损零组跳过：通过公开命令/样本/结果端口验证完整 FSM。
`timescale 1ns/1ps
module tb_b3_qat_lossless_zero_group_skip #(
    parameter integer SAMPLE_COUNT = 397
);
    localparam logic [3:0] OP_MODEL_BEGIN  = 4'h1;
    localparam logic [3:0] OP_MODEL_DATA   = 4'h2;
    localparam logic [3:0] OP_MODEL_COMMIT = 4'h3;

    logic clk = 1'b0;
    always #2.5 clk = ~clk;
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
    wire runtime_idle;
    wire model_valid;
    wire mask_valid;
    wire infer_frozen;
    wire [31:0] state_clear_count;
    wire [31:0] last_compute_cycles;
    wire [31:0] execute_group_count;
    wire [31:0] skip_group_count;
    wire [31:0] active_mask_epoch;
    wire [31:0] pending_mask_epoch;
    wire mask_staging_open;

    logic [31:0] model_words [0:633];
    logic [31:0] sample_words [0:SAMPLE_COUNT * 8 - 1];
    logic [31:0] expected_logits [0:SAMPLE_COUNT * 10 - 1];
    logic [31:0] expected_execute [0:SAMPLE_COUNT - 1];
    logic [31:0] expected_skip [0:SAMPLE_COUNT - 1];
    string model_path;
    string sample_path;
    string logits_path;
    string execute_path;
    string skip_path;

    npu_eneuron_single_clock_skeleton dut (
        .clk(clk), .rst(rst),
        .cmd_payload(cmd_payload), .cmd_valid(cmd_valid), .cmd_ready(cmd_ready),
        .rsp_payload(rsp_payload), .rsp_valid(rsp_valid), .rsp_ready(rsp_ready),
        .sample_data(sample_data), .sample_id(sample_id),
        .sample_valid(sample_valid), .sample_ready(sample_ready),
        .result_data(result_data), .result_sample_id(result_sample_id),
        .result_mask_epoch(result_mask_epoch),
        .result_valid(result_valid), .result_ready(result_ready),
        .runtime_idle(runtime_idle), .model_valid(model_valid), .mask_valid(mask_valid),
        .infer_frozen(infer_frozen), .state_clear_count(state_clear_count),
        .last_compute_cycles(last_compute_cycles),
        .execute_group_count(execute_group_count), .skip_group_count(skip_group_count),
        .active_mask_epoch(active_mask_epoch), .pending_mask_epoch(pending_mask_epoch),
        .mask_staging_open(mask_staging_open)
    );

    task automatic send_cmd(input logic [3:0] opcode, input logic [31:0] word);
        begin
            @(negedge clk);
            while (!cmd_ready) @(negedge clk);
            cmd_payload = '0;
            cmd_payload[127:124] = opcode;
            cmd_payload[31:0] = word;
            cmd_valid = 1'b1;
            @(negedge clk);
            cmd_valid = 1'b0;
            cmd_payload = '0;
            if (rsp_valid) $fatal(1, "unexpected command error opcode=%0h", opcode);
        end
    endtask

    task automatic send_sample(input integer sample_index);
        integer beat;
        begin
            sample_id = 32'h5141_5400 + sample_index;
            for (beat = 0; beat < 8; beat = beat + 1) begin
                @(negedge clk);
                while (!sample_ready) @(negedge clk);
                sample_data = sample_words[sample_index * 8 + beat];
                sample_valid = 1'b1;
                @(negedge clk);
                sample_valid = 1'b0;
                sample_data = '0;
            end
        end
    endtask

    integer i;
    integer sample_index;
    integer result_index;
    integer cumulative_execute;
    integer cumulative_skip;

    initial begin
        if (!$value$plusargs("MODEL=%s", model_path)) $fatal(1, "MODEL path missing");
        if (!$value$plusargs("SAMPLES=%s", sample_path)) $fatal(1, "SAMPLES path missing");
        if (!$value$plusargs("LOGITS=%s", logits_path)) $fatal(1, "LOGITS path missing");
        if (!$value$plusargs("EXECUTE=%s", execute_path)) $fatal(1, "EXECUTE path missing");
        if (!$value$plusargs("SKIP=%s", skip_path)) $fatal(1, "SKIP path missing");
        $readmemh(model_path, model_words);
        $readmemh(sample_path, sample_words);
        $readmemh(logits_path, expected_logits);
        $readmemh(execute_path, expected_execute);
        $readmemh(skip_path, expected_skip);

        repeat (3) @(negedge clk);
        rst = 1'b0;
        send_cmd(OP_MODEL_BEGIN, 32'd0);
        for (i = 0; i < 634; i = i + 1) send_cmd(OP_MODEL_DATA, model_words[i]);
        send_cmd(OP_MODEL_COMMIT, 32'd0);
        if (!model_valid) $fatal(1, "QAT model did not commit");

        cumulative_execute = 0;
        cumulative_skip = 0;
        for (sample_index = 0; sample_index < SAMPLE_COUNT; sample_index = sample_index + 1) begin
            send_sample(sample_index);
            result_index = 0;
            while (result_index < 10) begin
                @(posedge clk);
                if (result_valid && result_ready) begin
                    if (result_sample_id !== 32'h5141_5400 + sample_index)
                        $fatal(1, "sample id mismatch sample=%0d", sample_index);
                    if (result_mask_epoch !== 32'd0)
                        $fatal(1, "unexpected mask epoch sample=%0d", sample_index);
                    if (result_data !== expected_logits[sample_index * 10 + result_index])
                        $fatal(1, "logit mismatch sample=%0d logit=%0d got=%08x expected=%08x",
                               sample_index, result_index, result_data,
                               expected_logits[sample_index * 10 + result_index]);
                    result_index = result_index + 1;
                end
            end
            cumulative_execute = cumulative_execute + expected_execute[sample_index];
            cumulative_skip = cumulative_skip + expected_skip[sample_index];
            if (execute_group_count !== cumulative_execute)
                $fatal(1, "execute count mismatch sample=%0d got=%0d expected=%0d",
                       sample_index, execute_group_count, cumulative_execute);
            if (skip_group_count !== cumulative_skip)
                $fatal(1, "skip count mismatch sample=%0d got=%0d expected=%0d",
                       sample_index, skip_group_count, cumulative_skip);
            if (last_compute_cycles !== 32'd2494 - 3 * expected_skip[sample_index])
                $fatal(1, "cycle mismatch sample=%0d got=%0d expected=%0d",
                       sample_index, last_compute_cycles,
                       32'd2494 - 3 * expected_skip[sample_index]);
        end
        $display("B3_QAT_LOSSLESS_ZERO_GROUP_RTL_PASS samples=%0d", SAMPLE_COUNT);
        $finish;
    end

    initial begin
        repeat (2000000) @(posedge clk);
        $fatal(1, "watchdog: QAT lossless zero-group RTL test timed out");
    end
endmodule
