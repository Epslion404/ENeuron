"""ENeuron wrapper proof/reach 正式证据入口。"""

import unittest

import verify_formal_eneuron_prune_wrapper as verifier


class FormalENeuronPruneWrapperTests(unittest.TestCase):
    def test_atomic_mod_observe_and_public_success_witness(self) -> None:
        """独立 verifier 必须接受当前 proof、reach、日志和 witness。"""
        verifier.main()


if __name__ == "__main__":
    unittest.main()
