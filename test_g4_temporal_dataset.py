"""G4 V3 Temporal 数据生成、合同校验和 manifest 的测试先行规格。"""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import logging
import statistics
import tempfile
import unittest
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import g4_benchmark


LOGGER = logging.getLogger(__name__)
MASTER_SEED = 0x473454454D504F52
MODEL_SEED = 0x4E45
EXPECTED_SPLIT_SIZES = {
    "calibration": 128,
    "train": 32,
    "validation": 128,
    "iid_test": 512,
    "ood_test": 512,
}
EXPECTED_MANIFEST_VERSION = "g4_temporal_dataset_v2"
IID_SPLITS = frozenset({"calibration", "train", "validation", "iid_test"})
SOURCE_PATH = Path(g4_benchmark.__file__).resolve()
PUBLIC_INTERFACES = (
    "SPLIT_SIZES",
    "generate_temporal_split",
    "validate_temporal_contract",
    "write_temporal_manifest",
)
BASE_MOTIFS = {
    0: (0, 0, 2, 0, 2, 0, 2, 2),
    1: (0, 0, 2, 2, 0, 2, 0, 2),
}


def require_sample(testcase: unittest.TestCase, value: object) -> dict[str, Any]:
    testcase.assertIsInstance(value, Mapping, "Temporal sample 必须是 JSON-ready mapping")
    sample = dict(value)  # type: ignore[arg-type]
    required = {
        "split",
        "label",
        "phase",
        "time_skeleton_id",
        "domain",
        "burst_width",
        "symbols",
        "starts",
        "intervals",
        "input",
    }
    testcase.assertEqual(required - sample.keys(), set())
    testcase.assertIsInstance(sample["input"], Mapping)
    testcase.assertEqual({"episode_ticks", "events"} - sample["input"].keys(), set())
    return sample


def split_digest(samples: Sequence[Mapping[str, Any]]) -> str:
    """冻结 manifest 中 split SHA-256 的计算对象和排序方式。"""
    hashes = sorted(g4_benchmark.input_hash(sample) for sample in samples)
    return hashlib.sha256(g4_benchmark.canonical_json_bytes(hashes)).hexdigest()


def example_split_digest(samples: Sequence[Mapping[str, Any]]) -> str:
    hashes = sorted(g4_benchmark.example_hash(sample) for sample in samples)
    return hashlib.sha256(g4_benchmark.canonical_json_bytes(hashes)).hexdigest()


def rebuild_events(sample: dict[str, Any]) -> None:
    sample["input"]["events"] = [
        [start + offset, channel]
        for start, channel in zip(sample["starts"], sample["symbols"])
        for offset in range(sample["burst_width"])
    ]


def replace_intervals(sample: dict[str, Any], intervals: Sequence[int]) -> None:
    starts = [0]
    for interval in intervals:
        starts.append(starts[-1] + interval)
    sample["starts"] = starts
    sample["intervals"] = list(intervals)
    rebuild_events(sample)


class TemporalPublicInterfaceTests(unittest.TestCase):
    def test_formal_temporal_dataset_public_interfaces_exist(self) -> None:
        missing = [name for name in PUBLIC_INTERFACES if not hasattr(g4_benchmark, name)]
        self.assertEqual(missing, [], f"g4_benchmark 缺少公开接口: {', '.join(missing)}")


class TemporalDatasetContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = g4_benchmark

    def setUp(self) -> None:
        missing = [name for name in PUBLIC_INTERFACES if not hasattr(self.module, name)]
        if missing:
            self.skipTest("等待 Temporal 公开接口: " + ", ".join(missing))

    def generate(self, split: str, burst_width: int = 2) -> list[dict[str, Any]]:
        result = self.module.generate_temporal_split(
            MASTER_SEED,
            split,
            burst_width,
        )
        self.assertIsInstance(result, Sequence)
        self.assertNotIsInstance(result, (str, bytes))
        return [require_sample(self, sample) for sample in result]

    def generate_all(self, burst_width: int = 2) -> dict[str, list[dict[str, Any]]]:
        return {
            split: self.generate(split, burst_width)
            for split in EXPECTED_SPLIT_SIZES
        }

    def validate(
        self,
        splits: Mapping[str, Sequence[Mapping[str, Any]]],
        *,
        burst_width: int = 2,
        master_seed: int = MASTER_SEED,
    ) -> None:
        self.module.validate_temporal_contract(
            splits,
            master_seed=master_seed,
            expected_burst_width=burst_width,
        )

    def assert_sample_geometry(
        self,
        sample: Mapping[str, Any],
        split: str,
        burst_width: int,
    ) -> None:
        self.assertEqual(sample["split"], split)
        self.assertEqual(sample["burst_width"], burst_width)
        self.assertIn(sample["label"], (0, 1))
        self.assertIn(sample["phase"], range(8))
        expected_domain = "iid" if split in IID_SPLITS else "ood"
        self.assertEqual(sample["domain"], expected_domain)

        label = int(sample["label"])
        phase = int(sample["phase"])
        base = BASE_MOTIFS[label]
        rotated = base[phase:] + base[:phase]
        expected_symbols = rotated + rotated[:2]
        symbols = tuple(sample["symbols"])
        self.assertEqual(symbols, expected_symbols)
        self.assertEqual(len(symbols), 10)
        self.assertTrue(set(symbols).issubset({0, 2}))

        starts = tuple(sample["starts"])
        intervals = tuple(sample["intervals"])
        self.assertEqual(len(starts), 10)
        self.assertEqual(len(intervals), 9)
        self.assertEqual(intervals, tuple(b - a for a, b in zip(starts, starts[1:])))
        self.assertEqual(tuple(sorted(starts)), starts)
        self.assertGreaterEqual(starts[0], 0)
        self.assertLessEqual(starts[-1] + burst_width, 64)
        for current, following in zip(starts, starts[1:]):
            self.assertGreaterEqual(following - current, burst_width)

        input_data = sample["input"]
        self.assertEqual(input_data["episode_ticks"], 64)
        events = [tuple(event) for event in input_data["events"]]
        expected_events = [
            (start + offset, channel)
            for start, channel in zip(starts, symbols)
            for offset in range(burst_width)
        ]
        self.assertEqual(events, expected_events)
        self.assertEqual(len(events), 10 * burst_width)
        self.assertTrue(all(channel in (0, 2) for _, channel in events))
        self.assertTrue(all(0 <= tick < 64 for tick, _ in events))

        input_hash = self.module.input_hash(sample)
        self.assertIsInstance(input_hash, str)
        self.assertRegex(input_hash, r"^[0-9a-f]{64}$")

    def test_split_sizes_and_public_constant_are_frozen(self) -> None:
        self.assertEqual(dict(self.module.SPLIT_SIZES), EXPECTED_SPLIT_SIZES)
        for split, expected_count in EXPECTED_SPLIT_SIZES.items():
            with self.subTest(split=split):
                self.assertEqual(len(self.generate(split)), expected_count)

    def test_each_split_balances_label_phase_and_pairs_counterfactual_skeletons(self) -> None:
        for split, samples in self.generate_all().items():
            with self.subTest(split=split):
                frequency = Counter((sample["label"], sample["phase"]) for sample in samples)
                self.assertEqual(set(frequency), {(label, phase) for label in (0, 1) for phase in range(8)})
                self.assertEqual(len(set(frequency.values())), 1)

                pairs: dict[tuple[int, object], list[dict[str, Any]]] = defaultdict(list)
                for sample in samples:
                    pairs[(int(sample["phase"]), sample["time_skeleton_id"])].append(sample)
                self.assertEqual(len(pairs), len(samples) // 2)
                for pair in pairs.values():
                    self.assertEqual({sample["label"] for sample in pair}, {0, 1})
                    self.assertEqual(len(pair), 2)
                    self.assertEqual(pair[0]["starts"], pair[1]["starts"])
                    self.assertEqual(pair[0]["intervals"], pair[1]["intervals"])

    def test_all_legal_burst_widths_produce_valid_64_tick_event_streams(self) -> None:
        for burst_width in range(1, 5):
            samples = self.generate("calibration", burst_width)
            with self.subTest(burst_width=burst_width):
                for sample in samples:
                    self.assert_sample_geometry(sample, "calibration", burst_width)

    def test_invalid_burst_widths_are_rejected(self) -> None:
        for burst_width in (0, 5):
            with self.subTest(burst_width=burst_width):
                with self.assertRaises(ValueError):
                    self.module.generate_temporal_split(
                        MASTER_SEED,
                        "train",
                        burst_width,
                    )

    def test_input_hashes_are_unique_within_and_across_splits(self) -> None:
        all_splits = self.generate_all()
        seen: set[str] = set()
        for split, samples in all_splits.items():
            hashes = [self.module.input_hash(sample) for sample in samples]
            with self.subTest(split=split):
                self.assertEqual(len(hashes), len(set(hashes)))
                self.assertTrue(seen.isdisjoint(hashes))
            seen.update(hashes)
        self.assertEqual(len(seen), sum(EXPECTED_SPLIT_SIZES.values()))

    def test_generation_is_deterministic_and_independent_of_split_call_order(self) -> None:
        forward = {
            split: self.generate(split)
            for split in EXPECTED_SPLIT_SIZES
        }
        reverse = {
            split: self.generate(split)
            for split in reversed(tuple(EXPECTED_SPLIT_SIZES))
        }
        for split in EXPECTED_SPLIT_SIZES:
            with self.subTest(split=split):
                forward_bytes = self.module.canonical_json_bytes(
                    sorted(forward[split], key=self.module.input_hash)
                )
                reverse_bytes = self.module.canonical_json_bytes(
                    sorted(reverse[split], key=self.module.input_hash)
                )
                self.assertEqual(forward_bytes, reverse_bytes)

    def test_formal_dataset_is_shared_across_model_seeds_for_paired_evaluation(self) -> None:
        """正式数据 API 不接收模型 seed，模型随机性无法改变共享测试集。"""
        parameters = inspect.signature(self.module.generate_temporal_split).parameters
        self.assertEqual(tuple(parameters), ("master_seed", "split", "burst_width"))

    def test_ood_uses_a_distinct_stretched_interval_domain_without_label_leakage(self) -> None:
        all_splits = self.generate_all()
        iid_intervals = [
            interval
            for split in IID_SPLITS
            for sample in all_splits[split]
            for interval in sample["intervals"]
        ]
        ood_intervals = [
            interval
            for sample in all_splits["ood_test"]
            for interval in sample["intervals"]
        ]
        self.assertTrue(set(iid_intervals).isdisjoint(ood_intervals))
        self.assertGreater(statistics.mean(ood_intervals), statistics.mean(iid_intervals))

        for split, samples in all_splits.items():
            with self.subTest(split=split):
                by_label = {
                    label: Counter(
                        tuple(sample["intervals"])
                        for sample in samples
                        if sample["label"] == label
                    )
                    for label in (0, 1)
                }
                self.assertEqual(by_label[0], by_label[1])

    def test_validator_accepts_all_five_formal_splits(self) -> None:
        splits = self.generate_all()
        self.assertIsNone(self.validate(splits))

    def test_validator_rejects_tail_phase_episode_burst_channel_and_pairing_errors(self) -> None:
        valid = self.generate_all()

        def broken_tail(splits: dict[str, list[dict[str, Any]]]) -> None:
            symbols = list(splits["train"][0]["symbols"])
            symbols[-1] = 2 if symbols[-1] == 0 else 0
            splits["train"][0]["symbols"] = symbols

        def broken_phase(splits: dict[str, list[dict[str, Any]]]) -> None:
            splits["train"][0]["phase"] = 8

        def broken_episode(splits: dict[str, list[dict[str, Any]]]) -> None:
            splits["validation"][0]["input"]["episode_ticks"] = 63

        def broken_burst(splits: dict[str, list[dict[str, Any]]]) -> None:
            splits["calibration"][0]["burst_width"] = 5

        def broken_channel(splits: dict[str, list[dict[str, Any]]]) -> None:
            events = [list(event) for event in splits["iid_test"][0]["input"]["events"]]
            events[0][1] = 1
            splits["iid_test"][0]["input"]["events"] = events

        def broken_pair(splits: dict[str, list[dict[str, Any]]]) -> None:
            splits["ood_test"][0]["time_skeleton_id"] = "unpaired-skeleton"

        mutations = {
            "tail": broken_tail,
            "phase": broken_phase,
            "episode": broken_episode,
            "burst": broken_burst,
            "channel": broken_channel,
            "skeleton_pair": broken_pair,
        }
        for name, mutate in mutations.items():
            with self.subTest(error=name):
                damaged = copy.deepcopy(valid)
                mutate(damaged)
                with self.assertRaises((AssertionError, ValueError)):
                    self.validate(damaged)

    def test_input_schema_is_exact_and_rejects_label_hint(self) -> None:
        damaged = self.generate_all()
        damaged["train"][0]["input"]["label_hint"] = damaged["train"][0]["label"]
        with self.assertRaises(ValueError):
            self.validate(damaged)

    def test_duplicate_event_stream_with_nonce_is_still_split_leakage(self) -> None:
        train = self.generate("train")[0]
        leaked = copy.deepcopy(train)
        leaked["split"] = "validation"
        leaked["input"]["nonce"] = "must-not-change-semantic-input-hash"
        self.assertEqual(self.module.input_hash(train), self.module.input_hash(leaked))
        with self.assertRaises(ValueError):
            self.module.validate_split_isolation({"train": [train], "validation": [leaked]})

    def test_burst_width_is_one_frozen_global_value(self) -> None:
        valid = self.generate_all(burst_width=2)
        self.validate(valid, burst_width=2)

        label_leak = copy.deepcopy(valid)
        for samples in label_leak.values():
            for sample in samples:
                if sample["label"] == 0:
                    sample["burst_width"] = 1
                    rebuild_events(sample)
        with self.assertRaises(ValueError):
            self.validate(label_leak, burst_width=2)

        split_leak = self.generate_all(burst_width=2)
        split_leak["train"] = self.generate("train", burst_width=1)
        with self.assertRaises(ValueError):
            self.validate(split_leak, burst_width=2)

    def test_validator_enforces_frozen_iid_and_ood_interval_domains(self) -> None:
        mutations = (("train", 3), ("ood_test", 8))
        for split, illegal_interval in mutations:
            with self.subTest(split=split, interval=illegal_interval):
                damaged = self.generate_all()
                skeleton_id = damaged[split][0]["time_skeleton_id"]
                for sample in damaged[split]:
                    if sample["time_skeleton_id"] == skeleton_id:
                        intervals = list(sample["intervals"])
                        intervals[0] = illegal_interval
                        replace_intervals(sample, intervals)
                with self.assertRaises(ValueError):
                    self.validate(damaged)

    def test_validator_authenticates_seed_sample_id_skeleton_id_and_schema_provenance(self) -> None:
        def forged_seed(splits: dict[str, list[dict[str, Any]]]) -> None:
            splits["train"][0]["seed"] = 0

        def forged_sample_id(splits: dict[str, list[dict[str, Any]]]) -> None:
            splits["train"][0]["sample_id"] = "forged-sample"

        def forged_skeleton_id(splits: dict[str, list[dict[str, Any]]]) -> None:
            original = splits["train"][0]["time_skeleton_id"]
            for sample in splits["train"]:
                if sample["time_skeleton_id"] == original:
                    sample["time_skeleton_id"] = "forged-skeleton"

        def forged_provenance(splits: dict[str, list[dict[str, Any]]]) -> None:
            splits["train"][0]["provenance"] = {"generator": "forged"}

        mutations = {
            "seed": forged_seed,
            "sample_id": forged_sample_id,
            "skeleton_id": forged_skeleton_id,
            "provenance": forged_provenance,
        }
        for name, mutate in mutations.items():
            with self.subTest(field=name):
                damaged = self.generate_all()
                mutate(damaged)
                with self.assertRaises(ValueError):
                    self.validate(damaged)

    def test_each_skeleton_id_occurs_exactly_twice_and_is_the_direct_pair_key(self) -> None:
        damaged = self.generate_all()
        by_id: dict[object, list[dict[str, Any]]] = defaultdict(list)
        for sample in damaged["train"]:
            by_id[sample["time_skeleton_id"]].append(sample)
        first_pair, second_pair = list(by_id.values())[:2]
        self.assertNotEqual(first_pair[0]["phase"], second_pair[0]["phase"])
        reused_id = first_pair[0]["time_skeleton_id"]
        for sample in second_pair:
            sample["time_skeleton_id"] = reused_id
        with self.assertRaises(ValueError):
            self.validate(damaged)

    def test_validator_rejects_wrong_interval_domains_and_label_dependent_metadata(self) -> None:
        valid = self.generate_all()

        wrong_iid = copy.deepcopy(valid)
        pair = wrong_iid["train"][:2]
        starts = [0]
        intervals = [3] * 9
        for interval in intervals:
            starts.append(starts[-1] + interval)
        for sample in pair:
            sample["starts"] = starts
            sample["intervals"] = intervals
            sample["input"]["events"] = [
                [start + offset, channel]
                for start, channel in zip(starts, sample["symbols"])
                for offset in range(sample["burst_width"])
            ]
        with self.assertRaises((AssertionError, ValueError)):
            self.validate(wrong_iid)

        wrong_ood = copy.deepcopy(valid)
        ood_pair = wrong_ood["ood_test"][:2]
        ood_starts = [0]
        ood_intervals = [5] * 9
        for interval in ood_intervals:
            ood_starts.append(ood_starts[-1] + interval)
        for sample in ood_pair:
            sample["starts"] = ood_starts
            sample["intervals"] = ood_intervals
            sample["input"]["events"] = [
                [start + offset, channel]
                for start, channel in zip(ood_starts, sample["symbols"])
                for offset in range(sample["burst_width"])
            ]
        with self.assertRaises((AssertionError, ValueError)):
            self.validate(wrong_ood)

        label_leak = copy.deepcopy(valid)
        label_leak["validation"][0]["seed"] += 1
        with self.assertRaises((AssertionError, ValueError)):
            self.validate(label_leak)


class TemporalManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = g4_benchmark

    def setUp(self) -> None:
        missing = [name for name in PUBLIC_INTERFACES if not hasattr(self.module, name)]
        if missing:
            self.skipTest("等待 Temporal 公开接口: " + ", ".join(missing))

    def generate_all(self) -> dict[str, list[dict[str, Any]]]:
        return {
            split: [require_sample(self, sample) for sample in self.module.generate_temporal_split(
                MASTER_SEED,
                split,
                2,
            )]
            for split in EXPECTED_SPLIT_SIZES
        }

    def test_manifest_is_canonical_complete_and_byte_reproducible(self) -> None:
        splits = self.generate_all()
        with tempfile.TemporaryDirectory(prefix="eneuron_temporal_manifest_") as temp_dir:
            root = Path(temp_dir)
            first = root / "manifest_first.json"
            second = root / "manifest_second.json"

            LOGGER.info("写入两份 Temporal manifest 以检查字节级复现")
            self.module.write_temporal_manifest(
                first,
                splits,
                master_seed=MASTER_SEED,
                burst_width=2,
            )
            self.module.write_temporal_manifest(
                second,
                splits,
                master_seed=MASTER_SEED,
                burst_width=2,
            )

            first_bytes = first.read_bytes()
            self.assertEqual(first_bytes, second.read_bytes())
            manifest = json.loads(first_bytes.decode("utf-8"))
            self.assertEqual(first_bytes, self.module.canonical_json_bytes(manifest))
            self.assertEqual(manifest["generator_version"], EXPECTED_MANIFEST_VERSION)
            self.assertEqual(manifest["task"], "temporal")
            self.assertEqual(manifest["episode_ticks"], 64)
            self.assertEqual(manifest["burst_width"], 2)
            self.assertEqual(
                manifest["source_sha256"],
                hashlib.sha256(Path(self.module.__file__).resolve().read_bytes()).hexdigest(),
            )
            self.assertEqual(
                manifest["evaluation_policy"],
                {
                    "dataset_shared_across_model_seeds": True,
                    "statistical_unit": "paired_model_seed",
                },
            )
            self.assertEqual(
                manifest["seed_domain"],
                {
                    "algorithm": "sha256-canonical-json-first-64-bit",
                    "master_seed": MASTER_SEED,
                    "model_seed": None,
                    "purpose": "dataset",
                    "split_seeds": {
                        split: self.module.derive_seed(
                            MASTER_SEED,
                            task="temporal",
                            split=split,
                            model_seed=None,
                            purpose="dataset",
                        )
                        for split in sorted(EXPECTED_SPLIT_SIZES)
                    },
                },
            )
            self.assertEqual(set(manifest["splits"]), set(EXPECTED_SPLIT_SIZES))

            for split, expected_count in EXPECTED_SPLIT_SIZES.items():
                with self.subTest(split=split):
                    entry = manifest["splits"][split]
                    expected_input_hashes = sorted(self.module.input_hash(sample) for sample in splits[split])
                    expected_example_hashes = sorted(self.module.example_hash(sample) for sample in splits[split])
                    self.assertEqual(entry["count"], expected_count)
                    self.assertEqual(entry["input_hashes"], expected_input_hashes)
                    self.assertEqual(entry["input_sha256"], split_digest(splits[split]))
                    self.assertEqual(entry["example_hashes"], expected_example_hashes)
                    self.assertEqual(
                        entry["example_sha256"],
                        hashlib.sha256(
                            self.module.canonical_json_bytes(expected_example_hashes)
                        ).hexdigest(),
                    )

    def test_manifest_source_path_cannot_be_spoofed(self) -> None:
        splits = self.generate_all()
        with tempfile.TemporaryDirectory(prefix="eneuron_temporal_manifest_") as temp_dir:
            output = Path(temp_dir) / "manifest.json"
            with self.assertRaises(TypeError):
                self.module.write_temporal_manifest(
                    output,
                    splits,
                    Path(temp_dir) / "forged_source.py",
                    master_seed=MASTER_SEED,
                    burst_width=2,
                )

    def test_checked_in_development_manifest_matches_current_generator(self) -> None:
        splits = self.generate_all()
        checked_in = Path(__file__).resolve().parent / "g4_temporal_development_manifest.json"
        with tempfile.TemporaryDirectory(prefix="eneuron_temporal_manifest_") as temp_dir:
            regenerated = Path(temp_dir) / "manifest.json"
            self.module.write_temporal_manifest(
                regenerated,
                splits,
                master_seed=MASTER_SEED,
                burst_width=2,
            )
            self.assertEqual(checked_in.read_bytes(), regenerated.read_bytes())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    unittest.main()
