// QAT-v3纯PL NPU功耗激励：200 MHz、同一64样本，dense/gated仅mask不同。
`timescale 1ns/1ps
module tb_b3_npu_saif_power;
    localparam logic [3:0] OP_MODEL_BEGIN  = 4'h1;
    localparam logic [3:0] OP_MODEL_DATA   = 4'h2;
    localparam logic [3:0] OP_MODEL_COMMIT = 4'h3;
    localparam logic [3:0] OP_MASK_BEGIN   = 4'h4;
    localparam logic [3:0] OP_MASK_DATA    = 4'h5;
    localparam logic [3:0] OP_MASK_COMMIT  = 4'h6;
    localparam integer SAMPLE_COUNT = 64;

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

    // XSim Tcl仅在该窗口内采集dut层次的SAIF。
    logic saif_active = 1'b0;
    logic [31:0] model_words [0:633];
    logic [31:0] sample_beats [0:SAMPLE_COUNT*8-1];
    logic [31:0] gated_mask_words [0:18];
    string model_file;
    string samples_file;
    string mask_file;

    npu_eneuron_single_clock_skeleton dut (
        .clk(clk), .rst(rst),
        .cmd_payload(cmd_payload), .cmd_valid(cmd_valid), .cmd_ready(cmd_ready),
        .rsp_payload(rsp_payload), .rsp_valid(rsp_valid), .rsp_ready(rsp_ready),
        .sample_data(sample_data), .sample_id(sample_id), .sample_valid(sample_valid), .sample_ready(sample_ready),
        .result_data(result_data), .result_sample_id(result_sample_id), .result_mask_epoch(result_mask_epoch),
        .result_valid(result_valid), .result_ready(result_ready),
        .runtime_idle(runtime_idle), .model_valid(model_valid), .mask_valid(mask_valid),
        .infer_frozen(infer_frozen), .state_clear_count(state_clear_count),
        .last_compute_cycles(last_compute_cycles), .execute_group_count(execute_group_count),
        .skip_group_count(skip_group_count), .active_mask_epoch(active_mask_epoch),
        .pending_mask_epoch(pending_mask_epoch), .mask_staging_open(mask_staging_open)
    );

    task automatic send_cmd(input logic [3:0] opcode, input logic [31:0] epoch, input logic [31:0] word);
        begin
            @(negedge clk);
            cmd_payload = '0;
            cmd_payload[127:124] = opcode;
            cmd_payload[119:88] = epoch;
            cmd_payload[31:0] = word;
            cmd_valid = 1'b1;
            @(posedge clk);
            while (!cmd_ready) @(posedge clk);
            @(negedge clk);
            cmd_valid = 1'b0;
            cmd_payload = '0;
        end
    endtask

    task automatic publish_power_mask;
        integer word_index;
        logic [31:0] word;
        begin
            send_cmd(OP_MASK_BEGIN, 32'd1, 32'd0);
            for (word_index = 0; word_index < 19; word_index = word_index + 1) begin
`ifdef B3_SAIF_GATED
                word = gated_mask_words[word_index];
`else
                word = (word_index == 18) ? 32'h0000ffff : 32'hffffffff;
`endif
                send_cmd(OP_MASK_DATA, 32'd0, word);
            end
            send_cmd(OP_MASK_COMMIT, 32'd1, 32'd0);
        end
    endtask

    task automatic run_sample(input integer sample_index);
        integer beat;
        integer result_beat;
        begin
            for (beat = 0; beat < 8; beat = beat + 1) begin
                @(negedge clk);
                sample_id = 32'h51415400 + sample_index;
                sample_data = sample_beats[sample_index * 8 + beat];
                sample_valid = 1'b1;
                @(posedge clk);
                while (!sample_ready) @(posedge clk);
                @(negedge clk);
                sample_valid = 1'b0;
            end
            result_beat = 0;
            while (result_beat < 10) begin
                @(posedge clk);
                if (result_valid && result_ready) begin
                    if (result_sample_id !== 32'h51415400 + sample_index || result_mask_epoch !== 32'd1)
                        $fatal(1, "result metadata mismatch sample=%0d beat=%0d", sample_index, result_beat);
                    if (^result_data === 1'bx)
                        $fatal(1, "unknown logit sample=%0d beat=%0d", sample_index, result_beat);
                    result_beat = result_beat + 1;
                end
            end
        end
    endtask

    integer index;
    integer expected_cycles;
    integer expected_execute;
    integer expected_skip;
    initial begin
        if (!$value$plusargs("MODEL=%s", model_file)) model_file = "model.mem";
        if (!$value$plusargs("SAMPLES=%s", samples_file)) samples_file = "samples.mem";
        if (!$value$plusargs("MASK=%s", mask_file)) mask_file = "gated_mask.mem";
        $readmemh(model_file, model_words);
        $readmemh(samples_file, sample_beats);
        $readmemh(mask_file, gated_mask_words);

`ifdef B3_SAIF_GATED
        expected_cycles = 1606;
        expected_execute = 296;
        expected_skip = 296;
`else
        expected_cycles = 2494;
        expected_execute = 592;
        expected_skip = 0;
`endif

        // post-route功能网表的glbl.GSR约持续100 ns；150 ns后再开始协议配置。
        repeat (30) @(negedge clk);
        rst = 1'b0;
        send_cmd(OP_MODEL_BEGIN, 32'd0, 32'd0);
        for (index = 0; index < 634; index = index + 1)
            send_cmd(OP_MODEL_DATA, 32'd0, model_words[index]);
        send_cmd(OP_MODEL_COMMIT, 32'd0, 32'd0);
        publish_power_mask();
        if (!model_valid || rsp_valid)
            $fatal(1, "configuration failed model_valid=%0d rsp_valid=%0d", model_valid, rsp_valid);

        @(negedge clk);
        saif_active = 1'b1;
        // 给Tcl轮询留出两个时钟周期；相对64次推理窗口低于0.003%。
        repeat (2) @(posedge clk);
        for (index = 0; index < SAMPLE_COUNT; index = index + 1) begin
            run_sample(index);
            if (last_compute_cycles !== expected_cycles)
                $fatal(1, "cycle mismatch sample=%0d got=%0d expected=%0d", index, last_compute_cycles, expected_cycles);
        end
        if (execute_group_count !== SAMPLE_COUNT * expected_execute ||
            skip_group_count !== SAMPLE_COUNT * expected_skip)
            $fatal(1, "group count mismatch execute=%0d skip=%0d", execute_group_count, skip_group_count);
        @(negedge clk);
        saif_active = 1'b0;
        $display("B3_NPU_SAIF_PASS mode=%s samples=%0d cycles=%0d execute=%0d skip=%0d",
`ifdef B3_SAIF_GATED
                 "gated",
`else
                 "dense",
`endif
                 SAMPLE_COUNT, expected_cycles, execute_group_count, skip_group_count);
        repeat (20) @(posedge clk);
        $finish;
    end

    initial begin
        repeat (600000) @(posedge clk);
        $fatal(1, "watchdog: SAIF power simulation did not finish");
    end
endmodule
