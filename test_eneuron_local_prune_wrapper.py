"""ENeuron 单核局部剪枝 wrapper 的公开接口合同。"""

from __future__ import annotations

import unittest

from eneuron_local_prune_wrapper_cosim import (
    run_network_managed_clear_contract,
    run_wrapper_contract,
)


class ENeuronLocalPruneWrapperTests(unittest.TestCase):
    def test_bypass_mod_observe_and_issue_mask_contract(self) -> None:
        run_wrapper_contract()

    def test_network_barrier_can_own_post_commit_state_clear(self) -> None:
        run_network_managed_clear_contract()


if __name__ == "__main__":
    unittest.main()
