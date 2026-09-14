"""QAT 模型上 standalone PL auto-mask 引擎的 Icarus 仿真数据生成。

在 Windows 侧运行（iverilog/vvp 位于 C:/msys64/ucrt64/bin 或 PATH）：
    python tools/repro/b3_qat_pl_auto_mask_sim.py -o artifacts/results/b3_qat_pl_auto_mask_sim.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_fixed_vector_manifest import model_words_from_manifest  # noqa: E402
from eneuron_group4way_live import decide_group4way_live  # noqa: E402

DEFAULT_MANIFEST = ROOT / "tools" / "repro" / "b3_qat_model_manifest.json"
DEFAULT_OUTPUT = ROOT / "artifacts" / "results" / "b3_qat_pl_auto_mask_sim.json"
ENGINE_RTL = ROOT / "eneuron_pl_auto_mask_engine.sv"
GOLDEN_TB = ROOT / "tb_b3_pl_auto_mask_golden.sv"
CYCLE_BUDGET = 2048
FIXED_IVERILOG = Path(r"C:\msys64\ucrt64\bin\iverilog.exe")
FIXED_VVP = Path(r"C:\msys64\ucrt64\bin\vvp.exe")


def _find_tool(fixed: Path, name: str) -> Path | None:
    if fixed.exists():
        return fixed
    found = shutil.which(name)
    return Path(found) if found else None


def run_sim(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    model_words = model_words_from_manifest(manifest)
    samples = manifest["samples"]
    expected = []
    for sample in samples:
        decision = decide_group4way_live(model_words, sample["pixels"])
        expected.extend(f"0x{word:08X}\n" for word in decision.mask_words)

    iverilog = _find_tool(FIXED_IVERILOG, "iverilog")
    vvp = _find_tool(FIXED_VVP, "vvp")
    if iverilog is None or vvp is None:
        raise FileNotFoundError("Icarus Verilog is required for this simulation")

    with tempfile.TemporaryDirectory(prefix="eneuron_qat_pl_sim_") as temp:
        temp_path = Path(temp)
        model_file = temp_path / "model.mem"
        pixel_file = temp_path / "pixels.mem"
        expected_file = temp_path / "expected.mem"
        model_file.write_text("".join(f"{word:08x}\n" for word in model_words), encoding="ascii")
        pixel_file.write_text(
            "".join(f"{pixel:x}\n" for sample in samples for pixel in sample["pixels"]),
            encoding="ascii",
        )
        expected_file.write_text("".join(expected), encoding="ascii")
        binary = temp_path / "tb.vvp"
        compiled = subprocess.run(
            [str(iverilog), "-g2012", "-DPL_AUTO_MASK_ENGINE", "-o", str(binary),
             str(ENGINE_RTL), str(GOLDEN_TB)],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        if compiled.returncode != 0:
            raise RuntimeError(compiled.stderr)
        ran = subprocess.run(
            [str(vvp), str(binary),
             f"+MODEL={model_file.as_posix()}",
             f"+PIXELS={pixel_file.as_posix()}",
             f"+EXPECTED={expected_file.as_posix()}"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
    cycles = None
    for line in ran.stdout.splitlines():
        if line.startswith("B3_PL_AUTO_MASK_ENGINE_CYCLES="):
            cycles = int(line.split("=", 1)[1])
    return {
        "returncode": ran.returncode,
        "stdout": ran.stdout,
        "stderr": ran.stderr,
        "samples": len(samples),
        "cycles": cycles,
        "golden": "python_decide_group4way_live",
    }


def build_artifact(manifest_path: Path, sim: dict) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    passed = sim["returncode"] == 0 and "B3_PL_AUTO_MASK_GOLDEN_PASS" in sim["stdout"]
    return {
        "schema": "eneuron_b3_qat_pl_auto_mask_sim_v1",
        "status": "SIM_PASS" if passed else "SIM_FAIL",
        "identity": {
            "manifest": manifest_path.relative_to(ROOT).as_posix(),
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "packed_words_sha256": manifest["model"]["packed_words_sha256"],
            "engine_source_sha256": hashlib.sha256(ENGINE_RTL.read_bytes()).hexdigest(),
            "testbench_sha256": hashlib.sha256(GOLDEN_TB.read_bytes()).hexdigest(),
        },
        "samples": sim["samples"],
        "bit_exact": sim["samples"] if passed else 0,
        "engine_cycles_per_sample": sim["cycles"],
        "cycle_budget": CYCLE_BUDGET,
        "ooc": {"lut": 13855, "ff": 1046, "bram": 0, "dsp48e1": 8, "timing": "not_run"},
        "boundary": "Icarus 仿真数据，不是板级结果；引擎尚未接入主 NPU，未做 200 MHz 时序评定。",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="QAT PL auto-mask 引擎仿真")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    sim = run_sim(args.manifest)
    artifact = build_artifact(args.manifest, sim)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": artifact["status"],
        "samples": artifact["samples"],
        "bit_exact": artifact["bit_exact"],
        "engine_cycles_per_sample": artifact["engine_cycles_per_sample"],
        "output": str(args.output),
    }, indent=2))
    return 0 if artifact["status"] == "SIM_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
