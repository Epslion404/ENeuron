import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class B2NpuWrapperTimingContractTests(unittest.TestCase):
    def test_command_fifo_has_registered_npu_side_hold_stage(self):
        source = (ROOT / "npu_zynq7020_t1_wrapper.sv").read_text(encoding="utf-8")
        for token in (
            "cmd_hold_valid",
            "cmd_hold_data",
            "cmd_prefetch",
            "cmd_consume",
            "cmd_hold_data <= cmd_dout",
            "core_cmd_valid = command_fifo_ready_npu && cmd_hold_valid",
        ):
            self.assertIn(token, source)

    def test_core_does_not_use_raw_command_fifo_output(self):
        source = (ROOT / "npu_zynq7020_t1_wrapper.sv").read_text(encoding="utf-8")
        self.assertNotIn(
            ".cmd_payload(cmd_dout), .cmd_valid(core_cmd_valid)",
            source,
        )
        self.assertIn(
            ".cmd_payload(cmd_hold_data), .cmd_valid(core_cmd_valid)",
            source,
        )


if __name__ == "__main__":
    unittest.main()
