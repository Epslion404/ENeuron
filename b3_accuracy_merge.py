"""合并 dense/live 分块实板采集，生成 b3_accuracy_report.py 的输入。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load(path: Path) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    capture = document.get("accuracy_capture")
    if not isinstance(capture, dict) or capture.get("status") != 2:
        raise ValueError(f"{path} has no successful accuracy_capture")
    samples = capture.get("samples")
    if not isinstance(samples, list):
        raise ValueError(f"{path} accuracy_capture.samples is not a list")
    rows: dict[str, dict[str, object]] = {}
    for row in samples:
        if not isinstance(row, dict) or "sample_id" not in row:
            raise ValueError(f"{path} contains malformed capture sample")
        sample_id = str(row["sample_id"])
        if sample_id in rows:
            raise ValueError(f"{path} contains duplicate sample_id={sample_id}")
        rows[sample_id] = row
    return document, rows


def merge(dense_paths: list[Path], live_paths: list[Path]) -> dict[str, object]:
    dense_documents = [_load(path) for path in dense_paths]
    live_documents = [_load(path) for path in live_paths]
    dense: dict[str, dict[str, object]] = {}
    live: dict[str, dict[str, object]] = {}
    for _, rows in dense_documents:
        dense.update(rows)
    for _, rows in live_documents:
        live.update(rows)
    if set(dense) != set(live):
        raise ValueError("dense/live sample_id sets differ")
    samples: list[dict[str, object]] = []
    for sample_id in sorted(dense, key=lambda value: int(value)):
        left = dense[sample_id]
        right = live[sample_id]
        for field in ("input_sha256", "label"):
            if left.get(field) != right.get(field):
                raise ValueError(f"sample {sample_id} {field} differs between dense/live")
        if left.get("input_crc") != right.get("input_crc"):
            raise ValueError(f"sample {sample_id} input_crc differs between dense/live")
        samples.append({
            "sample_id": sample_id,
            "input_sha256": left["input_sha256"],
            "mask_epoch": right["mask_epoch"],
            "label": left["label"],
            "dense_logits": left["logits"],
            "live_logits": right["logits"],
            "protocol_errors": 0,
            "result_crc_match": left.get("status") == 2 and right.get("status") == 2,
            "input_match": True,
        })
    first_dense = dense_documents[0][0]
    first_live = live_documents[0][0]
    for field in ("model_id", "preprocess", "bitstream_sha256", "xsa_sha256", "elf_sha256", "benchmark_manifest_sha256"):
        if not str(first_dense.get(field, "")).strip() or not str(first_live.get(field, "")).strip():
            raise ValueError(f"dense/live identity field {field} is missing")
    identity = {
        "model": first_dense.get("model_id", "model-3"),
        "preprocess": first_dense.get("preprocess", "uint4_64_low_nibble_first_v1"),
        "bitstream_sha256": first_dense.get("bitstream_sha256", ""),
        "xsa_sha256": first_dense.get("xsa_sha256", ""),
        # dense/live 为不同编译模式，ELF 不要求相同；两份身份都单独留账。
        "elf_sha256": f"paired:{first_dense['elf_sha256']}:{first_live['elf_sha256']}",
        "dense_elf_sha256": first_dense.get("elf_sha256", ""),
        "live_elf_sha256": first_live.get("elf_sha256", ""),
        "benchmark_manifest_sha256": first_dense.get("benchmark_manifest_sha256", ""),
        "dense_run_count": len(dense_paths),
        "live_run_count": len(live_paths),
    }
    for dense_field, identity_field in (
        ("model_id", "model"),
        ("preprocess", "preprocess"),
        ("bitstream_sha256", "bitstream_sha256"),
        ("xsa_sha256", "xsa_sha256"),
        ("benchmark_manifest_sha256", "benchmark_manifest_sha256"),
    ):
        if identity[identity_field] != first_live.get(dense_field, ""):
            raise ValueError(f"dense/live {dense_field} differs")
    return {"schema": "eneuron_b3_accuracy_samples_v1", "identity": identity, "samples": samples}


def main() -> int:
    parser = argparse.ArgumentParser(description="合并 dense/live 精度采集 JSON")
    parser.add_argument("--dense", type=Path, nargs="+", required=True)
    parser.add_argument("--live", type=Path, nargs="+", required=True)
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()
    payload = merge(args.dense, args.live)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"merged_samples={len(payload['samples'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
