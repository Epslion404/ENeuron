from __future__ import annotations

import copy
import hashlib
import logging
import random
import unittest
from collections import Counter
from types import SimpleNamespace

from g4_benchmark import (
    assert_learning_state_frozen,
    build_manifest,
    build_temporal_symbols,
    canonical_json_bytes,
    capture_learning_state,
    derive_seed,
    example_hash,
    input_hash,
    permutation_seed,
    permute_labels,
    strict_decode,
    validate_split_isolation,
)


LOGGER = logging.getLogger("test_g4_benchmark")


def _rotated_temporal_symbols(motif: str, phase: int) -> tuple[str, ...]:
    rotated = motif[phase:] + motif[:phase]
    return tuple(rotated + rotated[:2])


def _ngram_histogram(symbols: tuple[str, ...], width: int) -> tuple[tuple[str, int], ...]:
    counts = Counter("".join(symbols[index : index + width]) for index in range(len(symbols) - width + 1))
    return tuple(sorted(counts.items()))


def _sample(*, split: str, sample_id: int, label: int, tick_offset: int = 0) -> dict[str, object]:
    return {
        "input": {
            "episode_ticks": 64,
            "events": [[tick_offset + 2, 0], [tick_offset + 7, 2]],
        },
        "label": label,
        "split": split,
        "sample_id": sample_id,
        "seed": 1000 + sample_id,
        "time_skeleton_id": f"skeleton-{sample_id}",
    }


class SeedDerivationTests(unittest.TestCase):
    def test_derive_seed_has_frozen_golden_vector(self) -> None:
        seed = derive_seed(
            123456789,
            task="temporal",
            split="train",
            model_seed=7,
            purpose="dataset",
            index=0,
        )
        self.assertEqual(seed, 12777466888667374808)

    def test_derive_seed_is_deterministic_and_preserves_global_rng(self) -> None:
        random.seed(91)
        before = random.getstate()
        first = derive_seed(5, task="xor", split="validation", model_seed=3, purpose="dataset", index=2)
        second = derive_seed(5, task="xor", split="validation", model_seed=3, purpose="dataset", index=2)
        self.assertEqual(first, second)
        self.assertEqual(random.getstate(), before)

    def test_derive_seed_separates_each_domain_field(self) -> None:
        cases = (
            dict(task="temporal", split="train", model_seed=7, purpose="dataset", index=0),
            dict(task="spatial", split="train", model_seed=7, purpose="dataset", index=0),
            dict(task="temporal", split="validation", model_seed=7, purpose="dataset", index=0),
            dict(task="temporal", split="train", model_seed=8, purpose="dataset", index=0),
            dict(task="temporal", split="train", model_seed=7, purpose="shuffle", index=0),
            dict(task="temporal", split="train", model_seed=7, purpose="dataset", index=1),
        )
        seeds = {derive_seed(123456789, **case) for case in cases}
        self.assertEqual(len(seeds), len(cases))

    def test_derive_seed_rejects_unknown_or_ambiguous_domains(self) -> None:
        with self.assertRaises(ValueError):
            derive_seed(1, task="temporal", split="trian", model_seed=0, purpose="dataset", index=0)
        with self.assertRaises(ValueError):
            derive_seed(1, task="temporal", split="train", model_seed=0, purpose="unknown", index=0)
        with self.assertRaises(ValueError):
            derive_seed(1, task="temporal", split="train", model_seed=0, purpose="dataset", index=-1)


