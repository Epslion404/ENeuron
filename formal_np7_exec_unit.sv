// NP7.5 共享突触执行单元的有限深度形式检查工装（不进入综合路径）。
//
// 检查目标（PR #6 评论 5498372499 裁定 B-V1+V2 后新增/改写的性质）：
//   P1 单槽协议：任意时刻最多一个未退出结果；只有旧结果退出的同一边沿才可接受下一
//      事务（V2），结果背压时必须停止接收；
//   P2 恰好一次完成：每个 accept 恰好一个 result（accept/retire 计数最多差 1）；
//   P3 地址边界：读请求地址必须落在 RAM 深度内且与本组一致；
//   P4 无重复发射：同一事务内同一位置的 lane 槽位不得发射两次；
//   P5 V1 零路径：issue_mask=0 不发 RAM 请求、不发 lane 操作，result_ready=1 时
//      accept 与 result 同一边沿完成，result_ready=0 时锁存不丢；
//   P6 逐拍账本恒等式：total = busy + latency + lane_stall + backpressure
//      + hold_retire + zero + accept_own，且所有自报计数器与影子逐拍分类一致；
//   P7 上游门控一致性：protocol_error/cfg_error/cfg_illegal_index 恒 0；
//   P8 背压稳定性：锁存期间 result_valid/result_sum/result_zero_path 逐拍保持；
//   P9 同拍元数据分离：retire 与 accept 同边沿时退出的结果属于上一事务；
//   P11 lane 一拍流水时序：result_valid 只来自 HOLD/DRAIN 折叠拍/V1 零路径，
//       最后一批发射后的下一拍恰好是 S_DRAIN（正好晚 1 拍，见 P1 裁定）。
 //   P10 lane_stall 不提前完成：被挡住的 BATCH 拍不得给出结果，也不得接受下一事务。
