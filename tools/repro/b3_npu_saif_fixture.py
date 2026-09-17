"""为B3纯PL NPU SAIF仿真生成确定性QAT-v3数据文件。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_fixed_vector_manifest import model_words_from_manifest  # noqa: E402


DEFAULT_MANIFEST = ROOT / "tools" / "repro" / "b3_qat_model_manifest.json"
DEFAULT_DIAGNOSTIC = ROOT / "artifacts" / "results" / "b3_qat_pruning_diagnostic.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_mem(path: Path, words: list[int]) -> None:
    path.write_text("".join(f"{word & 0xFFFFFFFF:08x}\n" for word in words), encoding="ascii")


def build_fixture(manifest_path: Path, diagnostic_path: Path, output_dir: Path, sample_count: int) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8-sig"))
    if manifest.get("schema") != "eneuron_b3_qat_model_v1":
        raise ValueError("manifest must use eneuron_b3_qat_model_v1")
    samples = manifest.get("samples", [])[:sample_count]
    if len(samples) != sample_count:
        raise ValueError(f"manifest contains only {len(samples)} samples, requested {sample_count}")

    model_words = model_words_from_manifest(manifest)
    mask_words = [int(word, 0) for word in diagnostic["mask"]["calibrated_mask_words"]]
    if len(model_words) != 634 or len(mask_words) != 19:
        raise ValueError("expected 634 model words and 19 mask words")
    if mask_words[18] & 0xFFFF0000:
        raise ValueError("reserved mask bits 592..607 must be zero")
    enabled = 0
    for base in range(0, 592, 4):
        group = sum(((mask_words[(base + lane) // 32] >> ((base + lane) % 32)) & 1) for lane in range(4))
        if group != 2:
            raise ValueError(f"mask is not strict 2:4 at meta {base // 4}: enabled={group}")
        enabled += group

    sample_beats = [int(beat, 0) for sample in samples for beat in sample["input_beats"]]
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = {
        "model.mem": model_words,
        "samples.mem": sample_beats,
        "gated_mask.mem": mask_words,
    }
    for name, words in generated.items():
        write_mem(output_dir / name, words)

    fixture = {
        "schema": "eneuron_b3_npu_saif_fixture_v1",
        "part": "xc7z020clg484-2",
        "clock_mhz": 200.0,
        "manifest": manifest_path.resolve().as_posix(),
        "manifest_sha256": sha256(manifest_path),
        "diagnostic": diagnostic_path.resolve().as_posix(),
        "diagnostic_sha256": sha256(diagnostic_path),
        "packed_words_sha256": manifest["model"]["packed_words_sha256"],
        "sample_count": sample_count,
        "sample_ids": [sample["sample_id"] for sample in samples],
        "model_word_count": len(model_words),
        "sample_beat_count": len(sample_beats),
        "gated_enabled_groups": enabled,
        "gated_disabled_groups": 592 - enabled,
        "generated_sha256": {name: sha256(output_dir / name) for name in generated},
    }
    (output_dir / "fixture.json").write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return fixture


def main() -> int:
    parser = argparse.ArgumentParser(description="生成B3 NPU SAIF仿真fixture")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--diagnostic", type=Path, default=DEFAULT_DIAGNOSTIC)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sample-count", type=int, default=64)
    args = parser.parse_args()
    fixture = build_fixture(args.manifest, args.diagnostic, args.output_dir, args.sample_count)
    print(json.dumps({key: fixture[key] for key in ("schema", "sample_count", "gated_enabled_groups")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
