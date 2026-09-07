# 测试面与缺口

阶段 2 B0 校正（2026-09-07）：`xc7z020clg484-2` 当前最小板级候选 `df16ed6c...8971` 的实现和第一次正式 program 已通过。run-1 的 `PL_LED1/P20` 稳定闪烁与10周期 `13.42 s` 实测均通过；理论为 `13.4217728 s`，预冻结窗口为 `12.6–14.2 s`，误差约 `-0.0132%`。`field_observation.json` 当前 SHA-256 为 `d93bcc25...ab083`。当前覆盖状态为 `B0_RUN1_FIELD_PASS / POWER_CYCLE_PENDING`；完整断电和run-2尚未完成，B0不完成，B1–B4尚未进入实测。

当前校正（2026-09-07）：T3 signoff 已在 `c2bc03f` 重跑并通过；真实 XPM/xsim 与 OOC 摘要均绑定该 HEAD。下方旧快照中的 `822cf93` 不代表当前证据绑定。

当前 T2 增量（2026-09-07）：统一复现入口新增 `--t2-full-matrix`，对 16 组半周期/相位组合运行完整 wrapper 场景并返回 `REPRO_G2_T2_FULL_MATRIX_PASS`。这是有限确定性矩阵，不是频率/相位数学穷举；固定种子随机矩阵已另行通过，仍待更广泛并发交错。

当前 T2 随机矩阵增量（2026-09-07）：统一复现入口 `--t2-random-matrix` 使用固定种子 `20260907` 生成 24 个唯一半周期/相位组合，按 `2000 + 400 × NPU_HALF` 个 Host 周期设置每组观察预算，完整运行后返回 `REPRO_G2_T2_RANDOM_MATRIX_PASS`。该证据记为 `T2_RANDOM_CLOCK_MATRIX_GREEN`，属于可复现的有限随机压力集，不是频率/相位数学穷举。

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-07
provenance: repository test names, signoff summaries, workflow state, latest GitHub/Webhook evidence

已覆盖：Python/RTL 协同仿真、有限形式安全与可达性、负向 mutation、Tile/System Vivado OOC、XPM 仿真、NP4B 三模型 60000 事务签核；CI-Fast V1 已完成 workflow 全量、文档轻量和 NPU-only 定向路径验证。CI Action 已升级到 `actions/checkout@v7` 与 `actions/setup-python@v7` 的 Node 24 基线，分类合同要求任何 workflow 变更运行全量门。NPU oracle 新增并通过 `test_zero_activity_with_closed_gate_emits_no_reads_or_macs`、`test_frequent_epoch_switches_never_mix_masks`、`test_pending_slot_backpressure_rejects_overwrite` 三项最坏情况测试。

NP6 结论为部分通过，NP7 已签核。OF1-OF6 Python oracle 保持 48/48。V2 已通过单时钟专项、固定 `20×100` 和完整仓库 `475 tests / OK (skipped=1)`；PR #64 run `33946568679` 的必需门全部成功。Vivado 已确认 4 个 DSP48E1、setup/hold/route/DRC 全部通过；板级性能仍未完成。

P15-T0 方案 A 与 A1-A7 已获批准。既有 T1 wrapper、四条 XPM async FIFO 和复现入口已进入仓库，外层 AXI-Stream shim 尚未实现；T1-12 边界、T1-06 fence、T1-09 N/A 文档与复现扩展已随 `e4d48dd` 纳入基线，T2 参数化可变时钟 testbench 与 `--t2` 入口的基础切片已随 `a616d60` 纳入基线，六组时钟扩展随 `f54e762`，并发 mask epoch 场景随 `872fa90` 纳入。T1 证据覆盖复位、非法字段、模型装载、`STATE_CLEAR`/`FREEZE_SET` 控制、fence 拒绝/成功、固定 8 beat、结果背压和 10 beat 输出等主要路径，另有 T1-12 四 FIFO 边界独立切片（128/128/64/96 bit，depth=16+FWFT 外部容量 17、overflow、回绕和长背压）及 T1-06 独立切片（`T1_FENCE_ACCEPT_PASS`）。T1-09 依据 A2 记录为 `NA_FOR_T1_WRAPPER / OUTER_SHIM_PENDING`，不能外推为当前 TLAST 仿真通过。T2 六组 `(NPU_HALF,PHASE)=(7,2),(9,1),(4,3),(5,0),(11,4),(3,1)` 均输出 `T2_VARIABLE_CLOCKS_PASS`；每组并发 epoch 切片在 `872fa90` 功能基线下通过：epoch=2 在旧样本计算期间发布，旧结果逐 beat 回显 epoch=1，下一 fence 仍回显 active=1，下一样本结果回显 epoch=2。统一入口 `python -X utf8 tools/repro/verify_repository.py --t2` 输出 `REPRO_G2_T2_VARIABLE_CLOCKS_PASS`；这是本机复现的扩展 T2 协同切片，不是数学穷举，也不是 GitHub Actions 结果。T1 全量、更广泛 T2 并发交错、外层 shim、首次端到端和板级验证仍未通过；T3 真实 AMD XPM/xsim 与 `xc7z020clg400-1` OOC 已通过。资源裁剪审查不构成实现证据，且所有裁剪已推迟到第一次完整端到端跑通之后。

FIFO 矩阵切片已提交于 `ee3a351` 并通过 24/24：`tb_xpm_fifo_async_matrix.sv` 固定 8 组时钟/相位（`(2,0)/(3,1)/(4,3)/(5,0)/(7,2)/(9,1)/(11,4)/(13,5)`）× seed `1/7/29`，覆盖填满、排空、随机读写、长背压和中途复位，并对四通道实际写入/读出序列逐项比对。统一入口 `python -X utf8 tools/repro/verify_repository.py --t2-fifo-matrix` 返回 `REPRO_G2_T2_FIFO_MATRIX_PASS`；这只验证 Icarus 等价 FIFO 模型，不是 AMD XPM/xsim 或 T3 证据。

