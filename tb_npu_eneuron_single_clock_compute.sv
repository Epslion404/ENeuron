// 真实计算 tracer：手算模型验证 uint4×INT8、hidden 饱和、INT32 logit 与 mask 门控。
`timescale 1ns/1ps
module tb_npu_eneuron_single_clock_compute;
    localparam logic [3:0] OP_MODEL_BEGIN  = 4'h1;
    localparam logic [3:0] OP_MODEL_DATA   = 4'h2;
    localparam logic [3:0] OP_MODEL_COMMIT = 4'h3;
    localparam logic [3:0] OP_MASK_BEGIN   = 4'h4;
    localparam logic [3:0] OP_MASK_DATA    = 4'h5;
    localparam logic [3:0] OP_MASK_COMMIT  = 4'h6;

`ifdef TIMING_REPAIR_V1_CONTRACT
`define TIMING_REPAIR_CONTRACT
`elsif TIMING_REPAIR_V2_CONTRACT
`define TIMING_REPAIR_CONTRACT
`endif

`ifdef TIMING_REPAIR_CONTRACT
    // 三拍流水的冻结状态编码，仅用于白盒合同，不增加综合端口。
    localparam logic [3:0] COMPUTE_IDLE             = 4'd0;
    localparam logic [3:0] COMPUTE_L0_BIAS_FETCH    = 4'd1;
    localparam logic [3:0] COMPUTE_L0_GROUP_FETCH   = 4'd3;
    localparam logic [3:0] COMPUTE_L0_GROUP_EXECUTE = 4'd4;
    localparam logic [3:0] COMPUTE_L0_GROUP_COMMIT  = 4'd5;
    localparam logic [3:0] COMPUTE_L1_BIAS_FETCH    = 4'd6;
    localparam logic [3:0] COMPUTE_L1_GROUP_FETCH   = 4'd8;
    localparam logic [3:0] COMPUTE_L1_GROUP_EXECUTE = 4'd9;
    localparam logic [3:0] COMPUTE_L1_GROUP_COMMIT  = 4'd10;
`ifdef TIMING_REPAIR_V2_CONTRACT
    localparam logic [3:0] COMPUTE_L0_WRITEBACK      = 4'd11;
    localparam logic [3:0] COMPUTE_L1_WRITEBACK      = 4'd12;
`endif
`endif

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
    wire [31:0] last_compute_cycles;
    wire [31:0] active_mask_epoch;
    wire [31:0] pending_mask_epoch;

    integer clock_count = 0;
