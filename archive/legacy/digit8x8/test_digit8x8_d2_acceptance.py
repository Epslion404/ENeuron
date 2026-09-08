import unittest

from digit8x8_d2_acceptance import (
    AcceptanceError,
    aggregate_seeds,
    passes_clean_gate,
    passes_fixed_weight_negative_control,
    passes_label_shuffle_negative_control,
    passes_robustness_gate,
    passes_seed_gate,
    validate_metrics,
    validate_training_ledger,
    validate_training_summary,
)


def _metrics(*, balanced_accuracy=0.75, coverage=1.0, sample_count=10):
    confusion = [[0] * 10 for _ in range(10)]
    for index in range(round(sample_count * coverage)):
        label = index % 10
        confusion[label][label] += 1
    return {
        "sample_count": sample_count,
        "balanced_accuracy": balanced_accuracy,
        "accuracy": balanced_accuracy,
        "macro_f1": balanced_accuracy,
        "coverage": coverage,
        "abstain_rate": 1.0 - coverage,
        "confusion": confusion,
    }


class D2AcceptanceTests(unittest.TestCase):
    def test_metric_shape_rejects_incomplete_or_inconsistent_results(self):
        with self.assertRaises(AcceptanceError):
            validate_metrics({"coverage": 1.0})
        malformed = _metrics(sample_count=10)
        malformed["confusion"][0][0] = 2
        with self.assertRaises(AcceptanceError):
            validate_metrics(malformed)

    def test_clean_gate_requires_absolute_and_relative_performance(self):
        self.assertTrue(passes_clean_gate(_metrics(), no_learning_balanced_accuracy=0.60))
        self.assertFalse(passes_clean_gate(_metrics(balanced_accuracy=0.69), no_learning_balanced_accuracy=0.50))
        self.assertFalse(passes_clean_gate(_metrics(balanced_accuracy=0.75), no_learning_balanced_accuracy=0.66))
        self.assertFalse(passes_clean_gate(_metrics(coverage=0.89), no_learning_balanced_accuracy=0.50))

    def test_multi_seed_gate_cannot_pass_with_one_lucky_seed(self):
        aggregate = aggregate_seeds([_metrics(), _metrics(), _metrics(balanced_accuracy=0.40), _metrics(balanced_accuracy=0.30)])
        self.assertEqual(aggregate.passed_count, 2)
        self.assertFalse(passes_seed_gate(aggregate))
        strong = aggregate_seeds([_metrics()] * 8 + [_metrics(balanced_accuracy=0.40), _metrics(balanced_accuracy=0.30)])
        self.assertTrue(passes_seed_gate(strong))

    def test_label_shuffle_and_fixed_weight_controls_are_not_allowed_to_abstain(self):
        self.assertTrue(passes_label_shuffle_negative_control(_metrics(balanced_accuracy=0.15)))
        self.assertFalse(passes_label_shuffle_negative_control(_metrics(balanced_accuracy=0.15, coverage=0.50)))
        self.assertTrue(passes_fixed_weight_negative_control(_metrics(balanced_accuracy=0.70), _metrics(balanced_accuracy=0.65)))
        self.assertFalse(passes_fixed_weight_negative_control(_metrics(balanced_accuracy=0.80), _metrics(balanced_accuracy=0.65)))

    def test_robustness_gate_checks_drop_and_coverage(self):
        clean = _metrics(balanced_accuracy=0.80)
        self.assertTrue(passes_robustness_gate(clean, _metrics(balanced_accuracy=0.70)))
        self.assertFalse(passes_robustness_gate(clean, _metrics(balanced_accuracy=0.64)))
        self.assertFalse(passes_robustness_gate(clean, _metrics(balanced_accuracy=0.70, coverage=0.89)))

    def test_training_ledger_requires_teacher_evidence_and_real_change(self):
        entry = {
            "sample_id": 1,
            "layer": "output",
            "neuron": 2,
            "evidence": {"teacher_post_tick": 3, "eligibility": [4, -2, 0, 1]},
            "modulator": 1,
            "old_weights": [1, 2, 3, 4],
            "new_weights": [1, 3, 3, 4],
        }
        validate_training_ledger([entry])
        with_delta = dict(entry, delta=[0, 1, 0, 0], weight_min=-7, weight_max=7)
        validate_training_ledger([with_delta])
        bad_delta = dict(with_delta, delta=[0, 2, 0, 0])
        with self.assertRaises(AcceptanceError):
            validate_training_ledger([bad_delta])
        no_change = dict(entry, new_weights=entry["old_weights"])
        with self.assertRaises(AcceptanceError):
            validate_training_ledger([no_change])
        no_evidence = dict(entry, evidence=None)
        with self.assertRaises(AcceptanceError):
            validate_training_ledger([no_evidence])

    def test_training_summary_requires_teacher_activity_and_zero_direct_writes(self):
        validate_training_summary(
            {
                "teacher_posts": 10,
                "natural_posts_during_train": 0,
                "weight_updates": 10,
                "direct_weight_writes": 0,
            }
        )
        with self.assertRaises(AcceptanceError):
            validate_training_summary(
                {
                    "teacher_posts": 10,
                    "natural_posts_during_train": 0,
                    "weight_updates": 10,
                    "direct_weight_writes": 1,
                }
            )


if __name__ == "__main__":
    unittest.main()
