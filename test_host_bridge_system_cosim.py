"""完整 Host Bridge + Controller + Tile 的双时钟端到端协同仿真。"""

import unittest

from host_bridge_system_cosim import (
    run_hard_reset_system_regression,
    run_random_system_cosim,
)


class HostBridgeSystemCosimTests(unittest.TestCase):
    def test_random_dual_clock_end_to_end(self) -> None:
        for seed in range(20):
            run_random_system_cosim(seed=seed, command_count=2000)

    def test_hard_reset_discards_outstanding_and_restores_weights(self) -> None:
        run_hard_reset_system_regression()


if __name__ == "__main__":
    unittest.main()
