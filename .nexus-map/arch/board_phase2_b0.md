# 项目阶段 2：HelloZynq B0 实板基础验证

verified_at: 2026-09-07

## 当前结论

状态为 `CURRENT_BITSTREAM_PROGRAM_PASS / B0_FIELD_OBSERVATION_PENDING`，**B0 尚未完成**。

当前源码的正式构建和当前 bitstream 的 JTAG 下载均已通过。历史等价设计的 bitstream 两次 program 记录继续保留为历史边界。仍缺用户现场确认 P20 LED 和断电复测；在这两项完成前不得标记 `B0_COMPLETE`，也不得据此宣称 NPU、ENeuron、PS7、DDR、DMA 或网口已经上板通过。

## 基线与最小电路

- PR #68 已合并到 `main`，merge commit 为 `7857d32561cbd5f86d02b1a21ee0edfb3ae895f1`。
- 当前 B0 源码提交为 `f3b8174e8ca30d427e9de3eea2d36feb6a5e6a06`；历史两次 program对应 `367c81316dc6fdc48105d6c657952a66314436bd`。
- 目标器件为 `xc7z020clg484-2`，取代历史 T3 OOC 使用的 `xc7z020clg400-1` 作为阶段 2 实板目标；历史 OOC 证据仍有效，但不能用于实际引脚签核。
- 最小电路为 M19 上的 50 MHz PL 时钟驱动 26-bit counter，计数器最高位输出到 P20 LED。
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
- 历史 bitstream `c16a1f8...e3d1` 的两次 JTAG program 及其 DONE 证据继续保留，不与当前产物混算。
- 配置寄存器证明当前产物已被器件接受，不直接证明外部 P20 LED 的肉眼行为。

## 剩余验收

1. 第一次现场观察板上 `PL_LED1`（FPGA P20）至少 10 个完整周期。
2. 第一次 program 的机器日志已固化；完成现场观察后，将观察记录纳入同一 run-1 边界并关闭其 `PENDING` 状态。
3. 关闭主电源，确认供电指示消失且原 JTAG device 不可访问，以证明完整断电而非热重连。
4. 重新上电，对同一 `df16ed6c...8971` 执行第二次正式 program，并复核身份、三项 DONE 与错误位。
5. 第二次观察同一 `PL_LED1/P20` 至少 10 个完整周期，将 program 与观察记录固化为 run-2。

以上项目和最终双运行摘要全部通过后才能将 B0 提升为 `B0_COMPLETE`，随后进入 B1 的 PS7、DDR、UART 与 PHY 基础设施验证。

## 发布状态审计快照

- PR #69 已创建，base 为 `main@7857d32561cbd5f86d02b1a21ee0edfb3ae895f1`。
- 2026-09-07 的观测状态为 `OPEN / CLEAN / MERGEABLE`。
- 审计时 HEAD 为 `8db816d29beabc490851719c34a83a6f603fc321`；这是固定历史快照，不是会随 PR 后续提交自动更新的“当前 HEAD”。
- GitHub Actions 已关闭，`statusCheckRollup` 为空；空 checks 只表示未运行，不是通过证据。
- P20 现场观察和断电复测仍为 pending，因此 PR #69 暂不合并。