`ifdef TIMING_REPAIR_CONTRACT
    integer compute_start_cycle = 0;
    integer observed_compute_cycles = 0;
    integer execute_count = 0;
    integer commit_count = 0;
    integer l0_execute_count = 0;
    integer l1_execute_count = 0;
    integer expected_compute_cycles = 0;
    integer expected_group_count = 0;
    integer expected_l0_group_count = 0;
    integer expected_l1_group_count = 0;
    logic contract_active = 1'b0;
    logic contract_done = 1'b0;
    logic pending_execute = 1'b0;
    logic pending_layer = 1'b0;
    logic [5:0] pending_unit = '0;
    logic [4:0] pending_group = '0;
    logic [31:0] pending_model_word = '0;
    logic signed [7:0] pending_activation_0 = '0;
    logic signed [7:0] pending_activation_1 = '0;
    logic signed [7:0] pending_activation_2 = '0;
    logic signed [7:0] pending_activation_3 = '0;
    logic pending_closed_fetch = 1'b0;
    logic pending_closed_layer = 1'b0;
    logic [5:0] pending_closed_unit = '0;
    logic [4:0] pending_closed_group = '0;
    logic [31:0] pending_closed_model_word = '0;
    logic [591:0] fetch_seen = '0;
    logic [591:0] execute_seen = '0;
    logic [591:0] commit_seen = '0;
    logic [3:0] previous_compute_state = '0;
    logic signed [31:0] previous_lane_sum = '0;
    logic monitor_initialized = 1'b0;
    integer l0_writeback_count = 0;
    integer l1_writeback_count = 0;
    integer expected_l0_writeback_count = 32;
    integer expected_l1_writeback_count = 10;
`endif

    always @(posedge clk)
        clock_count = clock_count + 1;

    npu_eneuron_single_clock_skeleton dut (
        .clk(clk), .rst(rst), .cmd_payload(cmd_payload), .cmd_valid(cmd_valid), .cmd_ready(cmd_ready),
        .rsp_payload(rsp_payload), .rsp_valid(rsp_valid), .rsp_ready(rsp_ready),
        .sample_data(sample_data), .sample_id(sample_id), .sample_valid(sample_valid), .sample_ready(sample_ready),
        .result_data(result_data), .result_sample_id(result_sample_id), .result_mask_epoch(result_mask_epoch),
        .result_valid(result_valid), .result_ready(result_ready), .runtime_idle(runtime_idle),
        .model_valid(model_valid), .mask_valid(mask_valid), .infer_frozen(infer_frozen),
        .state_clear_count(state_clear_count), .last_compute_cycles(last_compute_cycles),
        .active_mask_epoch(active_mask_epoch), .pending_mask_epoch(pending_mask_epoch)
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
            @(posedge clk);
            while (!cmd_ready) @(posedge clk);
            @(negedge clk);
            cmd_valid = 1'b0;
            cmd_payload = '0;
        end
    endtask

    task automatic send_sample(input logic [31:0] id);
        integer beat;
`ifdef TIMING_REPAIR_CONTRACT
        integer scan_bit;
        integer enabled_groups;
`endif
        begin
            for (beat = 0; beat < 8; beat = beat + 1) begin
                @(negedge clk);
                sample_id = id;
                if (beat == 0) sample_data = 32'h0000_ffff;
                else if (beat == 7) sample_data = 32'hffff_0000;
                else sample_data = 32'd0;
                sample_valid = 1'b1;
                @(posedge clk);
                while (!sample_ready) @(posedge clk);
                @(negedge clk);
`ifdef TIMING_REPAIR_CONTRACT
                if (beat == 7) begin
                    compute_start_cycle = clock_count;
                    enabled_groups = 0;
                    for (scan_bit = 0; scan_bit < 592; scan_bit = scan_bit + 1)
                        if (dut.mask_active_words[scan_bit >> 5][scan_bit & 31])
                            enabled_groups = enabled_groups + 1;
                    if (enabled_groups != expected_group_count)
                        $fatal(1, "active mask count mismatch got=%0d expected=%0d",
                               enabled_groups, expected_group_count);
                end
`endif
                sample_valid = 1'b0;
            end
        end
    endtask

    task automatic publish_mask(input logic [31:0] epoch, input integer mode);
        logic [31:0] word;
        integer mask_word;
        begin
            send_cmd(OP_MASK_BEGIN, epoch, 32'd0);
            for (mask_word = 0; mask_word < 19; mask_word = mask_word + 1) begin
                case (mode)
                    1: begin
                        if (mask_word == 0) word = 32'hffff_fffe;
                        else if (mask_word == 18) word = 32'h0000_7fff;
                        else word = 32'hffff_ffff;
                    end
                    2: word = 32'd0;
                    3: begin
                        if (mask_word == 0) word = 32'hffff_7fff;
                        else if (mask_word == 18) word = 32'h0000_ffff;
                        else word = 32'hffff_ffff;
                    end
                    default: begin
                        if (mask_word == 18) word = 32'h0000_ffff;
                        else word = 32'hffff_ffff;
                    end
                endcase
                send_cmd(OP_MASK_DATA, 32'd0, word);
            end
            send_cmd(OP_MASK_COMMIT, epoch, 32'd0);
        end
    endtask

`ifdef TIMING_REPAIR_CONTRACT
    task automatic start_contract(
        input integer groups,
        input integer l0_groups,
        input integer l1_groups,
        input integer cycles
    );
        begin
            expected_group_count = groups;
            expected_l0_group_count = l0_groups;
            expected_l1_group_count = l1_groups;
            expected_compute_cycles = cycles;
            observed_compute_cycles = 0;
            execute_count = 0;
            commit_count = 0;
            l0_execute_count = 0;
            l1_execute_count = 0;
            l0_writeback_count = 0;
            l1_writeback_count = 0;
            pending_execute = 1'b0;
            pending_closed_fetch = 1'b0;
            fetch_seen = '0;
            execute_seen = '0;
            commit_seen = '0;
            contract_done = 1'b0;
            contract_active = 1'b1;
            monitor_initialized = 1'b0;
        end
    endtask

    task automatic check_contract;
        begin
            if (!contract_done)
                $fatal(1, "timing contract did not observe result slot");
            if (execute_count != expected_group_count || commit_count != expected_group_count)
                $fatal(1, "group count mismatch execute=%0d commit=%0d expected=%0d l0=%0d l1=%0d",
                       execute_count, commit_count, expected_group_count,
                       l0_execute_count, l1_execute_count);
            if (l0_execute_count != expected_l0_group_count ||
                l1_execute_count != expected_l1_group_count)
                $fatal(1, "layer group count mismatch l0=%0d/%0d l1=%0d/%0d",
                       l0_execute_count, expected_l0_group_count,
                       l1_execute_count, expected_l1_group_count);
            if (observed_compute_cycles != expected_compute_cycles)
                $fatal(1, "compute cycle mismatch got=%0d expected=%0d",
                       observed_compute_cycles, expected_compute_cycles);
            if (last_compute_cycles != expected_compute_cycles)
                $fatal(1, "latched compute cycle mismatch got=%0d expected=%0d",
                       last_compute_cycles, expected_compute_cycles);
        end
    endtask

    integer active_mask_bit;
    integer expected_model_address;
    integer verify_bit;
    always @(negedge clk) begin
        if (rst) begin
            monitor_initialized = 1'b0;
            previous_compute_state = 4'd0;
            previous_lane_sum = 32'sd0;
        end else if (contract_active) begin
            if (pending_closed_fetch) begin
                if (dut.model_word_latched !== pending_closed_model_word)
                    $fatal(1, "disabled FETCH changed model_word_latched layer=%0d unit=%0d group=%0d",
                           pending_closed_layer, pending_closed_unit, pending_closed_group);
                if (!pending_closed_layer) begin
                    if (pending_closed_group != 5'd15) begin
                        if (dut.compute_state != COMPUTE_L0_GROUP_FETCH ||
                            dut.compute_unit_index !== pending_closed_unit ||
                            dut.compute_group_index !== (pending_closed_group + 5'd1))
                            $fatal(1, "disabled L0 group did not advance directly in FETCH");
                    end else begin
`ifdef TIMING_REPAIR_V2_CONTRACT
                        if (dut.compute_state != COMPUTE_L0_WRITEBACK ||
                            dut.compute_unit_index !== pending_closed_unit ||
                            dut.compute_group_index !== 5'd0)
                            $fatal(1, "disabled final L0 group did not enter WRITEBACK");
`else
                        if (pending_closed_unit != 6'd31) begin
                        if (dut.compute_state != COMPUTE_L0_BIAS_FETCH ||
                            dut.compute_unit_index !== (pending_closed_unit + 6'd1) ||
                            dut.compute_group_index !== 5'd0)
                            $fatal(1, "disabled final L0 group did not advance to next bias");
                        end else if (dut.compute_state != COMPUTE_L1_BIAS_FETCH ||
                                 dut.compute_unit_index !== 6'd0 ||
                                 dut.compute_group_index !== 5'd0) begin
                        $fatal(1, "disabled final L0 layer group did not cross to L1 bias");
                        end
`endif
                    end
                end else begin
                    if (pending_closed_group != 5'd7) begin
                        if (dut.compute_state != COMPUTE_L1_GROUP_FETCH ||
                            dut.compute_unit_index !== pending_closed_unit ||
                            dut.compute_group_index !== (pending_closed_group + 5'd1))
                            $fatal(1, "disabled L1 group did not advance directly in FETCH");
                    end else begin
`ifdef TIMING_REPAIR_V2_CONTRACT
                        if (dut.compute_state != COMPUTE_L1_WRITEBACK ||
                            dut.compute_unit_index !== pending_closed_unit ||
                            dut.compute_group_index !== 5'd0)
                            $fatal(1, "disabled final L1 group did not enter WRITEBACK");
`else
                        if (pending_closed_unit != 6'd9) begin
                        if (dut.compute_state != COMPUTE_L1_BIAS_FETCH ||
                            dut.compute_unit_index !== (pending_closed_unit + 6'd1) ||
                            dut.compute_group_index !== 5'd0)
                            $fatal(1, "disabled final L1 group did not advance to next bias");
                        end else if (dut.compute_state != COMPUTE_IDLE || !result_valid) begin
                        $fatal(1, "disabled final output group did not establish result slot");
                        end
`endif
                    end
                end
                pending_closed_fetch = 1'b0;
            end

            if (monitor_initialized && dut.lane_sum_latched !== previous_lane_sum &&
                previous_compute_state != COMPUTE_L0_GROUP_EXECUTE &&
                previous_compute_state != COMPUTE_L1_GROUP_EXECUTE &&
                previous_compute_state != COMPUTE_L0_GROUP_COMMIT &&
                previous_compute_state != COMPUTE_L1_GROUP_COMMIT)
                $fatal(1, "lane_sum_latched changed outside EXECUTE previous_state=%0d",
                       previous_compute_state);

            if (dut.compute_state == COMPUTE_L0_GROUP_FETCH ||
                dut.compute_state == COMPUTE_L1_GROUP_FETCH) begin
                if (dut.compute_state == COMPUTE_L1_GROUP_FETCH)
                    active_mask_bit = 512 + (dut.compute_unit_index * 8) + dut.compute_group_index;
                else
                    active_mask_bit = (dut.compute_unit_index * 16) + dut.compute_group_index;
                if (fetch_seen[active_mask_bit])
                    $fatal(1, "group FETCH repeated bit=%0d", active_mask_bit);
                fetch_seen[active_mask_bit] = 1'b1;
                if (!dut.mask_active_words[active_mask_bit >> 5][active_mask_bit & 31]) begin
                    pending_closed_fetch = 1'b1;
                    pending_closed_layer = (dut.compute_state == COMPUTE_L1_GROUP_FETCH);
                    pending_closed_unit = dut.compute_unit_index;
                    pending_closed_group = dut.compute_group_index;
                    pending_closed_model_word = dut.model_word_latched;
                end
            end

            if (dut.compute_state == COMPUTE_L0_GROUP_EXECUTE ||
                dut.compute_state == COMPUTE_L1_GROUP_EXECUTE) begin
                if (pending_execute)
                    $fatal(1, "EXECUTE observed before prior COMMIT");
                pending_execute = 1'b1;
                pending_layer = (dut.compute_state == COMPUTE_L1_GROUP_EXECUTE);
                pending_unit = dut.compute_unit_index;
                pending_group = dut.compute_group_index;
                pending_model_word = dut.model_word_latched;
                pending_activation_0 = dut.lane_activation_latched_0;
                pending_activation_1 = dut.lane_activation_latched_1;
                pending_activation_2 = dut.lane_activation_latched_2;
                pending_activation_3 = dut.lane_activation_latched_3;
`ifdef TIMING_REPAIR_V2_CONTRACT
                if (!pending_layer) begin
                    if (dut.lane_activation_latched_0 !== $signed({4'b0000, dut.input_pixels[(pending_group * 4) + 0]}) ||
                        dut.lane_activation_latched_1 !== $signed({4'b0000, dut.input_pixels[(pending_group * 4) + 1]}) ||
                        dut.lane_activation_latched_2 !== $signed({4'b0000, dut.input_pixels[(pending_group * 4) + 2]}) ||
                        dut.lane_activation_latched_3 !== $signed({4'b0000, dut.input_pixels[(pending_group * 4) + 3]}))
                        $fatal(1, "L0 FETCH activation latch mismatch unit=%0d group=%0d",
                               pending_unit, pending_group);
                end else if (dut.lane_activation_latched_0 !== $signed({1'b0, dut.hidden_values[(pending_group * 4) + 0]}) ||
                             dut.lane_activation_latched_1 !== $signed({1'b0, dut.hidden_values[(pending_group * 4) + 1]}) ||
                             dut.lane_activation_latched_2 !== $signed({1'b0, dut.hidden_values[(pending_group * 4) + 2]}) ||
                             dut.lane_activation_latched_3 !== $signed({1'b0, dut.hidden_values[(pending_group * 4) + 3]}))
                    $fatal(1, "L1 FETCH activation latch mismatch unit=%0d group=%0d",
                           pending_unit, pending_group);
`endif
                execute_count = execute_count + 1;
                if (pending_layer) begin
                    l1_execute_count = l1_execute_count + 1;
                    active_mask_bit = 512 + (pending_unit * 8) + pending_group;
                end else begin
                    l0_execute_count = l0_execute_count + 1;
                    active_mask_bit = (pending_unit * 16) + pending_group;
                end
                if (!dut.mask_active_words[active_mask_bit >> 5][active_mask_bit & 31])
                    $fatal(1, "disabled group entered EXECUTE layer=%0d unit=%0d group=%0d",
                           pending_layer, pending_unit, pending_group);
                if (execute_seen[active_mask_bit])
                    $fatal(1, "group EXECUTE repeated bit=%0d", active_mask_bit);
                execute_seen[active_mask_bit] = 1'b1;
                if (pending_layer)
                    expected_model_address = 544 + (pending_unit * 8) + pending_group;
                else
                    expected_model_address = (pending_unit * 16) + pending_group;
                if (dut.model_word_latched !== dut.model_staging[expected_model_address])
                    $fatal(1, "model word address mismatch layer=%0d unit=%0d group=%0d address=%0d",
                           pending_layer, pending_unit, pending_group, expected_model_address);
            end else if (pending_execute) begin
                if ((!pending_layer && dut.compute_state != COMPUTE_L0_GROUP_COMMIT) ||
                    (pending_layer && dut.compute_state != COMPUTE_L1_GROUP_COMMIT))
                    $fatal(1, "EXECUTE did not transition directly to COMMIT state=%0d",
                           dut.compute_state);
                if (dut.compute_unit_index !== pending_unit ||
                    dut.compute_group_index !== pending_group ||
                    dut.model_word_latched !== pending_model_word)
                    $fatal(1, "unit/group/model word changed before COMMIT");
`ifdef TIMING_REPAIR_V2_CONTRACT
                if (dut.lane_activation_latched_0 !== pending_activation_0 ||
                    dut.lane_activation_latched_1 !== pending_activation_1 ||
                    dut.lane_activation_latched_2 !== pending_activation_2 ||
                    dut.lane_activation_latched_3 !== pending_activation_3)
                    $fatal(1, "activation latch changed between EXECUTE and COMMIT");
`endif
                if (pending_layer)
                    active_mask_bit = 512 + (pending_unit * 8) + pending_group;
                else
                    active_mask_bit = (pending_unit * 16) + pending_group;
                if (commit_seen[active_mask_bit])
                    $fatal(1, "group COMMIT repeated bit=%0d", active_mask_bit);
                commit_seen[active_mask_bit] = 1'b1;
                commit_count = commit_count + 1;
                pending_execute = 1'b0;
            end else if (dut.compute_state == COMPUTE_L0_GROUP_COMMIT ||
                         dut.compute_state == COMPUTE_L1_GROUP_COMMIT) begin
                $fatal(1, "COMMIT observed without preceding EXECUTE");
            end

`ifdef TIMING_REPAIR_V2_CONTRACT
            if (dut.compute_state == COMPUTE_L0_WRITEBACK) begin
                if (dut.compute_unit_index > 6'd31)
                    $fatal(1, "invalid L0 WRITEBACK unit=%0d", dut.compute_unit_index);
                l0_writeback_count = l0_writeback_count + 1;
            end
            if (dut.compute_state == COMPUTE_L1_WRITEBACK) begin
                if (dut.compute_unit_index > 6'd9)
                    $fatal(1, "invalid L1 WRITEBACK unit=%0d", dut.compute_unit_index);
                l1_writeback_count = l1_writeback_count + 1;
            end
`endif

            if (result_valid && !contract_done) begin
                if (pending_execute || pending_closed_fetch)
                    $fatal(1, "result slot established with pending compute transition");
                for (verify_bit = 0; verify_bit < 592; verify_bit = verify_bit + 1) begin
                    if (!fetch_seen[verify_bit])
                        $fatal(1, "group FETCH missing bit=%0d", verify_bit);
                    if (execute_seen[verify_bit] !==
                        dut.mask_active_words[verify_bit >> 5][verify_bit & 31])
                        $fatal(1, "EXECUTE bitmap differs from active mask bit=%0d", verify_bit);
                    if (commit_seen[verify_bit] !==
                        dut.mask_active_words[verify_bit >> 5][verify_bit & 31])
                        $fatal(1, "COMMIT bitmap differs from active mask bit=%0d", verify_bit);
                end
                observed_compute_cycles = clock_count - compute_start_cycle;
`ifdef TIMING_REPAIR_V2_CONTRACT
                if (l0_writeback_count != expected_l0_writeback_count ||
                    l1_writeback_count != expected_l1_writeback_count)
                    $fatal(1, "WRITEBACK count mismatch l0=%0d/%0d l1=%0d/%0d",
                           l0_writeback_count, expected_l0_writeback_count,
                           l1_writeback_count, expected_l1_writeback_count);
                if (previous_compute_state != COMPUTE_L1_WRITEBACK)
                    $fatal(1, "result slot established outside final L1 WRITEBACK");
`endif
                contract_done = 1'b1;
                contract_active = 1'b0;
            end

            previous_compute_state = dut.compute_state;
            previous_lane_sum = dut.lane_sum_latched;
            monitor_initialized = 1'b1;
        end
    end
`endif

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
`ifdef TIMING_REPAIR_CONTRACT
`ifdef TIMING_REPAIR_V2_CONTRACT
        start_contract(592, 512, 80, 2494);
`else
        start_contract(592, 512, 80, 1860);
`endif
`endif
        send_sample(32'h101);
        if (sample_ready || cmd_ready || runtime_idle)
            $fatal(1, "ready/idle asserted while compute is active");
        // 当前样本计算期间并发发布下一 mask；它只能影响下一样本。
        publish_mask(32'd1, 1);
        if (active_mask_epoch !== 32'd0 || pending_mask_epoch !== 32'd1)
            $fatal(1, "published mask epoch state mismatch active=%0d pending=%0d mask_valid=%0d published=%0d",
                   active_mask_epoch, pending_mask_epoch, mask_valid, dut.mask_published_epoch);
        check_result(32'h101, 32'd0, 32'sd137, 32'sd59);
`ifdef TIMING_REPAIR_CONTRACT
        check_contract();
`ifdef TIMING_REPAIR_V2_CONTRACT
        start_contract(590, 511, 79, 2488);
`else
        start_contract(590, 511, 79, 1856);
`endif
`endif

        // 下一样本首 beat 激活新版本：logit0=-117，output9 只剩 bias=-1。
        send_sample(32'h102);
        if (active_mask_epoch !== 32'd1 || pending_mask_epoch !== 32'd0)
            $fatal(1, "published mask epoch did not activate atomically at sample boundary");
        check_result(32'h102, 32'd1, -32'sd117, -32'sd1);
`ifdef TIMING_REPAIR_CONTRACT
        check_contract();
`endif

        // epoch2 全关：所有权重组都在 FETCH 直接跳过，bias 仍然有效。
        publish_mask(32'd2, 2);
`ifdef TIMING_REPAIR_CONTRACT
`ifdef TIMING_REPAIR_V2_CONTRACT
        start_contract(0, 0, 0, 718);
`else
        start_contract(0, 0, 0, 676);
`endif
`endif
        send_sample(32'h103);
        check_result(32'h103, 32'd2, 32'sd3, -32'sd1);
`ifdef TIMING_REPAIR_CONTRACT
        check_contract();
`endif

        // epoch3 只关闭 L0 unit0/group15；此前 group0 已产生非零累加。
        publish_mask(32'd3, 3);
`ifdef TIMING_REPAIR_CONTRACT
`ifdef TIMING_REPAIR_V2_CONTRACT
        start_contract(591, 511, 80, 2491);
`else
        start_contract(591, 511, 80, 1858);
`endif
`endif
        send_sample(32'h104);
        check_result(32'h104, 32'd3, 32'sd137, 32'sd59);
`ifdef TIMING_REPAIR_CONTRACT
        check_contract();
`endif

        $display("PASS npu single-clock real compute tracer");
        $finish;
    end

    initial begin
        repeat (12000) @(posedge clk);
        $fatal(1, "watchdog: compute tracer did not finish");
    end
endmodule
