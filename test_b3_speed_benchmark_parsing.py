"""Host 侧 logits 十六进制解析回归：uint32 -> signed int32。

CRC 只用于原始帧校验，不能替代 logits 数值校验；本测试按实际数值
（0、223、INT32_MAX、INT32_MIN、UINT32_MAX）验证 runner 的解析结果。
"""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RUNNER = ROOT / "boards" / "hellozynq" / "b2_sw" / "run_b3_speed_benchmark.ps1"
CASES = (
    ("0x00000000", 0),
    ("0x000000DF", 223),
    ("0x7FFFFFFF", 2147483647),
    ("0x80000000", -2147483648),
    ("0xFFFFFFFF", -1),
)


def _find_powershell() -> str | None:
    for name in ("pwsh", "powershell", "powershell.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _extract_function(source: str, name: str) -> str:
    normalised = source.replace("\r\n", "\n")
    start = normalised.index(f"function {name} {{")
    end = normalised.index("\n}\n", start) + len("\n}\n")
    return normalised[start:end]


def _strip_comments(function_text: str) -> str:
    """通过 stdin 传给 PS 5.1 时只保留 ASCII 语句，避免中文注释被代码页破坏。"""
    kept = [line for line in function_text.splitlines() if not line.lstrip().startswith("#")]
    return "\n".join(kept) + "\n"


class B3SpeedBenchmarkParsingTests(unittest.TestCase):
    def test_runner_uses_explicit_uint32_threshold(self) -> None:
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn("[uint32]2147483648", source)
        self.assertNotIn("-ge 0x80000000", source)
        self.assertIn("Get-I32 $probeText", source)

    def test_i32_parsing_boundaries(self) -> None:
        shell = _find_powershell()
        if shell is None:
            self.skipTest("PowerShell unavailable")
        source = RUNNER.read_text(encoding="utf-8")
        script = [
            "Set-StrictMode -Version Latest",
            _strip_comments(_extract_function(source, "Get-U32")),
            _strip_comments(_extract_function(source, "Get-I32")),
        ]
        for index, (hex_value, expected) in enumerate(CASES):
            key = f"BENCH_{index}"
            script.append(f"$v = Get-I32 -Text '{key}={hex_value}' -Key '{key}'")
            script.append(
                f"if ($v -ne {expected}) {{ "
                f"Write-Output ('FAIL {key} expected={expected} actual=' + $v); exit 1 }}"
            )
            script.append(f"Write-Output ('PASS {key} {hex_value} -> ' + $v)")
        script.append("Write-Output 'HOST_LOGITS_PARSING_PASS'")
        ran = subprocess.run(
            [shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", "-"],
            input="\n".join(script) + "\n",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        self.assertIn("HOST_LOGITS_PARSING_PASS", ran.stdout)
        for index, (hex_value, expected) in enumerate(CASES):
            self.assertIn(f"PASS BENCH_{index} {hex_value} -> {expected}", ran.stdout)


if __name__ == "__main__":
    unittest.main()
