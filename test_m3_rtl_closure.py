"""M3 真实双时钟训练、读回与命令账本的端到端验收。"""

from __future__ import annotations

import logging
import unittest

from host_bridge_oracle import Opcode, Status
from m3_task import M3CommandPlan, run_rtl_m3
from m3_training_ledger import audit_training_ledger


LOGGER = logging.getLogger("test_m3_rtl_closure")


def _weight_read_addresses() -> tuple[int, ...]:
    """按 H0/H1/O0/O1 顺序覆盖当前 Tile 的全部 12 个权重地址。"""

    return tuple(
        neuron | (weight << 2)
        for neuron in range(4)
        for weight in range(4 if neuron < 2 else 2)
    )


def _signed32(value: int) -> int:
    """把 WEIGHT_READ 的 32-bit 符号扩展 payload 还原为 Python 整数。"""

    return value - (1 << 32) if value & (1 << 31) else value


class M3RtlClosureTests(unittest.TestCase):
    def test_real_dual_clock_training_closes_task_readback_and_ledger(self) -> None:
        plan = M3CommandPlan.build()
        report = run_rtl_m3(plan)

        self.assertEqual(report.pretrain_predictions, (-1, -1))
        self.assertEqual(report.clean_predictions, (0, 1))
        self.assertEqual((report.noisy_correct, report.noisy_total), (20, 20))
        self.assertEqual(report.weight_epoch, 4)

        mod_indices = tuple(
            index
            for index, command in enumerate(plan.commands)
            if command.opcode == int(Opcode.MOD_COMMIT)
        )
        self.assertEqual(len(mod_indices), 4)
        self.assertEqual(len(report.post_commit_weight_reads), 4)

        expected_addresses = _weight_read_addresses()
        for commit_number, (mod_index, reported_weights) in enumerate(
            zip(mod_indices, report.post_commit_weight_reads, strict=True)
        ):
            read_commands = plan.commands[mod_index + 1 : mod_index + 13]
            read_responses = report.responses[mod_index + 1 : mod_index + 13]
            self.assertEqual(len(read_commands), 12)
            self.assertTrue(
                all(command.opcode == int(Opcode.WEIGHT_READ) for command in read_commands)
            )
            self.assertEqual(
                tuple(command.arg0 & 0xF for command in read_commands),
                expected_addresses,
            )
            self.assertTrue(
                all(response.flags == int(Status.OK) for response in read_responses)
            )
            actual_weights = tuple(_signed32(response.arg0) for response in read_responses)
            self.assertEqual(reported_weights, actual_weights, f"commit={commit_number}")

        # 双时钟 runner 必须返回每条实际响应，不能只返回任务级汇总。
        self.assertEqual(len(report.responses), len(plan.commands))
        for index, (command, response) in enumerate(
            zip(plan.commands, report.responses, strict=True)
        ):
            self.assertEqual(
                (response.opcode, response.txn_id, response.episode_id, response.tick_id),
                (command.opcode, command.txn_id, command.episode_id, command.tick_id),
                f"response index={index}",
            )

        self.assertFalse(
            any(
                command.opcode == int(Opcode.WEIGHT_WRITE)
                for command in plan.commands[plan.training_start :]
            )
        )
        independent_ledger = audit_training_ledger(
            report.responses,
            training_start=plan.training_start,
        )
        self.assertEqual(report.ledger, independent_ledger)
        self.assertEqual(report.ledger.weight_write.seen, 0)
        self.assertEqual(report.ledger.weight_write.successful, 0)
        self.assertEqual(report.ledger.mod_commit.seen, 4)
        self.assertEqual(report.ledger.mod_commit.successful, 4)
        self.assertEqual(len(report.ledger.hash_chain), len(report.responses))
        LOGGER.info(
            "M3 RTL closure verified: commands=%d commits=%d noisy=%d/%d",
            len(plan.commands),
            report.ledger.mod_commit.successful,
            report.noisy_correct,
            report.noisy_total,
        )


if __name__ == "__main__":
    unittest.main()
