// NP7 CONFIG 拒绝语义的有限深度形式检查工装（PR #6 评审意见 2，不进入综合路径）。
//
// 被检对象是 np7_weight_ram 的硬件写握手，逐拍时间表（phase 为本拍寄存器值）：
//   1  装载合法字 legal_word            -> 3  读回必须等于 legal_word（合法路径可用）
//   4  内容非法写尝试（cfg_wr_ok=0）     -> 5  cfg_error 必须已锁存
//                                       -> 6  读回仍等于 legal_word（非法字未进 RAM）
//   7  错误锁存后再装合法字 legal_word2  -> 9  读回等于 legal_word2 且 cfg_error 仍为 1
//  10  运行期写尝试（cfg_open=0）        -> 11 cfg_error 仍为 1
//                                       -> 12 读回仍等于 legal_word2（运行期写被丢弃）
// 覆盖的合同：C1 非法内容写入被阻止、C2 错误锁存只由 rst 清除（sticky）、
// C3 合法字在错误之后仍可装载执行、C4 运行期严格只读、C5 cfg_ready 恒 1（不反压）。
//
// cfg_wr_ok 由工装自由驱动：本件证明的是 RAM 侧握手语义；"格式非法位模式确实映射为
// cfg_wr_ok=0"由 np7_exec_unit_sparse/dense 的单行组合解码 + tb_np7_config_negative.sv
// + 拒绝旁路 mutation 三件事共同封住。
//
// 符号量在复位拍用 $anyseq 装载、之后保持不变，等价于 $anyconst 口径
// （与 formal_np7_exec_unit.sv 同一手法，避开 (* anyconst *) 与 -set-init-zero 冲突）。
module formal_np7_config_reject(input logic clk);
    logic        rst;
    logic        cfg_valid;
    logic        cfg_ready;
    logic [4:0]  cfg_addr;
    logic [19:0] cfg_wdata;
    logic        cfg_open;
    logic        cfg_wr_ok;
    logic        cfg_error;
    logic        rd_ce;
    logic [4:0]  rd_addr;
    logic [19:0] rd_q;

    np7_weight_ram dut (.*);

    logic [19:0] legal_word;
    logic [19:0] legal_word2;
    logic [19:0] poison_word;
    logic [19:0] poison_word2;
    logic [4:0]  target_addr;
    logic [3:0]  phase;
    logic        past_valid;
    logic        err_prev;

    assign rst = !past_valid;

    always_comb begin
        cfg_valid = 1'b0;
        cfg_open = 1'b0;
        cfg_addr = target_addr;
        cfg_wdata = 20'd0;
        cfg_wr_ok = 1'b1;
        rd_ce = 1'b0;
        rd_addr = target_addr;
        if (past_valid) begin
            unique case (phase)
                4'd1: begin cfg_open = 1'b1; cfg_valid = 1'b1; cfg_wdata = legal_word; end
                4'd2: begin cfg_open = 1'b1; rd_ce = 1'b1; end
                4'd4: begin cfg_open = 1'b1; cfg_valid = 1'b1; cfg_wr_ok = 1'b0;
                          cfg_wdata = poison_word; end
                4'd5: rd_ce = 1'b1;
                4'd7: begin cfg_open = 1'b1; cfg_valid = 1'b1; cfg_wdata = legal_word2; end
                4'd8: begin cfg_open = 1'b1; rd_ce = 1'b1; end
                4'd10: begin cfg_open = 1'b0; cfg_valid = 1'b1; cfg_wdata = poison_word2; end
                4'd11: rd_ce = 1'b1;
                default: ;
            endcase
        end
    end

    always_ff @(posedge clk) begin
        if (!past_valid) begin
            legal_word <= $anyseq;
            legal_word2 <= $anyseq;
            poison_word <= $anyseq;
            poison_word2 <= $anyseq;
            target_addr <= $anyseq;
            assume(phase == 4'd0);
            past_valid <= 1'b1;
            err_prev <= 1'b0;
            phase <= 4'd1;
        end else begin
            assume(legal_word !== poison_word);
            assume(legal_word2 !== legal_word);
            assume(legal_word !== poison_word2);
            assume(legal_word2 !== poison_word2);
            err_prev <= cfg_error;
            // C5 CONFIG 口不反压
            assert(cfg_ready);
            // C2 锁存语义：错误一旦置位，非复位拍不得自行消失
            if (err_prev) assert(cfg_error);
            if (phase == 4'd1) assert(!cfg_error);
            // 合法装载路径
            if (phase == 4'd3) assert(rd_q === legal_word);
            // C1 非法内容写入不改变 RAM
            if (phase == 4'd5) assert(cfg_error);
            if (phase == 4'd6) assert(rd_q === legal_word);
            // C3 错误锁存后合法字仍可装载、执行
            if (phase == 4'd9) begin
                assert(rd_q === legal_word2);
                assert(cfg_error);
            end
            // C4 运行期写尝试被丢弃
            if (phase == 4'd11) assert(cfg_error);
            if (phase == 4'd12) assert(rd_q === legal_word2);
            if (phase < 4'd13) phase <= phase + 4'd1;
        end
    end
endmodule