class CanonicalJsonAndHashTests(unittest.TestCase):
    def test_canonical_json_has_frozen_utf8_vector(self) -> None:
        value = {"z": "e\u0301", "a": [1, True, None, "\u4e2d"]}
        encoded = canonical_json_bytes(value)
        self.assertEqual(encoded, b'{"a":[1,true,null,"\xe4\xb8\xad"],"z":"\xc3\xa9"}')
        self.assertEqual(hashlib.sha256(encoded).hexdigest(), "c163a429f9111d2e745c133e96e8b6082a9bbbd93b7ac63fe59760be035174fa")

    def test_canonical_json_ignores_mapping_order_but_preserves_array_order(self) -> None:
        self.assertEqual(canonical_json_bytes({"b": 2, "a": 1}), canonical_json_bytes({"a": 1, "b": 2}))
        self.assertNotEqual(canonical_json_bytes([0, 1]), canonical_json_bytes([1, 0]))

    def test_canonical_json_preserves_type_boundaries_and_rejects_floats(self) -> None:
        self.assertNotEqual(canonical_json_bytes(1), canonical_json_bytes(True))
        self.assertNotEqual(canonical_json_bytes(1), canonical_json_bytes("1"))
        for value in (1.0, float("nan"), float("inf"), {1: "non-string key"}):
            with self.subTest(value=value), self.assertRaises((TypeError, ValueError)):
                canonical_json_bytes(value)

    def test_input_hash_excludes_provenance_and_label(self) -> None:
        first = _sample(split="train", sample_id=1, label=0)
        second = copy.deepcopy(first)
        second.update(split="iid_test", sample_id=999, label=1, seed=77, time_skeleton_id="other")
        self.assertEqual(input_hash(first), input_hash(second))
        self.assertNotEqual(example_hash(first), example_hash(second))

    def test_input_and_example_hash_change_for_semantic_changes(self) -> None:
        first = _sample(split="train", sample_id=1, label=0)
        changed_input = copy.deepcopy(first)
        changed_input["input"]["events"][0][0] += 1  # type: ignore[index]
        changed_label = copy.deepcopy(first)
        changed_label["label"] = 1
        self.assertNotEqual(input_hash(first), input_hash(changed_input))
        self.assertNotEqual(example_hash(first), example_hash(changed_label))


class StrictDecoderTests(unittest.TestCase):
    def test_strict_decoder_selects_only_the_unique_larger_count(self) -> None:
        self.assertEqual(strict_decode(1, 0), 0)
        self.assertEqual(strict_decode(0, 1), 1)
        self.assertEqual(strict_decode(17, 4), 0)
        self.assertEqual(strict_decode(8, 21), 1)

    def test_strict_decoder_abstains_on_zero_and_nonzero_ties(self) -> None:
        self.assertEqual(strict_decode(0, 0), -1)
        self.assertEqual(strict_decode(3, 3), -1)

    def test_strict_decoder_rejects_invalid_counts(self) -> None:
        for counts in ((-1, 0), (0, -1), (1.0, 0), (True, 0), ("1", 0)):
            with self.subTest(counts=counts), self.assertRaises((TypeError, ValueError)):
                strict_decode(*counts)


class EvaluationPermutationTests(unittest.TestCase):
    def test_permutation_seed_has_frozen_vector_and_no_mode_argument(self) -> None:
        seed = permutation_seed(
            123456789,
            task="temporal",
            split="iid_test",
            model_seed=7,
            permutation_index=3,
        )
        self.assertEqual(seed, 16885001173579066535)

    def test_permutation_seed_separates_each_registered_domain(self) -> None:
        seeds = {
            permutation_seed(9, task=task, split=split, model_seed=model_seed, permutation_index=index)
            for task, split, model_seed, index in (
                ("temporal", "iid_test", 1, 0),
                ("xor", "iid_test", 1, 0),
                ("temporal", "ood_test", 1, 0),
                ("temporal", "iid_test", 2, 0),
                ("temporal", "iid_test", 1, 1),
            )
        }
        self.assertEqual(len(seeds), 5)

    def test_permute_labels_is_deterministic_bijective_and_non_mutating(self) -> None:
        labels = [0, 1] * 16
        before = list(labels)
        first = permute_labels(labels, 73)
        second = permute_labels(labels, 73)
        self.assertEqual(first, second)
        self.assertEqual(Counter(first), Counter(labels))
        self.assertEqual(labels, before)
        self.assertIsNot(first, labels)

    def test_permute_labels_preserves_global_rng_and_rejects_tiny_inputs(self) -> None:
        random.seed(123)
        before = random.getstate()
        permute_labels([0, 1, 0, 1], 11)
        self.assertEqual(random.getstate(), before)
        for labels in ([], [0]):
            with self.subTest(labels=labels), self.assertRaises(ValueError):
                permute_labels(labels, 11)


