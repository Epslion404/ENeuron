from pathlib import Path
import shutil
import subprocess
import tempfile

import pytest

from tools.ci.classify_changes import classify_paths


ROOT = Path(__file__).resolve().parent


def test_distribution_replay_contract_is_compile_time_opt_in() -> None:
    shim = (ROOT / "b3_pl_distribution_replay_shim.sv").read_text(encoding="utf-8")
    assert "INPUT_SAMPLES = 397" in shim
    assert "WARMUP_SAMPLES = 1000" in shim
    assert "MEASURE_SAMPLES = 10000" in shim
    assert "pl_replay_capture_count" in shim
    assert "pl_replay_completed_count" in shim
    assert "pl_replay_measured_cycles" in shim
    assert "sample_mem" in shim


def test_distribution_replay_changes_use_t1_repro_scope() -> None:
    scopes = classify_paths(
        ["b3_pl_distribution_replay_shim.sv", "tb_b3_pl_distribution_replay_shim.sv"]
    )
    assert scopes["t1_repro"]
    assert not scopes["full_repository"]


def test_distribution_replay_shim_behavior() -> None:
    iverilog = Path("C:/msys64/ucrt64/bin/iverilog.exe")
    vvp = Path("C:/msys64/ucrt64/bin/vvp.exe")
    if not iverilog.is_file() or not vvp.is_file():
        pytest.skip("Icarus Verilog unavailable")
    with tempfile.TemporaryDirectory(prefix="b3-pl-distribution-replay-") as temp:
        binary = Path(temp) / "tb.vvp"
        compiled = subprocess.run(
            [
                str(iverilog), "-g2012", "-s", "tb_b3_pl_distribution_replay_shim",
                "-o", str(binary), "b3_pl_distribution_replay_shim.sv",
                "tb_b3_pl_distribution_replay_shim.sv",
            ], cwd=ROOT, text=True, capture_output=True, check=False,
        )
        assert compiled.returncode == 0, compiled.stdout + compiled.stderr
        ran = subprocess.run(
            [str(vvp), str(binary)], cwd=ROOT, text=True,
            capture_output=True, check=False,
        )
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "B3_PL_DISTRIBUTION_REPLAY_SHIM_PASS captures=3 measures=5" in ran.stdout
