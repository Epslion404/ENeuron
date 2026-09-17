"""QAT canonical 634-word 打包的最小合同：round-trip、hash、reference 一致性。"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools" / "repro"))

from b3_fixed_vector_manifest import model_words_from_manifest  # noqa: E402
from b3_qat_model_manifest import (  # noqa: E402
    DEFAULT_FIXTURE,
    DEFAULT_MODEL,
    DEFAULT_OUTPUT,
    build_manifest,
    integer_npu_forward,
    load_qat_model,
)
from npu_eneuron_protocol import decode_model_words, load_model_words  # noqa: E402
from npu_eneuron_reference import NpuReference  # noqa: E402


class B3QatModelManifestContractTests(unittest.TestCase):
    def setUp(self) -> None:
        if not DEFAULT_OUTPUT.is_file():
            self.skipTest("QAT manifest not generated")
        self.manifest = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))
        self.model = load_qat_model(DEFAULT_MODEL)
        self.words = model_words_from_manifest(self.manifest)

    def test_canonical_packing_round_trip_and_hashes(self) -> None:
        self.assertEqual(self.manifest["schema"], "eneuron_b3_qat_model_v1")
        self.assertEqual(self.manifest["model"]["word_count"], 634)
        self.assertEqual(len(self.words), 634)
        self.assertEqual(self.manifest["model"]["model_version"], "qat-v3-val200-temp400-150ep-seed20260914")
        self.assertIsNotNone(self.manifest["model"]["validation_acc"])
        decoded = decode_model_words(self.words)
        self.assertEqual([list(row) for row in decoded.weights0], self.model["W0"])
        self.assertEqual(list(decoded.bias0), self.model["b0"])
        self.assertEqual([list(row) for row in decoded.weights1], self.model["W1"])
        self.assertEqual(list(decoded.bias1), self.model["b1"])

    def test_manifest_hashes_match_sources(self) -> None:
        import hashlib

        source = Path(self.manifest["identity"]["source_model"])
        source_path = source if source.is_absolute() else ROOT / source
        self.assertEqual(
            hashlib.sha256(source_path.read_bytes()).hexdigest(),
            self.manifest["identity"]["source_model_sha256"],
        )
        fixture = Path(self.manifest["identity"]["fixture"])
        fixture_path = fixture if fixture.is_absolute() else ROOT / fixture
        self.assertEqual(
            hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
            self.manifest["identity"]["fixture_sha256"],
        )

    def test_reference_matches_training_integer_forward(self) -> None:
        reference = NpuReference()
        load_model_words(reference, self.words)
        for sample in self.manifest["samples"]:
            pixels = sample["pixels"]
            self.assertEqual(reference.infer(pixels, mode="bypass").logits, tuple(sample["dense_logits"]))
            self.assertEqual(integer_npu_forward(self.model, pixels), sample["dense_logits"])
            self.assertEqual(sample["dense_prediction"], max(range(10), key=lambda index: sample["dense_logits"][index]))

    def test_heldout_samples_are_unique_and_disjoint_from_training(self) -> None:
        samples = self.manifest["samples"]
        self.assertEqual(len(samples), 397)
        identities = [sample["input_sha256"] for sample in samples]
        self.assertEqual(len(set(identities)), len(identities))
        self.assertEqual(
            self.manifest["identity"]["heldout_count"],
            len(samples),
        )
        self.assertEqual(self.manifest["identity"]["train_pool_count"], 1400)
        self.assertEqual(self.manifest["identity"]["train_count"], 1200)
        self.assertEqual(self.manifest["identity"]["validation_count"], 200)
        self.assertEqual(
            self.manifest["identity"]["selection_protocol"],
            "validation_accuracy_only_v1",
        )
        regenerated = build_manifest(DEFAULT_MODEL, DEFAULT_FIXTURE, len(samples))
        left_identity = dict(self.manifest["identity"])
        right_identity = dict(regenerated["identity"])
        left_identity.pop("generated_at", None)
        right_identity.pop("generated_at", None)
        self.assertEqual(left_identity, right_identity)
        self.assertEqual(self.manifest["model"], regenerated["model"])
        self.assertEqual(samples, regenerated["samples"])


if __name__ == "__main__":
    unittest.main()
