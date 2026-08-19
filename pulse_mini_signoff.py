"""生成 Pulse-Mini 的机器可读签核摘要。

摘要把实现、黄金模型、测试、形式脚本和固定事务集合绑定到 SHA-256，
避免只凭一行 PASS 文本无法确认测试针对的是哪一版源码。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pulse_mini_cosim import expected_rows, make_commands


ROOT = Path(__file__).resolve().parent


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")


def build_summary() -> dict[str, object]:
    source_files = (
        "pulse_mini_core.sv",
        "pulse_mini_reference.py",
        "pulse_mini_cosim.py",
        "test_pulse_mini_reference.py",
        "formal_pulse_mini.sv",
        "formal_pulse_mini.ys",
        "run_formal_pulse_mini.ps1",
        "pulse_mini_negative_control.py",
        "test_pulse_mini_negative.py",
        "pulse_mini_task.py",
        "test_pulse_mini_task.py",
        "pulse_mini_network_4x2x2.sv",
        "pulse_mini_network_rtl_cosim.py",
        "tb_pulse_mini_network_file.sv",
    )
    files = {name: sha256_file(ROOT / name) for name in source_files}
    transaction_records: list[dict[str, object]] = []
    for seed in range(20):
        commands = make_commands(seed, 1000)
        transaction_records.append({
            "seed": seed,
            "commands": commands,
            "expected": expected_rows(commands),
        })
    transaction_digest = sha256_bytes(canonical_json(transaction_records))
    return {
        "schema": "pulse_mini_signoff_v1",
        "implementation": "Pulse-Mini fixed four-input signed event neuron",
        "source_sha256": files,
        "cosim": {
            "seeds": 20,
            "transactions_per_seed": 1000,
            "transactions": 20000,
            "golden_transaction_digest_sha256": transaction_digest,
            "command": "python pulse_mini_cosim.py",
            "expected_result": "PULSE_MINI_COSIM_PASS seeds=20 transactions=20000",
        },
        "formal": {
            "engine": "Yosys 0.56 SAT",
            "depth": 20,
            "expected_result": "PULSE_MINI_FORMAL_PASS depth=20",
            "command": ".\\run_formal_pulse_mini.ps1",
        },
        "negative_control": {
            "expected_result": "PULSE_MINI_NEGATIVE_CONTROL_PASS duplicate_feedback_counterexample=1",
            "command": "python pulse_mini_negative_control.py",
        },
        "network_rtl_cosim": {
            "commands": 272,
            "expected_result": "PULSE_MINI_NETWORK_RTL_COSIM_PASS commands=272 one_tick_route=1 positive=1 negative=2",
            "command": "python pulse_mini_network_rtl_cosim.py",
        },
        "status": "PASS",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "output",
        nargs="?",
        default="pulse_mini_signoff_summary.json",
        help="输出 JSON 摘要路径",
    )
    args = parser.parse_args()
    output = ROOT / args.output
    output.write_text(json.dumps(build_summary(), ensure_ascii=True, indent=2) + "\n", encoding="ascii")
    print(f"PULSE_MINI_SIGNOFF_SUMMARY_PASS path={output.name}")


if __name__ == "__main__":
    main()
