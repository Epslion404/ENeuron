"""将变更路径映射到 ENeuron CI-Fast V1 的验证范围。"""

import argparse
import fnmatch
import logging
import subprocess
from pathlib import Path
from typing import Iterable


LOGGER = logging.getLogger(__name__)
SCOPES = ("npu_oracle", "full_repository", "xpm_cdc", "np7_functional", "np7_physical", "t1_repro")


def classify_paths(paths: Iterable[str], *, run_all: bool = False) -> dict[str, bool]:
    """返回需要执行的范围；未知文件采用全仓回归的保守默认值。"""
    selected = {scope: run_all for scope in SCOPES}
    for raw_path in paths:
        path = raw_path.replace("\\", "/")
        LOGGER.info("changed=%s", path)
        if fnmatch.fnmatch(path, ".github/workflows/*"):
            for scope in SCOPES[1:]:
                selected[scope] = True
        elif path in {
            "npu_eneuron_reference.py",
            "test_npu_eneuron_reference.py",
            "npu_eneuron_protocol.py",
        }:
            selected["npu_oracle"] = True
        elif _matches(path, "host_bridge_xpm*", "test_host_bridge_xpm_wrapper.py", "xpm_fifo_async*"):
            selected["xpm_cdc"] = True
        elif _matches(path, "npu_zynq7020_t1_wrapper.sv", "tb_npu_zynq7020_t1_wrapper.sv", "tb_npu_zynq7020_t1_fifo_boundary.sv", "tools/repro/*", "REPRODUCE.md"):
            selected["t1_repro"] = True
        elif _matches(
            path,
            "vivado_np7_*",
            "vivado_np7_*/*",
            "artifacts/results/np7*",
            "artifacts/signoff/np7*",
            "verify_np7_physical_cost.py",
            "test_np7_physical_mutations.py",
        ):
            selected["np7_physical"] = True
        elif _matches(path, "np7_*", "test_np7_*", "verify_np7_software_cost.py"):
            selected["np7_functional"] = True
            selected["np7_physical"] = True
        elif _matches(path, "*.md", "docs/*", ".nexus-map/*"):
            continue
        else:
            selected["full_repository"] = True
    return selected


def _matches(path: str, *patterns: str) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _changed_paths(base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [line for line in result.stdout.splitlines() if line]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base")
    parser.add_argument("--head")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if not args.all and (not args.base or not args.head):
        parser.error("--base and --head are required unless --all is used")
    paths = [] if args.all else _changed_paths(args.base, args.head)
    selected = classify_paths(paths, run_all=args.all)
    with args.github_output.open("a", encoding="utf-8", newline="\n") as output:
        for scope in SCOPES:
            value = str(selected[scope]).lower()
            LOGGER.info("scope.%s=%s", scope, value)
            output.write(f"{scope}={value}\n")


if __name__ == "__main__":
    main()
