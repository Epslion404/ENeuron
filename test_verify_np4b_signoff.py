"""NP4B 总摘要 verifier 的正向与失败敏感测试。"""

from __future__ import annotations

import copy
import hashlib
import json
import unittest

from generate_np4b_signoff import (
    ROOT,
    SUMMARY_PATH,
    WITNESS_FILES,
    canonical_sha256_bytes,
)
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


    def test_witness_binding_is_independent_of_line_endings(self) -> None:
        """Every signed witness must hash and measure identically in LF and CRLF trees."""

        hashes = self.summary["file_sha256"]
        witness_bytes = self.summary["formal"]["witness_bytes"]
        for key, name in WITNESS_FILES.items():
            with self.subTest(witness=name):
                lf = (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
                crlf = lf.replace(b"\n", b"\r\n")
                self.assertEqual(canonical_sha256_bytes(lf), canonical_sha256_bytes(crlf))
                self.assertEqual(canonical_sha256_bytes(lf), hashes[name])
                self.assertEqual(len(lf), witness_bytes[key])
                if b"\n" in lf:
                    self.assertNotEqual(
                        hashlib.sha256(lf).hexdigest(),
                        hashlib.sha256(crlf).hexdigest(),
                        "the naive raw digest must stay EOL sensitive, otherwise this test is vacuous",
                    )


if __name__ == "__main__":
    unittest.main()
