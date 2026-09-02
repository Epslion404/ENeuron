> generated_by: nexus-mapper v2
> verified_at: 2026-09-02
> provenance: git_detective.py over the last 90 days; RTL relationships additionally inferred manually

# Git 热点与耦合

最近 90 天分析到 195 个提交、5 位作者。最高热点是 `progress.md`（64 次）、`task_plan.md`（55 次）、`findings.md`（50 次），反映工作流记录频繁变化；实现热点包括 `local_prune_rtl_results.json`、`verify_local_prune_rtl.py` 和 `compare_simulation.py`。

最高耦合对集中在计划与证据文档：`progress.md`/`task_plan.md` 49 次共同变更，耦合度 0.98；`findings.md`/`progress.md` 46 次、耦合度 1.0。修改这些文件时应保持同一阶段状态、证据和 TODO 一致。
