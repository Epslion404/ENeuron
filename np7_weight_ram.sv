// NP7 共享突触权重 RAM（32 字 x 20 bit）。
//
// 冻结合同（NP7.0 决策 3）：权重与稀疏结构只在 CONFIG 阶段写入，运行期严格只读；
// 不存在训练回写端口，因此没有双写仲裁与一致性问题。cfg_open=0 时任何写尝试都会
// 置 cfg_error 并被丢弃（fail-closed）。
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
    output logic        cfg_error,

    input  logic        rd_ce,
    input  logic [4:0]  rd_addr,
    output logic [19:0] rd_q
);
    logic [19:0] mem [0:31];

    // CONFIG 装载期校验：非 OPEN 写入一律拒绝并锁存错误。
    assign cfg_ready = 1'b1;

    always_ff @(posedge clk) begin
        if (rst) begin
            cfg_error <= 1'b0;
        end else begin
            if (cfg_valid) begin
                if (!cfg_open)
                    cfg_error <= 1'b1;
                else
                    mem[cfg_addr] <= cfg_wdata;
            end
        end
    end

    // 同步 RAM 输出：t 拍请求，t+1 拍数据有效（BRAM 原语读延迟）。
    always_ff @(posedge clk) begin
        if (rd_ce)
            rd_q <= mem[rd_addr];
    end

endmodule