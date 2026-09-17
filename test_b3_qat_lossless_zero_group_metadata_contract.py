"""QAT 无损零组跳过的物理取数与 metadata 结构合同。"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RTL = ROOT / "npu_eneuron_single_clock_skeleton.sv"


def _rtl() -> str:
    return RTL.read_text(encoding="utf-8")


def test_lossless_metadata_is_explicit_and_reset_safe() -> None:
    text = _rtl()
    assert "model_word_nonzero" in text
    assert "l0_group_nonzero" in text
    assert "l1_group_nonzero" in text
    assert re.search(r"model_word_nonzero\s*\[[^\]]+\].*<=\s*\|model_write_data", text)
    assert re.search(r"model_word_nonzero\s*\[[^\]]+\]\s*<=\s*1'b0", text)


def test_lossless_zero_decision_does_not_reduce_raw_model_or_activation_arrays() -> None:
    text = _rtl()
    decision = text[text.index("lossless_l0_group_skip"):text.index("// 配置握手")]
    assert "model_staging[" not in decision
    assert "input_pixels[" not in decision
    assert "hidden_values[" not in decision
    assert "l0_group_nonzero" in decision
    assert "l1_group_nonzero" in decision


def test_model_storage_declares_synchronous_physical_intent() -> None:
    text = _rtl()
    assert "b3_model_sync_ram model_ram" in text
    assert "xpm_memory_sdpram" in text
    assert ".MEMORY_PRIMITIVE(\"block\")" in text
    assert ".READ_LATENCY_B(1)" in text


if __name__ == "__main__":
    raise SystemExit("run with pytest")
