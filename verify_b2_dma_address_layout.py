"""低地址 B2 DMA 布局合同的 fail-closed 验证器。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "tools" / "repro" / "b2_dma_address_layout.json"


def validate_layout(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema") != "b2_dma_address_layout_v1":
        errors.append("schema mismatch")
    if manifest.get("target_part") != "xc7z020clg484-2":
        errors.append("target part mismatch")
    if manifest.get("board_gate_state") != "B1_HIGH_DDR_PENDING":
        errors.append("board gate state must remain B1_HIGH_DDR_PENDING")

    window = manifest.get("verified_window", {})
    base = window.get("base")
    end = window.get("end_exclusive")
    size = window.get("size_bytes")
    if not all(isinstance(value, int) for value in (base, end, size)):
        errors.append("verified window fields must be integers")
        return errors
    if end <= base or end - base != size:
        errors.append("verified window range/size mismatch")

    alignment = manifest.get("region_alignment_bytes")
    cache_line = manifest.get("cache_line_bytes")
    max_frame = manifest.get("max_dma_frame_bytes")
    if not isinstance(alignment, int) or alignment <= 0:
        errors.append("region alignment must be positive")
        alignment = 1
    if not isinstance(cache_line, int) or cache_line <= 0:
        errors.append("cache line must be positive")
        cache_line = 1
    if not isinstance(max_frame, int) or max_frame <= 0:
        errors.append("max DMA frame must be positive")
        max_frame = 1

    regions = manifest.get("regions")
    if not isinstance(regions, list) or not regions:
        errors.append("regions must be a non-empty list")
        return errors

    spans: list[tuple[int, int, str]] = []
    for region in regions:
        name = region.get("name", "<unnamed>") if isinstance(region, dict) else "<invalid>"
        if not isinstance(region, dict):
            errors.append(f"{name}: region must be an object")
            continue
        region_base = region.get("base")
        capacity = region.get("capacity_bytes")
        payload = region.get("payload_bytes")
        if not all(isinstance(value, int) for value in (region_base, capacity, payload)):
            errors.append(f"{name}: base/capacity/payload must be integers")
            continue
        if capacity <= 0:
            errors.append(f"{name}: capacity must be positive")
            continue
        if payload < 0 or payload > capacity:
            errors.append(f"{name}: payload exceeds capacity")
        if region_base % alignment != 0 or region_base % cache_line != 0:
            errors.append(f"{name}: base is not aligned")
        if capacity % cache_line != 0:
            errors.append(f"{name}: capacity is not cache-line aligned")
        region_end = region_base + capacity
        if region_base < base or region_end > end:
            errors.append(f"{name}: region outside verified window")
        if region.get("dma_role") in {"tx", "rx"} and capacity < max_frame:
            errors.append(f"{name}: DMA frame capacity below max frame")
        spans.append((region_base, region_end, name))

    for left, right in zip(sorted(spans), sorted(spans)[1:]):
        if right[0] < left[1]:
            errors.append(f"region overlap: {left[2]} and {right[2]}")
    if spans and sum(end - start for start, end, _ in spans) > end - base:
        errors.append("reserved regions exceed verified window")

    by_name = {region.get("name"): region for region in regions if isinstance(region, dict)}
    expected_payloads = {
        "model_image": 634 * 4,
        "mask_image": 19 * 4,
        "sample_tx": 8 * 4,
        "result_rx": 10 * 4,
    }
    for name, expected in expected_payloads.items():
        region = by_name.get(name)
        if region is None:
            errors.append(f"missing required region: {name}")
        elif region.get("payload_bytes") != expected:
            errors.append(f"{name}: payload does not match frozen protocol size")
    return errors


def main() -> int:
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"B2_DMA_LAYOUT_REJECT: {exc}")
        return 1
    errors = validate_layout(manifest)
    if errors:
        print("B2_DMA_LAYOUT_REJECT:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    window = manifest["verified_window"]
    reserved = sum(region["capacity_bytes"] for region in manifest["regions"])
    print(
        "B2_DMA_LAYOUT_PASS "
        f"window=0x{window['base']:08x}-0x{window['end_exclusive']:08x} "
        f"reserved_bytes={reserved} "
        f"free_bytes={window['size_bytes'] - reserved} "
        f"max_frame_bytes={manifest['max_dma_frame_bytes']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
