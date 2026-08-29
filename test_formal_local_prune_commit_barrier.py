"""NP4B5 十 gate 提交屏障形式证明与三顶层绑定入口。"""

from pathlib import Path
import unittest

import verify_formal_local_prune_commit_barrier as verifier


ROOT = Path(__file__).resolve().parent


class FormalLocalPruneCommitBarrierTests(unittest.TestCase):
    def test_proof_reach_and_real_top_binding(self) -> None:
        result = verifier.verify()
        self.assertEqual(result["formal_depth"], 32)
        self.assertEqual(result["participants"], 10)
        self.assertEqual(result["real_tops"], 3)


if __name__ == "__main__":
    unittest.main()
