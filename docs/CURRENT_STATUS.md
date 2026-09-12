# 当前状态

更新时间：2026-09-12

## 结论

当前项目状态为：`FUNCTIONAL_PASS / PHYSICAL_PASS / B3_FIXED_VECTOR_PASS / BOARD_STATUS_PARTIAL`。

主线是 `xc7z020clg484-2` 上的 packet-NPU 与 ENeuron 动态剪枝 A/B。当前已经完成 NPU packet 基线、计数器物理门、dense/full-open/bypass 固定向量实板闭环，以及组级 `group_4way` 静态 mixed mask 实板闭环；还没有完成严格连接级 `2:4`、live-ENeuron 动态剪枝收益、功耗收益或 B2-GATE。

## 已确认事实

- Vivado 2024.1，器件 `xc7z020clg484-2`，`clk_fpga_0=200 MHz`。
- 已签核 packet 基线 routed timing：`WNS=+0.005 ns`、`TNS=0`、`WHS=+0.034 ns`、`THS=0`；route errors 和 DRC hard errors 均为 `0`。
- 计数器版本第三次 routed build `build_route_explore_20260912` 通过 `xc7z020clg484-2`、200 MHz 物理门：`WNS=+0.008 ns`、`TNS=0`、`WHS=+0.036 ns`、`THS=0`，route errors/DRC hard errors 为 `0`，DSP48E1 为 `4`。bit SHA-256=`5c6ebc07beb4bae83f5ddd1870ad2e4f53ccf56b244ae7577186c8398c910a88`，XSA SHA-256=`862883742e77e48c566fc49cc14746bc70830e27c894bdf948085c534177a614`。
- 当前文档 HEAD 为 `379c8d8`；物理产物 manifest 绑定源码构建身份 `c3a50eb`，Nexus 文档提交未改变 RTL/软件源文件，工作树仍非 clean，后续需在 clean worktree 重建正式 manifest。
- 新计数器版本在 COM15 完成三次同源实板运行：dense `20260912T093643Z`、full-open `20260912T094035Z`、bypass `20260912T094155Z`。三次均通过 XSCT/JTAG/UART、完整结果帧 CRC、sample/model/epoch 元数据和黄金 logits `165,-18,14,0,0,0,0,0,0,153`。
- 三次运行后的 `probe_b2_state.tcl` 均读回 `sample=8/8`、`response=1/1`、`result=10/1`、`fence_snapshot_valid=1`，并且 `execute_group_count=592`、`skip_group_count=0`；command 计数为 dense/full-open `658/658`、bypass `637/637`。这关闭 B3-00、B3-06、B3-07，不代表静态 `2:4` 或 live-ENeuron 已完成。
- 静态 mixed run `20260912T102046Z` 使用同一 bit/XSA、COM15 和 `b3_static_mixed` ELF 通过 UART；`B3_STATIC_MASK_VALID` 报告 `592` 组中 `296/296`，结果 logits 为 `74,-18,14,0,0,0,0,0,0,114`。随后 XSCT probe 读回 `sample=8/8`、`response=1/1`、`result=10/1`、`fence_snapshot_valid=1`、`execute_group_count=296`、`skip_group_count=296`。该证据只关闭组级 static mixed 子门，不关闭严格连接级 `2:4`。

证据入口：

- [packet run manifest](../boards/hellozynq/b2_sw/build/88bec9e9bdbec1de53ef45d2f22e4275308c0237/direct/runs/20260912T040206Z/run_manifest.json)
- [status probe 原始输出](../boards/hellozynq/b2_sw/build/88bec9e9bdbec1de53ef45d2f22e4275308c0237/direct/runs/20260912T040206Z/status_probe_20260912T120539Z/probe_stdout.log)
- [硬件构建 manifest](../boards/hellozynq/b2_sw/build/88bec9e9bdbec1de53ef45d2f22e4275308c0237/direct/build_manifest.json)
- [计数器版本 dense run](../boards/hellozynq/b2_sw/build/379c8d84859b8430c4ccde0b4e22ad5ce74781c9/direct/runs/20260912T093643Z/run_manifest.json)
- [计数器版本 full-open run](../boards/hellozynq/b2_sw/build/379c8d84859b8430c4ccde0b4e22ad5ce74781c9/direct/runs/20260912T094035Z/run_manifest.json)
- [计数器版本 bypass run](../boards/hellozynq/b2_sw/build/379c8d84859b8430c4ccde0b4e22ad5ce74781c9/direct/runs/20260912T094155Z/run_manifest.json)
- [dense 计数器 probe](../boards/hellozynq/b2_sw/build/c3a50ebd83bf1e93bd155c502e5abdb810cec431/direct/runs/20260912T093643Z/counter_probe_20260912T094100Z/probe_stdout.log)
- [full-open 计数器 probe](../boards/hellozynq/b2_sw/build/379c8d84859b8430c4ccde0b4e22ad5ce74781c9/direct/runs/20260912T094035Z/counter_probe_20260912T094200Z/probe_stdout.log)
- [bypass 计数器 probe](../boards/hellozynq/b2_sw/build/379c8d84859b8430c4ccde0b4e22ad5ce74781c9/direct/runs/20260912T094155Z/counter_probe_20260912T094300Z/probe_stdout.log)
- [计数器版本硬件 manifest](../boards/hellozynq/b2_hw/build/build_manifest.json)

## 尚未完成

- clean worktree 重建，确认最终可复现 manifest。
- B2-06～B2-10 的多 packet、完整错误矩阵、复位账本、统一时间戳和正式机器证据包。
- B2-GATE 发布门。
- B3-00、B3-02、B3-06、B3-07 和 B3-08a 已在同一通过物理门的计数器 bitstream 上关闭；B3-02 的 Python/Host 共享 manifest 已通过合同测试。B3-01 仍待补齐全量文件 SHA-256 与最终 clean 身份冻结；B3-03～B3-05、严格连接级 `2:4`、ENeuron 动态 mask A/B、epoch 原子性/恢复矩阵、周期和功耗测量仍未完成，不能外推为完整 B3-GATE。
- 计数器对外仍保持 32 位 AXI-Lite 读口；核心内部加法收窄为 24 位，可覆盖 B3-13 的 10000 样本上限（`592 * 10000 = 5,920,000 < 2^24`）。
- Pulse-Mini-L/L2 集成。它们是冻结的候选/历史支线，不是当前日常门。

旧软件状态区 `0x01008000` 没有由 packet smoke 初始化，当前读取值不可作为账本证据。

## 下一步

1. 在当前文档提交后的 clean worktree 上重建同源 bit/XSA/ELF，冻结正式 manifest 身份。
2. 补齐 Host 严格连接级 `2:4` mask；组级 `group_4way` mixed mask 已完成，但不能替代该门。
3. 接入 ENeuron 证据到动态 mask 的 pending/fence/epoch 路径，再做重复性、恢复和精度 A/B。
4. 在统一时间戳和外部测量条件下补齐周期、吞吐和功耗/能耗证据，并继续收口 B2 发布门。

## 文档口径

`task_plan.md`、`findings.md`、`progress.md` 是历史规划与执行日志，不是当前状态的唯一入口。当前结论以本页、`WORKFLOW_STATE.md` 和对应 manifest/原始日志为准。
