"""局部 2:4 结构化剪枝与前置动态门控黄金模型。

控制器独立于神经元方程，只消费四路权重和适配器归一化后的局部证据。
所有命令先完整校验、再原子提交；拒绝路径只改变审计日志和非法命令计数。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import NoReturn, Sequence


class PruneMode(Enum):
    CONFIG = "config"
    TRAIN = "train"
    INFER = "infer"


class ScoreMethod(Enum):
    S0 = "abs_weight"
    S1 = "snapshot_abs"
    S2 = "accumulated_abs"
    S3 = "accumulated_abs_weight"


@dataclass(frozen=True)
class PruneCommitResult:
    commit_id: int
    mask: int
    selected: tuple[int, int]
    reason: str


@dataclass(frozen=True)
class IssueResult:
    structural_mask: int
    activity_mask: int
    issue_mask: int
    dense_weight_reads: int
    weight_reads: int
    synapse_ops: int
    reads_saved_by_structure: int


class LocalPrune2of4:
    """每四条连接恰好保留两条的确定性局部控制器。"""

    N_INPUTS = 4
    UTILITY_MAX = 15
    DENSE_MASK = 0b1111
    COMMIT_ID_MAX = 0xFFFF

    def __init__(self, *, score_method: ScoreMethod) -> None:
        if not isinstance(score_method, ScoreMethod):
            raise TypeError("score_method must be a ScoreMethod")
        self._score_method = score_method
        self.mode = PruneMode.CONFIG
        self.utility = [0] * self.N_INPUTS
        self.structural_mask = self.DENSE_MASK
        self.mask_valid = False
        self.last_commit_id: int | None = None
        self.last_observation_id: int | None = None
        self.dense_weight_reads_requested = 0
        self.weight_reads_issued = 0
        self.synapse_ops_issued = 0
        self.reads_saved_by_structure = 0
        self.groups_skipped = 0
        self.inactive_groups = 0
        self.mask_commits = 0
        self.illegal_commands = 0
        self.accepted_commands: dict[str, int] = {}
        self.rejected_commands: dict[str, int] = {}
        self.event_log: list[dict[str, object]] = []

    @property
    def score_method(self) -> ScoreMethod:
        return self._score_method

    def _accept(self, command: str, **fields: object) -> None:
        self.accepted_commands[command] = self.accepted_commands.get(command, 0) + 1
        self.event_log.append({"event": command, "accepted": True, **fields})

    def _reject(
        self,
        command: str,
        error_type: type[Exception],
        message: str,
    ) -> NoReturn:
        self.illegal_commands += 1
        self.rejected_commands[command] = self.rejected_commands.get(command, 0) + 1
        self.event_log.append({
            "event": command,
            "accepted": False,
            "reason": message,
        })
        raise error_type(message)

    def _four_ints(
        self,
        values: Sequence[int],
        name: str,
        command: str,
    ) -> tuple[int, int, int, int]:
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            self._reject(command, TypeError, f"{name} must be an integer sequence")
        if len(values) != self.N_INPUTS:
            self._reject(command, ValueError, f"{name} must contain exactly four values")
        if any(not isinstance(value, int) or isinstance(value, bool) for value in values):
            self._reject(command, TypeError, f"{name} must contain integers")
        return values[0], values[1], values[2], values[3]

    def _bounded_id(self, value: int, name: str, command: str) -> int:
        if not isinstance(value, int) or isinstance(value, bool):
            self._reject(command, TypeError, f"{name} must be an integer")
        if not 0 <= value <= self.COMMIT_ID_MAX:
            self._reject(command, ValueError, f"{name} must be within 0..65535")
        return value

    def _require_mode(self, required: PruneMode, command: str) -> None:
        if self.mode is not required:
            self._reject(command, RuntimeError, f"{command} requires {required.name} mode")

    def set_mode(self, mode: PruneMode) -> None:
        command = "mode_set"
        if not isinstance(mode, PruneMode):
            self._reject(command, TypeError, "mode must be a PruneMode")
        old_mode = self.mode
        self.mode = mode
        self._accept(command, old_mode=old_mode.value, mode=mode.value)

    def observe(
        self,
        *,
        weights: Sequence[int],
        evidence_levels: Sequence[int],
        modulator: int,
        observation_id: int,
    ) -> None:
        """以 exactly-once 事务更新 0..15 局部分数。"""
        command = "observe"
        self._require_mode(PruneMode.TRAIN, command)
        weight_values = self._four_ints(weights, "weights", command)
        evidence = self._four_ints(evidence_levels, "evidence_levels", command)
        if any(value < 0 or value > 3 for value in evidence):
            self._reject(command, ValueError, "evidence_levels must be within 0..3")
        if not isinstance(modulator, int) or isinstance(modulator, bool):
            self._reject(command, TypeError, "modulator must be an integer")
        observation_value = self._bounded_id(observation_id, "observation_id", command)
        if self.last_observation_id is not None and observation_value <= self.last_observation_id:
            self._reject(command, ValueError, "observation_id must increase strictly")

        active_mask = self.structural_mask if self.mask_valid else self.DENSE_MASK
        new_utility = list(self.utility)
        if modulator != 0:
            if self.score_method is ScoreMethod.S1:
                for index, level in enumerate(evidence):
                    if active_mask & (1 << index):
                        new_utility[index] = level
            elif self.score_method in (ScoreMethod.S2, ScoreMethod.S3):
                for index, level in enumerate(evidence):
                    if active_mask & (1 << index):
                        new_utility[index] = min(
                            self.UTILITY_MAX,
                            max(0, self.utility[index] - 1) + level,
                        )

        self.utility = new_utility
        self.last_observation_id = observation_value
        self._accept(
            command,
            observation_id=observation_value,
            weights=list(weight_values),
            evidence_levels=list(evidence),
            active_mask=active_mask,
            utility=list(self.utility),
            modulator=0 if modulator == 0 else (1 if modulator > 0 else -1),
            score_method=self.score_method.name,
        )

    def _ranking_key(self, index: int, weights: tuple[int, int, int, int]) -> tuple[int, ...]:
        if self.score_method is ScoreMethod.S0:
            return abs(weights[index]), -index
        if self.score_method is ScoreMethod.S3:
            return self.utility[index], abs(weights[index]), -index
        return self.utility[index], -index

    def prune_commit(
        self,
        *,
        weights: Sequence[int],
        commit_id: int,
        core_idle: bool = True,
        pending_snapshot: bool = False,
        pending_mod_commit: bool = False,
    ) -> PruneCommitResult:
        command = "prune_commit"
        self._require_mode(PruneMode.TRAIN, command)
        weight_values = self._four_ints(weights, "weights", command)
        commit_value = self._bounded_id(commit_id, "commit_id", command)
        for name, value in (
            ("core_idle", core_idle),
            ("pending_snapshot", pending_snapshot),
            ("pending_mod_commit", pending_mod_commit),
        ):
            if not isinstance(value, bool):
                self._reject(command, TypeError, f"{name} must be boolean")
        if not core_idle:
            self._reject(command, RuntimeError, "prune_commit requires an idle core")
        if pending_snapshot or pending_mod_commit:
            self._reject(command, RuntimeError, "prune_commit requires no pending learning transaction")
        if self.last_commit_id is not None and commit_value <= self.last_commit_id:
            self._reject(command, ValueError, "commit_id must increase strictly")
        if self.mask_valid:
            self._reject(command, RuntimeError, "V1 forbids a second prune without PRUNE_CLEAR")

        ranking_keys = [self._ranking_key(index, weight_values) for index in range(self.N_INPUTS)]
        ranked = sorted(range(self.N_INPUTS), key=lambda index: ranking_keys[index], reverse=True)
        selected = tuple(sorted(ranked[:2]))
        mask = sum(1 << index for index in selected)
        if mask.bit_count() != 2:
            raise AssertionError("internal error: structural mask is not 2:4")
        reason = {
            ScoreMethod.S0: "abs_weight_index",
            ScoreMethod.S1: "snapshot_abs_index",
            ScoreMethod.S2: "utility_index",
            ScoreMethod.S3: "utility_abs_weight_index",
        }[self.score_method]

        old_mask = self.mask_read(log_event=False)
        old_mask_valid = self.mask_valid
        self.structural_mask = mask
        self.mask_valid = True
        self.last_commit_id = commit_value
        self.mask_commits += 1
        result = PruneCommitResult(commit_value, mask, selected, reason)
        self._accept(
            command,
            commit_id=commit_value,
            score_method=self.score_method.name,
            weights=list(weight_values),
            utility=list(self.utility),
            ranking_keys=[list(key) for key in ranking_keys],
            ranked=ranked,
            old_mask=old_mask,
            old_mask_valid=old_mask_valid,
            mask=mask,
            selected=list(selected),
            reason=reason,
        )
        return result

    def issue(self, activity_mask: int) -> IssueResult:
        command = "issue"
        if not isinstance(activity_mask, int) or isinstance(activity_mask, bool):
            self._reject(command, TypeError, "activity_mask must be an integer")
        if not 0 <= activity_mask <= self.DENSE_MASK:
            self._reject(command, ValueError, "activity_mask must be a four-bit value")

        effective_structural = self.structural_mask if self.mask_valid else self.DENSE_MASK
        issue_mask = effective_structural & activity_mask
        dense_work = activity_mask.bit_count()
        work = issue_mask.bit_count()
        saved = dense_work - work
        self.dense_weight_reads_requested += dense_work
        self.weight_reads_issued += work
        self.synapse_ops_issued += work
        self.reads_saved_by_structure += saved
        if activity_mask == 0:
            self.inactive_groups += 1
        elif issue_mask == 0:
            self.groups_skipped += 1
        result = IssueResult(
            effective_structural,
            activity_mask,
            issue_mask,
            dense_work,
            work,
            work,
            saved,
        )
        self._accept(
            command,
            structural_mask=effective_structural,
            activity_mask=activity_mask,
            issue_mask=issue_mask,
            dense_weight_reads=dense_work,
            weight_reads=work,
            synapse_ops=work,
            reads_saved_by_structure=saved,
        )
        return result

    def prune_clear(self) -> None:
        command = "prune_clear"
        self._require_mode(PruneMode.CONFIG, command)
        self.utility = [0] * self.N_INPUTS
        self.structural_mask = self.DENSE_MASK
        self.mask_valid = False
        self.last_commit_id = None
        self.last_observation_id = None
        self._accept(command)

    def hard_reset(self) -> None:
        """模拟硬复位；累计审计计数和日志也回到初始状态。"""
        score_method = self.score_method
        self.__init__(score_method=score_method)
        self._accept("hard_reset")

    def mask_write(self, mask: int) -> None:
        command = "mask_write"
        self._require_mode(PruneMode.CONFIG, command)
        if not isinstance(mask, int) or isinstance(mask, bool):
            self._reject(command, TypeError, "mask must be an integer")
        if not 0 <= mask <= self.DENSE_MASK or mask.bit_count() != 2:
            self._reject(command, ValueError, "mask_write requires an exact 2:4 mask")
        old_mask = self.mask_read(log_event=False)
        self.structural_mask = mask
        self.mask_valid = True
        self._accept(command, old_mask=old_mask, mask=mask)

    def mask_read(self, *, log_event: bool = True) -> int:
        """返回数据路径当前实际使用的结构掩码。"""
        mask = self.structural_mask if self.mask_valid else self.DENSE_MASK
        if log_event:
            self._accept("mask_read", mask=mask, mask_valid=self.mask_valid)
        return mask


__all__ = [
    "IssueResult",
    "LocalPrune2of4",
    "PruneCommitResult",
    "PruneMode",
    "ScoreMethod",
]
