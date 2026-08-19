"""Host Bridge XPM CDC wrapper 的双时钟定向回归。"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
IVERILOG = Path(r"C:\msys64\ucrt64\bin\iverilog.exe")
VVP = Path(r"C:\msys64\ucrt64\bin\vvp.exe")


def compile_and_run(testbench: str) -> subprocess.CompletedProcess[str]:
    """用接口等价 FIFO 模型编译并运行一个临时双时钟 testbench。"""
    if not IVERILOG.exists() or not VVP.exists():
        raise RuntimeError("需要 C:/msys64/ucrt64/bin 下的 iverilog 和 vvp")

    with tempfile.TemporaryDirectory(prefix="eneuron_xpm_wrapper_") as temp_dir:
        temp = Path(temp_dir)
        tb_path = temp / "tb.sv"
        sim_path = temp / "tb.vvp"
        tb_path.write_text(testbench, encoding="utf-8")
        compile_result = subprocess.run(
            [
                str(IVERILOG),
                "-g2012",
                "-Wall",
                "-s",
                "tb",
                "-o",
                str(sim_path),
                str(ROOT / "xpm_fifo_async_sim.sv"),
                str(ROOT / "digital_snn_host_bridge.sv"),
                str(tb_path),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if compile_result.returncode != 0:
            raise RuntimeError(
                "iverilog failed:\n"
                f"{compile_result.stdout}\n{compile_result.stderr}"
            )

        env = os.environ.copy()
        env["PATH"] = f"{VVP.parent}{os.pathsep}{env.get('PATH', '')}"
        return subprocess.run(
            [str(VVP), str(sim_path)],
            cwd=temp,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )


COMMON_DECLARATIONS = r"""
    logic host_clk = 1'b0;
    logic tile_clk = 1'b0;
    logic bridge_rst = 1'b1;

    logic host_cmd_valid = 1'b0;
    wire host_cmd_ready;
    logic [127:0] host_cmd_data = '0;
    wire host_rsp_valid;
    logic host_rsp_ready = 1'b0;
    wire [127:0] host_rsp_data;
    wire status_irq;

    wire tile_cmd_valid;
    logic tile_cmd_ready = 1'b0;
    wire [127:0] tile_cmd_data;
    logic tile_rsp_valid = 1'b0;
    wire tile_rsp_ready;
    logic [127:0] tile_rsp_data = '0;

    wire host_rst;
    wire tile_rst;
    wire tile_domain_up;
    wire cmd_wr_rst_busy;
    wire cmd_rd_rst_busy;
    wire rsp_wr_rst_busy;
    wire rsp_rd_rst_busy;

    time last_host_posedge = 0;
    time last_tile_posedge = 0;

    always #10 host_clk = ~host_clk;
    always #7 tile_clk = ~tile_clk;
    always @(posedge host_clk) last_host_posedge = $time;
    always @(posedge tile_clk) last_tile_posedge = $time;

    digital_snn_host_bridge dut (
        .host_clk(host_clk),
        .tile_clk(tile_clk),
        .bridge_rst(bridge_rst),
        .host_cmd_valid(host_cmd_valid),
        .host_cmd_ready(host_cmd_ready),
        .host_cmd_data(host_cmd_data),
        .host_rsp_valid(host_rsp_valid),
        .host_rsp_ready(host_rsp_ready),
        .host_rsp_data(host_rsp_data),
        .status_irq(status_irq),
        .tile_cmd_valid(tile_cmd_valid),
        .tile_cmd_ready(tile_cmd_ready),
        .tile_cmd_data(tile_cmd_data),
        .tile_rsp_valid(tile_rsp_valid),
        .tile_rsp_ready(tile_rsp_ready),
        .tile_rsp_data(tile_rsp_data),
        .host_rst(host_rst),
        .tile_rst(tile_rst),
        .tile_domain_up(tile_domain_up),
        .cmd_wr_rst_busy(cmd_wr_rst_busy),
        .cmd_rd_rst_busy(cmd_rd_rst_busy),
        .rsp_wr_rst_busy(rsp_wr_rst_busy),
        .rsp_rd_rst_busy(rsp_rd_rst_busy)
    );

    always @(host_rst) begin
        if (($time > 0) && ($time != last_host_posedge))
            $fatal(1, "host_rst 未在 host_clk 上升沿变化");
    end

    always @(tile_rst) begin
        if (($time > 0) && ($time != last_tile_posedge))
            $fatal(1, "tile_rst 未在 tile_clk 上升沿变化");
    end
