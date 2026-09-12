"""用 ENeuron S2 控制器从当前样本证据生成 592-bit group_4way live mask。

每个隐藏/输出单元把相邻四个 NPU 组当成一个四输入 meta-neuron：
证据来自该组对当前激活的有符号贡献幅度，再按 ENeuron 的 0..3 量化。
S2 一次 OBSERVE + PRUNE_COMMIT 后恰好保留两个组。这是组级动态剪枝，
不是严格连接级 2:4，也不是 Host 重放冻结 mixed mask。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from eneuron_prune_adapter import quantize_eligibility
from local_prune_reference import LocalPrune2of4, PruneMode, ScoreMethod
from npu_eneuron_protocol import decode_model_words, decode_mask_words
from npu_eneuron_reference import NpuReference, saturate_hidden


GROUP_COUNT = 592
MASK_WORD_COUNT = 19
L0_GROUPS_PER_HIDDEN = 16
L1_GROUPS_PER_OUTPUT = 8
META_WIDTH = 4
GAIN = 1
MASK_EPOCH = 1
SAMPLE_ID = 0x12345678


@dataclass(frozen=True)
class LiveCommit:
    layer: str
    unit: int
    meta_index: int
    group_base: int
    evidence_levels: tuple[int, int, int, int]
    contributions: tuple[int, int, int, int]
    selected: tuple[int, int]
    mask: int
    commit_id: int
    gain: int = GAIN


@dataclass(frozen=True)
class LiveGroup4WayDecision:
    mask_words: tuple[int, ...]
    logits: tuple[int, ...]
    prediction_class: int | None
    active_groups: int
    skipped_groups: int
    mask_granularity: str
    strict_2of4_candidate: bool
    score_method: str
    gain: int
    mask_epoch: int
    sample_id: int
    commits: tuple[LiveCommit, ...]


def _pack_bits(bits: Sequence[bool]) -> tuple[int, ...]:
    words = [0] * MASK_WORD_COUNT
    for index, enabled in enumerate(bits):
        if enabled:
            words[index // 32] |= 1 << (index % 32)
    return tuple(words)


def _group_contribution(weights: Sequence[int], activations: Sequence[int], start: int) -> int:
    return sum(int(weights[start + offset]) * int(activations[start + offset]) for offset in range(META_WIDTH))


def _commit_meta(
    *,
    layer: str,
    unit: int,
    meta_index: int,
    group_base: int,
    contributions: tuple[int, int, int, int],
    commit_id: int,
) -> LiveCommit:
    evidence = tuple(quantize_eligibility(value * GAIN) for value in contributions)
    gate = LocalPrune2of4(score_method=ScoreMethod.S2)
    gate.set_mode(PruneMode.TRAIN)
    dummy_weights = (0, 0, 0, 0)
    gate.observe(
        weights=dummy_weights,
        evidence_levels=evidence,
        modulator=1,
        observation_id=commit_id,
    )
    result = gate.prune_commit(weights=dummy_weights, commit_id=commit_id)
    return LiveCommit(
        layer=layer,
        unit=unit,
        meta_index=meta_index,
        group_base=group_base,
        evidence_levels=evidence,
        contributions=contributions,
        selected=result.selected,
        mask=result.mask,
        commit_id=commit_id,
    )


def decide_group4way_live(
    model_words: Sequence[int],
    pixels: Sequence[int],
    *,
    sample_id: int = SAMPLE_ID,
    mask_epoch: int = MASK_EPOCH,
) -> LiveGroup4WayDecision:
    """从已提交模型和当前样本计算 live group_4way mask，并给出参考 logits。"""
    decoded = decode_model_words(model_words)
    bits = [False] * GROUP_COUNT
    commits: list[LiveCommit] = []
    commit_id = 1
    hidden_dense: list[int] = []

    for hidden, row in enumerate(decoded.weights0):
        acc = decoded.bias0[hidden]
        for group in range(L0_GROUPS_PER_HIDDEN):
            acc += _group_contribution(row, pixels, group * META_WIDTH)
        hidden_dense.append(saturate_hidden(acc))
        for meta_index in range(L0_GROUPS_PER_HIDDEN // META_WIDTH):
            group_base = hidden * L0_GROUPS_PER_HIDDEN + meta_index * META_WIDTH
            contributions = tuple(
                _group_contribution(row, pixels, (meta_index * META_WIDTH + offset) * META_WIDTH)
                for offset in range(META_WIDTH)
            )
            commit = _commit_meta(
                layer="L0",
                unit=hidden,
                meta_index=meta_index,
                group_base=group_base,
                contributions=contributions,
                commit_id=commit_id,
            )
            commit_id += 1
            commits.append(commit)
            for local, keep in enumerate((commit.mask >> index) & 1 for index in range(META_WIDTH)):
                bits[group_base + local] = bool(keep)

    for output, row in enumerate(decoded.weights1):
        for meta_index in range(L1_GROUPS_PER_OUTPUT // META_WIDTH):
            group_base = 512 + output * L1_GROUPS_PER_OUTPUT + meta_index * META_WIDTH
            contributions = tuple(
                _group_contribution(row, hidden_dense, (meta_index * META_WIDTH + offset) * META_WIDTH)
                for offset in range(META_WIDTH)
            )
            commit = _commit_meta(
                layer="L1",
                unit=output,
                meta_index=meta_index,
                group_base=group_base,
                contributions=contributions,
                commit_id=commit_id,
            )
            commit_id += 1
            commits.append(commit)
            for local, keep in enumerate((commit.mask >> index) & 1 for index in range(META_WIDTH)):
                bits[group_base + local] = bool(keep)

    mask_words = _pack_bits(bits)
    model = NpuReference()
    model.load_weights(decoded.weights0, decoded.bias0, decoded.weights1, decoded.bias1)
    decoded_masks = decode_mask_words(mask_words)
    result = model.infer(
        pixels,
        mode="gated",
        group_mask0=decoded_masks.mask0,
        group_mask1=decoded_masks.mask1,
    )
    active = sum(1 for bit in bits if bit)
    return LiveGroup4WayDecision(
        mask_words=mask_words,
        logits=result.logits,
        prediction_class=result.prediction,
        active_groups=active,
        skipped_groups=GROUP_COUNT - active,
        mask_granularity="group_4way",
        strict_2of4_candidate=False,
        score_method="S2",
        gain=GAIN,
        mask_epoch=mask_epoch,
        sample_id=sample_id,
        commits=tuple(commits),
    )
