"""NP4B3 固定 4→8→2 一拍路由调度器测试。"""

from __future__ import annotations

import unittest

from pruned_network_tick_cosim import (
    run_one_tick_route_contract,
    run_route_flush_contract,
)


class PrunedNetworkTickSchedulerTest(unittest.TestCase):
    def test_outputs_read_previous_hidden_result(self) -> None:
        """输出启动数据必须来自旧 pending，而不是本拍 detector 结果。"""

        run_one_tick_route_contract()

    def test_route_flush_advances_only_outputs_and_clears_pending(self) -> None:
        """episode 尾部只排空输出层，不得再次推进隐藏层。"""

        run_route_flush_contract()


if __name__ == "__main__":
    unittest.main()
