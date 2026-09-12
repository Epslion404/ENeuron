# 当前状态

更新时间：2026-09-12

## 结论

当前项目状态为：`FUNCTIONAL_PASS / PHYSICAL_PASS / BOARD_STATUS_PARTIAL`。

主线是 `xc7z020clg484-2` 上的 packet-NPU 与 ENeuron 动态剪枝 A/B。当前已经完成 NPU packet 基线和最小实板闭环，但还没有完成动态剪枝收益、功耗收益或 B2-GATE。

## 已确认事实

- Vivado 2024.1，器件 `xc7z020clg484-2`，`clk_fpga_0=200 MHz`。
- 最新 routed timing：`WNS=+0.005 ns`、`TNS=0`、`WHS=+0.034 ns`、`THS=0`；route errors 和 DRC hard errors 均为 `0`。
- 最新 packet smoke HEAD：`88bec9e9bdbec1de53ef45d2f22e4275308c0237`。
- 实板 run：`20260912T040206Z`，`COM15`，XSCT/JTAG/UART 均为 `PASS`。
- packet smoke 验证了 634 个 model words、19 个 mask words、fence、sample 和 result。
- `0x40430000` 状态块读取成功：command `658/658`、sample `8/8`、response `1/1`、result `10/1`；fence snapshot valid。
- B3 dense 固定向量已完成一次实板数值子门：run `20260912T050553Z`、COM15，B3 ELF SHA-256 为 `3dc79b7319eb7112131c7b9ff39011013640afc48a316f9745587570ea27368c`；完整 10 个 signed INT32 logits 与黄金值 `165,-18,14,0,0,0,0,0,0,153` 一致，结果帧 CRC、sample ID、model ID、mask epoch 和长度均通过。

证据入口：

- [packet run manifest](../boards/hellozynq/b2_sw/build/88bec9e9bdbec1de53ef45d2f22e4275308c0237/direct/runs/20260912T040206Z/run_manifest.json)
- [status probe 原始输出](../boards/hellozynq/b2_sw/build/88bec9e9bdbec1de53ef45d2f22e4275308c0237/direct/runs/20260912T040206Z/status_probe_20260912T120539Z/probe_stdout.log)
- [硬件构建 manifest](../boards/hellozynq/b2_sw/build/88bec9e9bdbec1de53ef45d2f22e4275308c0237/direct/build_manifest.json)

## 尚未完成

- clean worktree 重建，确认最终可复现 manifest。
- B2-06～B2-10 的多 packet、完整错误矩阵、复位账本、统一时间戳和正式机器证据包。
- B2-GATE 发布门。
- B3 dense/bypass 完整对照、静态 `2:4` 与 ENeuron 动态 mask A/B、周期和功耗测量。当前仅完成 dense/full-open 固定向量子门，不能外推为完整 B3-GATE。
- Pulse-Mini-L/L2 集成。它们是冻结的候选/历史支线，不是当前日常门。

旧软件状态区 `0x01008000` 没有由 packet smoke 初始化，当前读取值不可作为账本证据。

## 下一步

1. 固化当前 packet-NPU 基线和 clean rebuild 身份。
2. 用固定向量完成 bypass 对照，再进入静态 `2:4` mask。
3. 接入 ENeuron 动态 mask，记录结果一致性、执行/跳过 group、周期和功耗。
4. 再补齐影响发布的 B2 错误矩阵和正式证据包。

## 文档口径

`task_plan.md`、`findings.md`、`progress.md` 是历史规划与执行日志，不是当前状态的唯一入口。当前结论以本页、`WORKFLOW_STATE.md` 和对应 manifest/原始日志为准。