"""


TRANSPORT_TESTBENCH = (
    "`timescale 1ns/1ps\n"
    "module tb;\n"
    + COMMON_DECLARATIONS
    + r"""
    localparam logic [127:0] CMD_BASE = 128'h1000_0000_0000_0000_0000_0000_0000_0000;
    localparam logic [127:0] RSP_BASE = 128'h9000_0000_0000_0000_0000_0000_0000_0000;

    task automatic host_send_command(input logic [127:0] value);
        begin
            @(negedge host_clk);
            host_cmd_data = value;
            host_cmd_valid = 1'b1;
            do @(posedge host_clk); while (!host_cmd_ready);
            @(negedge host_clk);
            host_cmd_valid = 1'b0;
        end
    endtask

    task automatic tile_receive_command(input logic [127:0] expected);
        logic [127:0] observed;
        begin
            @(negedge tile_clk);
            tile_cmd_ready = 1'b1;
            do @(posedge tile_clk); while (!tile_cmd_valid);
            observed = tile_cmd_data;
            if (observed !== expected)
                $fatal(1, "命令乱序: actual=%032h expected=%032h", observed, expected);
            @(negedge tile_clk);
            tile_cmd_ready = 1'b0;
        end
    endtask

    task automatic tile_send_response(input logic [127:0] value);
        begin
            @(negedge tile_clk);
            tile_rsp_data = value;
            tile_rsp_valid = 1'b1;
            do @(posedge tile_clk); while (!tile_rsp_ready);
            @(negedge tile_clk);
            tile_rsp_valid = 1'b0;
        end
    endtask

    task automatic host_receive_response(input logic [127:0] expected);
        logic [127:0] observed;
        begin
            @(negedge host_clk);
            host_rsp_ready = 1'b1;
            do @(posedge host_clk); while (!host_rsp_valid);
            observed = host_rsp_data;
            if (observed !== expected)
                $fatal(1, "响应乱序: actual=%032h expected=%032h", observed, expected);
            @(negedge host_clk);
            host_rsp_ready = 1'b0;
        end
    endtask

    integer i;
    initial begin
        // 上电 hard reset 必须覆盖两个时钟域至少四个上升沿。
        repeat (8) @(posedge host_clk);
        bridge_rst = 1'b0;
        wait (host_cmd_ready && tile_rsp_ready && tile_domain_up);

        // XPM FWFT 的读侧预取槽使本配置可见有效容量为 17。
        for (i = 0; i < 17; i = i + 1)
            host_send_command(CMD_BASE + i);
        @(negedge host_clk);
        if (host_cmd_ready)
            $fatal(1, "命令 FIFO 深度不是 16 或 full 门控失效");

        fork
            begin
                for (i = 17; i < 40; i = i + 1)
                    host_send_command(CMD_BASE + i);
            end
            begin : command_consumer
                integer j;
                repeat (12) @(posedge tile_clk);
                for (j = 0; j < 40; j = j + 1)
                    tile_receive_command(CMD_BASE + j);
            end
        join

        // 响应 FIFO 做镜像测试，覆盖回绕、同时 push/pop 和 Host 长背压。
        for (i = 0; i < 17; i = i + 1)
            tile_send_response(RSP_BASE + i);
        @(negedge tile_clk);
        if (tile_rsp_ready)
            $fatal(1, "响应 FIFO 深度不是 16 或 full 门控失效");

        fork
            begin
                for (i = 17; i < 40; i = i + 1)
                    tile_send_response(RSP_BASE + i);
            end
            begin : response_consumer
                integer j;
                repeat (10) @(posedge host_clk);
                for (j = 0; j < 40; j = j + 1)
                    host_receive_response(RSP_BASE + j);
            end
        join

        if (host_rsp_valid || tile_cmd_valid)
            $fatal(1, "排空后仍报告 valid");
        if (status_irq !== host_rsp_valid)
            $fatal(1, "status_irq 未严格等于 host_rsp_valid");

        // 合法 hard reset 清空两条 FIFO，reset-busy 期间四侧均不得握手。
        wait (!cmd_wr_rst_busy && !rsp_wr_rst_busy);
        #3 bridge_rst = 1'b1;
        repeat (8) @(posedge host_clk);
        if (host_cmd_ready || host_rsp_valid || tile_cmd_valid || tile_rsp_ready)
            $fatal(1, "reset/reset-busy 期间发生握手资格泄漏");
        bridge_rst = 1'b0;
        wait (host_cmd_ready && tile_rsp_ready && tile_domain_up);
        if (host_rsp_valid || tile_cmd_valid)
            $fatal(1, "hard reset 后 FIFO 未清空");

        $display("XPM_WRAPPER_TRANSPORT_PASS");
        $finish;
    end

    initial begin
        #200000;
        $fatal(1, "transport test timeout");
    end
endmodule
"""
)


ILLEGAL_RESET_TESTBENCH = (
    "`timescale 1ns/1ps\n"
    "module tb;\n"
    + COMMON_DECLARATIONS
    + r"""
    initial begin
        repeat (8) @(posedge host_clk);
        bridge_rst = 1'b0;
        wait (host_cmd_ready && tile_rsp_ready && tile_domain_up);
        wait (!cmd_wr_rst_busy && !rsp_wr_rst_busy);

        // 第一次重入合法；在其 reset-busy 尚未退出时再次断言必须报协议错误。
        #3 bridge_rst = 1'b1;
        wait (host_rst && tile_rst);
        #3 bridge_rst = 1'b0;
        #3 bridge_rst = 1'b1;
        #200;
        $fatal(1, "非法 reset 重入未触发断言");
    end
endmodule
"""
)


class HostBridgeXpmWrapperTests(unittest.TestCase):
    def test_xpm_configuration_is_frozen(self) -> None:
        source = (ROOT / "digital_snn_host_bridge.sv").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"xpm_fifo_async\s*#", source)), 2)
        for setting in (
            r"\.FIFO_WRITE_DEPTH\s*\(\s*16\s*\)",
            r"\.WRITE_DATA_WIDTH\s*\(\s*128\s*\)",
            r"\.READ_DATA_WIDTH\s*\(\s*128\s*\)",
            r'\.READ_MODE\s*\(\s*"fwft"\s*\)',
            r"\.FIFO_READ_LATENCY\s*\(\s*0\s*\)",
            r"\.CDC_SYNC_STAGES\s*\(\s*2\s*\)",
        ):
            self.assertEqual(len(re.findall(setting, source)), 2, setting)

    def test_bidirectional_transport_backpressure_wrap_and_reset(self) -> None:
        result = compile_and_run(TRANSPORT_TESTBENCH)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("XPM_WRAPPER_TRANSPORT_PASS", result.stdout)

    def test_illegal_reset_reentry_is_rejected(self) -> None:
        result = compile_and_run(ILLEGAL_RESET_TESTBENCH)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RESET_REENTRY_ERROR", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
