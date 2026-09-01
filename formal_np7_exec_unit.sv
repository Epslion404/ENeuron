// NP7.5 共享突触执行单元的有限深度形式检查工装（不进入综合路径）。
//
// 检查目标（TODO §5 NP7.5）：
//   P1 单槽协议：一个事务完成前不得再次接受执行请求；
//   P2 恰好一次完成：每个接受事务产生且只产生一次 done，空闲时不得有未完成事务；
//   P3 地址边界：读请求地址必须落在 RAM 深度内且与本组一致；
//   P4 无重复发射：同一事务内同一位置的 lane 槽位不得被发射两次，
//      且 lane_fire_count 必须等于当拍 batch_mask 的置位数（LANES=1 时恰为一位）；
//   P5 零突触快速路径：issue_mask=0 的事务不发 RAM 请求、不发 lane 操作，
//      仍在 2 拍内完成一个事务；
//   P6 计数守恒：busy = 读请求 + lane 操作；权重槽 = 2 x 读请求；
//      完成数 = 读请求 + 零路径；total = busy + stall + 3x非零 + 2x零；
//   P7 上游门控一致性：由记录索引重建掩码并取与活动掩码时，执行单元自检
//      永不过滤（protocol_error/cfg_error/cfg_illegal_index 恒 0）。
//
// 形式模型对握手取"无反压"假设（lane_stall=0、result_ready=1），把状态空间
// 让给协议与账本不变式；随机背压下的逐拍等价的覆盖由 NP7.3 的 160000 事务
// 协同仿真提供，两者互补，不互相替代。
module formal_np7_exec_unit(input logic clk);
    localparam int LANES = 1;

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

    // 形式输入：任意但合法的一组位模式（索引严格升序），组号固定为 0。
    // 三个形式输入都由复位拍装载 + 非复位拍重新取任意值（yosys $anyseq），
    // 不用 (* anyseq *) 属性：属性变量再被 always_ff 驱动会与 -set-init-zero 冲突。
    logic [19:0] record_word;
    logic        request_now;
    logic [3:0]  activity;

    wire [1:0] idx0 = record_word[17:16];
    wire [1:0] idx1 = record_word[19:18];
    wire [3:0] struct_mask = (4'b1 << idx0) | (4'b1 << idx1);
    wire [3:0] gate_mask = struct_mask & activity;
    wire [2:0] skip_bits = ((activity & ~struct_mask & 4'b0001) != 4'b0)
                         + ((activity & ~struct_mask & 4'b0010) != 4'b0)
                         + ((activity & ~struct_mask & 4'b0100) != 4'b0)
                         + ((activity & ~struct_mask & 4'b1000) != 4'b0);

    logic [2:0] phase;
    logic       past_valid;

    assign rst = !past_valid;
    assign cfg_open = (phase < 3'd3);
    assign cfg_valid = (phase == 3'd2);
    assign cfg_addr = 5'd0;
    assign cfg_wdata = record_word;
    assign issue_group = 4'd0;
    assign issue_activity = activity;
    assign issue_mask = gate_mask;
    assign issue_skip_count = skip_bits;
    assign issue_valid = request_now && (phase >= 3'd3);
    assign lane_stall = 1'b0;
    assign result_ready = 1'b1;

    // 影子状态：单槽协议、重复发射与零路径观测。
    logic        outstanding;
    logic        txn_zero;
    logic [3:0]  fired;
    logic [3:0]  txn_mask;
    logic [3:0]  txn_read_cycles;
    logic [3:0]  txn_fire_cycles;
    logic [4:0]  txn_cycles;

    wire done_now = result_valid && result_ready;
    wire [2:0] batch_mask_bits = ((batch_mask & 4'b0001) != 4'b0)
                         + ((batch_mask & 4'b0010) != 4'b0)
                         + ((batch_mask & 4'b0100) != 4'b0)
                         + ((batch_mask & 4'b1000) != 4'b0);

    always_ff @(posedge clk) begin
        if (!past_valid) begin
            // 复位拍不得 assume 输入位模式：-set-init-zero 已把被 always_ff 驱动的
            // anyseq 变量钉成 0，此时 assume(idx1 > idx0) 会让假设集不可满足，
            // 整个证明退化为空真（NP7.5 首轮就是这样漏掉的，已用可达性检查抓到）。
            // 复位拍先把符号输入装载为任意值，非复位拍的 assume 才有可满足的取值空间。
            record_word <= $anyseq;
            assume(phase == 3'd0);
            assume(!outstanding);
            assume(!protocol_error);
            past_valid <= 1'b1;
            outstanding <= 1'b0;
            txn_zero <= 1'b0;
            fired <= 4'd0;
            txn_read_cycles <= 4'd0;
            txn_fire_cycles <= 4'd0;
            txn_cycles <= 5'd0;
            phase <= 3'd1;
        end else begin
            // record_word 保持复位拍装载的符号常量，与 RAM 中的配置同源；
            // 逐拍自由会让工装侧 issue_mask 与被测件从 RAM 解码出的掩码不一致，
            // 从而虚假触发 protocol_error。activity/request_now 逐拍自由。
            assume(record_word[19:18] > record_word[17:16]);
            activity <= $anyseq;
            request_now <= $anyseq;
            phase <= phase + 3'd1;

            // P1 单槽协议
            assert(!(accept_pulse && outstanding));
            // P2 恰好一次完成
            assert(!(done_now && !outstanding));
            assert(!(issue_ready && outstanding));
            // P3 地址边界
            assert(!ram_ce || {1'b0, ram_addr} < 6'd32);
            assert(!ram_ce || ram_addr == {1'b0, issue_group});
            // P4 无重复发射、发射宽度自洽
            assert(lane_fire_count == 3'd0 || batch_mask != 4'd0);
            if (lane_fire_count != 3'd0)
                assert({1'b0, batch_mask_bits} == lane_fire_count);
            assert(!(lane_fire_count != 3'd0 && (batch_mask & fired) != 4'd0));
            assert(!(lane_fire_count != 3'd0 && (batch_mask & ~txn_mask) != 4'd0));
            if (done_now && !txn_zero)
                assert(fired == txn_mask);
            // P5 零路径静默
            assert(!(outstanding && txn_zero && ram_ce));
            assert(!(outstanding && txn_zero && lane_fire_count != 3'd0));
            // P7 上游门控一致性
            assert(!protocol_error);
            assert(!cfg_error);
            assert(!cfg_illegal_index);
            // P6 计数守恒（空闲且未启动新事务的那一拍检查）
            if (issue_ready && !accept_pulse && past_valid) begin
                assert(busy_cycles_state
                       == group_read_requests_state + lane_ops_issued_state);
                assert(weight_values_fetched_state
                       == (group_read_requests_state << 1));
                assert(completed_groups_state
                       == group_read_requests_state + zero_fast_paths_state);
                assert(total_cycles_state == busy_cycles_state + stall_cycles_state
                       + (completed_groups_state - zero_fast_paths_state) * 3
                       + zero_fast_paths_state * 2);
                assert(stall_cycles_state == 32'd0);
            end

            if (accept_pulse) begin
                assert(!outstanding);
                outstanding <= 1'b1;
                txn_zero <= (issue_mask == 4'd0);
                fired <= 4'd0;
                txn_mask <= issue_mask;
                txn_read_cycles <= 4'd0;
                txn_fire_cycles <= 4'd0;
                txn_cycles <= 5'd1;
            end else if (outstanding) begin
                txn_cycles <= txn_cycles + 5'd1;
                if (ram_ce)
                    txn_read_cycles <= txn_read_cycles + 4'd1;
                if (lane_fire_count != 3'd0) begin
                    txn_fire_cycles <= txn_fire_cycles + 4'd1;
                    fired <= fired | batch_mask;
                end
                if (done_now) begin
                    outstanding <= 1'b0;
                    fired <= 4'd0;
                    // P5/P1 周期合同：零路径 2 拍；非零 = 3 + 读拍 + 发射拍
                    if (txn_zero)
                        assert(txn_cycles + 5'd1 == 5'd2);
                    else
                        assert(txn_cycles + 5'd1 == 5'd3 + {1'b0, txn_read_cycles}
                                                 + {1'b0, txn_fire_cycles});
                    assert(!ram_ce || !txn_zero);
                end
            end
        end
    end
endmodule

// 稠密顶层的同类检查：四个槽位全读，只检查单槽协议、地址边界与计数守恒。
module formal_np7_exec_unit_dense(input logic clk);
    localparam int LANES = 1;

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

    // 权重字：复位拍装载一次的符号常量；activity/request_now：逐拍自由。
    logic [19:0] word_low;
    logic [19:0] word_high;
    logic        request_now;
    logic [3:0]  activity;

    logic [2:0] phase;
    logic       past_valid;
    logic       outstanding;
    logic [3:0] fired;
    logic [3:0] txn_mask;
    logic       txn_zero;
    logic [3:0] txn_read_cycles;
    logic [3:0] txn_fire_cycles;
    logic [4:0] txn_cycles;

    wire [3:0] gate_mask = activity;
    wire done_now = result_valid && result_ready;

    assign rst = !past_valid;
    assign cfg_open = (phase < 3'd4);
    assign cfg_valid = (phase == 3'd2) || (phase == 3'd3);
    assign cfg_addr = (phase == 3'd2) ? 5'd0 : 5'd1;
    assign cfg_wdata = (phase == 3'd2) ? {4'b0, word_low[15:0]}
                                       : {4'b0, word_high[15:0]};
    assign issue_group = 4'd0;
    assign issue_activity = activity;
    assign issue_mask = gate_mask;
    assign issue_skip_count = 3'd0;
    assign issue_valid = request_now && (phase >= 3'd4);
    assign lane_stall = 1'b0;
    assign result_ready = 1'b1;

    always_ff @(posedge clk) begin
        if (!past_valid) begin
            word_low <= $anyseq;
            word_high <= $anyseq;
            assume(phase == 3'd0);
            assume(!outstanding);
            past_valid <= 1'b1;
            outstanding <= 1'b0;
            txn_zero <= 1'b0;
            fired <= 4'd0;
            txn_read_cycles <= 4'd0;
            txn_fire_cycles <= 4'd0;
            txn_cycles <= 5'd0;
            phase <= 3'd1;
        end else begin
            phase <= phase + 3'd1;
            activity <= $anyseq;
            request_now <= $anyseq;
            assert(!(accept_pulse && outstanding));
            assert(!(done_now && !outstanding));
            assert(!(issue_ready && outstanding));
            assert(!ram_ce || {1'b0, ram_addr} < 6'd32);
            // P3-prime: dense may only read the two words of the accepted group
            assert(!ram_ce || ram_addr == {issue_group, 1'b0}
                              || ram_addr == {issue_group, 1'b1});
            assert(lane_fire_count == 3'd0 || batch_mask != 4'd0);
            assert(!(lane_fire_count != 3'd0 && (batch_mask & fired) != 4'd0));
            assert(!(lane_fire_count != 3'd0 && (batch_mask & ~txn_mask) != 4'd0));
            if (done_now && !txn_zero)
                assert(fired == txn_mask);
            assert(!protocol_error);
            assert(!cfg_error);
            if (issue_ready && !accept_pulse) begin
                assert(weight_values_fetched_state
                       == (group_read_requests_state << 1));
                assert(completed_groups_state
                       == group_read_requests_state / 2 + zero_fast_paths_state);
                assert(busy_cycles_state
                       == group_read_requests_state + lane_ops_issued_state);
                assert(total_cycles_state == busy_cycles_state
                       + stall_cycles_state
                       + (completed_groups_state - zero_fast_paths_state) * 3
                       + zero_fast_paths_state * 2);
                assert(input_zero_groups_state == zero_fast_paths_state);
                // 工装无反压假设：lane_stall=0 且 result_ready=1
                assert(stall_cycles_state == 32'd0);
            end
            if (accept_pulse) begin
                outstanding <= 1'b1;
                txn_zero <= (issue_mask == 4'd0);
                fired <= 4'd0;
                txn_mask <= issue_mask;
                txn_read_cycles <= 4'd0;
                txn_fire_cycles <= 4'd0;
                txn_cycles <= 5'd1;
            end else if (done_now) begin
                outstanding <= 1'b0;
                fired <= 4'd0;
                // P5: zero path completes in 2 cycles; non-zero = accept + reads + latency
                //     + fire + done.  The shadow counter excludes the done cycle.
                if (txn_zero)
                    assert(txn_cycles + 5'd1 == 5'd2);
                else
                    assert(txn_cycles + 5'd1 == 5'd3 + {1'b0, txn_read_cycles}
                                             + {1'b0, txn_fire_cycles});
                assert(!ram_ce || !txn_zero);
            end else if (outstanding) begin
                txn_cycles <= txn_cycles + 5'd1;
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