class TemporalMotifContractTests(unittest.TestCase):
    MOTIFS = {0: "AABABABB", 1: "AABBABAB"}

    def test_temporal_golden_vectors_cover_phase_boundaries(self) -> None:
        golden = {
            (0, 0): tuple("AABABABBAA"),
            (0, 1): tuple("ABABABBAAB"),
            (0, 7): tuple("BAABABABBA"),
            (1, 0): tuple("AABBABABAA"),
            (1, 1): tuple("ABBABABAAB"),
            (1, 7): tuple("BAABBABABA"),
        }
        for key, expected in golden.items():
            with self.subTest(label=key[0], phase=key[1]):
                self.assertEqual(build_temporal_symbols(*key), expected)

    def test_temporal_all_label_phase_pairs_follow_the_ten_symbol_rule(self) -> None:
        for label, motif in self.MOTIFS.items():
            for phase in range(8):
                with self.subTest(label=label, phase=phase):
                    symbols = build_temporal_symbols(label, phase)
                    self.assertEqual(symbols, _rotated_temporal_symbols(motif, phase))
                    self.assertEqual(len(symbols), 10)
                    self.assertEqual(symbols[-2:], symbols[:2])

    def test_temporal_classes_are_disjoint_and_first_differ_at_four_grams(self) -> None:
        classes = {
            label: {build_temporal_symbols(label, phase) for phase in range(8)}
            for label in self.MOTIFS
        }
        self.assertTrue(classes[0].isdisjoint(classes[1]))
        for width in range(1, 4):
            left = Counter(_ngram_histogram(symbols, width) for symbols in classes[0])
            right = Counter(_ngram_histogram(symbols, width) for symbols in classes[1])
            self.assertEqual(left, right, f"{width}-gram distribution leaked label")
        left_four = Counter(_ngram_histogram(symbols, 4) for symbols in classes[0])
        right_four = Counter(_ngram_histogram(symbols, 4) for symbols in classes[1])
        self.assertNotEqual(left_four, right_four)

    def test_temporal_low_order_position_bigram_and_half_counts_match(self) -> None:
        classes = {
            label: [build_temporal_symbols(label, phase) for phase in range(8)]
            for label in self.MOTIFS
        }
        for position in range(10):
            self.assertEqual(
                Counter(symbols[position] for symbols in classes[0]),
                Counter(symbols[position] for symbols in classes[1]),
            )
        for position in range(9):
            self.assertEqual(
                Counter(symbols[position : position + 2] for symbols in classes[0]),
                Counter(symbols[position : position + 2] for symbols in classes[1]),
            )
        self.assertEqual(
            Counter((symbols[:5].count("A"), symbols[5:].count("A")) for symbols in classes[0]),
            Counter((symbols[:5].count("A"), symbols[5:].count("A")) for symbols in classes[1]),
        )

    def test_temporal_builder_rejects_invalid_label_and_phase(self) -> None:
        for label, phase in ((-1, 0), (2, 0), (0, -1), (0, 8), (True, 0)):
            with self.subTest(label=label, phase=phase), self.assertRaises((TypeError, ValueError)):
                build_temporal_symbols(label, phase)


