// 无损零组跳过 RTL 切片：验证输出逐位保持和组计数语义。
`timescale 1ns/1ps
module tb_b3_lossless_zero_group_skip;
    localparam logic [3:0] OP_MODEL_BEGIN  = 4'h1;
    localparam logic [3:0] OP_MODEL_DATA   = 4'h2;
    localparam logic [3:0] OP_MODEL_COMMIT = 4'h3;

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
    logic [31:0] sample_id = 32'h0000_00a5;
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
            while (rsp_valid) @(negedge clk);
        end
    endtask

    task automatic send_sample_beat(input logic [31:0] word);
        begin
            @(negedge clk);
            while (!sample_ready) @(negedge clk);
            sample_data = word;
            sample_valid = 1'b1;
            @(negedge clk);
            sample_valid = 1'b0;
            sample_data = '0;
        end
    endtask

    integer i;
    integer result_beats;
    integer nonzero_result;
    logic [31:0] model_word;

    function automatic logic [31:0] model_for_index(input integer index);
        begin
            model_for_index = 32'd0;
            // L0 unit 0, group 0: weight lane 0 = 1.
            if (index == 0) model_for_index = 32'h0000_0001;
            // L1 output 0, group 0: hidden lane 0 weight = 1.
            if (index == 544) model_for_index = 32'h0000_0001;
            // L0 bias unit 0 = 1; all other biases remain zero.
            if (index == 512) model_for_index = 32'h0000_0001;
        end
    endfunction

    initial begin
        repeat (10000) @(posedge clk);
        $fatal(1, "watchdog: lossless skip test did not finish");
    end

    initial begin
        repeat (3) @(negedge clk);
        rst = 1'b0;
        send_cmd(OP_MODEL_BEGIN, 32'd0);
        for (i = 0; i < 634; i = i + 1)
            send_cmd(OP_MODEL_DATA, model_for_index(i));
        send_cmd(OP_MODEL_COMMIT, 32'd0);
        if (!model_valid) $fatal(1, "model did not commit");

        // pixel0=1 使 L0 group0 执行；pixel4=2 落在全零权重组，必须被跳过。
        send_sample_beat(32'h0000_2001);
        for (i = 1; i < 8; i = i + 1) send_sample_beat(32'd0);

        result_beats = 0;
        nonzero_result = 0;
        while (result_beats < 10) begin
            @(posedge clk);
            if (result_valid && result_ready) begin
                if (result_sample_id !== 32'h0000_00a5)
                    $fatal(1, "sample id mismatch");
                if (result_beats == 0 && result_data !== 32'd2)
                    $fatal(1, "logit0 mismatch: got %0d", result_data);
                if (result_data !== 32'd0) nonzero_result = nonzero_result + 1;
                result_beats = result_beats + 1;
            end
        end

        if (nonzero_result != 1) $fatal(1, "unexpected nonzero logits: %0d", nonzero_result);
`ifdef LOSSLESS_ZERO_GROUP_SKIP
        if (execute_group_count !== 32'd2)
            $fatal(1, "lossless skip execute count mismatch: %0d", execute_group_count);
        if (skip_group_count !== 32'd590)
            $fatal(1, "lossless skip count mismatch: %0d", skip_group_count);
`else
        if (execute_group_count !== 32'd592)
            $fatal(1, "dense execute count mismatch: %0d", execute_group_count);
        if (skip_group_count !== 32'd0)
            $fatal(1, "dense skip count mismatch: %0d", skip_group_count);
`endif
        $display("PASS lossless zero-group skip output/counters");
        $finish;
    end
endmodule
