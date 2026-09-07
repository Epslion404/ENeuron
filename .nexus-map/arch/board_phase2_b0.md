# 项目阶段 2：HelloZynq B0 实板基础验证

verified_at: 2026-09-07

## 当前结论

状态为 `B0_LED_STABLE / PERIOD_QUANTIFICATION_PENDING`，**B0 尚未完成**。

当前源码的正式构建和当前 bitstream 的 JTAG 下载均已通过，用户也已确认 LED 稳定闪烁，并目测完整周期约为 `1.0 s`。该字段明确为 `approximate=true`，不是精确测量；相对理论 `1.34217728 s` 可能约快 `25.5%`。如果后续精确确认周期确为 `1.0 s`，按 `counter[25]` 可条件推断输入时钟约为 `67.109 MHz`，但当前证据不足以判定硬件失败。应先确认观察对象为 `PL_LED1/P20`，测量 10 个完整周期的总时长；在此之前暂停断电 run-2。

## 基线与最小电路

- PR #68 已合并到 `main`，merge commit 为 `7857d32561cbd5f86d02b1a21ee0edfb3ae895f1`。
- 当前 B0 源码提交为 `f3b8174e8ca30d427e9de3eea2d36feb6a5e6a06`；历史两次 program对应 `367c81316dc6fdc48105d6c657952a66314436bd`。
- 目标器件为 `xc7z020clg484-2`，取代历史 T3 OOC 使用的 `xc7z020clg400-1` 作为阶段 2 实板目标；历史 OOC 证据仍有效，但不能用于实际引脚签核。
- 最小电路为 M19 上的 50 MHz PL 时钟驱动 26-bit counter，计数器最高位输出到 P20 LED。
- 对 `counter[25]`，50 MHz 下理论单次翻转间隔为 `0.67108864 s`，完整亮灭周期为 `1.34217728 s`。
- 仓库 XDC、本地引脚速查和两个本地板级例程均支持 `M19=50 MHz`、`P20=PL_LED1`；该一致性缩小了映射错误的可能性，但不能替代现场对象确认与周期测量。
- 可复现源码入口位于 `boards/hellozynq/b0_smoke/`。

## 构建证据

Vivado 2024.1 当前正式候选构建结果：

- 资源：`1 LUT / 26 FF / 0 BRAM / 0 DSP`。
- setup：`WNS=+17.918 ns`，失败端点 0。
- hold：`WHS=+0.251 ns`，失败端点 0。
- route errors：0。
- DRC errors / critical warnings：`0 / 0`。
- 唯一 DRC warning 为 `ZPS7-1`，原因是纯 PL B0 设计未实例化 PS7；它不阻断本门，B1 才引入 PS7。
- bitstream SHA-256：`df16ed6ccd9124f2dc4391d96e868ebd7846aebf3df335099b742cc7cd318971`。
- manifest记录 `git_worktree_clean=false`，原因是构建时存在尚未提交的文档/Nexus更新；源码提交和各输入文件哈希已绑定。

本地生成报告位于 `boards/hellozynq/b0_smoke/build/`。该目录是本机证据输出，不替代版本化源码和复现脚本。

## JTAG 证据

- 当前 bitstream `df16ed6c...8971` 于 `2026-09-07T10:22:56Z` 正式 program PASS。
- JTAG target 为 `localhost:3121/xilinx_tcf/Digilent/210251A08870`，device 为 `xc7z020_1`。
- program 后 `DONE_INTERNAL=1`、`DONE_PIN=1`、`ISC_DONE=1`；`CRC_ERROR=0`、`IDCODE_ERROR=0`、`SECURITY_ERROR=0`。
- `archive_b0_program_run.ps1` 已将第一次 program 的机器证据固化到 `artifacts/logs/hellozynq_b0/20260907T102256Z_df16ed6c_run1_machine/`；归档 manifest 绑定 bitstream `df16ed6c...8971`、program log `0152fe32...a49e`，并明确标记 `observation_status=PENDING`。
- 同一 run-1 目录的 `field_observation.json` 记录 `stable_blinking_confirmed=true`、`approximate=true`、`approximate_complete_period_seconds=1.0`，状态仍为 `PERIOD_QUANTIFICATION_PENDING`；当前 SHA-256 为 `3d54ffeb...0fa55`。旧 `fb0d9318...ea9e` 仅对应更新前版本，不再作为当前文件哈希。
- 历史 bitstream `c16a1f8...e3d1` 的两次 JTAG program 及其 DONE 证据继续保留，不与当前产物混算。
- 配置寄存器证明当前产物已被器件接受，不直接证明外部 P20 LED 的肉眼行为。

## 剩余验收

1. 确认实际观察的是板上 `PL_LED1`，对应 FPGA P20，而不是相邻 LED。
2. 从一次“刚亮”开始计时，到第 10 次完整周期后的“再次刚亮”停止，测量 10 个完整周期总时长。
3. 理论总时长为 `13.4217728 s`；人工秒表通过窗预先冻结为 `12.6–14.2 s`。近似 `1.0 s/周期` 不能替代该定量结果。
4. 若落在通过窗内，继续补全 run-1；若落在窗外，再核对观察对象和 M19 实际频率。当前不判 FAIL。
5. 第一次 program 的机器日志已固化；定量观察通过后，将完整观察记录纳入 run-1 并关闭其 `PENDING` 状态。
6. 只有周期合同通过后才恢复完整断电、同一 bitstream 第二次 program/观察和 run-2 固化。

以上项目和最终双运行摘要全部通过后才能将 B0 提升为 `B0_COMPLETE`，随后进入 B1 的 PS7、DDR、UART 与 PHY 基础设施验证。

## 发布状态审计快照

- PR #69 已创建，base 为 `main@7857d32561cbd5f86d02b1a21ee0edfb3ae895f1`。
- 2026-09-07 的观测状态为 `OPEN / CLEAN / MERGEABLE`。
- 审计时 HEAD 为 `8db816d29beabc490851719c34a83a6f603fc321`；这是固定历史快照，不是会随 PR 后续提交自动更新的“当前 HEAD”。
- GitHub Actions 已关闭，`statusCheckRollup` 为空；空 checks 只表示未运行，不是通过证据。
- LED 稳定闪烁已确认，但周期量化、完整 run-1 和断电复测仍 pending，因此 PR #69 暂不合并。
