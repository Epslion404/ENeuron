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

    def test_core_caches_each_units_group_mask_before_group_loop(self):
        source = (ROOT / "npu_eneuron_single_clock_skeleton.sv").read_text(encoding="utf-8")
        for token in (
            "compute_unit_mask_latched",
            "compute_unit_mask_latched <= l0_unit_mask(compute_unit_index)",
            "compute_unit_mask_latched <= l1_unit_mask(compute_unit_index)",
            "compute_unit_mask_latched[compute_group_index[3:0]]",
            "compute_unit_mask_latched[compute_group_index[2:0]]",
        ):
            self.assertIn(token, source)
        self.assertNotIn("active_mask_enabled((compute_unit_index * 16)", source)
        self.assertNotIn("active_mask_enabled(512 + (compute_unit_index * 8)", source)

    def test_core_uses_registered_model_address_for_group_fetch(self):
        source = (ROOT / "npu_eneuron_single_clock_skeleton.sv").read_text(encoding="utf-8")
        self.assertIn("compute_model_addr", source)
        self.assertIn("model_staging[compute_model_addr]", source)
        self.assertNotIn(
            "model_staging[(compute_unit_index * 16) + compute_group_index]",
            source,
        )
        self.assertNotIn(
            "model_staging[544 + (compute_unit_index * 8) + compute_group_index]",
            source,
        )

    def test_core_uses_balanced_lane_sum_tree(self):
        source = (ROOT / "npu_eneuron_single_clock_skeleton.sv").read_text(encoding="utf-8")
        for token in ("lane_pair_sum_01", "lane_pair_sum_23"):
            self.assertIn(token, source)
        self.assertIn("lane_pair_sum_01 + lane_pair_sum_23", source)

    def test_core_registers_dsp_products_before_sum(self):
        source = (ROOT / "npu_eneuron_single_clock_skeleton.sv").read_text(encoding="utf-8")
        self.assertIn("lane_product_0 <= lane_activation_0 * lane_weight_0", source)
        self.assertIn("mac_low_sum_latched <= mac_low_sum_comb", source)
        self.assertIn("mac_high_lane_sum_latched <= lane_sum_comb[31:16]", source)
        self.assertIn("mac_accumulator = {mac_accumulator_hi, mac_accumulator_lo}", source)
        self.assertNotIn("lane_sum_latched <= lane_sum_comb", source.split("COMPUTE_L0_GROUP_EXECUTE", 1)[1].split("COMPUTE_L0_GROUP_COMMIT", 1)[0])

    def test_core_registers_low_sum_before_high_accumulator_update(self):
        source = (ROOT / "npu_eneuron_single_clock_skeleton.sv").read_text(encoding="utf-8")
        for token in (
            "COMPUTE_L0_GROUP_ACCUM",
            "COMPUTE_L1_GROUP_ACCUM",
            "mac_low_sum_latched",
            "mac_high_lane_sum_latched",
            "mac_low_sum_latched <= mac_low_sum_comb",
            "mac_high_lane_sum_latched <= lane_sum_comb[31:16]",
            "mac_accumulator_hi <= mac_accumulator_hi + mac_high_lane_sum_latched + mac_low_sum_latched[16]",
        ):
            self.assertIn(token, source)

    def test_core_registers_model_write_before_bram_update(self):
        source = (ROOT / "npu_eneuron_single_clock_skeleton.sv").read_text(encoding="utf-8")
        for token in ("model_write_pending", "model_write_data", "model_write_addr", "model_write_pending <= 1'b1"):
            self.assertIn(token, source)
        self.assertIn("model_staging[model_write_addr] <= model_write_data", source)

    def test_core_replicates_active_epoch_for_error_response_path(self):
        source = (ROOT / "npu_eneuron_single_clock_skeleton.sv").read_text(encoding="utf-8")
        self.assertIn("mask_response_epoch", source)
        self.assertIn("mask_response_epoch <= mask_published_epoch", source)
        self.assertNotIn(
            "make_error_response(\n                            4'h4, cmd_opcode, {2'd0, mask_state},\n                            {27'd0, mask_word_index}, mask_active_epoch",
            source,
        )
        self.assertNotIn(
            "make_error_response(\n                            4'h6, cmd_opcode, {2'd0, mask_state},\n                            {27'd0, mask_word_index}, mask_active_epoch",
            source,
        )


if __name__ == "__main__":
    unittest.main()
