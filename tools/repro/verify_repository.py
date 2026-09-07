"""G0/G1 复现检查器；运行产物写入临时目录。"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(command: list[str], cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, encoding="utf-8")


def _tracked(relative: str) -> bool:
    if (ROOT / ".git").exists():
        return _run(["git", "ls-files", "--error-unmatch", relative]).returncode == 0
    # git archive 快照没有 .git；文件已存在即表示它来自提交闭包。
    return (ROOT / relative).is_file()


def _manifest_errors() -> list[str]:
    data = json.loads((ROOT / "tools/repro/repro_manifest.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    for relative in data["required_tracked_files"]:
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"缺少文件: {relative}")
        elif not _tracked(relative):
            errors.append(f"文件未被 Git 跟踪: {relative}")
        if Path(relative).is_absolute() or ":\\" in relative:
            errors.append(f"manifest 含绝对路径: {relative}")
    return errors


def _tools() -> tuple[str, str] | None:
    fixed = Path("C:/msys64/ucrt64/bin")
    if (fixed / "iverilog.exe").is_file() and (fixed / "vvp.exe").is_file():
        return str(fixed / "iverilog.exe"), str(fixed / "vvp.exe")
    iverilog, vvp = shutil.which("iverilog"), shutil.which("vvp")
    return (iverilog, vvp) if iverilog and vvp else None


def _run_t1() -> list[str]:
    tools = _tools()
    if tools is None:
        return ["找不到 Icarus Verilog；Windows 约定路径为 C:/msys64/ucrt64/bin"]
    with tempfile.TemporaryDirectory(prefix="eneuron-repro-") as temp:
        cases = [
            ("tb_npu_zynq7020_t1_wrapper", "tb_npu_zynq7020_t1_wrapper.sv", "T1_PROTOCOL_SKELETON_PASS"),
            ("tb_npu_zynq7020_t1_fifo_boundary", "tb_npu_zynq7020_t1_fifo_boundary.sv", "T1_FIFO_BOUNDARY_PASS"),
            ("tb_npu_zynq7020_t1_fence_accept", "tb_npu_zynq7020_t1_fence_accept.sv", "T1_FENCE_ACCEPT_PASS"),
        ]
        for top, testbench, marker in cases:
            output = Path(temp) / f"{top}.vvp"
            compile_result = _run([tools[0], "-g2012", "-Wall", "-s", top, "-o", str(output),
                                   "xpm_fifo_async_sim.sv", "npu_eneuron_single_clock_skeleton.sv",
                                   "npu_zynq7020_t1_wrapper.sv", testbench])
            if compile_result.returncode:
                return [f"{top} 编译失败:\n" + compile_result.stderr[-4000:]]
            simulation = subprocess.run([tools[1], str(output)], cwd=ROOT, text=True,
                                        capture_output=True, encoding="utf-8")
            text = simulation.stdout + simulation.stderr
            if simulation.returncode or marker not in text:
                return [f"{top} 仿真失败或缺少通过标记:\n" + text[-4000:]]
    return []


def _run_t2() -> list[str]:
    tools = _tools()
    if tools is None:
        return ["找不到 Icarus Verilog；Windows 约定路径为 C:/msys64/ucrt64/bin"]
    cases = [(7, 2), (9, 1), (4, 3), (5, 0), (11, 4), (3, 1)]
    with tempfile.TemporaryDirectory(prefix="eneuron-repro-t2-") as temp:
        for npu_half, npu_phase in cases:
            name = f"t2_variable_{npu_half}_{npu_phase}"
            output = Path(temp) / f"{name}.vvp"
            compile_result = _run([tools[0], "-g2012", "-Wall", "-s", "tb_npu_zynq7020_t2_variable_clocks",
                                   f"-Ptb_npu_zynq7020_t2_variable_clocks.NPU_HALF={npu_half}",
                                   f"-Ptb_npu_zynq7020_t2_variable_clocks.NPU_PHASE={npu_phase}",
                                   "-o", str(output), "xpm_fifo_async_sim.sv",
                                   "npu_eneuron_single_clock_skeleton.sv", "npu_zynq7020_t1_wrapper.sv",
                                   "tb_npu_zynq7020_t2_variable_clocks.sv"])
            if compile_result.returncode:
                return [f"{name} 编译失败:\n" + compile_result.stderr[-4000:]]
            simulation = subprocess.run([tools[1], str(output)], cwd=ROOT, text=True,
                                        capture_output=True, encoding="utf-8")
            text = simulation.stdout + simulation.stderr
            marker = f"T2_VARIABLE_CLOCKS_PASS NPU_HALF={npu_half} NPU_PHASE={npu_phase}"
            if simulation.returncode or marker not in text:
                return [f"{name} 仿真失败或缺少通过标记:\n" + text[-4000:]]
    return []


def _run_t2_full_matrix() -> list[str]:
    """运行有限、可复现的 wrapper 时钟/相位矩阵；不是数学穷举。"""
    tools = _tools()
    if tools is None:
        return ["找不到 Icarus Verilog；Windows 约定路径为 C:/msys64/ucrt64/bin"]
    cases = (
        (2, 0), (2, 1), (3, 0), (3, 2),
        (4, 1), (4, 3), (5, 0), (5, 4),
        (6, 2), (7, 1), (7, 6), (8, 3),
        (9, 0), (9, 8), (10, 4), (11, 10),
    )
    with tempfile.TemporaryDirectory(prefix="eneuron-repro-t2-full-") as temp:
        for npu_half, npu_phase in cases:
            name = f"t2_full_{npu_half}_{npu_phase}"
            output = Path(temp) / f"{name}.vvp"
            compile_result = _run([
                tools[0], "-g2012", "-Wall", "-s", "tb_npu_zynq7020_t2_variable_clocks",
                f"-Ptb_npu_zynq7020_t2_variable_clocks.NPU_HALF={npu_half}",
                f"-Ptb_npu_zynq7020_t2_variable_clocks.NPU_PHASE={npu_phase}",
                "-o", str(output), "xpm_fifo_async_sim.sv",
                "npu_eneuron_single_clock_skeleton.sv", "npu_zynq7020_t1_wrapper.sv",
                "tb_npu_zynq7020_t2_variable_clocks.sv",
            ])
            if compile_result.returncode:
                return [f"{name} 编译失败:\n" + compile_result.stderr[-4000:]]
            simulation = subprocess.run(
                [tools[1], str(output)], cwd=ROOT, text=True,
                capture_output=True, encoding="utf-8"
            )
            text = simulation.stdout + simulation.stderr
            marker = f"T2_VARIABLE_CLOCKS_PASS NPU_HALF={npu_half} NPU_PHASE={npu_phase}"
            if simulation.returncode or marker not in text:
                return [f"{name} 仿真失败或缺少通过标记:\n" + text[-4000:]]
    return []


def _run_t2_fifo_matrix() -> list[str]:
    tools = _tools()
    if tools is None:
        return ["找不到 Icarus Verilog；Windows 约定路径为 C:/msys64/ucrt64/bin"]
    # 固定 seed 的伪随机矩阵，覆盖 NPU 慢于、快于和接近 Host 的时钟关系。
    cases = [(2, 0), (3, 1), (4, 3), (5, 0), (7, 2), (9, 1), (11, 4), (13, 5)]
    seeds = (1, 7, 29)
    with tempfile.TemporaryDirectory(prefix="eneuron-repro-t2-fifo-") as temp:
        for npu_half, npu_phase in cases:
            for seed in seeds:
                name = f"t2_fifo_{npu_half}_{npu_phase}_{seed}"
                output = Path(temp) / f"{name}.vvp"
                compile_result = _run([
                    tools[0], "-g2012", "-Wall", "-s", "tb_xpm_fifo_async_matrix",
                    "-P", f"tb_xpm_fifo_async_matrix.NPU_HALF={npu_half}",
                    "-P", f"tb_xpm_fifo_async_matrix.NPU_PHASE={npu_phase}",
                    "-P", f"tb_xpm_fifo_async_matrix.SEED={seed}",
                    "-o", str(output), "xpm_fifo_async_sim.sv", "tb_xpm_fifo_async_matrix.sv",
                ])
                if compile_result.returncode:
                    return [f"{name} 编译失败:\n" + compile_result.stderr[-4000:]]
                simulation = subprocess.run(
                    [tools[1], str(output)], cwd=ROOT, text=True,
                    capture_output=True, encoding="utf-8"
                )
                text = simulation.stdout + simulation.stderr
                marker = (
                    f"T2_FIFO_MATRIX_PASS NPU_HALF={npu_half} "
                    f"NPU_PHASE={npu_phase} SEED={seed}"
                )
                if simulation.returncode or marker not in text:
                    return [f"{name} 仿真失败或缺少通过标记:\n" + text[-4000:]]
    return []


def _run_t2_interleave_reset() -> list[str]:
    tools = _tools()
    if tools is None:
        return ["找不到 Icarus Verilog；Windows 约定路径为 C:/msys64/ucrt64/bin"]
    cases = [(2, 0), (3, 1), (7, 2), (11, 4)]
    with tempfile.TemporaryDirectory(prefix="eneuron-repro-t2-interleave-") as temp:
        for npu_half, npu_phase in cases:
            name = f"t2_interleave_{npu_half}_{npu_phase}"
            output = Path(temp) / f"{name}.vvp"
            compile_result = _run([
                tools[0], "-g2012", "-Wall", "-s", "tb_npu_zynq7020_t2_interleave_reset",
                "-P", f"tb_npu_zynq7020_t2_interleave_reset.NPU_HALF={npu_half}",
                "-P", f"tb_npu_zynq7020_t2_interleave_reset.NPU_PHASE={npu_phase}",
                "-o", str(output), "xpm_fifo_async_sim.sv", "npu_eneuron_single_clock_skeleton.sv",
                "npu_zynq7020_t1_wrapper.sv", "tb_npu_zynq7020_t2_interleave_reset.sv",
            ])
            if compile_result.returncode:
                return [f"{name} 编译失败:\n" + compile_result.stderr[-4000:]]
            simulation = subprocess.run(
                [tools[1], str(output)], cwd=ROOT, text=True,
                capture_output=True, encoding="utf-8"
            )
            text = simulation.stdout + simulation.stderr
            marker = f"T2_INTERLEAVE_RESET_PASS NPU_HALF={npu_half} NPU_PHASE={npu_phase}"
            if simulation.returncode or marker not in text:
                return [f"{name} 仿真失败或缺少通过标记:\n" + text[-4000:]]
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--t1", action="store_true", help="运行 T1 协议切片")
    parser.add_argument("--t2", action="store_true", help="运行 T2 非整数时钟切片")
    parser.add_argument("--t2-full-matrix", action="store_true", help="运行 T2 wrapper 有限时钟/相位矩阵")
    parser.add_argument("--t2-fifo-matrix", action="store_true", help="运行 T2 FIFO 压力矩阵")
    parser.add_argument("--t2-interleave-reset", action="store_true", help="运行 T2 wrapper 交错与复位切片")
    args = parser.parse_args()
    errors = _manifest_errors()
    if args.t1:
        errors.extend(_run_t1())
    if args.t2:
        errors.extend(_run_t2())
    if args.t2_full_matrix:
        errors.extend(_run_t2_full_matrix())
    if args.t2_fifo_matrix:
        errors.extend(_run_t2_fifo_matrix())
    if args.t2_interleave_reset:
        errors.extend(_run_t2_interleave_reset())
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        return 1
    print("REPRO_G0_MANIFEST_PASS")
    if args.t1:
        print("REPRO_G1_T1_PROTOCOL_SLICE_PASS")
    if args.t2:
        print("REPRO_G2_T2_VARIABLE_CLOCKS_PASS")
    if args.t2_full_matrix:
        print("REPRO_G2_T2_FULL_MATRIX_PASS")
    if args.t2_fifo_matrix:
        print("REPRO_G2_T2_FIFO_MATRIX_PASS")
    if args.t2_interleave_reset:
        print("REPRO_G2_T2_INTERLEAVE_RESET_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
