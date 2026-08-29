"""NP4/NP5 局部 2:4 剪枝 RTL 验收入口。"""

from __future__ import annotations

import unittest

from local_prune_gate_cosim import (
    run_directed_contract,
    run_mixed_cosim,
    run_negative_controls,
)


class LocalPruneGateRtlTest(unittest.TestCase):
    def test_directed_contract(self) -> None:
        run_directed_contract()

    def test_three_fixed_gain_wrappers(self) -> None:
        for model_name in ("eneuron", "pulse_mini_l", "pulse_mini_l2"):
            with self.subTest(model=model_name):
                run_mixed_cosim(model_name=model_name, seed=23, transaction_count=256)

    def test_negative_controls_produce_counterexamples(self) -> None:
        run_negative_controls()


if __name__ == "__main__":
    unittest.main()
