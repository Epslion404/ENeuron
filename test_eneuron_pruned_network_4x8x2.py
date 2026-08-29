"""ENeuron 严格 2:4 的 4→8→2 网络公开接口合同。"""

from __future__ import annotations

import unittest

from eneuron_pruned_network_4x8x2_cosim import (
    run_hidden_output_accounting_contract,
    run_host_transaction_and_backpressure_contract,
    run_topology_route_and_commit_contract,
)


class ENeuronPrunedNetwork4x8x2Tests(unittest.TestCase):
    def test_topology_route_and_atomic_commit(self) -> None:
        run_topology_route_and_commit_contract()

    def test_host_broadcast_addressing_and_response_backpressure(self) -> None:
        run_host_transaction_and_backpressure_contract()

    def test_hidden_and_output_work_are_accounted_separately(self) -> None:
        run_hidden_output_accounting_contract()


if __name__ == "__main__":
    unittest.main()
