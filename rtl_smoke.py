"""对参考 RTL 做不依赖外部 HDL 工具的接口/参数静态检查，并生成黄金向量元数据。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from neuron_sim import make_trial
from rtl_cosim import find_tool, run as run_cosim
from rtl_reference import generate_trace


REQUIRED_PORTS = (
    "clk",
    "rst",
    "state_clear",
    "tick_valid",
    "input_spikes",
    "learn_enable",
    "mod_valid",
    "modulator",
    "snapshot_we",
    "weight_we",
    "weight_addr",
    "weight_wdata",
    "weight_rdata",
    "spike",
    "membrane",
    "threshold_state",
    "ready",
)


def main() -> None:
    rtl = Path("digital_lif_core.sv").read_text(encoding="utf-8")
    for port in REQUIRED_PORTS:
        if not re.search(rf"\b{port}\b", rtl):
            raise AssertionError(f"missing RTL port: {port}")
    if "always_ff @(posedge clk)" not in rtl:
        raise AssertionError("RTL must use a single synchronous clock")
    if "if (rst)" not in rtl or "if (mod_valid && learn_enable)" not in rtl:
        raise AssertionError("reset and inference write gate are missing")

    vector = [state.__dict__ for state in generate_trace(make_trial(1))]

    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    rtl_tool_available = iverilog is not None and vvp is not None
    cosim_passed = False
    if rtl_tool_available:
        run_cosim(seed=11, ticks=64)
        cosim_passed = True

    result = {
        "rtl": "digital_lif_core.sv",
        "required_ports": list(REQUIRED_PORTS),
        "python_reference": "RtlReferenceNeuron(n_inputs=4)",
        "golden_vector": vector,
        "rtl_tool_available": rtl_tool_available,
        "iverilog": str(iverilog) if iverilog else None,
        "vvp": str(vvp) if vvp else None,
        "cosim_passed": cosim_passed,
    }
    Path("artifacts/results/rtl_smoke_results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("RTL interface smoke check passed")
    if cosim_passed:
        print("Icarus HDL 编译/仿真和 Python 逐周期 cosim 已通过")
    else:
        print("外部 HDL 工具不可用，未执行 RTL 编译/仿真")
    print("黄金向量已写入 artifacts/results/rtl_smoke_results.json")


if __name__ == "__main__":
    main()
