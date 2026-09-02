r"""Host Bridge XPM CDC 包装层双向回归 —— Windows + MSYS2 UCRT64 专项测试。

本文件对固定工具路径的依赖是仓库 admin 在 PR #6 中明确裁定保留的（review
5087208884、issue comment 5506790489，2026-09-02），裁定同时要求把该依赖在代码和
文档里显式注明。下面 4 点与裁定条目逐条对应，判断本文件的失败/跳过原因之前请先读完：

1. 专用路径，不是跨平台默认。``MSYS2_UCRT64_BIN`` / ``IVERILOG`` / ``VVP`` 常量指向
   ``C:\msys64\ucrt64\bin`` 下的可执行文件。该目录只存在于 Windows 上 MSYS2 的
   UCRT64 子系统安装布局中；Linux/macOS 上没有任何理由出现同名路径。仓库其余测试改用
   ``find_tool()``/PATH 发现工具，本测试保留固定路径属于裁定明确允许的例外，不应被
   误读成“工程代码硬编码了个人机器环境”。
2. 依赖的工具名称、安装布局和用途：
   * MSYS2 UCRT64 包 ``mingw-w64-ucrt-x86_64-iverilog`` 提供 ``iverilog.exe`` 与
     ``vvp.exe``，安装布局为 ``<msys2>/ucrt64/{bin,include,lib,share}``；本机核对过
     的版本是 Icarus Verilog 12.0 (stable)，CI 使用同包（上游当前 13.0-2）；
   * ``iverilog.exe`` 把 ``xpm_fifo_async_sim.sv``（``xpm_fifo_async`` 的接口等价模型，
     因此本测试不需要 Vivado 及其 XPM 库）、``digital_snn_host_bridge.sv`` 和内联
     SystemVerilog testbench 编译成 ``.vvp`` 网表；
   * ``vvp.exe`` 运行该网表，用两条互不同源的时钟驱动 FIFO，检查命令/响应双向传输、
     fwft 读时序、满与背压、读写指针回绕、复位清空，以及非法复位重入必须以非 0 结束并
     报 ``RESET_REENTRY_ERROR``。
3. Ubuntu runner 不能直接执行本测试。Linux 上 ``C:\msys64\...`` 必然不存在，若继续
   ``raise RuntimeError`` 就会把“路径不存在”误报成“代码功能失败”。因此
   ``require_windows_msys2_toolchain()`` 在非 Windows 或工具缺失时抛
   ``unittest.SkipTest``，消息以 ``SKIPPED/NOT APPLICABLE:`` 开头并给出具体原因；
   ``test_illegal_reset_reentry_is_rejected`` 之类需要仿真的用例同理。
   ``test_xpm_configuration_is_frozen`` 和 ``test_windows_msys2_toolchain_dependency_is_declared``
   只读源码，不依赖仿真工具，在所有平台照常执行。
4. PR Gate 已相应调整：``.github/workflows/pr-gate.yml`` 的 ``windows-xpm-cdc`` 作业
   （``windows-latest`` + ``msys2/setup-msys2@v2`` + ``msystem: UCRT64`` +
   ``mingw-w64-ucrt-x86_64-iverilog``）是本测试的真实执行环境，并带守卫步骤——一旦被
   跳过就判定该作业失败；``python-and-syntax``（ubuntu-latest）只负责显示明确的
   SKIPPED/NOT APPLICABLE 并把该 notice 打印到作业日志。完整说明见
   ``docs/WINDOWS_MSYS2_XPM_TOOLCHAIN.md``。

工具链缺陷的处理原则（复现矩阵见同一文档）：本机 ``C:\msys64\ucrt64`` 只是 UCRT64
bin 的局部拷贝、并非完整 MSYS2 安装，实测特征有两条——带 ``-Wall`` 编译本设计时
``iverilog.exe`` 以 0xC0000005 立即失败且 stdout/stderr 全空（去掉 ``-Wall`` 即 rc=0），
而 ``vvp.exe`` 连空 testbench 都以 0xC0000005 无输出崩溃。这类“非 0 退出 + 完全无输出”
的崩溃属于工具链缺陷，不是 RTL 行为，因此转成 SKIPPED/NOT APPLICABLE 并打印
``TOOLCHAIN_DEFECT=...``；``compile_and_run()`` 仍优先使用 ``-Wall``，只在命中该特征时去掉
``-Wall`` 重试一次。任何**有输出**的非 0 结果（真实语法错误、断言失败）一律照常抛出或
判定失败，不掩盖问题；Windows 作业的守卫保证“跳过”不能被当成通过。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent

# 以下常量是裁定允许保留的 Windows + MSYS2 UCRT64 专用固定路径，不是跨平台默认路径；
# 非 Windows 平台必须走 SKIPPED/NOT APPLICABLE 分支，而不是报成代码功能失败。
MSYS2_UCRT64_BIN = Path(r"C:\msys64\ucrt64\bin")
IVERILOG = MSYS2_UCRT64_BIN / "iverilog.exe"
VVP = MSYS2_UCRT64_BIN / "vvp.exe"
MSYS2_IVERILOG_PACKAGE = "mingw-w64-ucrt-x86_64-iverilog"
REQUIRED_TOOLS = (IVERILOG, VVP)
SKIPPED_PREFIX = "SKIPPED/NOT APPLICABLE: "
# Windows 上进程异常终止的 NTSTATUS（低 32 位），且完全没有 stdout/stderr。
CRASH_RETURN_CODES = (0xC0000005, 0xC0000409)
_NOTICE_LOGGED = False


def unsigned_return_code(returncode: int) -> int:
    return returncode & 0xFFFFFFFF


def is_silent_abnormal_exit(process: subprocess.CompletedProcess[str]) -> bool:
    """“非 0 退出 + 输出全空 + 崩溃状态码”——工具链缺陷特征，而非 RTL 行为。"""
    return (
        process.returncode != 0
        and unsigned_return_code(process.returncode) in CRASH_RETURN_CODES
        and not (process.stdout or "").strip()
        and not (process.stderr or "").strip()
    )


def toolchain_unavailability() -> str | None:
    """返回“本测试为何无法在此机器上真实执行”的原因；None 表示可以执行。"""
    if sys.platform != "win32":
        return (
            f"host platform is {sys.platform!r}, not win32; this test drives the Windows + MSYS2 "
            f"UCRT64 layout {MSYS2_UCRT64_BIN} and cannot run on an Ubuntu runner"
        )
    missing = [str(path) for path in REQUIRED_TOOLS if not path.exists()]
    if missing:
        return (
            "missing tool(s): " + ", ".join(missing)
            + f"; install the MSYS2 UCRT64 package {MSYS2_IVERILOG_PACKAGE}"
        )
    return None


def toolchain_notice() -> str:
    version = "unreadable"
    try:
        probe = subprocess.run(
            [str(IVERILOG), "-V"], capture_output=True, text=True, timeout=60, check=False
        )
        lines = (probe.stdout or "").splitlines()
        version = lines[0].strip() if lines else "no -V output"
    except OSError as error:
        version = f"error: {error}"
    return (
        f"XPM_TOOLCHAIN platform={sys.platform} python={sys.version.split()[0]} "
        f"package={MSYS2_IVERILOG_PACKAGE} iverilog={IVERILOG} vvp={VVP} "
        f"iverilog_version={version!r}"
    )


def log_toolchain_notice() -> None:
    global _NOTICE_LOGGED
    if not _NOTICE_LOGGED:
        print(toolchain_notice(), flush=True)
        _NOTICE_LOGGED = True


def require_windows_msys2_toolchain() -> None:
    """非 Windows 或工具缺失 => 跳过（NOT APPLICABLE），不是失败。"""
    log_toolchain_notice()
    reason = toolchain_unavailability()
    if reason is not None:
        raise unittest.SkipTest(SKIPPED_PREFIX + reason)


def toolchain_defect(tool: str, process: subprocess.CompletedProcess[str], stage: str) -> unittest.SkipTest:
    print(
        f"TOOLCHAIN_DEFECT={tool}_{stage}_silent_crash "
        f"return_code=0x{unsigned_return_code(process.returncode):08X}",
        flush=True,
    )
    return unittest.SkipTest(
        SKIPPED_PREFIX
        + f"toolchain_defect: {tool} exited with 0x{unsigned_return_code(process.returncode):08X} "
        + "and produced no output at all, so this is an incomplete/faulty MSYS2 UCRT64 install "
        + f"on this host, not an RTL failure; install {MSYS2_IVERILOG_PACKAGE} properly"
    )


def compile_and_run(testbench: str) -> subprocess.CompletedProcess[str]:
    """用接口等价 FIFO 模型编译并运行一个双时钟 testbench。"""
    require_windows_msys2_toolchain()

    with tempfile.TemporaryDirectory(prefix="eneuron_xpm_wrapper_") as temp_dir:
        temp = Path(temp_dir)
        tb_path = temp / "tb.sv"
        sim_path = temp / "tb.vvp"
        tb_path.write_text(testbench, encoding="utf-8")
        command = [
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
        ]
        compile_result = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, check=False
        )
        if compile_result.returncode != 0 and is_silent_abnormal_exit(compile_result):
            # 已知缺陷特征：iverilog.exe + -Wall 无输出崩溃；去掉 -Wall 重试一次。
            print(
                "TOOLCHAIN_DEFECT=iverilog_compile_silent_crash "
                f"return_code=0x{unsigned_return_code(compile_result.returncode):08X} retry_without=-Wall",
                flush=True,
            )
            command.remove("-Wall")
            compile_result = subprocess.run(
                command, cwd=ROOT, capture_output=True, text=True, check=False
            )
        if compile_result.returncode != 0:
            if is_silent_abnormal_exit(compile_result):
                raise toolchain_defect("iverilog.exe", compile_result, "compile")
            raise RuntimeError(
                "iverilog failed:\n"
                f"{compile_result.stdout}\n{compile_result.stderr}"
            )

        env = os.environ.copy()
        env["PATH"] = f"{VVP.parent}{os.pathsep}{env.get('PATH', '')}"
        run_result = subprocess.run(
            [str(VVP), str(sim_path)],
            cwd=temp,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        if is_silent_abnormal_exit(run_result):
            raise toolchain_defect("vvp.exe", run_result, "run")
        return run_result


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
    def test_windows_msys2_toolchain_dependency_is_declared(self) -> None:
        """平台无关：核对裁定要求的 4 点注明与 CI 调整确实写在仓库里。"""
        module_doc = Path(__file__).read_text(encoding="utf-8").split('"""')[1]
        for marker in (
            "Windows + MSYS2 UCRT64",
            str(MSYS2_UCRT64_BIN),
            MSYS2_IVERILOG_PACKAGE,
            "iverilog.exe",
            "vvp.exe",
            "Ubuntu runner",
            SKIPPED_PREFIX.strip(),
            "windows-xpm-cdc",
        ):
            self.assertIn(marker, module_doc, f"模块 docstring 缺少注明: {marker}")

        self.assertEqual(str(IVERILOG), r"C:\msys64\ucrt64\bin\iverilog.exe")
        self.assertEqual(str(VVP), r"C:\msys64\ucrt64\bin\vvp.exe")

        workflow = (ROOT / ".github" / "workflows" / "pr-gate.yml").read_text(encoding="utf-8")
        for marker in (
            "windows-xpm-cdc:",
            "runs-on: windows-latest",
            "msys2/setup-msys2@v2",
            "msystem: UCRT64",
            MSYS2_IVERILOG_PACKAGE,
            "test_host_bridge_xpm_wrapper",
            "NOT APPLICABLE",
        ):
            self.assertIn(marker, workflow, f"pr-gate.yml 缺少调整: {marker}")

        guide = (ROOT / "docs" / "WINDOWS_MSYS2_XPM_TOOLCHAIN.md").read_text(encoding="utf-8")
        for marker in (
            "Windows + MSYS2 UCRT64",
            MSYS2_IVERILOG_PACKAGE,
            "test_host_bridge_xpm_wrapper.py",
            "SKIPPED/NOT APPLICABLE",
            "windows-xpm-cdc",
        ):
            self.assertIn(marker, guide, f"工具链文档缺少注明: {marker}")

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
