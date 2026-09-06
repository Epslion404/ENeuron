"""CI-Fast V1 路径分类矩阵。"""

from pathlib import Path
import unittest

from tools.ci.classify_changes import classify_paths


class ClassifyChangesTest(unittest.TestCase):
    def test_documentation_only_uses_fast_gate(self):
        selected = classify_paths(["docs/design/note.md", ".nexus-map/INDEX.md"])
        self.assertFalse(any(selected.values()))

    def test_npu_oracle_change_runs_only_targeted_oracle(self):
        selected = classify_paths(["npu_eneuron_reference.py"])
        self.assertEqual([name for name, enabled in selected.items() if enabled], ["npu_oracle"])

    def test_npu_protocol_change_runs_only_targeted_oracle(self):
        selected = classify_paths(["npu_eneuron_protocol.py"])
        self.assertEqual([name for name, enabled in selected.items() if enabled], ["npu_oracle"])

    def test_xpm_change_selects_windows_gate(self):
        selected = classify_paths(["host_bridge_xpm_fifo.sv"])
        self.assertTrue(selected["xpm_cdc"])
        self.assertFalse(selected["full_repository"])

    def test_np7_source_selects_functional_and_physical_gates(self):
        selected = classify_paths(["np7_shared_lane_exec.sv"])
        self.assertTrue(selected["np7_functional"])
        self.assertTrue(selected["np7_physical"])

    def test_unknown_code_uses_full_repository_gate(self):
        selected = classify_paths(["digital_lif_engine.sv"])
        self.assertTrue(selected["full_repository"])

    def test_workflow_and_manual_dispatch_run_every_heavy_scope(self):
        workflow = classify_paths([".github/workflows/pr-gate.yml"])
        manual = classify_paths([], run_all=True)
        self.assertTrue(all(workflow[name] for name in workflow if name != "npu_oracle"))
        self.assertTrue(all(manual.values()))

    def test_actions_use_node24_compatible_majors(self):
        workflow = Path(".github/workflows/pr-gate.yml").read_text(encoding="utf-8")
        self.assertEqual(workflow.count("uses: actions/checkout@v7"), 7)
        self.assertEqual(workflow.count("uses: actions/setup-python@v7"), 6)
        self.assertNotIn("uses: actions/checkout@v4", workflow)
        self.assertNotIn("uses: actions/setup-python@v5", workflow)


if __name__ == "__main__":
    unittest.main()
