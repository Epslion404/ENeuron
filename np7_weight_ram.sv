// NP7 共享突触权重 RAM（32 字 x 20 bit）。
//
// 冻结合同（NP7.0 决策 3）：权重与稀疏结构只在 CONFIG 阶段写入，运行期严格只读；
// 不存在训练回写端口，因此没有双写仲裁与一致性问题。
//
// CONFIG 写入拒绝语义（NP7.0 决策 2 + PR #6 评审意见 2）：写使能在硬件握手处被双重
// 门控——cfg_open=0（不在 CONFIG 阶段）或 cfg_wr_ok=0（上层格式解码器判定内容非法：
// sparse 索引非严格升序 / dense 保留位非零）时，本拍写入被丢弃，mem[] 保持原值，
// 同时置 cfg_error。cfg_error 为锁存语义：一旦置位只由 rst 清除，后续合法写入仍
// 继续被接受，但错误标志不会被清除（错误可见性不被吞掉）。
// cfg_ready 恒为 1：CONFIG 装载口采用"丢弃 + 锁存错误"而非反压握手，装载方必须检查
// cfg_error 决定是否签核；issue_ready 不受 cfg_error 影响，因此单个非法字不会阻塞
// 其余合法字的装载与执行（评审要求"非法字不改变 RAM、合法字仍可执行"）。
//
// 位布局：dense 一组两字，每字 [7:0]=wA、[15:8]=wB、[19:16] 保留必须为 0；
// sparse 一组一字，[7:0]=w0、[15:8]=w1、[17:16]=idx0、[19:18]=idx1，
// 结构掩码只由索引重建，索引必须严格升序（idx1 > idx0）。
module np7_weight_ram (
    input  logic        clk,
    input  logic        rst,

    input  logic        cfg_valid,
    output logic        cfg_ready,
    input  logic [4:0]  cfg_addr,
    input  logic [19:0] cfg_wdata,
    input  logic        cfg_open,
    // 内容由上层格式解码器判定：0 表示该字违反冻结位布局（必须拒绝）。
    input  logic        cfg_wr_ok,
    output logic        cfg_error,

    input  logic        rd_ce,
    input  logic [4:0]  rd_addr,
    output logic [19:0] rd_q
);
    logic [19:0] mem [0:31];

    // CONFIG 装载期校验：非 OPEN 写入与内容非法写入一律阻止并锁存错误。
    assign cfg_ready = 1'b1;
    logic cfg_write_en;
    assign cfg_write_en = cfg_valid && cfg_open && cfg_wr_ok;

    // 错误锁存：任何被阻止的写尝试都置位，且只由 rst 清除。
    always_ff @(posedge clk) begin
        if (rst)
            cfg_error <= 1'b0;
        else if (cfg_valid && !cfg_write_en)
            cfg_error <= 1'b1;
    end

    // 写端口只由 cfg_write_en 选通：非法写入绝不改变 mem[]。
    always_ff @(posedge clk) begin
        if (cfg_write_en)
            mem[cfg_addr] <= cfg_wdata;
    end

    // 同步 RAM 输出：t 拍请求，t+1 拍数据有效（BRAM 原语读延迟）。
    always_ff @(posedge clk) begin
        if (rd_ce)
            rd_q <= mem[rd_addr];
    end

endmodule