"""Host Bridge controller 的事务流协同仿真。"""

import unittest

from host_bridge_controller_cosim import (
    run_directed_controller_regression,
    run_random_controller_cosim,
)


class HostBridgeControllerCosimTests(unittest.TestCase):
    def test_directed_session_and_response_commit_boundaries(self) -> None:
        run_directed_controller_regression()

    def test_random_commands_match_python_oracle(self) -> None:
        for seed in range(20):
            run_random_controller_cosim(seed=seed, command_count=1000)

    def test_mod_response_reports_updated_weight_epoch(self) -> None:
        run_directed_controller_regression(check_mod_epoch=True)


if __name__ == "__main__":
    unittest.main()