//
// 与上一轮的差别：形式输入不再假设"无反压"，lane_stall 与 result_ready 逐拍自由，
// 因为背压稳定性与同拍不覆盖正是本轮裁定要求证明的性质；影子账本按 B-V1+V2 的
// 互斥类别逐拍重建，用来证明新恒等式而不是旧的 +DONE 口径。
`timescale 1ns/1ps

module formal_np7_exec_unit(input logic clk);
    localparam int LANES = 1;
    localparam logic [3:0] READS_PER_TXN = 4'd1;   // sparse：每非零事务 1 次组读
    localparam logic [31:0] VALS_PER_LAT = 32'd2;   // sparse：一次读 2 个权重槽
    localparam logic [3:0] CFG_OPEN_LAST = 4'd3;     // sparse：1 个 CONFIG 写拍

    logic        rst;
    logic        cfg_valid;
    logic        cfg_ready;
    logic [4:0]  cfg_addr;
    logic [19:0] cfg_wdata;
    logic        cfg_open;
    logic        cfg_error;
    logic        issue_valid;
    logic        issue_ready;
    logic [3:0]  issue_group;
    logic [3:0]  issue_activity;
    logic [3:0]  issue_mask;
    logic [2:0]  issue_skip_count;
    logic        lane_stall;
    logic        result_valid;
    logic        result_ready;
    logic signed [11:0] result_sum;
    logic        result_zero_path;
    logic        ram_ce;
    logic [4:0]  ram_addr;
    logic [3:0]  batch_mask;
    logic [2:0]  lane_fire_count;
    logic [2:0]  state_code;
    logic        accept_pulse;
    logic [31:0] group_read_requests_state;
    logic [31:0] weight_values_fetched_state;
    logic [31:0] lane_ops_issued_state;
    logic [31:0] zero_fast_paths_state;
    logic [31:0] busy_cycles_state;
    logic [31:0] stall_cycles_state;
    logic [31:0] completed_groups_state;
    logic [31:0] structural_skips_state;
    logic [31:0] input_zero_groups_state;
    logic [31:0] activity_zero_after_structure_state;
    logic [31:0] saturation_events_state;
    logic [31:0] total_cycles_state;
    logic        cfg_illegal_index;
    logic        protocol_error;

    np7_exec_unit_sparse #(.LANES(LANES)) dut (.*);

    // 形式输入：位模式是复位拍装载一次的符号常量；activity/request/背压逐拍自由。
    logic [19:0] record_word;

    wire [1:0] idx0 = record_word[17:16];
    wire [1:0] idx1 = record_word[19:18];
    wire signed [7:0] w0 = $signed(record_word[7:0]);
    wire signed [7:0] w1 = $signed(record_word[15:8]);
    wire [3:0] struct_mask = (4'b1 << idx0) | (4'b1 << idx1);
    wire [3:0] gate_mask = struct_mask & activity;
    wire [2:0] skip_bits = ((activity & ~struct_mask & 4'b0001) != 4'b0)
                         + ((activity & ~struct_mask & 4'b0010) != 4'b0)
                         + ((activity & ~struct_mask & 4'b0100) != 4'b0)
                         + ((activity & ~struct_mask & 4'b1000) != 4'b0);

    logic [3:0] phase;
    logic       past_valid;
    logic       request_now;
    logic [3:0] activity;
    logic       stall_seq;
    logic       ready_seq;

    // ---- 影子状态：单槽协议、逐拍类别与背压锁存的可观测模型 ----
    logic        outstanding;
    logic        txn_zero;
    logic [3:0]  txn_mask;
    logic [3:0]  fired;
    logic [3:0]  txn_read_cycles;
    logic [3:0]  txn_fire_cycles;
    logic        prev_bp;
    logic signed [11:0] prev_sum;
    logic        prev_zero_flag;
    // V1/V2 关键路径可达性见证（供 reach/zero witness 使用，防止"空真通过"）：
    //   saw_zero_single  V1 单拍零路径（accept 与 result 同一边沿）
    //   saw_zero_hold    V1 零路径遇到结果背压 -> 锁存进 S_HOLD
    //   saw_fold         V2 旧结果退出与下一事务接受同一边沿
    //   saw_backpressure 结果背压保持拍（S_HOLD 且 result_ready=0）
    //   saw_lane_stall   lane_stall 挡住 BATCH 的拍
    // P11（P1 流水时序）影子：上一拍是否发射了本事务的最后一批
    logic       prev_last_fire;
    logic        saw_zero_single;
    logic        saw_zero_hold;
    logic        saw_fold;
    logic        saw_backpressure;
    logic        saw_lane_stall;
    logic [31:0] s_total, s_busy, s_stall, s_lat, s_lstall, s_bp, s_hr, s_zero;
    logic [31:0] s_own, s_accepts, s_retires, s_reads, s_ops, s_vals, s_zero_paths;

    assign rst = !past_valid;
    assign cfg_open = (phase < CFG_OPEN_LAST);
    assign cfg_valid = (phase == 4'd2);
    assign cfg_addr = 5'd0;
    assign cfg_wdata = record_word;
    assign issue_group = 4'd0;
    assign issue_activity = activity;
    assign issue_mask = gate_mask;
    assign issue_skip_count = skip_bits;
    assign issue_valid = request_now && (phase >= 4'd3);
    assign lane_stall = stall_seq && (phase >= 4'd3);
    assign result_ready = ready_seq;

    wire done_now = result_valid && result_ready;
    // 退出边沿上被比较的事务掩码：已接受未退出的是旧事务，冷启动当拍的是新事务。
    wire [3:0] sum_mask = outstanding ? txn_mask : issue_mask;
    wire [2:0] mask_bits = ((sum_mask & 4'b0001) != 4'b0)
                        + ((sum_mask & 4'b0010) != 4'b0)
                        + ((sum_mask & 4'b0100) != 4'b0)
                        + ((sum_mask & 4'b1000) != 4'b0);
    wire [2:0] batch_mask_bits = ((batch_mask & 4'b0001) != 4'b0)
                        + ((batch_mask & 4'b0010) != 4'b0)
                        + ((batch_mask & 4'b0100) != 4'b0)
                        + ((batch_mask & 4'b1000) != 4'b0);
    // 逐拍互斥类别，优先级与 oracle/RTL 完全一致：
    //   RAM > LANE > LAT > LANE_STALL > BACKPRESSURE > HOLD_RETIRE > ZERO > ACCEPT
    // 最后一批的锁存边沿归入 LANE（busy），只有已锁存进 HOLD 且 result_ready=0
    // 的保持拍才算 BACKPRESSURE。
    wire raw_bp = result_valid && !result_ready;
    wire e_ram = ram_ce;
    wire e_lane = (lane_fire_count != 3'd0);
    // P1 周期合同（PR #6 裁定 5085536010）：新增 state_code=6 即 S_DRAIN，lane 的
    // Stage B 在该拍折叠最后一批。折叠拍归 LAT 类（latency_cycles），被 lane_stall
    // 停住的折叠拍归 LANE_STALL 类；但权重读取仍只发生在真正的 S_LAT 拍，所以把两件事
    // 拆成 e_lat_val（权重口径）与 e_lat（账本分类口径），与 RTL 逐拍计数器一一对应。
    wire hold_st = (state_code == 3'd5);
    wire drain_st = (state_code == 3'd6);
    wire e_lat_val = (state_code == 3'd3);
    wire e_lat = e_lat_val || (drain_st && !lane_stall);
    wire e_lstall = ((state_code == 3'd4) || drain_st) && lane_stall;
    wire e_bp = (state_code == 3'd5) && raw_bp;
    wire e_hr = (state_code == 3'd5) && result_valid && result_ready;
    wire e_zero = accept_pulse && (issue_mask == 4'd0) && done_now
                  && (state_code == 3'd0);
    wire e_own = accept_pulse && !e_zero && !done_now;
    // 旧结果已退出、且本拍接受的零路径事务同拍完成 -> 该事务不留下在途结果。
    wire v1_single_done = accept_pulse && !outstanding && done_now
                          && (issue_mask == 4'd0);
    // P11：本拍发射的批次是否覆盖掉事务剩下的全部槽位（= 最后一批发射拍）
    wire last_fire_now = e_lane && outstanding
                         && ((fired | batch_mask) == txn_mask);
    wire e_active = e_ram || e_lane || e_lat || e_lstall || e_bp || e_hr
                    || e_zero || e_own;

    // 期望突触和：至多 4 x 127 = 508，12 bit 饱和路径不会触发，可解析比较。
    logic signed [11:0] expect_sum;
    always_comb begin
        expect_sum = 12'sd0;
        if ((sum_mask & 4'b0001) != 4'b0) expect_sum = expect_sum + ((idx0 == 2'd0) ? w0 : (idx1 == 2'd0) ? w1 : 8'sd0);
        if ((sum_mask & 4'b0010) != 4'b0) expect_sum = expect_sum + ((idx0 == 2'd1) ? w0 : (idx1 == 2'd1) ? w1 : 8'sd0);
        if ((sum_mask & 4'b0100) != 4'b0) expect_sum = expect_sum + ((idx0 == 2'd2) ? w0 : (idx1 == 2'd2) ? w1 : 8'sd0);
        if ((sum_mask & 4'b1000) != 4'b0) expect_sum = expect_sum + ((idx0 == 2'd3) ? w0 : (idx1 == 2'd3) ? w1 : 8'sd0);
    end

    always_ff @(posedge clk) begin
        if (!past_valid) begin
            // 复位拍不得 assume 输入位模式：-set-init-zero 会把被 always_ff 驱动的
            // anyseq 钉成 0，此时 assume 会让假设集不可满足（NP7.5 首轮空真教训）。
            record_word <= $anyseq;
            assume(phase == 4'd0);
            assume(!outstanding);
            assume(!protocol_error);
            past_valid <= 1'b1;
            outstanding <= 1'b0;
            txn_zero <= 1'b0;
            txn_mask <= 4'd0;
            fired <= 4'd0;
            txn_read_cycles <= 4'd0;
            txn_fire_cycles <= 4'd0;
            prev_bp <= 1'b0;
            prev_sum <= 12'sd0;
            prev_zero_flag <= 1'b0;
            prev_last_fire <= 1'b0;
            s_total <= 32'd0; s_busy <= 32'd0; s_stall <= 32'd0; s_lat <= 32'd0;
            s_lstall <= 32'd0; s_bp <= 32'd0; s_hr <= 32'd0; s_zero <= 32'd0;
            s_own <= 32'd0; s_accepts <= 32'd0; s_retires <= 32'd0;
            s_reads <= 32'd0; s_ops <= 32'd0; s_zero_paths <= 32'd0;
            s_vals <= 32'd0;
            saw_zero_single <= 1'b0; saw_zero_hold <= 1'b0; saw_fold <= 1'b0;
            saw_backpressure <= 1'b0; saw_lane_stall <= 1'b0;
            phase <= 4'd1;
        end else begin
            assume(record_word[19:18] > record_word[17:16]);
            activity <= $anyseq;
            request_now <= $anyseq;
            stall_seq <= $anyseq;
            ready_seq <= $anyseq;
            if (phase != 4'd15) phase <= phase + 4'd1;

            // P1 单槽协议：任意时刻最多一个未退出结果；只有在旧结果退出的同一边沿
            //     才允许接受下一事务（V2），结果背压时必须停止接收。
            assert(!(accept_pulse && outstanding && !done_now));
            assert(!(raw_bp && accept_pulse));
            // P2 恰好一次完成：不会凭空退出（V1 零路径的退出与 accept 同拍，
            //     此时影子 outstanding 尚未置位，属于合法的单拍完成）。
            assert(!(done_now && !outstanding && !accept_pulse));
            assert(s_accepts == s_retires || s_accepts == s_retires + 32'd1);
            // P3 地址边界
            assert(!ram_ce || {1'b0, ram_addr} < 6'd32);
            assert(!ram_ce || ram_addr == {1'b0, issue_group});
            // P4 无重复发射、发射宽度自洽
            assert(lane_fire_count == 3'd0 || batch_mask != 4'd0);
            if (lane_fire_count != 3'd0)
                assert({1'b0, batch_mask_bits} == lane_fire_count);
            assert(!(lane_fire_count != 3'd0 && (batch_mask & fired) != 4'd0));
            assert(!(lane_fire_count != 3'd0 && (batch_mask & ~txn_mask) != 4'd0));
            // P5 V1 零路径静默：不发 RAM 请求、不发 lane 操作，仍当拍给出 0 结果。
            assert(!(outstanding && txn_zero && ram_ce));
            assert(!(outstanding && txn_zero && lane_fire_count != 3'd0));
            if (accept_pulse && (issue_mask == 4'd0) && !outstanding) begin
                assert(!ram_ce);
                assert(lane_fire_count == 3'd0);
                if (result_ready) begin
                    assert(result_valid);
                    assert(result_zero_path);
                    assert(result_sum == 12'sd0);
                end else begin
                    assert(!done_now);
                end
            end
            // P8 背压锁存稳定性：result_valid 且 result_ready=0 时结果必须原样保持。
            if (prev_bp) begin
                assert(result_valid);
                assert(result_sum == prev_sum);
                assert(result_zero_path == prev_zero_flag);
            end
            // P9 同拍 retire/accept 的元数据分离：退出的结果必须属于上一事务，
            //     新接受的 issue_mask/零标志不得污染本拍的 result_*。
            if (done_now)
                assert(result_sum == expect_sum);
            if (done_now && accept_pulse && outstanding)
                assert(result_zero_path == txn_zero);
            // P10 lane_stall 挡住的 BATCH 拍：不提前完成、不提前接受。
            if (e_lstall) begin
                assert(!done_now);
                assert(!result_valid);
                assert(!accept_pulse);
            end
            // P11 lane 一拍流水的时序合同（PR #6 裁定 5085536010 §一第 3 项）：
            //   (a) result_valid 只可能来自 S_HOLD、S_DRAIN 折叠拍或 V1 零路径；
            //   (b) 最后一批发射后的『下一拍』恰好落在 S_DRAIN（不迟不早，正好 1 拍）；
            //   (c) S_DRAIN 的非 stall 拍一定给出 result_valid（配合 P10 的反向保证）。
            if (result_valid)
                assert(hold_st || (drain_st && !lane_stall) || e_zero);
            if (prev_last_fire)
                assert(state_code == 3'd6);
            if (drain_st && !lane_stall) begin
                assert(result_valid);
                assert(!accept_pulse || done_now);
            end
            // P7 上游门控一致性
            assert(!protocol_error);
            assert(!cfg_error);
            assert(!cfg_illegal_index);
            // P6 逐拍账本恒等式（与 np7_ledger_reconstruction.py 的 B-V1+V2 同源）：
            //     自报计数器必须与影子逐拍分类完全一致，旧 DONE 拍口径不再出现。
            assert(group_read_requests_state == s_reads);
            assert(lane_ops_issued_state == s_ops);
            assert(weight_values_fetched_state == s_vals);
            assert(zero_fast_paths_state == s_zero_paths);
            assert(completed_groups_state == s_retires);
            assert(busy_cycles_state == s_busy);
            assert(stall_cycles_state == s_stall);
            assert(s_stall == s_lstall + s_bp);
            assert(s_total == s_busy + s_lat + s_lstall + s_bp + s_hr + s_zero
                           + s_own);
            assert(total_cycles_state == s_total);
            if (issue_ready && !accept_pulse && !outstanding) begin
                // 空闲且无在途结果时：权重槽 = 2x 读请求；接受数 = 退出数；
                // 完成数 = 读事务数 + 零路径数（每非零事务占 READS_PER_TXN 次读，
                // sparse 为 1、dense 为 2，因此用 READS_PER_TXN 归一而不是直接相等）。
                assert(s_vals == (s_reads << 1));
                assert(s_accepts == s_retires);
                assert({28'd0, READS_PER_TXN} * completed_groups_state
                       == group_read_requests_state
                       + {28'd0, READS_PER_TXN} * zero_fast_paths_state);
            end

            if (phase >= 4'd3) begin
                s_accepts <= s_accepts + {31'd0, accept_pulse};
                s_retires <= s_retires + {31'd0, done_now};
                s_reads <= s_reads + {31'd0, e_ram};
                s_vals <= s_vals + (e_lat_val ? VALS_PER_LAT : 32'd0);
                s_ops <= s_ops + {29'd0, lane_fire_count};
                s_zero_paths <= s_zero_paths + {31'd0,
                              (accept_pulse && (issue_mask == 4'd0))};
                s_busy <= s_busy + {31'd0, (e_ram || e_lane)};
                s_lat <= s_lat + {31'd0, e_lat};
                s_lstall <= s_lstall + {31'd0, e_lstall};
                s_stall <= s_stall + {31'd0, (e_lstall || e_bp)};
                s_bp <= s_bp + {31'd0, e_bp};
                s_hr <= s_hr + {31'd0, e_hr};
                s_zero <= s_zero + {31'd0, e_zero};
                s_own <= s_own + {31'd0, e_own};
                s_total <= s_total + {31'd0, e_active};
                // 见证标志：只在正式流水期（phase>=3）累计，与 s_* 计数器同步。
                saw_zero_single <= saw_zero_single || e_zero;
                saw_zero_hold <= saw_zero_hold || (accept_pulse
                        && (issue_mask == 4'd0) && !outstanding && !result_ready);
                saw_fold <= saw_fold || (done_now && accept_pulse && outstanding);
                saw_backpressure <= saw_backpressure || e_bp;
                saw_lane_stall <= saw_lane_stall || e_lstall;
                // 见证标志必须与对应计数器一致（这些性质同时保证标志本身
                // 不会被优化掉，reachable/witness 检查才有意义）。
                assert(!(saw_fold && !(s_retires > 32'd0)));
                assert(!(saw_zero_single && !(s_zero > 32'd0)));
                assert(!(saw_zero_hold && !(s_zero_paths > 32'd0)));
                assert(!(saw_backpressure && !(s_bp > 32'd0)));
                assert(!(saw_lane_stall && !(s_lstall > 32'd0)));
            end
            prev_last_fire <= last_fire_now;
            prev_bp <= raw_bp;
            prev_sum <= result_sum;
            prev_zero_flag <= result_zero_path;
            // 先收尾旧事务，再登记新事务：V2 的折叠边沿两侧都要更新。
            if (done_now) begin
                assert(outstanding || accept_pulse);
                if (outstanding) begin
                    // 退出的是上一个事务：按它的影子逐拍账本核对读/lane 覆盖。
                    if (!txn_zero) begin
                        assert(txn_read_cycles == READS_PER_TXN);
                        assert(txn_fire_cycles + {3'd0, e_lane} == mask_bits);
                        assert((fired | (e_lane ? batch_mask : 4'd0)) == txn_mask);
                    end
                end else begin
                    // V1 单拍零路径：退出结果属于本拍刚接受的事务，因此必须是
                    // issue_mask=0 的零结果，非零事务不可能在 accept 同拍完成。
                    assert(accept_pulse);
                    assert(issue_mask == 4'd0);
                    assert(result_zero_path);
                    assert(result_sum == 12'sd0);
                end
                fired <= 4'd0;
                outstanding <= 1'b0;
            end
            if (accept_pulse) begin
                assert(!outstanding || done_now);
                // V1：零路径事务可以在 accept 的同一边沿完成退出，此时它从来不是
                //     "未退出结果"，影子不得把它记成 outstanding（否则 P1 会误报）。
                outstanding <= !v1_single_done;
                txn_zero <= (issue_mask == 4'd0) && !v1_single_done;
                txn_mask <= issue_mask;
                fired <= 4'd0;
                txn_read_cycles <= 4'd0;
                txn_fire_cycles <= 4'd0;
            end else if (outstanding) begin
                if (ram_ce)
                    txn_read_cycles <= txn_read_cycles + 4'd1;
                if (lane_fire_count != 3'd0) begin
                    txn_fire_cycles <= txn_fire_cycles + 4'd1;
                    fired <= fired | batch_mask;
                end
            end
        end
    end
endmodule

module formal_np7_exec_unit_dense(input logic clk);
    localparam int LANES = 1;
    localparam logic [3:0] READS_PER_TXN = 4'd2;   // dense：每非零事务 2 次组读
    localparam logic [31:0] VALS_PER_LAT = 32'd4;   // dense：LAT 拍一次入账 4 个权重槽
    localparam logic [3:0] CFG_OPEN_LAST = 4'd4;     // dense：2 个 CONFIG 写拍

    logic        rst;
    logic        cfg_valid;
    logic        cfg_ready;
    logic [4:0]  cfg_addr;
    logic [19:0] cfg_wdata;
    logic        cfg_open;
    logic        cfg_error;
    logic        issue_valid;
    logic        issue_ready;
    logic [3:0]  issue_group;
    logic [3:0]  issue_activity;
    logic [3:0]  issue_mask;
    logic [2:0]  issue_skip_count;
    logic        lane_stall;
    logic        result_valid;
    logic        result_ready;
    logic signed [11:0] result_sum;
    logic        result_zero_path;
    logic        ram_ce;
    logic [4:0]  ram_addr;
    logic [3:0]  batch_mask;
    logic [2:0]  lane_fire_count;
    logic [2:0]  state_code;
    logic        accept_pulse;
    logic [31:0] group_read_requests_state;
    logic [31:0] weight_values_fetched_state;
    logic [31:0] lane_ops_issued_state;
    logic [31:0] zero_fast_paths_state;
    logic [31:0] busy_cycles_state;
    logic [31:0] stall_cycles_state;
    logic [31:0] completed_groups_state;
    logic [31:0] structural_skips_state;
    logic [31:0] input_zero_groups_state;
    logic [31:0] activity_zero_after_structure_state;
    logic [31:0] saturation_events_state;
    logic [31:0] total_cycles_state;
    logic        cfg_illegal_index;
    logic        protocol_error;

    np7_exec_unit_dense #(.LANES(LANES)) dut (.*);

    // 形式输入：位模式是复位拍装载一次的符号常量；activity/request/背压逐拍自由。
    logic [19:0] word_low;
    logic [19:0] word_high;

    wire signed [7:0] w0 = $signed(word_low[7:0]);
    wire signed [7:0] w1 = $signed(word_low[15:8]);
    wire signed [7:0] w2 = $signed(word_high[7:0]);
    wire signed [7:0] w3 = $signed(word_high[15:8]);
    wire [3:0] gate_mask = activity;
    wire [2:0] skip_bits = 3'd0;

    logic [3:0] phase;
    logic       past_valid;
    logic       request_now;
    logic [3:0] activity;
    logic       stall_seq;
    logic       ready_seq;

    // ---- 影子状态：单槽协议、逐拍类别与背压锁存的可观测模型 ----
    logic        outstanding;
    logic        txn_zero;
    logic [3:0]  txn_mask;
    logic [3:0]  fired;
    logic [3:0]  txn_read_cycles;
    logic [3:0]  txn_fire_cycles;
    logic        prev_bp;
    logic signed [11:0] prev_sum;
    logic        prev_zero_flag;
    // V1/V2 关键路径可达性见证（供 reach/zero witness 使用，防止"空真通过"）：
    //   saw_zero_single  V1 单拍零路径（accept 与 result 同一边沿）
    //   saw_zero_hold    V1 零路径遇到结果背压 -> 锁存进 S_HOLD
    //   saw_fold         V2 旧结果退出与下一事务接受同一边沿
    //   saw_backpressure 结果背压保持拍（S_HOLD 且 result_ready=0）
    //   saw_lane_stall   lane_stall 挡住 BATCH 的拍
    // P11（P1 流水时序）影子：上一拍是否发射了本事务的最后一批
    logic       prev_last_fire;
    logic        saw_zero_single;
    logic        saw_zero_hold;
    logic        saw_fold;
    logic        saw_backpressure;
    logic        saw_lane_stall;
    logic [31:0] s_total, s_busy, s_stall, s_lat, s_lstall, s_bp, s_hr, s_zero;
    logic [31:0] s_own, s_accepts, s_retires, s_reads, s_ops, s_vals, s_zero_paths;

    assign rst = !past_valid;
    assign cfg_open = (phase < CFG_OPEN_LAST);
    assign cfg_valid = ((phase == 4'd2) || (phase == 4'd3));
    assign cfg_addr = ((phase == 4'd2) ? 5'd0 : 5'd1);
    assign cfg_wdata = ((phase == 4'd2) ? {4'b0, word_low[15:0]} : {4'b0, word_high[15:0]});
    assign issue_group = 4'd0;
    assign issue_activity = activity;
    assign issue_mask = gate_mask;
    assign issue_skip_count = skip_bits;
    assign issue_valid = request_now && (phase >= 4'd3);
    assign lane_stall = stall_seq && (phase >= 4'd3);
    assign result_ready = ready_seq;

    wire done_now = result_valid && result_ready;
    // 退出边沿上被比较的事务掩码：已接受未退出的是旧事务，冷启动当拍的是新事务。
    wire [3:0] sum_mask = outstanding ? txn_mask : issue_mask;
    wire [2:0] mask_bits = ((sum_mask & 4'b0001) != 4'b0)
                        + ((sum_mask & 4'b0010) != 4'b0)
                        + ((sum_mask & 4'b0100) != 4'b0)
                        + ((sum_mask & 4'b1000) != 4'b0);
    wire [2:0] batch_mask_bits = ((batch_mask & 4'b0001) != 4'b0)
                        + ((batch_mask & 4'b0010) != 4'b0)
                        + ((batch_mask & 4'b0100) != 4'b0)
                        + ((batch_mask & 4'b1000) != 4'b0);
    // 逐拍互斥类别，优先级与 oracle/RTL 完全一致：
    //   RAM > LANE > LAT > LANE_STALL > BACKPRESSURE > HOLD_RETIRE > ZERO > ACCEPT
    // 最后一批的锁存边沿归入 LANE（busy），只有已锁存进 HOLD 且 result_ready=0
    // 的保持拍才算 BACKPRESSURE。
    wire raw_bp = result_valid && !result_ready;
    wire e_ram = ram_ce;
    wire e_lane = (lane_fire_count != 3'd0);
    // P1 周期合同（PR #6 裁定 5085536010）：新增 state_code=6 即 S_DRAIN，lane 的
    // Stage B 在该拍折叠最后一批。折叠拍归 LAT 类（latency_cycles），被 lane_stall
    // 停住的折叠拍归 LANE_STALL 类；但权重读取仍只发生在真正的 S_LAT 拍，所以把两件事
    // 拆成 e_lat_val（权重口径）与 e_lat（账本分类口径），与 RTL 逐拍计数器一一对应。
    wire hold_st = (state_code == 3'd5);
    wire drain_st = (state_code == 3'd6);
    wire e_lat_val = (state_code == 3'd3);
    wire e_lat = e_lat_val || (drain_st && !lane_stall);
    wire e_lstall = ((state_code == 3'd4) || drain_st) && lane_stall;
    wire e_bp = (state_code == 3'd5) && raw_bp;
    wire e_hr = (state_code == 3'd5) && result_valid && result_ready;
    wire e_zero = accept_pulse && (issue_mask == 4'd0) && done_now
                  && (state_code == 3'd0);
    wire e_own = accept_pulse && !e_zero && !done_now;
    // 旧结果已退出、且本拍接受的零路径事务同拍完成 -> 该事务不留下在途结果。
    wire v1_single_done = accept_pulse && !outstanding && done_now
                          && (issue_mask == 4'd0);
    // P11：本拍发射的批次是否覆盖掉事务剩下的全部槽位（= 最后一批发射拍）
    wire last_fire_now = e_lane && outstanding
                         && ((fired | batch_mask) == txn_mask);
    wire e_active = e_ram || e_lane || e_lat || e_lstall || e_bp || e_hr
                    || e_zero || e_own;

    // 期望突触和：至多 4 x 127 = 508，12 bit 饱和路径不会触发，可解析比较。
    logic signed [11:0] expect_sum;
    always_comb begin
        expect_sum = 12'sd0;
        if ((sum_mask & 4'b0001) != 4'b0) expect_sum = expect_sum + w0;
        if ((sum_mask & 4'b0010) != 4'b0) expect_sum = expect_sum + w1;
        if ((sum_mask & 4'b0100) != 4'b0) expect_sum = expect_sum + w2;
        if ((sum_mask & 4'b1000) != 4'b0) expect_sum = expect_sum + w3;
    end

    always_ff @(posedge clk) begin
        if (!past_valid) begin
            // 复位拍不得 assume 输入位模式：-set-init-zero 会把被 always_ff 驱动的
            // anyseq 钉成 0，此时 assume 会让假设集不可满足（NP7.5 首轮空真教训）。
            word_low <= $anyseq;
            word_high <= $anyseq;
            assume(phase == 4'd0);
            assume(!outstanding);
            assume(!protocol_error);
            past_valid <= 1'b1;
            outstanding <= 1'b0;
            txn_zero <= 1'b0;
            txn_mask <= 4'd0;
            fired <= 4'd0;
            txn_read_cycles <= 4'd0;
            txn_fire_cycles <= 4'd0;
            prev_bp <= 1'b0;
            prev_sum <= 12'sd0;
            prev_zero_flag <= 1'b0;
            prev_last_fire <= 1'b0;
            s_total <= 32'd0; s_busy <= 32'd0; s_stall <= 32'd0; s_lat <= 32'd0;
            s_lstall <= 32'd0; s_bp <= 32'd0; s_hr <= 32'd0; s_zero <= 32'd0;
            s_own <= 32'd0; s_accepts <= 32'd0; s_retires <= 32'd0;
            s_reads <= 32'd0; s_ops <= 32'd0; s_zero_paths <= 32'd0;
            s_vals <= 32'd0;
            saw_zero_single <= 1'b0; saw_zero_hold <= 1'b0; saw_fold <= 1'b0;
            saw_backpressure <= 1'b0; saw_lane_stall <= 1'b0;
            phase <= 4'd1;
        end else begin

            activity <= $anyseq;
            request_now <= $anyseq;
            stall_seq <= $anyseq;
            ready_seq <= $anyseq;
            if (phase != 4'd15) phase <= phase + 4'd1;

            // P1 单槽协议：任意时刻最多一个未退出结果；只有在旧结果退出的同一边沿
            //     才允许接受下一事务（V2），结果背压时必须停止接收。
            assert(!(accept_pulse && outstanding && !done_now));
            assert(!(raw_bp && accept_pulse));
            // P2 恰好一次完成：不会凭空退出（V1 零路径的退出与 accept 同拍，
            //     此时影子 outstanding 尚未置位，属于合法的单拍完成）。
            assert(!(done_now && !outstanding && !accept_pulse));
            assert(s_accepts == s_retires || s_accepts == s_retires + 32'd1);
            // P3 地址边界
            assert(!ram_ce || {1'b0, ram_addr} < 6'd32);
            assert(!ram_ce || (ram_addr == {issue_group, 1'b0} || ram_addr == {issue_group, 1'b1}));
            // P4 无重复发射、发射宽度自洽
            assert(lane_fire_count == 3'd0 || batch_mask != 4'd0);
            if (lane_fire_count != 3'd0)
                assert({1'b0, batch_mask_bits} == lane_fire_count);
            assert(!(lane_fire_count != 3'd0 && (batch_mask & fired) != 4'd0));
            assert(!(lane_fire_count != 3'd0 && (batch_mask & ~txn_mask) != 4'd0));
            // P5 V1 零路径静默：不发 RAM 请求、不发 lane 操作，仍当拍给出 0 结果。
            assert(!(outstanding && txn_zero && ram_ce));
            assert(!(outstanding && txn_zero && lane_fire_count != 3'd0));
            if (accept_pulse && (issue_mask == 4'd0) && !outstanding) begin
                assert(!ram_ce);
                assert(lane_fire_count == 3'd0);
                if (result_ready) begin
                    assert(result_valid);
                    assert(result_zero_path);
                    assert(result_sum == 12'sd0);
                end else begin
                    assert(!done_now);
                end
            end
            // P8 背压锁存稳定性：result_valid 且 result_ready=0 时结果必须原样保持。
            if (prev_bp) begin
                assert(result_valid);
                assert(result_sum == prev_sum);
                assert(result_zero_path == prev_zero_flag);
            end
            // P9 同拍 retire/accept 的元数据分离：退出的结果必须属于上一事务，
            //     新接受的 issue_mask/零标志不得污染本拍的 result_*。
            if (done_now)
                assert(result_sum == expect_sum);
            if (done_now && accept_pulse && outstanding)
                assert(result_zero_path == txn_zero);
            // P10 lane_stall 挡住的 BATCH 拍：不提前完成、不提前接受。
            if (e_lstall) begin
                assert(!done_now);
                assert(!result_valid);
                assert(!accept_pulse);
            end
            // P11 lane 一拍流水的时序合同（PR #6 裁定 5085536010 §一第 3 项）：
            //   (a) result_valid 只可能来自 S_HOLD、S_DRAIN 折叠拍或 V1 零路径；
            //   (b) 最后一批发射后的『下一拍』恰好落在 S_DRAIN（不迟不早，正好 1 拍）；
            //   (c) S_DRAIN 的非 stall 拍一定给出 result_valid（配合 P10 的反向保证）。
            if (result_valid)
                assert(hold_st || (drain_st && !lane_stall) || e_zero);
            if (prev_last_fire)
                assert(state_code == 3'd6);
            if (drain_st && !lane_stall) begin
                assert(result_valid);
                assert(!accept_pulse || done_now);
            end
            // P7 上游门控一致性
            assert(!protocol_error);
            assert(!cfg_error);
            assert(!cfg_illegal_index);
            // P6 逐拍账本恒等式（与 np7_ledger_reconstruction.py 的 B-V1+V2 同源）：
            //     自报计数器必须与影子逐拍分类完全一致，旧 DONE 拍口径不再出现。
            assert(group_read_requests_state == s_reads);
            assert(lane_ops_issued_state == s_ops);
            assert(weight_values_fetched_state == s_vals);
            assert(zero_fast_paths_state == s_zero_paths);
            assert(completed_groups_state == s_retires);
            assert(busy_cycles_state == s_busy);
            assert(stall_cycles_state == s_stall);
            assert(s_stall == s_lstall + s_bp);
            assert(s_total == s_busy + s_lat + s_lstall + s_bp + s_hr + s_zero
                           + s_own);
            assert(total_cycles_state == s_total);
            if (issue_ready && !accept_pulse && !outstanding) begin
                // 空闲且无在途结果时：权重槽 = 2x 读请求；接受数 = 退出数；
                // 完成数 = 读事务数 + 零路径数（每非零事务占 READS_PER_TXN 次读，
                // sparse 为 1、dense 为 2，因此用 READS_PER_TXN 归一而不是直接相等）。
                assert(s_vals == (s_reads << 1));
                assert(s_accepts == s_retires);
                assert({28'd0, READS_PER_TXN} * completed_groups_state
                       == group_read_requests_state
                       + {28'd0, READS_PER_TXN} * zero_fast_paths_state);
            end

            if (phase >= 4'd3) begin
                s_accepts <= s_accepts + {31'd0, accept_pulse};
                s_retires <= s_retires + {31'd0, done_now};
                s_reads <= s_reads + {31'd0, e_ram};
                s_vals <= s_vals + (e_lat_val ? VALS_PER_LAT : 32'd0);
                s_ops <= s_ops + {29'd0, lane_fire_count};
                s_zero_paths <= s_zero_paths + {31'd0,
                              (accept_pulse && (issue_mask == 4'd0))};
                s_busy <= s_busy + {31'd0, (e_ram || e_lane)};
                s_lat <= s_lat + {31'd0, e_lat};
                s_lstall <= s_lstall + {31'd0, e_lstall};
                s_stall <= s_stall + {31'd0, (e_lstall || e_bp)};
                s_bp <= s_bp + {31'd0, e_bp};
                s_hr <= s_hr + {31'd0, e_hr};
                s_zero <= s_zero + {31'd0, e_zero};
                s_own <= s_own + {31'd0, e_own};
                s_total <= s_total + {31'd0, e_active};
                // 见证标志：只在正式流水期（phase>=3）累计，与 s_* 计数器同步。
                saw_zero_single <= saw_zero_single || e_zero;
                saw_zero_hold <= saw_zero_hold || (accept_pulse
                        && (issue_mask == 4'd0) && !outstanding && !result_ready);
                saw_fold <= saw_fold || (done_now && accept_pulse && outstanding);
                saw_backpressure <= saw_backpressure || e_bp;
                saw_lane_stall <= saw_lane_stall || e_lstall;
                // 见证标志必须与对应计数器一致（这些性质同时保证标志本身
                // 不会被优化掉，reachable/witness 检查才有意义）。
                assert(!(saw_fold && !(s_retires > 32'd0)));
                assert(!(saw_zero_single && !(s_zero > 32'd0)));
                assert(!(saw_zero_hold && !(s_zero_paths > 32'd0)));
                assert(!(saw_backpressure && !(s_bp > 32'd0)));
                assert(!(saw_lane_stall && !(s_lstall > 32'd0)));
            end
            prev_last_fire <= last_fire_now;
            prev_bp <= raw_bp;
            prev_sum <= result_sum;
            prev_zero_flag <= result_zero_path;
            // 先收尾旧事务，再登记新事务：V2 的折叠边沿两侧都要更新。
            if (done_now) begin
                assert(outstanding || accept_pulse);
                if (outstanding) begin
                    // 退出的是上一个事务：按它的影子逐拍账本核对读/lane 覆盖。
                    if (!txn_zero) begin
                        assert(txn_read_cycles == READS_PER_TXN);
                        assert(txn_fire_cycles + {3'd0, e_lane} == mask_bits);
                        assert((fired | (e_lane ? batch_mask : 4'd0)) == txn_mask);
                    end
                end else begin
                    // V1 单拍零路径：退出结果属于本拍刚接受的事务，因此必须是
                    // issue_mask=0 的零结果，非零事务不可能在 accept 同拍完成。
                    assert(accept_pulse);
                    assert(issue_mask == 4'd0);
                    assert(result_zero_path);
                    assert(result_sum == 12'sd0);
                end
                fired <= 4'd0;
                outstanding <= 1'b0;
            end
            if (accept_pulse) begin
                assert(!outstanding || done_now);
                // V1：零路径事务可以在 accept 的同一边沿完成退出，此时它从来不是
                //     "未退出结果"，影子不得把它记成 outstanding（否则 P1 会误报）。
                outstanding <= !v1_single_done;
                txn_zero <= (issue_mask == 4'd0) && !v1_single_done;
                txn_mask <= issue_mask;
                fired <= 4'd0;
                txn_read_cycles <= 4'd0;
                txn_fire_cycles <= 4'd0;
            end else if (outstanding) begin
                if (ram_ce)
                    txn_read_cycles <= txn_read_cycles + 4'd1;
                if (lane_fire_count != 3'd0) begin
                    txn_fire_cycles <= txn_fire_cycles + 4'd1;
                    fired <= fired | batch_mask;
                end
            end
        end
    end
endmodule
