"""NP4B3 十组剪枝提交屏障的公开接口测试。"""

from __future__ import annotations

import unittest

from local_prune_commit_barrier_cosim import (
    run_atomic_commit_then_clear_contract,
    run_clear_failure_halts_contract,
    run_unsafe_precheck_contract,
)


class LocalPruneCommitBarrierTest(unittest.TestCase):
    def test_any_unready_participant_prevents_all_gate_starts(self) -> None:
        """任一参与者未就绪时，提交必须整体拒绝且不能部分启动。"""

        run_unsafe_precheck_contract()

    def test_success_is_published_only_after_all_commit_and_clear_responses(self) -> None:
        """先后完成的参与者必须由 sticky barrier 汇合后再统一公开。"""

        run_atomic_commit_then_clear_contract()

    def test_clear_failure_enters_sticky_halt(self) -> None:
        """mask 已提交后若清历史失败，只能停机，不能伪造成功或回滚。"""

        run_clear_failure_halts_contract()


if __name__ == "__main__":
    unittest.main()
