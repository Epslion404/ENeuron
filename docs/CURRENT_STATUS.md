# 当前状态

更新时间：2026-09-13

## 结论

当前项目状态为：`FUNCTIONAL_PASS / PHYSICAL_PASS / B3_MVP_GATE_PASS / B3_SPEED_MEASURED / B3_SPEED_GATE_OPEN / B3_POWER_GATE_OPEN / B3_STRICT_DEFERRED_STRUCTURAL / B2_GATE_PENDING`。

主线是 `xc7z020clg484-2` 上部署 NPU，并用 ENeuron 组级动态剪枝证明推理加速与功耗下降。B3-MVP-GATE 已关：同一 200 MHz bitstream 上 dense/full-open/static/live 小集合 A/B、epoch 读回和局部周期差值可回放。单样本速度诊断已完成，但端到端加速未证明；外部功耗未测。严格连接级 `2:4` 是结构实验，不是当前加速硬门。

## 已确认事实

- B3-04 集中实现（RTL 身份 `be84596`）通过：`WNS=+0.045 ns`、`TNS=0`、`WHS=+0.036 ns`、`THS=0`、DSP48E1=4。bit SHA-256=`0ecbe76274c39418f2a60a88358d3ff6f09f5a2ed73a44a3a419c34eb91d3a11`，XSA SHA-256=`135d979d61c629922ee5419e51dd97ef045d9bab79930432816d09f109291d1a`。
- B3-11 实板：COM15 overlap 两次 hold 窗口 JTAG `0x54=0` / `0x58=1`，样本后 `active=1 pending=0`。0x50/5C/60 可读；0x00–0x4C 未改址。
- B3-13/14 两轮一致：dense/full-open `592/0` 组、`2494` cycles、logits `165,-18,...,153`；static `296/296`、`1606` cycles、logits `74,-18,...,114`；live `296/296`、`1606` cycles、logits 与 dense 相同且 `decision_source=live_eneuron_s2`。证据 `artifacts/logs/b3_mvp_20260912_be84596/`。
- Vivado 2024.1，器件 `xc7z020clg484-2`，`clk_fpga_0=200 MHz`。
- 已签核 packet 基线 routed timing：`WNS=+0.005 ns`、`TNS=0`、`WHS=+0.034 ns`、`THS=0`；route errors 和 DRC hard errors 均为 `0`。
- 计数器版本第三次 routed build `build_route_explore_20260912` 通过 `xc7z020clg484-2`、200 MHz 物理门：`WNS=+0.008 ns`、`TNS=0`、`WHS=+0.036 ns`、`THS=0`，route errors/DRC hard errors 为 `0`，DSP48E1 为 `4`。bit SHA-256=`5c6ebc07beb4bae83f5ddd1870ad2e4f53ccf56b244ae7577186c8398c910a88`，XSA SHA-256=`862883742e77e48c566fc49cc14746bc70830e27c894bdf948085c534177a614`。
- B3 目标门与测试管理修正已由 PR #91 合并到 `main@30e3b38`；后续 checkout 身份以 Git 实时输出为准。下载/签核物理身份仍是 RTL `be84596`，bit SHA-256=`0ecbe762…3a11`。历史 HEAD `13abdb7`/`3d26340`/`c3a50eb`/`88bec9e` 只描述当时产物，不得覆盖本条；clean worktree 发布身份仍属 B3-01。
- 新计数器版本在 COM15 完成三次同源实板运行：dense `20260912T093643Z`、full-open `20260912T094035Z`、bypass `20260912T094155Z`。三次均通过 XSCT/JTAG/UART、完整结果帧 CRC、sample/model/epoch 元数据和黄金 logits `165,-18,14,0,0,0,0,0,0,153`。
- 三次运行后的 `probe_b2_state.tcl` 均读回 `sample=8/8`、`response=1/1`、`result=10/1`、`fence_snapshot_valid=1`，并且 `execute_group_count=592`、`skip_group_count=0`；command 计数为 dense/full-open `658/658`、bypass `637/637`。这关闭 B3-00、B3-06、B3-07，不代表静态 `2:4` 或 live-ENeuron 已完成。
- 静态 mixed run `20260912T102046Z` 使用同一 bit/XSA、COM15 和 `b3_static_mixed` ELF 通过 UART；`B3_STATIC_MASK_VALID` 报告 `592` 组中 `296/296`，结果 logits 为 `74,-18,14,0,0,0,0,0,0,114`。随后 XSCT probe 读回 `sample=8/8`、`response=1/1`、`result=10/1`、`fence_snapshot_valid=1`、`execute_group_count=296`、`skip_group_count=296`。该证据只关闭组级 static mixed 子门，不关闭严格连接级 `2:4`。
- live ENeuron run `20260912T131302Z`（HEAD `fe25a70`、COM15、同一 bit/XSA）UART `B3_LIVE_ENEURON_PASS`，logits=`165,-18,14,0,0,0,0,0,0,153`，`decision_source=live_eneuron_s2`。JTAG `execute/skip=296/296`、`fence_snapshot_valid=1`。证据 `artifacts/logs/b3_live_eneuron_pass_20260912_fe25a70/`。关闭 B3-09 组级 live 路径，不是严格 `2:4`。

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
- B3-MVP-GATE 已关。`B3-SPEED-MEASURED` 已完成，但它只是单样本嵌套计时诊断；`B3-SPEED-GATE` 因端到端加速未证明而保持打开。功耗仪器合同已冻结但仍是 `POWER_NOT_MEASURED`；`B3-POWER-MEASURED` 与 `B3-POWER-GATE` 都未关闭，完成测量也不能自动代表降功耗。`B3-GOAL-GATE` 因此保持打开。B2-GATE 挡网口发布。
- 计数器对外仍保持 32 位 AXI-Lite 读口；核心内部加法收窄为 24 位，可覆盖 B3-13 的 10000 样本上限（`592 * 10000 = 5,920,000 < 2^24`）。
- Pulse-Mini-L/L2 集成。它们是冻结的候选/历史支线，不是当前日常门。

旧软件状态区 `0x01008000` 没有由 packet smoke 初始化，当前读取值不可作为账本证据。

## 下一步

1. 主线并列为 `B3-SPEED-GATE` 与 `B3-POWER-GATE`：提交 `82b079e` 已消除 512 次重复 L0 `group_mac`，三次实板保持数值/计数正确且 `ps_us=827/829/828`，低于历史单次 996；但 dense L0 扫描仍存在，也尚未冻结不含 UART 的重复端到端 A/B。功耗线仍需要外部仪器和明确统计门限。当前分别为 `END_TO_END_ACCELERATION_NOT_PROVEN` 与 `POWER_NOT_MEASURED`。
2. B2-GATE 剩余项并行，挡网口发布。
3. 不把 888 cycle 写成端到端加速，不用 Vivado 估算冒充板上功耗。

## 文档口径

`task_plan.md`、`findings.md`、`progress.md` 是历史规划与执行日志，不是当前状态的唯一入口。当前结论以本页、`WORKFLOW_STATE.md` 和对应 manifest/原始日志为准。
