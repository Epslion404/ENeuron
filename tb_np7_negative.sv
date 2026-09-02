// NP7.5 负向控制实现的逐拍观测测试台。
//
// 编译：iverilog -g2012 -s tb -Ptb.LANES=<1|2|4|8> -Ptb.NEG=<0|1> 本文件与负向 RTL...
// 运行：vvp sim.out +NTXN=<n> +NWORD=<n>，工作目录内需有 np7_cfg.hex、np7_txn.hex、
// np7_bp.hex 三个由 np7_formal_and_mutations.py 生成的激励文件。
// 每拍打印一行 CYC CSV，结束打印一行 LEDGER，格式与 NP7.3 完全一致，便于同一
// 套重建规则同时用于 golden 与负向实现。本文件不进入综合路径。
//
// B-V1+V2 口径：负向实现与 golden 共用同一套 V1/V2 握手（同拍 retire+accept、
// 零路径单拍、背压锁存），激励也是连续无气泡 + 随机背压流；两者只在"自报账本"
// 上不同，因此窗口按整条流（首次 accept → 最后退出）切分，不再按事务分段。
`timescale 1ns/1ps
module tb;
    localparam int MAX_TXN = 2048;
    localparam int MAX_CYC = 60000;
    localparam int MAX_WORDS = 64;

    parameter int LANES = 4;
    // NTXN/NWORD 允许两条路径注入：Icarus 用 +NTXN=/+NWORD= plusarg，
    // Vivado xsim 用实例化参数（xsim.bat 经 cmd 转发会把 NAME=VALUE 拆成两个参数）。
    // plusarg 优先，参数为 0 时退回原有的 1000/20 默认值，行为与历史证据完全一致。
    parameter int NTXN = 0;
    parameter int NWORD = 0;
    parameter int NEG = 0;

    logic clk = 1'b0;
    always #5 clk = ~clk;

    logic rst = 1'b1;
    logic cfg_valid = 1'b0;
    logic cfg_ready;
    logic [4:0] cfg_addr = 5'd0;
    logic [19:0] cfg_wdata = 20'd0;
    logic cfg_open = 1'b1;
    logic cfg_error;
    wire cfg_illegal_index;
    wire issue_valid;
    logic issue_ready;
    wire [3:0] issue_group;
    wire [3:0] issue_activity;
    wire [3:0] issue_mask;
    wire [2:0] issue_skip;
    wire lane_stall;
    logic result_valid;
    wire result_ready;
    wire signed [11:0] result_sum;
    wire result_zero_path;
    wire ram_ce;
    wire [4:0] ram_addr;
    wire [3:0] batch_mask;
    wire [2:0] lane_fire_count;
    wire [2:0] state_code;
    wire accept_pulse;
    wire protocol_error;
    wire [31:0] req_s, val_s, ops_s, zero_s, busy_s, stall_s, done_s;
    wire [31:0] skip_s, inzero_s, azero_s, sat_s, total_s;

    logic [31:0] words [0:MAX_WORDS - 1];
    logic [31:0] txn [0:MAX_TXN - 1];
    logic [7:0] bp [0:MAX_CYC - 1];

    int ntxn;
    int nword;
    int cycle;
    int index;
    int completed;
    int issued;
    // Vivado xvlog 要求标识符先声明后使用：run_phase 在下方 initial 与连续赋值中均被引用。
    logic run_phase = 1'b0;
    generate
        if (NEG == 0) begin : g_dut_neg_read_all
            np7_neg_read_all_then_gate #(.LANES(LANES)) dut (
                .clk(clk), .rst(rst),
                .cfg_valid(cfg_valid), .cfg_ready(cfg_ready),
                .cfg_addr(cfg_addr), .cfg_wdata(cfg_wdata),
                .cfg_open(cfg_open), .cfg_error(cfg_error),
                .cfg_illegal_index(cfg_illegal_index),
                .issue_valid(issue_valid), .issue_ready(issue_ready),
                .issue_group(issue_group), .issue_activity(issue_activity),
                .issue_mask(issue_mask), .issue_skip_count(issue_skip),
                .lane_stall(lane_stall), .result_valid(result_valid),
                .result_ready(result_ready), .result_sum(result_sum),
                .result_zero_path(result_zero_path),
                .ram_ce(ram_ce), .ram_addr(ram_addr), .batch_mask(batch_mask),
                .lane_fire_count(lane_fire_count), .state_code(state_code),
                .accept_pulse(accept_pulse),
                .group_read_requests_state(req_s),
                .weight_values_fetched_state(val_s),
                .lane_ops_issued_state(ops_s), .zero_fast_paths_state(zero_s),
                .busy_cycles_state(busy_s), .stall_cycles_state(stall_s),
                .completed_groups_state(done_s),
                .structural_skips_state(skip_s),
                .input_zero_groups_state(inzero_s),
                .activity_zero_after_structure_state(azero_s),
                .saturation_events_state(sat_s),
                .total_cycles_state(total_s),
                .protocol_error(protocol_error)
            );
        end else begin : g_dut_neg_mac_clear
            np7_neg_mac_then_clear #(.LANES(LANES)) dut (
                .clk(clk), .rst(rst),
                .cfg_valid(cfg_valid), .cfg_ready(cfg_ready),
                .cfg_addr(cfg_addr), .cfg_wdata(cfg_wdata),
                .cfg_open(cfg_open), .cfg_error(cfg_error),
                .cfg_illegal_index(cfg_illegal_index),
                .issue_valid(issue_valid), .issue_ready(issue_ready),
                .issue_group(issue_group), .issue_activity(issue_activity),
                .issue_mask(issue_mask), .issue_skip_count(issue_skip),
                .lane_stall(lane_stall), .result_valid(result_valid),
                .result_ready(result_ready), .result_sum(result_sum),
                .result_zero_path(result_zero_path),
                .ram_ce(ram_ce), .ram_addr(ram_addr), .batch_mask(batch_mask),
                .lane_fire_count(lane_fire_count), .state_code(state_code),
                .accept_pulse(accept_pulse),
                .group_read_requests_state(req_s),
                .weight_values_fetched_state(val_s),
                .lane_ops_issued_state(ops_s), .zero_fast_paths_state(zero_s),
                .busy_cycles_state(busy_s), .stall_cycles_state(stall_s),
                .completed_groups_state(done_s),
                .structural_skips_state(skip_s),
                .input_zero_groups_state(inzero_s),
                .activity_zero_after_structure_state(azero_s),
                .saturation_events_state(sat_s),
                .total_cycles_state(total_s),
                .protocol_error(protocol_error)
            );
        end
    endgenerate    initial begin
        if (!$value$plusargs("NTXN=%d", ntxn)) ntxn = (NTXN > 0) ? NTXN : 1000;
        if (!$value$plusargs("NWORD=%d", nword)) nword = (NWORD > 0) ? NWORD : 20;
        for (index = 0; index < MAX_CYC; index = index + 1)
            bp[index] = 8'h02;
        $readmemh("np7_cfg.hex", words);
        $readmemh("np7_txn.hex", txn);
        $readmemh("np7_bp.hex", bp);
        cycle = 0;
        issued = 0;
        completed = 0;
        repeat (3) @(posedge clk);
        rst <= 1'b0;
        @(posedge clk);
        #1;
        // CONFIG 装载：块内阻塞赋值 + 上升沿写入，保证每个字恰好写一次。
        for (index = 0; index < nword; index = index + 1) begin
            cfg_addr = index % MAX_WORDS;
            cfg_wdata = words[index] & 20'hFFFFF;
            cfg_valid = 1'b1;
            if (cfg_illegal_index) begin
                $display("TB_FAIL illegal_config_word %0d %h", index, words[index]);
                $finish;
            end
            @(posedge clk);
            #1;
        end
        cfg_valid = 1'b0;
        cfg_open = 1'b0;
        @(posedge clk);
        #1;
        if (cfg_error) begin
            $display("TB_FAIL config_error_after_load");
            $finish;
        end
        run_phase = 1'b1;
        while (completed < ntxn && cycle < MAX_CYC - 8) begin
            @(posedge clk);
            #1;
        end
        run_phase = 1'b0;
        @(posedge clk);
        $display("LEDGER req=%0d val=%0d ops=%0d zero=%0d busy=%0d stall=%0d done=%0d skip=%0d inzero=%0d azero=%0d sat=%0d total=%0d proto=%0d cfgerr=%0d completed=%0d",
            req_s, val_s, ops_s, zero_s, busy_s, stall_s, done_s, skip_s,
            inzero_s, azero_s, sat_s, total_s, protocol_error, cfg_error, completed);
        $finish;
    end

    // 组合驱动激励：接受拍与后续拍的编号与 oracle 的"本地周期序号"完全对齐，
    // 不接受拍不消耗周期，因此无需为流水线气泡补拍。
    wire [31:0] cur_txn = txn[issued < ntxn ? issued : (ntxn - 1)];
    wire [7:0] cur_bp = bp[cycle < MAX_CYC ? cycle : (MAX_CYC - 1)];

    assign issue_group = cur_txn[3:0];
    assign issue_activity = cur_txn[7:4];
    assign issue_mask = cur_txn[11:8];
    assign issue_skip = cur_txn[14:12];
    assign lane_stall = run_phase && cur_bp[0];
    assign result_ready = !run_phase || cur_bp[1];
    // B-V1+V2：上游连续供数（无气泡），接受拍可与前一事务结果退出同拍，
    // 因此不再用 state_code==IDLE 门控 issue_valid（旧口径永远测不到 V2 重叠）。
    assign issue_valid = run_phase && (issued < ntxn);

    always @(posedge clk) begin
        cycle <= cycle + 1;
        if (!rst && run_phase) begin
            // 非阻塞更新：避免与 DUT 在同一边沿采样 issue_* 形成竞争。
            if (accept_pulse)
                issued <= issued + 1;
            if (result_valid && result_ready)
                completed <= completed + 1;
        end
    end

    always @(negedge clk) begin
        if (!rst) begin
            $display("CYC %0d st=%0d ce=%0b ad=%0d lf=%0d bm=%0h rv=%0b rr=%0b ap=%0b zp=%0b sum=%0d ls=%0b cmp=%0d",
                cycle, state_code, ram_ce, ram_addr, lane_fire_count,
                batch_mask, result_valid, result_ready, accept_pulse,
                result_zero_path, result_sum, lane_stall, done_s);
        end
    end
endmodule
