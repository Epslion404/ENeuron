"""固定四输入阵列与共享树突处理 lane 的可复现周期模型。

这是架构比较模型，不是 Vivado 资源签核。它只利用每个神经元状态
彼此独立这一事实，计算一条 lane 逐神经元处理时的周期和吞吐上限。
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class ArchitecturePoint:
    cores: int
    lanes: int
    cycles_per_tick: int
    ticks_per_cycle: float
    feedback_cycles_per_all_core_update: int


def compare(cores: int, lanes: int) -> ArchitecturePoint:
    if cores <= 0 or lanes <= 0 or lanes > cores:
        raise ValueError("cores and lanes must satisfy 0 < lanes <= cores")
    cycles = (cores + lanes - 1) // lanes
    return ArchitecturePoint(
        cores=cores,
        lanes=lanes,
        cycles_per_tick=cycles,
        ticks_per_cycle=lanes / cores,
        feedback_cycles_per_all_core_update=cycles,
    )


def main() -> None:
    points = [compare(cores, lanes) for cores in (32, 64, 128) for lanes in (1, 2, 4, 8, cores)]
    result = [point.__dict__ for point in points]
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    for point in points:
        assert point.cycles_per_tick * point.lanes >= point.cores
    print("PULSE_MINI_LANE_MODEL_PASS points=%d" % len(points))


if __name__ == "__main__":
    main()
