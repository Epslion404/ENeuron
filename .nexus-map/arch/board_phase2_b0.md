# 项目阶段 2：HelloZynq B0 实板基础验证

verified_at: 2026-09-07

## 当前结论

状态为 `B0_COMPLETE`，B0-GATE 已通过。

当前源码的正式构建、同一 bitstream 的两次 JTAG program、两次现场门和完整断电确认均已通过。run-1/run-2 的10周期分别为 `13.42 s`、`13.4 s`，均位于预冻结通过窗 `12.6–14.2 s`；中间断电探针证明器件不可访问，重新上电后下载前器件为未配置状态。下一执行点是将PR #69合并到main后进入B1。

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
- `archive_b0_program_run.ps1` 已将第一次 program 的机器证据固化到 `artifacts/logs/hellozynq_b0/20260907T102256Z_df16ed6c_run1_machine/`；归档 manifest 绑定 bitstream `df16ed6c...8971`、program log `0152fe32...a49e`，当前 `observation_status=PASS`。
- 同一 run-1 目录的 `field_observation.json` 记录 10 周期 `13.42 s`、平均周期 `1.342 s`、通过窗命中和 `status=PASS`；当前 SHA-256 为 `d93bcc25...ab083`。run-1 已形成机器 + 现场闭环。
- 完整断电后，run-2 于 `2026-09-07T15:26:56Z` 对同一 `df16ed6c...8971` 正式program；下载前 `DONE=0`、`PROGRAM.FILE`为空，下载后三项DONE=`1/1/1`且CRC/IDCODE/security error均为0。
- run-2目录为 `artifacts/logs/hellozynq_b0/20260907T152656Z_df16ed6c_run2_machine/`；program log SHA-256为 `1d4fada3...3613b`。现场10周期为 `13.4 s`，观察文件SHA-256为 `73c81d86...a25f8`，机器与现场状态均为PASS。
- 历史 bitstream `c16a1f8...e3d1` 的两次 JTAG program 及其 DONE 证据继续保留，不与当前产物混算。
- 配置寄存器证明当前产物已被器件接受，不直接证明外部 P20 LED 的肉眼行为。

## 完整断电与冷启动复测

- 用户已确认板卡完全断电。正式只读探针于 `2026-09-07T15:02:49Z` 精确匹配 target `localhost:3121/xilinx_tcf/Digilent/210251A08870` 1 个，但无法打开 target，且可访问器件数为 0；Vivado transcript 明确报告 `No devices detected`，断电探针结果为 `PASS`。
- 证据目录为 `artifacts/logs/hellozynq_b0/20260907T150221Z_df16ed6c_power_off/`；结果 SHA-256 为 `fe594c87bf4795fcfd7566322a0abb6e53d2c5b9fdf17683cd66cc24ce43776e`，transcript SHA-256 为 `3a953999dc611332f19fa9a12c7fcafc04f9fdbd425cb8dc92fc0b4a0da1f634`。
- 重新上电后只读探针精确恢复同一target和唯一 `xc7z020_1`，随后run-2完成下载与现场测量。
- 最终摘要已绑定两次program、两次现场观察、完整断电证据、两个运行目录和日志哈希。

以上项目全部通过，B0提升为 `B0_COMPLETE`。它只证明PL配置、M19时钟、P20路径和冷启动重复性；B1的PS7、DDR、UART、PHY及最小UDP仍需独立实板验证。

## 发布状态审计快照

- PR #69 已创建，base 为 `main@7857d32561cbd5f86d02b1a21ee0edfb3ae895f1`。
- 2026-09-07 的观测状态为 `OPEN / CLEAN / MERGEABLE`。
- 审计时 HEAD 为 `8db816d29beabc490851719c34a83a6f603fc321`；这是固定历史快照，不是会随 PR 后续提交自动更新的“当前 HEAD”。
- GitHub Actions 已关闭，`statusCheckRollup` 为空；空 checks 只表示未运行，不是通过证据。
- run-1、完整断电和run-2均已通过；最终本地验证与证据推送完成后，PR #69可进入合并判断。
