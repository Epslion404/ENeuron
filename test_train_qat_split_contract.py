"""QAT 训练划分合同：最终 held-out 不得参与 best epoch 选择。"""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "train_qat.py"


def _name(node: ast.AST) -> str | None:
    return node.id if isinstance(node, ast.Name) else None


def test_qat_split_constants_and_disjoint_counts() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    constants: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, int):
                constants[target.id] = node.value.value
    assert constants["TRAIN_POOL_COUNT"] == 1400
    assert constants["TRAIN_COUNT"] == 1200
    assert constants["TRAIN_POOL_COUNT"] - constants["TRAIN_COUNT"] == 200
    assert "VALIDATION_COUNT = TRAIN_POOL_COUNT - TRAIN_COUNT" in SOURCE.read_text(encoding="utf-8")


def test_test_accuracy_is_evaluated_after_validation_selection() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    loops = [node for node in tree.body if isinstance(node, ast.For) and _name(node.target) == "ep"]
    assert len(loops) == 1
    loop = loops[0]

    validation_calls = [
        node
        for node in ast.walk(loop)
        if isinstance(node, ast.Call)
        and _name(node.func) == "accuracy"
        and node.args
        and _name(node.args[0]) == "val"
    ]
    heldout_calls_in_loop = [
        node
        for node in ast.walk(loop)
        if isinstance(node, ast.Call)
        and _name(node.func) == "accuracy"
        and node.args
        and _name(node.args[0]) == "te"
    ]
    assert validation_calls
    assert not heldout_calls_in_loop

    heldout_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _name(node.func) == "accuracy"
        and node.args
        and _name(node.args[0]) == "te"
    ]
    assert len(heldout_calls) == 1
    assert heldout_calls[0].lineno > loop.lineno
