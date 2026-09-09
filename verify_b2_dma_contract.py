"""验证 B2-D1 首轮 AXI DMA 控制合同，失败时拒绝继续进入硬件实现。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "tools" / "repro" / "b2_dma_contract.json"


def validate_contract(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if contract.get("schema") != "b2_dma_contract_v1":
        errors.append("schema mismatch")
    if contract.get("target_part") != "xc7z020clg484-2":
        errors.append("target part mismatch")
    if contract.get("board_gate_state") != "B1_HIGH_DDR_PENDING":
        errors.append("board gate state must remain B1_HIGH_DDR_PENDING")

    mode = contract.get("dma_mode")
    if not isinstance(mode, dict):
        errors.append("dma_mode must be an object")
    else:
        for field in ("simple", "polling"):
            if mode.get(field) is not True:
                errors.append(f"{field} must be enabled")
        for field in ("scatter_gather", "micro_dma", "interrupts_enabled", "dre_required"):
            if mode.get(field) is not False:
                errors.append(f"{field} must be disabled")

    register_map = contract.get("register_map")
    expected_registers = {
        "tx_channel_offset": 0,
        "rx_channel_offset": 0x30,
        "control_offset": 0,
        "status_offset": 0x04,
        "address_offset": 0x18,
        "buffer_length_offset": 0x28,
        "runstop_mask": 0x01,
        "reset_mask": 0x04,
        "halted_mask": 0x01,
        "idle_mask": 0x02,
        "error_mask": 0x770,
        "irq_all_mask": 0x7000,
    }
    if not isinstance(register_map, dict):
        errors.append("register_map must be an object")
    else:
        for name, expected in expected_registers.items():
            if register_map.get(name) != expected:
                errors.append(f"register map mismatch: {name}")

    limits = contract.get("transfer_limits")
    if not isinstance(limits, dict):
        errors.append("transfer_limits must be an object")
    else:
        if limits.get("min_frame_bytes") != 1:
            errors.append("min frame must be 1 byte")
        if limits.get("max_frame_bytes") != 4096:
            errors.append("max frame must be 4096 bytes")
        if limits.get("buffer_alignment_bytes") != 64:
            errors.append("buffer alignment must be 64 bytes")

    sequence = contract.get("transfer_sequence")
    expected_sequence = [
        "reset_and_wait_done",
        "disable_tx_rx_interrupts",
        "prepare_rx_buffer",
        "flush_tx_buffer",
        "invalidate_rx_buffer",
        "submit_s2mm",
        "submit_mm2s",
        "poll_s2mm_and_mm2s",
        "invalidate_rx_buffer_after_completion",
        "verify_payload",
    ]
    if sequence != expected_sequence:
        errors.append("transfer sequence mismatch")

    timeout = contract.get("timeout")
    if not isinstance(timeout, dict):
        errors.append("timeout must be an object")
    else:
        if timeout.get("poll_interval_us") != 1:
            errors.append("poll interval must be 1 us")
        if timeout.get("transfer_timeout_us") != 1_000_000:
            errors.append("transfer timeout must be 1000000 us")
        if timeout.get("reset_poll_budget") != 500:
            errors.append("reset poll budget must be 500")

    recovery = contract.get("recovery")
    expected_recovery = [
        "stop_new_submissions",
        "snapshot_registers_and_context",
        "reset_dma_engine",
        "wait_reset_done",
        "require_halted_channels",
        "clear_software_ownership",
        "retry_known_short_frame_once",
    ]
    if not isinstance(recovery, dict):
        errors.append("recovery must be an object")
    else:
        if recovery.get("on_error_or_timeout") != expected_recovery:
            errors.append("recovery sequence mismatch")
        if recovery.get("max_recovery_retries") != 1:
            errors.append("recovery retry count must be 1")

    evidence = contract.get("evidence")
    required_snapshots = {
        "tx_cr", "tx_sr", "tx_srcaddr", "tx_btt",
        "rx_cr", "rx_sr", "rx_destaddr", "rx_btt",
    }
    if not isinstance(evidence, dict):
        errors.append("evidence must be an object")
    else:
        snapshots = evidence.get("register_snapshot")
        if not isinstance(snapshots, list) or set(snapshots) != required_snapshots:
            errors.append("register snapshot is incomplete")
        if not isinstance(evidence.get("run_fields"), list) or len(evidence["run_fields"]) < 10:
            errors.append("run evidence fields are incomplete")
        if not evidence.get("source_basis"):
            errors.append("source basis is required")

    return errors


def main() -> int:
    try:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"B2_DMA_CONTRACT_REJECT: {exc}")
        return 1
    errors = validate_contract(contract)
    if errors:
        print("B2_DMA_CONTRACT_REJECT:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print(
        "B2_DMA_CONTRACT_PASS "
        f"mode=simple/polling max_frame_bytes={contract['transfer_limits']['max_frame_bytes']} "
        f"reset_poll_budget={contract['timeout']['reset_poll_budget']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
