"""D2 最小网络的协议合同测试。

这些测试故意覆盖容易把监督学习证据做假的路径：教师事件缺失、自然发放冒充
教师、推理并列时强行选最小编号，以及固定特征层被意外更新。
"""

import unittest
from pathlib import Path

from digit8x8 import TIME_STEPS, load_fixture, load_manifest
from digit8x8_d2 import D2Network, run_d2_experiment
from digit8x8_d2_acceptance import validate_metrics, validate_training_ledger, validate_training_summary


ROOT = Path(__file__).resolve().parent


class Digit8x8D2ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.samples = load_fixture(ROOT / "digit8x8_fixture.json")
        cls.manifest = load_manifest(ROOT / "digit8x8_manifest.json")
        cls.sample = cls.samples[int(cls.manifest["splits"]["train"][0])]

    def test_feature_route_has_two_tail_ticks_and_four_input_quadrant_events(self):
        network = D2Network(init_seed=0)
        events = network.encode_features(self.sample.pixels)
        self.assertEqual(len(events), TIME_STEPS + 2)
        self.assertTrue(all(0 <= index < 4 for tick in events for index in tick))

    def test_training_has_explicit_teacher_after_each_input_micro_window(self):
        network = D2Network(init_seed=0)
        episode = network.train_sample(self.sample.sample_id, self.sample.pixels, self.sample.label)
        # D2 的教师事件与非空输入事件一一配对；不能把一次 episode 级教师事件
        # 当成所有输入事件的监督证据，也不要求为空 tick 伪造监督事件。
        input_event_count = sum(bool(tick_events) for tick_events in episode.feature_events)
        self.assertEqual(len(episode.teacher_post_ticks), input_event_count)
        self.assertGreater(len(episode.teacher_post_ticks), 0)
        self.assertEqual(episode.natural_spikes_during_train, 0)
        self.assertTrue(all(left < right for left, right in zip(episode.teacher_post_ticks, episode.teacher_post_ticks[1:])))

    def test_fixed_feature_fingerprint_and_inference_weights_are_frozen(self):
        network = D2Network(init_seed=0)
        fixed_before = network.fixed_weight_fingerprint
        network.train_sample(self.sample.sample_id, self.sample.pixels, self.sample.label)
        fixed_after = network.fixed_weight_fingerprint
        self.assertEqual(fixed_before, fixed_after)
        weights_before = network.output_weights
        network.inference_sample(self.sample.sample_id, self.sample.pixels, self.sample.label)
        self.assertEqual(weights_before, network.output_weights)

    def test_inference_tie_and_all_zero_are_abstentions(self):
        self.assertEqual(D2Network._predict((0, 0, 0, 0, 0, 0, 0, 0, 0, 0)), -1)
        self.assertEqual(D2Network._predict((2, 0, 2, 0, 0, 0, 0, 0, 0, 0)), -1)
        self.assertEqual(D2Network._predict((0, 0, 3, 0, 1, 0, 0, 0, 0, 0)), 2)

    def test_training_ledger_entries_have_replayable_teacher_evidence(self):
        network = D2Network(init_seed=0)
        network.train_sample(self.sample.sample_id, self.sample.pixels, self.sample.label)
        validate_training_ledger(network.ledger)
        self.assertEqual(len(network.ledger), 10)
        self.assertTrue(all(entry["modulator"] in (-1, 1) for entry in network.ledger))

    def test_runner_emits_auditable_metrics_and_training_counters(self):
        result = run_d2_experiment(
            ROOT / "digit8x8_fixture.json",
            ROOT / "digit8x8_manifest.json",
            epochs=1,
            seed=0,
        )
        model = result["models"]["d2_teacher"]
        validate_metrics(model["validation"])
        validate_metrics(model["test"])
        validate_training_summary(model["ledger"])


if __name__ == "__main__":
    unittest.main()
