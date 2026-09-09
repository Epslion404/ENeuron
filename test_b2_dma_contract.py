import copy
import json
import unittest
from pathlib import Path

from verify_b2_dma_contract import validate_contract
from tools.ci.classify_changes import classify_paths


ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "tools" / "repro" / "b2_dma_contract.json"


class B2DmaContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_frozen_contract_passes(self):
        self.assertEqual(validate_contract(self.contract), [])

    def test_rejects_scatter_gather(self):
        candidate = copy.deepcopy(self.contract)
        candidate["dma_mode"]["scatter_gather"] = True
        self.assertTrue(any("scatter" in error for error in validate_contract(candidate)))

    def test_rejects_wrong_channel_order(self):
        candidate = copy.deepcopy(self.contract)
        candidate["transfer_sequence"] = ["mm2s", "s2mm"]
        self.assertTrue(any("sequence" in error for error in validate_contract(candidate)))

    def test_rejects_unbounded_frame(self):
        candidate = copy.deepcopy(self.contract)
        candidate["transfer_limits"]["max_frame_bytes"] = 8192
        self.assertTrue(any("max frame" in error for error in validate_contract(candidate)))

    def test_rejects_missing_error_snapshot(self):
        candidate = copy.deepcopy(self.contract)
        candidate["evidence"]["register_snapshot"] = ["tx_cr"]
        self.assertTrue(any("snapshot" in error for error in validate_contract(candidate)))

    def test_verifier_uses_targeted_repro_gate(self):
        scopes = classify_paths(["verify_b2_dma_contract.py"])
        self.assertTrue(scopes["t1_repro"])
        self.assertFalse(scopes["full_repository"])


if __name__ == "__main__":
    unittest.main()
