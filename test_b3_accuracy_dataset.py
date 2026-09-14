from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from b3_accuracy_dataset import build_accuracy_samples, write_accuracy_chunks


class B3AccuracyDatasetTests(unittest.TestCase):
    def test_fixture_rows_have_labels_and_mode_epochs(self) -> None:
        rows = build_accuracy_samples(sample_count=3)
        self.assertEqual([row["label"] for row in rows], [0, 1, 2])
        self.assertEqual([row["dense_mask_epoch"] for row in rows], [1, 1, 1])
        self.assertEqual([row["live_mask_epoch"] for row in rows], [2, 3, 4])
        self.assertEqual(len(rows[0]["dense_logits"]), 10)
        self.assertEqual(len(rows[0]["live_logits"]), 10)

    def test_one_thousand_samples_split_into_sixteen_board_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = write_accuracy_chunks(Path(temp), sample_count=1000)
            self.assertEqual(len(paths), 16)
            documents = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
            self.assertEqual(sum(document["sample_count"] for document in documents), 1000)
            self.assertEqual(documents[-1]["sample_count"], 40)
            ids = [row["sample_id"] for document in documents for row in document["samples"]]
            self.assertEqual(len(ids), len(set(ids)))

    def test_each_board_chunk_rebases_live_epoch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = write_accuracy_chunks(Path(temp), sample_count=130)
            first = json.loads(paths[0].read_text(encoding="utf-8"))["samples"]
            second = json.loads(paths[1].read_text(encoding="utf-8"))["samples"]
            self.assertEqual(first[0]["live_mask_epoch"], 2)
            self.assertEqual(first[-1]["live_mask_epoch"], 65)
            self.assertEqual(second[0]["live_mask_epoch"], 2)
            self.assertEqual(second[-1]["live_mask_epoch"], 65)


if __name__ == "__main__":
    unittest.main()
