"""公共 2:4 gate 正式 proof/reach 证据入口。"""

import unittest

import verify_formal_local_prune_gate as verifier


class FormalLocalPruneGateTests(unittest.TestCase):
    def test_proof_reach_and_exact_two_witness(self) -> None:
        """proof、成功提交和 exact-two witness 必须同时存在。"""
        result = verifier.verify()
        self.assertEqual(result["formal_depth"], 32)
        self.assertEqual(result["reach_depth"], 8)
        self.assertGreater(result["witness_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
