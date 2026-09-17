"""在主 NPU FSM 上验证 QAT-v3 无损零组跳过语义。"""

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
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from b3_qat_lossless_skip_eval import _search_input_permutation, _split_fixture  # noqa: E402
from b3_qat_model_manifest import pack_model_words  # noqa: E402
from npu_eneuron_reference import saturate_hidden  # noqa: E402


DEFAULT_MANIFEST = ROOT / "tools" / "repro" / "b3_qat_model_manifest.json"
DEFAULT_OUTPUT = ROOT / "artifacts" / "results" / "b3_qat_lossless_zero_group_rtl_sim.json"
FIXED_IVERILOG = Path(r"C:\msys64\ucrt64\bin\iverilog.exe")
FIXED_VVP = Path(r"C:\msys64\ucrt64\bin\vvp.exe")
DENSE_CYCLES = 2494
GROUP_COUNT = 592


def _find_tool(fixed: Path, name: str) -> Path | None:
    if fixed.exists():
        return fixed
    discovered = shutil.which(name)
    return Path(discovered) if discovered else None


def _pack_pixels(pixels: list[int]) -> list[int]:
    return [sum(pixels[beat * 8 + lane] << (lane * 4) for lane in range(8)) for beat in range(8)]


def _derive_vectors(manifest: dict) -> dict:
    train, heldout = _split_fixture(manifest)
    order = _search_input_permutation(train)
    source_model = json.loads((ROOT / manifest["identity"]["source_model"]).read_text(encoding="utf-8-sig"))
    model = {
        "W0": [[int(row[order[index]]) for index in range(64)] for row in source_model["W0"]],
        "b0": [int(value) for value in source_model["b0"]],
        "W1": [[int(value) for value in row] for row in source_model["W1"]],
        "b1": [int(value) for value in source_model["b1"]],
    }
    model_words = pack_model_words(model)
    sample_words: list[int] = []
    expected_logits: list[int] = []
    execute_per_sample: list[int] = []
    skip_per_sample: list[int] = []

    for sample in heldout:
        pixels = [int(sample["pixels"][order[index]]) for index in range(64)]
        sample_words.extend(_pack_pixels(pixels))
        hidden: list[int] = []
        executed = 0
        skipped = 0
        for row, bias in zip(model["W0"], model["b0"]):
            accumulator = bias
            for group in range(16):
                start = group * 4
                activations = pixels[start:start + 4]
                weights = row[start:start + 4]
                if not any(activations) or not any(weights):
                    skipped += 1
                    continue
                executed += 1
                accumulator += sum(weight * activation for weight, activation in zip(weights, activations))
            hidden.append(saturate_hidden(accumulator))

        logits: list[int] = []
        for row, bias in zip(model["W1"], model["b1"]):
            accumulator = bias
            for group in range(8):
                start = group * 4
                activations = hidden[start:start + 4]
                weights = row[start:start + 4]
                if not any(activations) or not any(weights):
                    skipped += 1
                    continue
                executed += 1
                accumulator += sum(weight * activation for weight, activation in zip(weights, activations))
            logits.append(accumulator)
        if logits != [int(value) for value in sample["dense_logits"]]:
            raise AssertionError(f"permuted zero-group reference changed sample {sample['sample_index']}")
        if executed + skipped != GROUP_COUNT:
            raise AssertionError("group accounting mismatch")
        expected_logits.extend(value & 0xFFFFFFFF for value in logits)
        execute_per_sample.append(executed)
        skip_per_sample.append(skipped)

    return {
        "order": order,
        "model_words": model_words,
        "sample_words": sample_words,
        "expected_logits": expected_logits,
        "execute_per_sample": execute_per_sample,
        "skip_per_sample": skip_per_sample,
    }