class SplitIsolationAndManifestTests(unittest.TestCase):
    def test_split_isolation_accepts_unique_inputs(self) -> None:
        splits = {
            "train": [_sample(split="train", sample_id=1, label=0, tick_offset=0)],
            "validation": [_sample(split="validation", sample_id=2, label=1, tick_offset=1)],
            "iid_test": [_sample(split="iid_test", sample_id=3, label=0, tick_offset=2)],
        }
        validate_split_isolation(splits)

    def test_split_isolation_detects_duplicates_despite_metadata_or_label_changes(self) -> None:
        train = _sample(split="train", sample_id=1, label=0)
        leaked = copy.deepcopy(train)
        leaked.update(split="iid_test", sample_id=999, label=1, seed=9999, time_skeleton_id="renamed")
        with self.assertRaises(ValueError):
            validate_split_isolation({"train": [train], "iid_test": [leaked]})

    def test_split_isolation_detects_duplicates_within_one_split(self) -> None:
        first = _sample(split="train", sample_id=1, label=0)
        duplicate = copy.deepcopy(first)
        duplicate["sample_id"] = 2
        with self.assertRaises(ValueError):
            validate_split_isolation({"train": [first, duplicate]})

    def test_manifest_is_deterministic_and_records_required_provenance(self) -> None:
        splits = {
            "train": [_sample(split="train", sample_id=1, label=0, tick_offset=0)],
            "iid_test": [_sample(split="iid_test", sample_id=2, label=1, tick_offset=1)],
        }
        manifest = build_manifest(splits, generator_version="g4-v3", source_sha256="a" * 64)
        repeated = build_manifest(copy.deepcopy(splits), generator_version="g4-v3", source_sha256="a" * 64)
        self.assertEqual(manifest, repeated)
        self.assertEqual(manifest["generator_version"], "g4-v3")
        self.assertEqual(manifest["source_sha256"], "a" * 64)
        self.assertEqual(set(manifest["splits"]), set(splits))
        for split_name, entries in manifest["splits"].items():
            self.assertEqual(len(entries), len(splits[split_name]))
            self.assertIn("input_hash", entries[0])
            self.assertIn("example_hash", entries[0])


class LearningStateFreezeInterfaceTests(unittest.TestCase):
    @staticmethod
    def _network_state() -> SimpleNamespace:
        neurons = []
        for index in range(4):
            neurons.append(
                SimpleNamespace(
                    weights=[index + 1, index + 2],
                    pre_trace=[10 + index, 20 + index],
                    post_trace=30 + index,
                    eligibility=[40 + index, 50 + index],
                    eligibility_snapshot=[60 + index, 70 + index],
                    threshold=4 + index,
                    current=80 + index,
                    membrane=90 + index,
                    refractory=index,
                    spike_count=100 + index,
                )
            )
        return SimpleNamespace(
            neurons=neurons,
            pending_commits={3: SimpleNamespace(commit_id=3, weight_epoch=8)},
            next_commit_to_apply=3,
            max_captured_commit_id=3,
            weight_epoch=8,
        )

    def test_capture_learning_state_excludes_inference_dynamic_fields(self) -> None:
        network = self._network_state()
        before = capture_learning_state(network)
        for neuron in network.neurons:
            neuron.current += 1
            neuron.membrane += 2
            neuron.refractory += 1
            neuron.spike_count += 3
        after = capture_learning_state(network)
        self.assertEqual(before, after)
        assert_learning_state_frozen(before, after)

    def test_freeze_interface_detects_each_learning_state_family(self) -> None:
        mutators = {
            "weights": lambda state: state.neurons[0].weights.__setitem__(0, 7),
            "pre_trace": lambda state: state.neurons[0].pre_trace.__setitem__(0, 99),
            "post_trace": lambda state: setattr(state.neurons[0], "post_trace", 99),
            "eligibility": lambda state: state.neurons[0].eligibility.__setitem__(0, 99),
            "eligibility_snapshot": lambda state: state.neurons[0].eligibility_snapshot.__setitem__(0, 99),
            "threshold": lambda state: setattr(state.neurons[0], "threshold", 99),
            "pending_commit": lambda state: state.pending_commits.clear(),
            "commit_cursor": lambda state: setattr(state, "next_commit_to_apply", None),
            "weight_epoch": lambda state: setattr(state, "weight_epoch", 9),
        }
        for name, mutate in mutators.items():
            with self.subTest(field=name):
                network = self._network_state()
                before = capture_learning_state(network)
                mutate(network)
                after = capture_learning_state(network)
                with self.assertRaises(AssertionError):
                    assert_learning_state_frozen(before, after)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    LOGGER.info("running G4 benchmark contract tests")
    unittest.main()
