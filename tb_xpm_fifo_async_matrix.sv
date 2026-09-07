`timescale 1ns/1ps

// T2 FIFO 独立压力矩阵。本文件只验证 Icarus 等价 FIFO 模型的调用合同；Vivado 使用真实 XPM 时仍需要 T3。
module tb_xpm_fifo_async_matrix #(
    parameter integer NPU_HALF = 7,
    parameter integer NPU_PHASE = 2,
    parameter integer SEED = 1
);
    localparam integer DEPTH = 16;
    localparam integer LOG_DEPTH = 8192;

    logic host_clk = 1'b0;
    logic npu_clk = 1'b0;
    logic rst = 1'b1;
    integer mode = 0;

    always #5 host_clk = ~host_clk;
    initial begin
        #(NPU_PHASE);
        forever #(NPU_HALF) npu_clk = ~npu_clk;
    end

    logic [127:0] cmd_din = '0;
    logic cmd_wr_en = 1'b0;
    wire cmd_full, cmd_empty, cmd_wr_busy, cmd_rd_busy;
    wire [127:0] cmd_dout;
    logic cmd_rd_en = 1'b0;

    logic [127:0] rsp_din = '0;
    logic rsp_wr_en = 1'b0;
    wire rsp_full, rsp_empty, rsp_wr_busy, rsp_rd_busy;
    wire [127:0] rsp_dout;
    logic rsp_rd_en = 1'b0;

    logic [63:0] sample_din = '0;
    logic sample_wr_en = 1'b0;
    wire sample_full, sample_empty, sample_wr_busy, sample_rd_busy;
    wire [63:0] sample_dout;
    logic sample_rd_en = 1'b0;

    logic [95:0] result_din = '0;
    logic result_wr_en = 1'b0;
    wire result_full, result_empty, result_wr_busy, result_rd_busy;
    wire [95:0] result_dout;
    logic result_rd_en = 1'b0;

    logic [127:0] unused_cmd_wr_count, unused_cmd_rd_count;
    logic [127:0] unused_rsp_wr_count, unused_rsp_rd_count;
    logic [127:0] unused_sample_wr_count, unused_sample_rd_count;
    logic [127:0] unused_result_wr_count, unused_result_rd_count;

    xpm_fifo_async #(
        .FIFO_WRITE_DEPTH(DEPTH), .WRITE_DATA_WIDTH(128),
        .READ_DATA_WIDTH(128), .WR_DATA_COUNT_WIDTH(5), .RD_DATA_COUNT_WIDTH(5)
    ) cmd_fifo (
        .sleep(1'b0), .rst(rst), .wr_clk(host_clk), .wr_en(cmd_wr_en), .din(cmd_din),
        .full(cmd_full), .prog_full(), .wr_data_count(), .overflow(), .wr_rst_busy(cmd_wr_busy),
        .almost_full(), .wr_ack(), .rd_clk(npu_clk), .rd_en(cmd_rd_en), .dout(cmd_dout),
        .empty(cmd_empty), .prog_empty(), .rd_data_count(), .underflow(), .rd_rst_busy(cmd_rd_busy),
        .almost_empty(), .data_valid(), .injectsbiterr(1'b0), .injectdbiterr(1'b0), .sbiterr(), .dbiterr()
    );

    xpm_fifo_async #(
        .FIFO_WRITE_DEPTH(DEPTH), .WRITE_DATA_WIDTH(128),
        .READ_DATA_WIDTH(128), .WR_DATA_COUNT_WIDTH(5), .RD_DATA_COUNT_WIDTH(5)
    ) rsp_fifo (
        .sleep(1'b0), .rst(rst), .wr_clk(npu_clk), .wr_en(rsp_wr_en), .din(rsp_din),
        .full(rsp_full), .prog_full(), .wr_data_count(), .overflow(), .wr_rst_busy(rsp_wr_busy),
        .almost_full(), .wr_ack(), .rd_clk(host_clk), .rd_en(rsp_rd_en), .dout(rsp_dout),
        .empty(rsp_empty), .prog_empty(), .rd_data_count(), .underflow(), .rd_rst_busy(rsp_rd_busy),
        .almost_empty(), .data_valid(), .injectsbiterr(1'b0), .injectdbiterr(1'b0), .sbiterr(), .dbiterr()
    );

    xpm_fifo_async #(
        .FIFO_WRITE_DEPTH(DEPTH), .WRITE_DATA_WIDTH(64),
        .READ_DATA_WIDTH(64), .WR_DATA_COUNT_WIDTH(5), .RD_DATA_COUNT_WIDTH(5)
    ) sample_fifo (
        .sleep(1'b0), .rst(rst), .wr_clk(host_clk), .wr_en(sample_wr_en), .din(sample_din),
        .full(sample_full), .prog_full(), .wr_data_count(), .overflow(), .wr_rst_busy(sample_wr_busy),
        .almost_full(), .wr_ack(), .rd_clk(npu_clk), .rd_en(sample_rd_en), .dout(sample_dout),
        .empty(sample_empty), .prog_empty(), .rd_data_count(), .underflow(), .rd_rst_busy(sample_rd_busy),
        .almost_empty(), .data_valid(), .injectsbiterr(1'b0), .injectdbiterr(1'b0), .sbiterr(), .dbiterr()
    );

    xpm_fifo_async #(
        .FIFO_WRITE_DEPTH(DEPTH), .WRITE_DATA_WIDTH(96),
        .READ_DATA_WIDTH(96), .WR_DATA_COUNT_WIDTH(5), .RD_DATA_COUNT_WIDTH(5)
    ) result_fifo (
        .sleep(1'b0), .rst(rst), .wr_clk(npu_clk), .wr_en(result_wr_en), .din(result_din),
        .full(result_full), .prog_full(), .wr_data_count(), .overflow(), .wr_rst_busy(result_wr_busy),
        .almost_full(), .wr_ack(), .rd_clk(host_clk), .rd_en(result_rd_en), .dout(result_dout),
        .empty(result_empty), .prog_empty(), .rd_data_count(), .underflow(), .rd_rst_busy(result_rd_busy),
        .almost_empty(), .data_valid(), .injectsbiterr(1'b0), .injectdbiterr(1'b0), .sbiterr(), .dbiterr()
    );

    function automatic [31:0] next_lfsr(input [31:0] value);
        next_lfsr = {value[30:0], value[31] ^ value[21] ^ value[1] ^ value[0]};
    endfunction

    function automatic choose_write(input integer current_mode, input [31:0] value);
        begin
            case (current_mode)
                1: choose_write = 1'b1; // 填满
                2: choose_write = 1'b0; // 排空
                3: choose_write = value[0] | value[3];
                4: choose_write = value[1] | value[5];
                default: choose_write = 1'b0;
            endcase
        end
    endfunction

    function automatic choose_read(input integer current_mode, input [31:0] value);
        begin
            case (current_mode)
                1: choose_read = 1'b0;
                2: choose_read = 1'b1; // 排空
                3: choose_read = value[2] | value[6];
                4: choose_read = value[2] | value[7];
                default: choose_read = 1'b0;
            endcase
        end
    endfunction

    logic [31:0] cmd_lfsr, sample_lfsr, rsp_lfsr, result_lfsr;
    integer cmd_wr_count, cmd_rd_count, sample_wr_count, sample_rd_count;
    integer rsp_wr_count, rsp_rd_count, result_wr_count, result_rd_count;
    logic [127:0] cmd_wr_log [0:LOG_DEPTH-1];
    logic [127:0] cmd_rd_log [0:LOG_DEPTH-1];
    logic [127:0] rsp_wr_log [0:LOG_DEPTH-1];
    logic [127:0] rsp_rd_log [0:LOG_DEPTH-1];
    logic [63:0] sample_wr_log [0:LOG_DEPTH-1];
    logic [63:0] sample_rd_log [0:LOG_DEPTH-1];
    logic [95:0] result_wr_log [0:LOG_DEPTH-1];
    logic [95:0] result_rd_log [0:LOG_DEPTH-1];

    integer cmd_wr_seq, sample_wr_seq, rsp_wr_seq, result_wr_seq;

    // Host domain drives command/sample writes and response/result reads.
    always @(posedge host_clk) begin
        if (rst) begin
            cmd_wr_en <= 1'b0;
            sample_wr_en <= 1'b0;
            rsp_rd_en <= 1'b0;
            result_rd_en <= 1'b0;
            cmd_din <= '0;
            sample_din <= '0;
            cmd_lfsr <= 32'h1 ^ SEED;
            sample_lfsr <= 32'h9e3779b9 ^ SEED;
            cmd_wr_count <= 0;
            cmd_rd_count <= 0;
            sample_wr_count <= 0;
            sample_rd_count <= 0;
            cmd_wr_seq <= 0;
            sample_wr_seq <= 0;
        end else begin
            cmd_lfsr <= next_lfsr(cmd_lfsr);
            sample_lfsr <= next_lfsr(sample_lfsr);
            cmd_wr_en <= choose_write(mode, cmd_lfsr);
            sample_wr_en <= choose_write(mode, sample_lfsr);
            rsp_rd_en <= choose_read(mode, cmd_lfsr);
            result_rd_en <= choose_read(mode, sample_lfsr);
            cmd_din <= {32'hc0de0001, cmd_wr_seq[31:0], cmd_lfsr, 32'h00000001};
            sample_din <= {32'hc0de0002, sample_wr_seq[31:0]};
            if (cmd_wr_en && !cmd_full && !cmd_wr_busy) begin
                cmd_wr_log[cmd_wr_count] <= cmd_din;
                cmd_wr_count <= cmd_wr_count + 1;
                cmd_wr_seq <= cmd_wr_seq + 1;
            end
            if (sample_wr_en && !sample_full && !sample_wr_busy) begin
                sample_wr_log[sample_wr_count] <= sample_din;
                sample_wr_count <= sample_wr_count + 1;
                sample_wr_seq <= sample_wr_seq + 1;
            end
            if (rsp_rd_en && !rsp_empty && !rsp_rd_busy) begin
                rsp_rd_log[rsp_rd_count] <= rsp_dout;
                rsp_rd_count <= rsp_rd_count + 1;
            end
            if (result_rd_en && !result_empty && !result_rd_busy) begin
                result_rd_log[result_rd_count] <= result_dout;
                result_rd_count <= result_rd_count + 1;
            end
        end
    end

    // NPU domain drives response/result writes and command/sample reads.
    always @(posedge npu_clk) begin
        if (rst) begin
            rsp_wr_en <= 1'b0;
            result_wr_en <= 1'b0;
            cmd_rd_en <= 1'b0;
            sample_rd_en <= 1'b0;
            rsp_din <= '0;
            result_din <= '0;
            rsp_lfsr <= 32'h243f6a88 ^ SEED;
            result_lfsr <= 32'hb7e15162 ^ SEED;
            rsp_wr_count <= 0;
            rsp_rd_count <= 0;
            result_wr_count <= 0;
            result_rd_count <= 0;
            rsp_wr_seq <= 0;
            result_wr_seq <= 0;
        end else begin
            rsp_lfsr <= next_lfsr(rsp_lfsr);
            result_lfsr <= next_lfsr(result_lfsr);
            rsp_wr_en <= choose_write(mode, rsp_lfsr);
            result_wr_en <= choose_write(mode, result_lfsr);
            cmd_rd_en <= choose_read(mode, rsp_lfsr);
            sample_rd_en <= choose_read(mode, result_lfsr);
            rsp_din <= {32'hc0de0003, rsp_wr_seq[31:0], rsp_lfsr, 32'h00000003};
            result_din <= {32'hc0de0004, result_wr_seq[31:0], result_lfsr};
            if (rsp_wr_en && !rsp_full && !rsp_wr_busy) begin
                rsp_wr_log[rsp_wr_count] <= rsp_din;
                rsp_wr_count <= rsp_wr_count + 1;
                rsp_wr_seq <= rsp_wr_seq + 1;
            end
            if (result_wr_en && !result_full && !result_wr_busy) begin
                result_wr_log[result_wr_count] <= result_din;
                result_wr_count <= result_wr_count + 1;
                result_wr_seq <= result_wr_seq + 1;
            end
            if (cmd_rd_en && !cmd_empty && !cmd_rd_busy) begin
                cmd_rd_log[cmd_rd_count] <= cmd_dout;
                cmd_rd_count <= cmd_rd_count + 1;
            end
            if (sample_rd_en && !sample_empty && !sample_rd_busy) begin
                sample_rd_log[sample_rd_count] <= sample_dout;
                sample_rd_count <= sample_rd_count + 1;
            end
        end
    end

    integer i;
    task automatic compare_channel(input integer wr_count, input integer rd_count,
                                   input integer width, input integer channel);
        begin
            if (wr_count != rd_count)
                $fatal(1, "FIFO channel %0d count mismatch write=%0d read=%0d", channel, wr_count, rd_count);
            for (i = 0; i < wr_count; i = i + 1) begin
                case (channel)
                    0: if (cmd_wr_log[i] !== cmd_rd_log[i])
                           $fatal(1, "FIFO channel 0 order mismatch at %0d", i);
                    1: if (rsp_wr_log[i] !== rsp_rd_log[i])
                           $fatal(1, "FIFO channel 1 order mismatch at %0d", i);
                    2: if (sample_wr_log[i] !== sample_rd_log[i])
                           $fatal(1, "FIFO channel 2 order mismatch at %0d", i);
                    3: if (result_wr_log[i] !== result_rd_log[i])
                           $fatal(1, "FIFO channel 3 order mismatch at %0d", i);
                    default: $fatal(1, "invalid FIFO channel");
                endcase
            end
        end
    endtask

    initial begin
        // 初始复位后先填满再排空，随后随机读写和长背压，最后重复一次复位边界。
        repeat (20) @(posedge host_clk);
        rst = 1'b0;
        mode = 1;
        repeat (80) @(posedge host_clk);
        mode = 2;
        repeat (120) @(posedge host_clk);
        mode = 3;
        repeat (700) @(posedge host_clk);
        mode = 4;
        repeat (700) @(posedge host_clk);
        mode = 2;
        repeat (500) @(posedge host_clk);

        rst = 1'b1;
        repeat (28) @(posedge host_clk);
        mode = 0;
        rst = 1'b0;
        repeat (45) @(posedge host_clk);
        mode = 1;
        repeat (70) @(posedge host_clk);
        mode = 2;
        repeat (130) @(posedge host_clk);
        mode = 3;
        repeat (650) @(posedge host_clk);
        mode = 4;
        repeat (650) @(posedge host_clk);
        mode = 2;
        repeat (500) @(posedge host_clk);

        compare_channel(cmd_wr_count, cmd_rd_count, 128, 0);
        compare_channel(rsp_wr_count, rsp_rd_count, 128, 1);
        compare_channel(sample_wr_count, sample_rd_count, 64, 2);
        compare_channel(result_wr_count, result_rd_count, 96, 3);
        $display("T2_FIFO_MATRIX_PASS NPU_HALF=%0d NPU_PHASE=%0d SEED=%0d CMD=%0d RSP=%0d SAMPLE=%0d RESULT=%0d",
                 NPU_HALF, NPU_PHASE, SEED, cmd_wr_count, rsp_wr_count, sample_wr_count, result_wr_count);
        $finish;
    end
endmodule
