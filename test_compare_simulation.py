"""ENeuron 1.0 与 Pulse-Mini 纯仿真比较的验收测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from compare_simulation import run_comparison, write_outputs


class SimulationComparisonTests(unittest.TestCase):
    def test_common_single_neuron_task_reports_all_three_models(self) -> None:
        result = run_comparison(seeds=range(3))

        self.assertEqual(result["scope"]["method"], "simulation_only")
        self.assertFalse(result["scope"]["vivado_used"])
        shared = result["single_neuron"]["shared_task"]
        self.assertEqual(shared["eneuron"]["trained_correct"], 20)
        for model in ("pulse_mini", "pulse_mini_l"):
            self.assertEqual(shared[model]["baseline_correct"], 10)
            self.assertEqual(shared[model]["trained_correct"], 20)
        self.assertEqual(shared["samples"], 20)

    def test_result_delay_scan_distinguishes_state_memory_from_effective_update(self) -> None:
        rows = run_comparison(seeds=range(1))["single_neuron"]["result_delay_scan"]

        self.assertEqual([row["gap_ticks"] for row in rows], list(range(13)))
        self.assertEqual([row["pulse_mini_weight_delta"] for row in rows[:4]], [1, 1, 1, 0])
        self.assertEqual([row["pulse_mini_l_weight_delta"] for row in rows[:4]], [1, 1, 1, 0])
        self.assertEqual([row["eneuron_weight_delta"] for row in rows[:4]], [2, 1, 1, 0])
        self.assertGreater(rows[3]["eneuron_eligibility"], 0)
        self.assertEqual(rows[10]["eneuron_eligibility"], 0)

    def test_information_compression_and_leak_probes_are_reported(self) -> None:
        single = run_comparison(seeds=range(1))["single_neuron"]
        multiplicity = single["event_multiplicity_scan"]
        spacing = single["identical_weight_spacing_scan"]
        learned_spacing = single["one_update_spacing_scan"]
        conflict = single["conflicting_evidence"]

        for model in ("pulse_mini", "pulse_mini_l"):
            self.assertEqual([row[f"{model}_weight_delta"] for row in multiplicity], [1] * 8)
        self.assertGreater(multiplicity[-1]["eneuron_eligibility"], multiplicity[0]["eneuron_eligibility"])
        self.assertEqual(spacing[0]["pulse_mini_spikes"], 1)
        self.assertGreater(spacing[-1]["pulse_mini_spikes"], 0)
        self.assertEqual(spacing[-1]["pulse_mini_l_spikes"], 0)
        self.assertEqual(spacing[-1]["eneuron_spikes"], 0)
        self.assertGreater(learned_spacing[0]["eneuron_spikes"], 0)
        self.assertEqual(learned_spacing[2]["eneuron_spikes"], 0)
        self.assertEqual(learned_spacing[0]["pulse_mini_spikes"], 1)
        self.assertGreater(learned_spacing[1]["pulse_mini_spikes"], 0)
        self.assertEqual(learned_spacing[1]["pulse_mini_l_spikes"], 0)
        self.assertEqual(learned_spacing[-1]["pulse_mini_l_spikes"], 0)
        self.assertEqual(conflict["pulse_mini_captured_direction"], 0)
        self.assertGreater(conflict["eneuron_eligibility"], 0)

        leak = single["leak_period_scan"]
        self.assertEqual(leak["selected_minimal_period"], 8)
        self.assertEqual(leak["rows"][0]["leak_period"], 0)
        self.assertTrue(next(row for row in leak["rows"] if row["leak_period"] == 8)["passes_minimal_gate"])
        self.assertFalse(next(row for row in leak["rows"] if row["leak_period"] == 4)["passes_minimal_gate"])

    def test_convergence_and_negative_controls_use_the_same_training_budget(self) -> None:
        single = run_comparison(seeds=range(1))["single_neuron"]
        convergence = single["convergence"]
        controls = single["negative_controls"]

        self.assertEqual(convergence["eneuron_first_full_score_repetition"], 1)
        self.assertEqual(convergence["pulse_mini_first_full_score_repetition"], 1)
        for model in ("eneuron", "pulse_mini", "pulse_mini_l"):
            self.assertEqual(controls[model]["correct_feedback"], 20)
            self.assertEqual(controls[model]["no_feedback"], 10)
            self.assertEqual(controls[model]["reversed_feedback"], 0)
            self.assertEqual(controls[model]["label_shuffled"], 10)

    def test_noise_sweep_uses_shared_samples_and_reports_distribution(self) -> None:
        noise = run_comparison(seeds=range(3))["single_neuron"]["noise_sweep"]

        self.assertEqual(noise["seed_count"], 3)
        self.assertEqual(noise["samples_per_seed"], 200)
        self.assertEqual(set(noise["profiles"]), {"dropout", "cross_class", "neutral", "combined"})
        neutral = noise["profiles"]["neutral"][-1]
        self.assertEqual(neutral["eneuron_mean_accuracy"], 1.0)
        self.assertEqual(neutral["pulse_mini_mean_accuracy"], 1.0)
        self.assertEqual(neutral["pulse_mini_l_mean_accuracy"], 1.0)
        combined = noise["profiles"]["combined"][-1]
        self.assertLess(combined["eneuron_mean_accuracy"], 1.0)
        self.assertLess(combined["pulse_mini_mean_accuracy"], 1.0)
        self.assertLess(combined["pulse_mini_l_mean_accuracy"], 1.0)

    def test_fixed_network_comparison_separates_shared_and_native_protocols(self) -> None:
        network = run_comparison(seeds=range(3))["network_4x2x2"]
        shared = network["shared_task"]
        native = network["native_protocols"]

        self.assertEqual(shared["eneuron"]["trained_mean_accuracy"], 1.0)
        self.assertEqual(shared["eneuron"]["trained_min_accuracy"], 1.0)
        self.assertEqual(shared["pulse_mini"]["trained_correct"], 20)
        self.assertTrue(shared["eneuron"]["inference_weights_frozen"])
        self.assertTrue(shared["pulse_mini"]["inference_weights_frozen"])
        self.assertEqual(native["eneuron_teacher"]["clean_mean_accuracy"], 1.0)
        for model in ("pulse_mini_local_teacher", "pulse_mini_l_local_teacher"):
            self.assertEqual(native[model]["clean_correct"], 20)
        self.assertEqual(native["pulse_mini_global_reward"], "not_tested")

    def test_outputs_include_raw_json_and_a_scoped_chinese_report(self) -> None:
        result = run_comparison(seeds=range(1))
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            json_path = root / "results.json"
            report_path = root / "report.md"
            write_outputs(result, json_path=json_path, report_path=report_path)

            saved = json.loads(json_path.read_text(encoding="utf-8"))
            report = report_path.read_text(encoding="utf-8")
        self.assertEqual(saved["scope"]["method"], "simulation_only")
        self.assertIn("仅仿真", report)
        self.assertIn("共同条件直接比较", report)
        self.assertIn("网络层优缺点", report)
        self.assertIn("Pulse-Mini-L 网络", report)
        self.assertIn("不能得出的结论", report)


if __name__ == "__main__":
    unittest.main()