T2 wrapper 交错/复位切片已提交于 `8457a20` 并通过 4/4：`tb_npu_zynq7020_t2_interleave_reset.sv` 固定 `(2,0)/(3,1)/(7,2)/(11,4)` 四组时钟/相位，覆盖命令与样本交错、模型装载中途复位、结果背压期间复位、半帧复位及复位后旧响应/结果清除。统一入口 `python -X utf8 tools/repro/verify_repository.py --t2-interleave-reset` 返回 `REPRO_G2_T2_INTERLEAVE_RESET_PASS`；该结果仅为 Icarus wrapper 切片，不能外推为 T2 全矩阵、AMD XPM/xsim、Vivado T3 或 GitHub Actions 通过。

T2 新增证据已归档：FIFO 矩阵对应 `ee3a351`，wrapper 交错/复位对应 `8457a20`。两者都是本机 Icarus 切片，不改变 T2 全矩阵与 T3 仍待验收的状态。

T3 已完成并通过。真实 AMD XPM/xsim 报告 `vivado_npu_zynq7020_t3_xsim/xsim_signoff_summary.txt` 为 `RESULT=PASS`，绑定 Vivado 2024.1、`xc7z020clg400-1`、`XPM_LIBRARIES=XPM_FIFO`、`REAL_XPM_MODEL=AMD_XPM_FIFO`、HEAD=`c2bc03f`，测试顶层为 `tb_npu_zynq7020_t1_wrapper`。对应 OOC 报告 `vivado_npu_zynq7020_t3_ooc_reports/signoff_summary.txt` 为 `PHYSICAL_GATE=PASS`：顶层资源 `2467 LUT / 2301 FF / 6 RAMB36 / 1 RAMB18 / 4 DSP48E1`，host/npu 均 100 MHz，host `WNS=3.639 ns / WHS=0.105 ns`，npu `WNS=0.214 ns / WHS=0.042 ns`，setup/hold failing endpoints、route errors、DRC errors 均为 0，外部 CDC critical/warning 均为 0。XPM 内部 CDC 仍报告 8 个 warning；DRC 有建议性 warning，但没有 error。该 T3 只证明“核心 + 适配器 + 四条真实 XPM 异步 FIFO”的仿真和 OOC，不覆盖 AXI/DMA/PS7/Ethernet、bitstream、板级 I/O/吞吐、功耗或首次端到端运行；Actions 已关闭，远端 checks 为空不作 CI 通过证据。

## 当前签核门（T3 OOC 后）

- 实现与 report head=`f744bff`；C1-C4 的启用组/周期为 `592/1902`、`590/1898`、`0/718`、`591/1900`，逐组 bitmap、模型地址、激活锁存和 WRITEBACK 均通过。
- T3 Vivado 2024.1、`xc7z020clg400-1`、100 MHz 结果为 `2467 LUT / 2301 FF / 6 RAMB36 / 1 RAMB18 / 4 DSP48E1`；host `WNS=3.639 ns / WHS=0.105 ns`，NPU `WNS=0.214 ns / WHS=0.042 ns`，setup/hold/route/DRC error 为 0。
- 扩展 50-path 报告中的 22 条 `Slack (VIOLATED)` 已全部核对：14 条经过动态激活选择、DSP48E1 和四乘积求和到 `lane_sum_latched`，8 条从 `compute_group_index` 到 `logit_values` 写使能，不再存在未分类失败端点。外部报告 `eneuron_timing_expand_50.rpt` 的 SHA-256 为 `BE8F1BF268553E9BDAEB31FF7DB348D6F4573011DF6CBDB699D840A71D91F04D`。
- V2 已获 TR7-TR12 批准并完成实施；实施地图为 `docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_V2_IMPLEMENTATION_MAP.md`，KISS 方案复用 signed 32-bit `mac_accumulator`，不新增 `writeback_value_latched`，OOC 已通过。
- T3 真实 XPM/xsim 与 XC7Z020 OOC 已通过；T3 后续缺口是 T1/T2 全量矩阵、外层 AXI-Stream shim、首次完整端到端和板级验证，不得把本次 OOC 结果外推为这些目标已完成。

## V2 审核门（历史/协议背景）

- V2 八项裁定已获管理员批准，曾记录为 `RTL_DESIGN_CONTRACT_V2_APPROVED / RTL_SKELETON_IN_PROGRESS`；该状态属于实现过程历史，当前 RTL 已通过真实计算切片与随机门。
- Python/Icarus、随机逐 beat 和历史 PR 合并门已通过；该条只保留协议背景。当前 TR1-TR6 已实现，新的活动门是 V2 RED、RTL 和功能回归。
- 后续逐拍证据必须覆盖 OF6 确定性边界、统一响应路由、配置/样本背压、freeze/clear/reset、epoch 回绕和负向 mutation；Python 函数级 48/48 不替代这些证据。
# OF6 证据更新（历史记录）

OF4g 修正 `committed` 模型冻结边界，OF5 验证模型/mask/runtime hard reset 丢弃 staging、结果和冻结状态并恢复 `epoch=0`、全开 mask、`model_valid=0`；OF6 对 OF1-OF5 做最终汇总，`test_npu_eneuron_reference.py` 为 48/48、CI-Fast 为 8/8，曾合并至 `main@0982ac5`。该段保留作为协议签核历史；当前权威状态以上方“当前签核门”和 DSP V1 manifest 为准。