def run_sim(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    vectors = _derive_vectors(manifest)
    sample_count = len(vectors["execute_per_sample"])
    iverilog = _find_tool(FIXED_IVERILOG, "iverilog")
    vvp = _find_tool(FIXED_VVP, "vvp")
    if iverilog is None or vvp is None:
        raise FileNotFoundError("Icarus Verilog is required")

    with tempfile.TemporaryDirectory(prefix="b3_qat_lossless_zero_group_") as temp:
        temp_path = Path(temp)
        files = {
            "MODEL": ("model.mem", vectors["model_words"]),
            "SAMPLES": ("samples.mem", vectors["sample_words"]),
            "LOGITS": ("logits.mem", vectors["expected_logits"]),
            "EXECUTE": ("execute.mem", vectors["execute_per_sample"]),
            "SKIP": ("skip.mem", vectors["skip_per_sample"]),
        }
        args = []
        for plusarg, (name, values) in files.items():
            path = temp_path / name
            path.write_text("".join(f"{int(value) & 0xFFFFFFFF:08x}\n" for value in values), encoding="ascii")
            args.append(f"+{plusarg}={path.as_posix()}")
        binary = temp_path / "tb.vvp"
        compiled = subprocess.run(
            [str(iverilog), "-g2012", "-DLOSSLESS_ZERO_GROUP_SKIP",
             f"-Ptb_b3_qat_lossless_zero_group_skip.SAMPLE_COUNT={sample_count}",
             "-s", "tb_b3_qat_lossless_zero_group_skip", "-o", str(binary),
             str(ROOT / "tb_b3_qat_lossless_zero_group_skip.sv"),
             str(ROOT / "npu_eneuron_single_clock_skeleton.sv")],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        if compiled.returncode != 0:
            raise RuntimeError(compiled.stdout + compiled.stderr)
        ran = subprocess.run([str(vvp), str(binary), *args], cwd=ROOT, text=True,
                             capture_output=True, check=False)

    skipped_total = sum(vectors["skip_per_sample"])
    mean_cycles = sum(DENSE_CYCLES - 3 * value for value in vectors["skip_per_sample"]) / sample_count
    return {
        "returncode": ran.returncode,
        "stdout": ran.stdout,
        "stderr": ran.stderr,
        "samples": sample_count,
        "permutation": vectors["order"],
        "derived_model_words_sha256": hashlib.sha256(
            b"".join(int(word).to_bytes(4, "little") for word in vectors["model_words"])
        ).hexdigest(),
        "skipped_total": skipped_total,
        "skip_rate": skipped_total / (GROUP_COUNT * sample_count),
        "mean_cycles": mean_cycles,
        "core_speedup": DENSE_CYCLES / mean_cycles,
    }


def build_artifact(manifest_path: Path, sim: dict) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    passed = sim["returncode"] == 0 and "B3_QAT_LOSSLESS_ZERO_GROUP_RTL_PASS" in sim["stdout"]
    return {
        "schema": "eneuron_b3_qat_lossless_zero_group_rtl_sim_v1",
        "status": "SIM_PASS" if passed else "SIM_FAIL",
        "identity": {
            "manifest": manifest_path.relative_to(ROOT).as_posix(),
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "canonical_packed_words_sha256": manifest["model"]["packed_words_sha256"],
            "derived_permuted_packed_words_sha256": sim["derived_model_words_sha256"],
            "permutation": sim["permutation"],
            "rtl_sha256": hashlib.sha256((ROOT / "npu_eneuron_single_clock_skeleton.sv").read_bytes()).hexdigest(),
            "testbench_sha256": hashlib.sha256((ROOT / "tb_b3_qat_lossless_zero_group_skip.sv").read_bytes()).hexdigest(),
        },
        "samples": sim["samples"],
        "logit_exact_match": sim["samples"] if passed else 0,
        "group_instances_total": GROUP_COUNT * sim["samples"],
        "skipped_groups_total": sim["skipped_total"],
        "skip_rate": sim["skip_rate"],
        "mean_compute_cycles": sim["mean_cycles"],
        "estimated_core_speedup": sim["core_speedup"],
        "included_rules": ["zero_activation_group", "zero_weight_group"],
        "excluded_rules": ["l0_relu_suffix_early_stop"],
        "boundary": "公开端口级Icarus仿真；输入置换同步应用于L0权重和输入。未做OOC、200MHz时序或板级验证。",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="QAT-v3主NPU无损零组跳过RTL仿真")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    sim = run_sim(args.manifest)
    artifact = build_artifact(args.manifest, sim)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: artifact[key] for key in (
        "status", "samples", "logit_exact_match", "skip_rate", "mean_compute_cycles", "estimated_core_speedup"
    )}, ensure_ascii=False))
    if artifact["status"] != "SIM_PASS":
        print(sim["stdout"])
        print(sim["stderr"], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
