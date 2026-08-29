"""NP4B 总摘要 verifier 的正向与失败敏感测试。"""

from __future__ import annotations

import copy
import json
import unittest

from generate_np4b_signoff import SUMMARY_PATH
from verify_np4b_signoff import verify_summary


class VerifyNp4bSignoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))

    def test_current_summary_and_file_hashes_pass(self) -> None:
        verify_summary(self.summary)

    def test_wrong_seed_set_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.summary)
        mutated["models"]["eneuron"]["seeds"][0] = 100
        with self.assertRaisesRegex(AssertionError, "models.eneuron.seeds"):
            verify_summary(mutated, check_files=False)

    def test_missing_or_extra_hash_key_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.summary)
        mutated["file_sha256"]["unexpected.tmp.log"] = "0" * 64
        with self.assertRaisesRegex(AssertionError, "file_sha256.keys"):
            verify_summary(mutated, check_files=False)


if __name__ == "__main__":
    unittest.main()
