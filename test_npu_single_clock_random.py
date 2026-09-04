"""20 个固定 seed × 100 样本的单时钟 NPU 随机 bit-exact 协同仿真。"""

from __future__ import annotations

import random
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIXED_IVERILOG = Path(r"C:\msys64\ucrt64\bin\iverilog.exe")
FIXED_VVP = Path(r"C:\msys64\ucrt64\bin\vvp.exe")
SEEDS = (0, 1, 2, 3, 4, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61)


def find_tool(fixed: Path, name: str) -> Path | None:
    if fixed.exists():
        return fixed
    found = shutil.which(name)
    return Path(found) if found else None


def signed_byte(value: int) -> int:
    return value & 0xFF


def pack_weights(weights: list[list[int]], groups: int) -> list[int]:
    words: list[int] = []
    for row in weights:
        for group in range(groups):
            word = 0
            for offset in range(4):
                word |= signed_byte(row[group * 4 + offset]) << (offset * 8)
            words.append(word)
    return words


def pack_masks(mask0: list[bool], mask1: list[bool]) -> list[int]:
    bits = mask0 + mask1
    # 19 个 word 的最后 16 位是保留位，必须保持为零。
    return [
        sum((1 << bit) for bit in range(32) if word * 32 + bit < len(bits) and bits[word * 32 + bit])
        for word in range(19)
    ]


def infer(
    sample: list[int],
    weights0: list[list[int]],
    bias0: list[int],
    weights1: list[list[int]],
    bias1: list[int],
    mask0: list[bool],
    mask1: list[bool],
) -> list[int]:
    hidden: list[int] = []
    for output, row in enumerate(weights0):
        acc = bias0[output]
        for group in range(16):
            if mask0[output * 16 + group]:
                acc += sum(sample[group * 4 + offset] * row[group * 4 + offset] for offset in range(4))
        hidden.append(max(0, min(127, acc)))

    logits: list[int] = []
    for output, row in enumerate(weights1):
        acc = bias1[output]
        for group in range(8):
            if mask1[output * 8 + group]:
                acc += sum(hidden[group * 4 + offset] * row[group * 4 + offset] for offset in range(4))
        logits.append(acc)
    return logits


def write_words(path: Path, words: list[int]) -> None:
    path.write_text("".join(f"{word & 0xFFFFFFFF:08x}\n" for word in words), encoding="ascii")


def make_case(seed: int) -> tuple[list[int], list[int], list[int], list[int]]:
    rng = random.Random(seed)
    weights0 = [[rng.randint(-128, 127) for _ in range(64)] for _ in range(32)]
    weights1 = [[rng.randint(-128, 127) for _ in range(32)] for _ in range(10)]
    bias0 = [rng.randint(-10_000, 10_000) for _ in range(32)]
    bias1 = [rng.randint(-10_000, 10_000) for _ in range(10)]
    # 每个 seed 都强制包含负权重、正权重和两端 INT8 值。
    weights0[0][:4] = [-128, -1, 0, 127]
    weights1[0][:4] = [127, 0, -1, -128]

    model_words = pack_weights(weights0, 16)
    model_words += [value & 0xFFFFFFFF for value in bias0]
    model_words += pack_weights(weights1, 8)
    model_words += [value & 0xFFFFFFFF for value in bias1]

    sample_words: list[int] = []
    mask_words: list[int] = []
    expected_words: list[int] = []
    for sample_index in range(100):
        if sample_index == 0:
            sample = [0] * 64
        elif sample_index == 1:
            sample = [15] * 64
        else:
            sample = [rng.randrange(16) for _ in range(64)]
        for beat in range(8):
            word = sum(sample[beat * 8 + offset] << (offset * 4) for offset in range(8))
            sample_words.append(word)

        if sample_index == 0:
            mask0 = [True] * 512
            mask1 = [True] * 80
        elif sample_index % 10 == 0:
            mask0 = [False] * 512
            mask1 = [False] * 80
        elif sample_index % 10 == 1:
            mask0 = [True] * 512
            mask1 = [True] * 80
        else:
            mask0 = [rng.random() >= 0.45 for _ in range(512)]
            mask1 = [rng.random() >= 0.45 for _ in range(80)]
        mask_words.extend(pack_masks(mask0, mask1))
        logits = infer(sample, weights0, bias0, weights1, bias1, mask0, mask1)
        expected_words.extend(value & 0xFFFFFFFF for value in logits)
    return model_words, sample_words, mask_words, expected_words


class NpuSingleClockRandomTests(unittest.TestCase):
    def test_fixed_seed_random_bit_exact(self) -> None:
        iverilog = find_tool(FIXED_IVERILOG, "iverilog")
        vvp = find_tool(FIXED_VVP, "vvp")
        self.assertIsNotNone(iverilog, "Icarus unavailable")
        self.assertIsNotNone(vvp, "vvp unavailable")
        with tempfile.TemporaryDirectory(prefix="eneuron_npu_random_") as temp:
            temp_path = Path(temp)
            for seed in SEEDS:
                model, samples, masks, expected = make_case(seed)
                model_path = temp_path / f"model_{seed}.hex"
                samples_path = temp_path / f"samples_{seed}.hex"
                masks_path = temp_path / f"masks_{seed}.hex"
                expected_path = temp_path / f"expected_{seed}.hex"
                write_words(model_path, model)
                write_words(samples_path, samples)
                write_words(masks_path, masks)
                write_words(expected_path, expected)
                output = temp_path / f"random_{seed}.vvp"
                compiled = subprocess.run(
                    [str(iverilog), "-g2012", "-Wall", "-s", "tb_npu_eneuron_single_clock_random",
                     "-o", str(output), "tb_npu_eneuron_single_clock_random.sv",
                     "npu_eneuron_single_clock_skeleton.sv"],
                    cwd=ROOT, text=True, capture_output=True, check=False,
                )
                self.assertEqual(compiled.returncode, 0, f"seed={seed}\n{compiled.stderr}")
                ran = subprocess.run(
                    [str(vvp), str(output), f"+SEED={seed}", f"+MODEL={model_path}",
                     f"+SAMPLES={samples_path}", f"+MASKS={masks_path}", f"+EXPECTED={expected_path}"],
                    cwd=ROOT, text=True, capture_output=True, check=False,
                )
                self.assertEqual(ran.returncode, 0, f"seed={seed}\n{ran.stdout}\n{ran.stderr}")
                self.assertIn(f"PASS random bit-exact seed={seed} samples=100", ran.stdout)
        print(f"RANDOM_BIT_EXACT_PASS seeds={len(SEEDS)} samples={len(SEEDS) * 100}")


if __name__ == "__main__":
    unittest.main()
