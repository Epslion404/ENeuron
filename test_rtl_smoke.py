import json
import subprocess
import sys
import unittest
from pathlib import Path


class RtlSmokeTests(unittest.TestCase):
    def test_rtl_interface_smoke(self) -> None:
        subprocess.run([sys.executable, "rtl_smoke.py"], check=True)
        result = json.loads(Path("rtl_smoke_results.json").read_text(encoding="utf-8"))
        self.assertTrue(result["rtl_tool_available"])
        self.assertTrue(result["cosim_passed"])
        self.assertGreater(len(result["golden_vector"]), 0)


if __name__ == "__main__":
    unittest.main()
