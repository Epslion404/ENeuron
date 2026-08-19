"""原始 Goal M3：最小任务合同的公开行为测试。"""

from __future__ import annotations

import unittest

from m3_task import run_oracle_m3


class M3TaskContractTests(unittest.TestCase):
    def test_fixed_teacher_plan_learns_without_direct_weight_programming(self) -> None:
        """固定 RTL 初态应从全 abstain 训练为稳定的二分类网络。"""
        report = run_oracle_m3()

        self.assertEqual(report.pretrain_predictions, (-1, -1))
        self.assertEqual(report.clean_predictions, (0, 1))
        self.assertEqual(report.noisy_correct, report.noisy_total)
        self.assertEqual(report.weight_epoch, 4)
        self.assertEqual(
            report.final_weights,
            (
                (-6, -7, 7, 7),
                (7, 7, -6, -7),
                (7, -7),
                (-7, 7),
            ),
        )


if __name__ == "__main__":
    unittest.main()
