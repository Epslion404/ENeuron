// NP7 CONFIG 拒绝语义负向测试台（PR #6 评审意见 2）。
//
// 目的：在硬件层面证明"非法 CONFIG 字被阻止写入、错误锁存、合法字仍可执行"。
// 四个相位共用完全相同的事务序列与期望突触和：
//   PHASE 0 CLEAN  只装载合法字                            -> cfg_error 必须为 0
//   PHASE 1 EQ     合法字之后再写非法字（索引等值/保留位非零）-> RAM 内容不得改变，错误锁存
//   PHASE 2 DESC   先写非法字（索引降序）再补合法字          -> 非法字被丢弃，合法字必须生效
//   PHASE 3 RT     装载合法、关闭 CONFIG 之后再尝试写入      -> 运行期写被丢弃，前后两批和一致
// 任一相位的突触和序列若与 CLEAN 不同，即说明非法字真的进入了 RAM。
//
// 编译：iverilog -g2012 -s tb -Ptb.LANES=<1|2|4|8> [-Ptb.SPARSE=1'b1] 本文件与 RTL
//       xvlog -sv 本文件与同一组 RTL（Vivado 2024.x）
// 运行：vvp sim.out / xsim siminst，无需任何外部激励文件（激励全部内置）。
// 输出：以 CFGNEG 开头的机器可判定行，末行 CFGNEG SUMMARY ... RESULT=PASS|FAIL。
// 本文件是验证工装，不进入任何综合路径。
`timescale 1ns/1ps
module tb;
    parameter int LANES = 4;
    parameter bit SPARSE = 1'b0;

    localparam int NREP = 3;
    localparam int NPHASE = 4;
    localparam int MAXSUM = 1024;

    logic clk = 1'b0;
    always #5 clk = ~clk;

    logic rst = 1'b1;
    logic cfg_valid = 1'b0;
    logic cfg_open = 1'b1;
    logic cfg_ready;
    logic [4:0] cfg_addr = 5'd0;
    logic [19:0] cfg_wdata = 20'd0;
    logic cfg_error;
    wire cfg_illegal_index;
    logic issue_valid = 1'b0;
    wire issue_ready;
    logic [3:0] issue_group = 4'd0;
    logic [3:0] issue_activity = 4'd0;
    logic [3:0] issue_mask = 4'd0;
    logic [2:0] issue_skip = 3'd0;
    logic lane_stall = 1'b0;
    wire result_valid;
    logic result_ready = 1'b1;
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

    logic [19:0] legal [0:7];
    logic [19:0] poison [0:1];
    logic [3:0] struct_mask [0:3];
    int nlegal;
    int poison_addr;
    int nsum [0:NPHASE - 1];
    logic signed [11:0] sums [0:NPHASE - 1][0:MAXSUM - 1];
    int err_after_cfg [0:NPHASE - 1];
    int err_final [0:NPHASE - 1];
    int proto_seen [0:NPHASE - 1];
    int strobe_cnt [0:NPHASE - 1];
    int done_cnt [0:NPHASE - 1];
    int phase;
    int guard;
    int idx;
    int rep;
    int failed;
    int checks;
    logic ok_match;
    logic [4:0] wr_addr;
    logic accepted_flag;

    generate
        if (SPARSE) begin : g_dut_sparse
            np7_exec_unit_sparse #(.LANES(LANES)) dut (
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
        end else begin : g_dut_dense
            np7_exec_unit_dense #(.LANES(LANES)) dut (
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
    endgenerate

    function automatic [19:0] sparse_word(input [1:0] i0, input [1:0] i1,
                                          input signed [7:0] a,
                                          input signed [7:0] b);
        sparse_word = {i1, i0, b, a};
    endfunction

    function automatic [19:0] dense_word(input signed [7:0] a,
                                         input signed [7:0] b,
                                         input [3:0] reserved);
        dense_word = {reserved, b, a};
    endfunction

    task automatic build_stimulus;
    begin
        if (SPARSE) begin
            nlegal = 4;
            poison_addr = 1;
            legal[0] = sparse_word(2'd0, 2'd1, 8'sd1, 8'sd2);
            legal[1] = sparse_word(2'd0, 2'd2, 8'sd3, 8'sd5);
            legal[2] = sparse_word(2'd1, 2'd3, 8'sd7, -8'sd4);
            legal[3] = sparse_word(2'd2, 2'd3, -8'sd3, 8'sd6);
            struct_mask[0] = 4'b0011;
            struct_mask[1] = 4'b0101;
            struct_mask[2] = 4'b1010;
            struct_mask[3] = 4'b1100;
            poison[0] = sparse_word(2'd1, 2'd1, -8'sd100, -8'sd100);
            poison[1] = sparse_word(2'd3, 2'd0, -8'sd100, -8'sd100);
        end else begin
            nlegal = 8;
            poison_addr = 2;
            legal[0] = dense_word(8'sd1, 8'sd2, 4'b0000);
            legal[1] = dense_word(8'sd3, 8'sd4, 4'b0000);
            legal[2] = dense_word(8'sd5, 8'sd6, 4'b0000);
            legal[3] = dense_word(8'sd7, 8'sd8, 4'b0000);
            legal[4] = dense_word(-8'sd4, 8'sd7, 4'b0000);
            legal[5] = dense_word(8'sd6, -8'sd3, 4'b0000);
            legal[6] = dense_word(-8'sd2, 8'sd5, 4'b0000);
            legal[7] = dense_word(-8'sd1, 8'sd4, 4'b0000);
            struct_mask[0] = 4'b1111;
            struct_mask[1] = 4'b1111;
            struct_mask[2] = 4'b1111;
            struct_mask[3] = 4'b1111;
            poison[0] = dense_word(-8'sd100, -8'sd99, 4'b1111);
            poison[1] = dense_word(8'sd99, -8'sd99, 4'b1000);
        end
    end
    endtask

    task automatic cfg_write(input [4:0] addr, input [19:0] word);
    begin
        cfg_addr = addr;
        cfg_wdata = word;
        cfg_valid = 1'b1;
        @(posedge clk);
        #1;
        if (cfg_illegal_index) strobe_cnt[phase] = strobe_cnt[phase] + 1;
        cfg_valid = 1'b0;
        @(posedge clk);
        #1;
    end
    endtask

    // 接受拍必须按时钟沿记录：accept_pulse 在边沿前为 1、边沿后随状态离开
    // IDLE 归 0，直接用 while(!accept_pulse) 轮询会在同一时间步内竞态。
    always @(posedge clk) begin
        if (accept_pulse) accepted_flag = 1'b1;
    end

    task automatic send_txn(input [3:0] grp, input [3:0] act, input [3:0] msk);
    begin
        @(posedge clk);
        #1;
        issue_group = grp;
        issue_activity = act;
        issue_mask = msk;
        issue_skip = 3'd0;
        accepted_flag = 1'b0;
        issue_valid = 1'b1;
        guard = 0;
        while (!accepted_flag && guard < 5000) begin
            @(posedge clk);
            #1;
            guard = guard + 1;
        end
        issue_valid = 1'b0;
        if (guard >= 5000)
            $display("CFGNEG FAIL phase=%0d txn_timeout group=%0d mask=%0h", phase, grp, msk);
    end
    endtask

    task automatic run_txn_list;
        logic [3:0] grp;
    begin
        for (rep = 0; rep < NREP; rep = rep + 1) begin
            for (grp = 4'd0; grp < 4'd4; grp = grp + 4'd1) begin
                send_txn(grp, 4'hF, struct_mask[grp]);
                if (grp == 1 && rep == 1) begin
                    lane_stall = 1'b1;
                    repeat (3) @(posedge clk);
                    #1;
                    lane_stall = 1'b0;
                end
                if (grp == 2 && rep == 0) begin
                    result_ready = 1'b0;
                    repeat (2) @(posedge clk);
                    #1;
                    result_ready = 1'b1;
                end
            end
            send_txn(4'd0, 4'h0, 4'b0000);
            send_txn(4'd3, 4'hF, 4'b0000);
        end
        repeat (16) @(posedge clk);
        #1;
    end
    endtask

    always @(posedge clk) begin
        if (result_valid && result_ready) begin
            if (nsum[phase] < MAXSUM) begin
                sums[phase][nsum[phase]] = result_sum;
                nsum[phase] = nsum[phase] + 1;
            end
            done_cnt[phase] = done_cnt[phase] + 1;
        end
    end

    always @(posedge clk) begin
        if (!rst && protocol_error) proto_seen[phase] = 1;
    end

    task automatic run_phase(input int p, input [19:0] poison_word);
    begin
        phase = p;
        nsum[p] = 0;
        done_cnt[p] = 0;
        proto_seen[p] = 0;
        strobe_cnt[p] = 0;
        err_after_cfg[p] = 0;
        err_final[p] = 0;
        rst = 1'b1;
        cfg_valid = 1'b0;
        cfg_open = 1'b1;
        issue_valid = 1'b0;
        lane_stall = 1'b0;
        result_ready = 1'b1;
        repeat (3) @(posedge clk);
        #1;
        rst = 1'b0;
        repeat (2) @(posedge clk);
        #1;
        if (p == 2) begin
            wr_addr = poison_addr;
            cfg_write(wr_addr, poison_word);
        end
        for (idx = 0; idx < nlegal; idx = idx + 1) begin
            wr_addr = idx[4:0];
            cfg_write(wr_addr, legal[idx]);
        end
        if (p == 1) begin
            wr_addr = poison_addr;
            cfg_write(wr_addr, poison_word);
        end
        cfg_open = 1'b0;
        @(posedge clk);
        #1;
        err_after_cfg[p] = cfg_error ? 1 : 0;
        run_txn_list();
        if (p == 3) begin
            wr_addr = poison_addr;
            cfg_write(wr_addr, poison_word);
            run_txn_list();
        end
        err_final[p] = cfg_error ? 1 : 0;
        $display("CFGNEG PHASE %0d err_after_cfg=%0d err_final=%0d proto=%0d strobes=%0d sums=%0d done=%0d total=%0d",
                 p, err_after_cfg[p], err_final[p], proto_seen[p],
                 strobe_cnt[p], nsum[p], done_cnt[p], total_s);
    end
    endtask

    // sums[p][start .. start+len-1] 必须与相位 0 的前 len 笔逐笔相同。
    function automatic logic sums_slice_match(input int p, input int start,
                                              input int len);
        int k;
        logic good;
    begin
        good = 1'b1;
        if (len <= 0 || start < 0 || start + len > nsum[p] || len > nsum[0])
            good = 1'b0;
        else begin
            for (k = 0; k < len; k = k + 1)
                if (sums[p][start + k] !== sums[0][k]) good = 1'b0;
        end
        sums_slice_match = good;
    end
    endfunction

    task automatic expect_ok(input string name, input logic cond);
    begin
        checks = checks + 1;
        if (!cond) begin
            failed = failed + 1;
            $display("CFGNEG FAIL check=%s", name);
        end else begin
            $display("CFGNEG CHECK %s PASS", name);
        end
    end
    endtask

    initial begin
        #4000000;
        $display("CFGNEG FAIL watchdog_timeout");
        $display("CFGNEG SUMMARY RESULT=FAIL reason=watchdog");
        $finish;
    end

    initial begin
        failed = 0;
        checks = 0;
        build_stimulus();
        for (idx = 0; idx < NPHASE; idx = idx + 1) nsum[idx] = 0;
        run_phase(0, 20'd0);
        run_phase(1, poison[0]);
        run_phase(2, poison[1]);
        run_phase(3, poison[0]);
        expect_ok("clean_load_no_error", err_after_cfg[0] == 0 && err_final[0] == 0);
        expect_ok("illegal_strobe_only_on_illegal_word", strobe_cnt[1] == 1 && strobe_cnt[2] == 1 && strobe_cnt[0] == 0 && strobe_cnt[3] == 0);
        expect_ok("poison_after_legal_ram_unchanged", sums_slice_match(1, 0, nsum[0]) && nsum[1] == nsum[0]);
        expect_ok("poison_before_legal_ram_unchanged", sums_slice_match(2, 0, nsum[0]) && nsum[2] == nsum[0]);
        expect_ok("runtime_write_rejected", sums_slice_match(3, 0, nsum[0]) && sums_slice_match(3, nsum[0], nsum[0]) && nsum[3] == 2 * nsum[0]);
        expect_ok("error_latched_sticky", err_after_cfg[1] == 1 && err_final[1] == 1 && err_after_cfg[2] == 1 && err_final[2] == 1 && err_after_cfg[3] == 0 && err_final[3] == 1);
        expect_ok("no_protocol_error_any_phase", proto_seen[0] == 0 && proto_seen[1] == 0 && proto_seen[2] == 0 && proto_seen[3] == 0);
        expect_ok("legal_words_still_execute", nsum[1] == nsum[0] && nsum[2] == nsum[0] && nsum[3] == 2 * nsum[0] && done_cnt[1] == nsum[1] && done_cnt[3] == nsum[3]);
        ok_match = (failed == 0);
        if (SPARSE) begin
            if (ok_match) $display("CFGNEG SUMMARY FORMAT=sparse LANES=%0d CHECKS=%0d FAILED=0 RESULT=PASS", LANES, checks);
            else $display("CFGNEG SUMMARY FORMAT=sparse LANES=%0d CHECKS=%0d FAILED=%0d RESULT=FAIL", LANES, checks, failed);
        end else begin
            if (ok_match) $display("CFGNEG SUMMARY FORMAT=dense LANES=%0d CHECKS=%0d FAILED=0 RESULT=PASS", LANES, checks);
            else $display("CFGNEG SUMMARY FORMAT=dense LANES=%0d CHECKS=%0d FAILED=%0d RESULT=FAIL", LANES, checks, failed);
        end
        $finish;
    end
endmodule