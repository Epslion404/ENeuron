# HelloZynq B0 实板 smoke 阶段报告

状态：`RUN1_PROGRAM_AND_LED_PASS / COMPLETE_POWER_OFF_PASS / RUN2_PENDING`

日期：2026-09-07

## 本轮范围

本轮只验证 `xc7z020clg484-2` 的 PL配置链、M19 50 MHz时钟约束和 P20 LED最小路径。设计不含 PS7、DDR、Ethernet、ILA、DMA、NPU或 ENeuron。

## 身份

- PR #68 merge commit：`7857d32561cbd5f86d02b1a21ee0edfb3ae895f1`。
- 当前 B0 源码提交：`f3b8174e8ca30d427e9de3eea2d36feb6a5e6a06`。
- 历史两次 program 对应源码提交：`367c81316dc6fdc48105d6c657952a66314436bd`。
- 板厂参考提交：`73d529d8f159ca372b7d9855eddc80880ecd9d05`。
- Vivado：2024.1，目标：`xc7z020clg484-2`。
- 当前正式候选 bitstream SHA-256：`df16ed6ccd9124f2dc4391d96e868ebd7846aebf3df335099b742cc7cd318971`。
- 历史已 program bitstream SHA-256：`c16a1f8a035c9f5d70677cf71e433b8b19e040ff336d58c85efc89761e85e3d1`。

## 当前正式候选实现结果

| 项目 | 结果 |
|---|---:|
| LUT | 1 |
| FF | 26 |
| BRAM | 0 |
| DSP | 0 |
| BUFG | 1 |
| WNS / TNS | +17.918 ns / 0 |
| WHS / THS | +0.251 ns / 0 |
| route errors | 0 |
| DRC Error / Critical Warning | 0 / 0 |

唯一 DRC Warning 为 `ZPS7-1`。它来自批准的 PL-only B0 不实例化 PS7；本轮明确不把该实现用于验证 PS默认配置。B1 接入 PS7 后必须重新做完整顶层 DRC，不能沿用本次解释。

当前构建时工作树含尚未提交的文档和证据更新，因此 manifest 如实记录 `git_worktree_clean=false`。RTL、XDC、构建/编程脚本哈希和源码提交均已绑定；这不影响实现结果，但最终报告必须保留该事实。

## 当前产物 JTAG 实测

当前 `df16ed6c...8971` 于 `2026-09-07T10:22:56Z` 通过正式入口下载到：

- target：`localhost:3121/xilinx_tcf/Digilent/210251A08870`
- device：`xc7z020_1`
- `DONE_INTERNAL=1`
- `DONE_PIN=1`
- `ISC_DONE=1`
- CRC error / IDCODE error / security error：`0 / 0 / 0`
- program log SHA-256：`0152fe3258cefb16f6e7efd3b12058e5da6cd352c8416f3d12a290e21d6ea49e`
- run-1 机器证据目录：`artifacts/logs/hellozynq_b0/20260907T102256Z_df16ed6c_run1_machine/`
- 现场观察：用户确认 `PL_LED1/P20` 稳定闪烁。
- 10个完整周期实测：13.42秒。
- 理论值 / 预冻结通过窗：13.4217728秒 / 12.6～14.2秒。
- 误差：约-0.013%。
- 观察状态：`PASS`

脚本终态为 `B0_PROGRAM_PASS`，并再次输出实际下载哈希 `df16ed6c...8971`。这证明当前候选已被目标器件接受，但仍不替代对P20输出的现场观察。

run-1 已在第二次下载前固化，归档包含原始 program result、完整 transcript、构建 manifest及各文件 SHA-256；后续 run-2 不得覆盖该目录。归档时工作树含尚未提交的规划和归档脚本，manifest 已明确记录 `archive_worktree_clean=false`，未伪装为干净提交证据。

当前 RTL 为 `led=counter[25]`。在 50 MHz 下，LED 每 `2^25 / 50 MHz = 0.67108864 s` 翻转一次，即亮约0.671秒、灭约0.671秒；完整“亮→灭→再亮”周期为1.34217728秒。10周期实测13.42秒与理论13.4217728秒一致，并通过事前冻结的12.6～14.2秒窗口。因此先前单周期“约1秒”的目测差异不是时钟或引脚故障证据，run-1现场周期门已关闭。

## 历史 JTAG 实测

目标为 `localhost:3121/xilinx_tcf/Digilent/210251A08870/xc7z020_1`。

第一次下载前 Vivado明确报告 `DONE=0`。下载命令成功后：

- `DONE_INTERNAL=1`
- `DONE_PIN=1`
- `ISC_DONE=1`
- End of startup：HIGH

第二次对同一 SHA-256 bitstream 重复下载也成功，下载前后上述 DONE状态均保持为 1。两次运行分别记录于 `2026-09-07T09:49:51Z` 和 `2026-09-07T09:51:40Z`。

这两次记录绑定历史 bitstream `c16a1f8...e3d1`，只保留为配置链重复性历史证据；当前状态由上一节的 `df16ed6c...8971` program记录决定。

## 尚未关闭的硬门

完整断电已于 `2026-09-07T15:02:49Z` 通过只读 JTAG探针确认：精确 Digilent线缆仍被枚举，target无法打开且Vivado明确报告 `No devices detected`，可访问FPGA数为0。原始证据位于 `artifacts/logs/hellozynq_b0/20260907T150221Z_df16ed6c_power_off/`，transcript SHA-256为 `3a953999dc611332f19fa9a12c7fcafc04f9fdbd425cb8dc92fc0b4a0da1f634`。这排除了仅断开调试线或热重连的情况。

尚未关闭：

- 重新上电、连接JTAG并下载同一 `df16ed6c...8971`。
- 再次观察 `PL_LED1/P20` 至少10个完整周期并固化run-2。

run-2完成前，准确状态是“run-1与完整断电通过、重新上电恢复待验证”，不是 B0 最终通过。当前证据不证明 PS、DDR、Ethernet、DMA、NPU或 ENeuron。
