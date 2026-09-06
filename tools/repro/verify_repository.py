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
        output = Path(temp) / "t1.vvp"
        compile_result = _run([tools[0], "-g2012", "-Wall", "-s", "tb_npu_zynq7020_t1_wrapper", "-o", str(output),
                               "xpm_fifo_async_sim.sv", "npu_eneuron_single_clock_skeleton.sv",
                               "npu_zynq7020_t1_wrapper.sv", "tb_npu_zynq7020_t1_wrapper.sv"])
        if compile_result.returncode:
            return ["T1 编译失败:\n" + compile_result.stderr[-4000:]]
        simulation = subprocess.run([tools[1], str(output)], cwd=ROOT, text=True,
                                    capture_output=True, encoding="utf-8")
        text = simulation.stdout + simulation.stderr
        if simulation.returncode or "T1_PROTOCOL_SKELETON_PASS" not in text:
            return ["T1 仿真失败或缺少通过标记:\n" + text[-4000:]]
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--t1", action="store_true", help="运行 T1 协议切片")
    args = parser.parse_args()
    errors = _manifest_errors()
    if args.t1:
        errors.extend(_run_t1())
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        return 1
    print("REPRO_G0_MANIFEST_PASS")
    if args.t1:
        print("REPRO_G1_T1_PROTOCOL_SLICE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
