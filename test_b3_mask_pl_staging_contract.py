import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "boards" / "hellozynq" / "b2_sw" / "src" / "packet_main.c"


class B3MaskPlStagingContractTests(unittest.TestCase):
    def setUp(self):
        self.source = SOURCE.read_text(encoding="utf-8")

    def test_batch_builder_keeps_command_word_boundaries(self):
        for token in (
            "build_command_batch_frame",
            "command_count * 16U",
            "commands[index][word_index]",
            "finish_frame(frame, 8U + command_count * 4U)",
        ):
            self.assertIn(token, self.source)

    def test_mask_update_is_one_dma_batch(self):
        start = self.source.index("static int send_mask_for_epoch")
        end = self.source.index("static u32 finish_frame", start)
        function = self.source[start:end]
        self.assertIn("u32 command_words[21][4]", function)
        self.assertIn("set_command_fields(command_words[0], OP_MASK_BEGIN", function)
        self.assertIn("set_command_fields(command_words[20], OP_MASK_COMMIT", function)
        self.assertIn("build_command_batch_frame(tx, command_words, 21U", function)
        self.assertIn("submit_frame(frame_bytes, 0U, 0U, 0)", function)
        self.assertNotIn("send_command(OP_MASK_DATA", function)

    def test_batch_does_not_remove_epoch_or_fence_protocol(self):
        self.assertIn("set_command_fields(command_words[index + 1U], OP_MASK_DATA, epoch", self.source)
        self.assertIn("send_fence_and_check", self.source)

    def test_build_manifest_names_the_submission_path(self):
        build_script = (ROOT / "boards" / "hellozynq" / "b2_sw" / "run_b2_packet_sw_build.ps1").read_text(encoding="utf-8")
        self.assertIn("mask_submit_path = 'pl_staging_command_batch_v1'", build_script)


if __name__ == "__main__":
    unittest.main()
