"""给定 Host 命令序列的双时钟系统协同仿真。"""

import unittest

from host_bridge_controller_cosim import command
from host_bridge_oracle import HostBridgeOracle, Opcode
from host_bridge_system_cosim import run_command_sequence


class HostBridgeSequenceCosimTests(unittest.TestCase):
    def test_given_sequence_returns_actual_responses_in_order(self) -> None:
        commands = (
            command(Opcode.WEIGHT_WRITE, txn_id=1, arg0=9 << 4),
            command(Opcode.WEIGHT_READ, txn_id=2, arg0=0),
            command(0xFE, txn_id=3),
            *(command(Opcode.STATUS_READ, txn_id=txn_id) for txn_id in range(4, 28)),
        )
        oracle = HostBridgeOracle()
        expected = tuple(oracle.execute(request) for request in commands)

        actual = run_command_sequence(commands, seed=0x5EED)

        self.assertEqual(actual, expected)
        self.assertEqual(actual[1].arg0, 7)


if __name__ == "__main__":
    unittest.main()
