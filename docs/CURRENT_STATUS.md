# 当前状态

更新时间：2026-09-14

## 当前裁定（B3-22.3 后）

`B3-22.2`、`B3-22.3` 与 `B3-22.4` 首轮均已完成。校准 static 在零决策成本下相对 dense 旧路径仅改善约 `2%`（`157→154 us`）；B3-22.4 优化路径后 dense `63–64 us`、calibrated `60 us`，动态 live 仍为 `623 us`（mask compute 占 80.5%）。当前主线为固定协议开销/批量 sample DMA 与 fence 摊销实验；PL-auto、PS NEON 暂缓。精度口径拆分为 `output_preservation=PASS` 与 `task_accuracy=MODEL_TASK_FIT_UNVERIFIED`；`accuracy_gate=ACCURACY_NEAR_DENSE` 仅表示输出保持，不代表任务精度。`B3-SPEED-GATE`、`B3-POWER-GATE`、`B3-GOAL-GATE` 仍保持 OPEN。

## 结论

当前项目状态为：`FUNCTIONAL_PASS / PHYSICAL_PASS / B3_MVP_GATE_PASS / B3_L0_CACHE_BOARD_DIAGNOSTIC_PASS / B3_SPEED_MEASURED / B3_ACCURACY_GATE_OPEN / B3_SPEED_GATE_OPEN / B3_POWER_NOT_MEASURED / B3_POWER_GATE_OPEN / B3_GOAL_GATE_OPEN / B3_STRICT_DEFERRED_STRUCTURAL / PL_AUTO_MASK_CONTRACT_PASS / PL_AUTO_MASK_BOARD_PENDING / B2_GATE_PENDING`。

主线是 `xc7z020clg484-2` 上部署 NPU，并用 ENeuron 组级动态剪枝证明推理加速与功耗下降且基本保持精度。B3-MVP-GATE 已关：同一 200 MHz bitstream 上 dense/full-open/static/live 小集合 A/B、epoch 读回和局部周期差值可回放。第一轮 16 样本速度测量结论为 `NO_END_TO_END_SPEEDUP`；B3-20.1/20.2 已完成 K=16 mask 摊销及 3 组 dense/live 对称复测。PL staging 与 PS mask 计算优化后的 64 样本多输入复测已通过：live `722–727 us`、dense `155–159 us`；live 仍约为 dense 的 `4.65×`，尚未形成端到端加速。优化后的 live 累计 `mask_us=36324 us`，相对上一版约 `55688 us` 下降约 35%，但 PS mask 决策仍是主要瓶颈。外部功耗未测，速度门和精度门保持 OPEN。精度证明链已补齐模式相关 epoch 合同、板端标签采集字段、1000 样本分块生成和 dense/live 合并工具；2026-09-14 已完成 1024 样本成对采集（v2 报告：agreement 1.0、golden 1024/1024、协议 2048/2048），输出保持单独成立，任务精度因模型/任务适配性未证明不能进入门判定。严格连接级 `2:4` 仍是结构实验，不是当前加速硬门。

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
- PR #93 已合并到 `main@1c64245`。提交 `82b079e` 复用 L0 contribution，同源 bit/XSA、新 ELF 三次实板为 `ps_us=827/829/828`，logits、`296/296`、1606 cycles 与 protocol errors=0 均保持。证据 `artifacts/logs/b3_live_l0_cache_20260913_82b079e/`；这是缓存诊断通过，不是速度门通过。
- B3-17C 实板速度账本已完成，使用同一 `be84596` bit/XSA、固定 16 样本和 warm-up 条件。dense run `20260913T182533Z` 为 `16/16 PASS`，端到端窗口 `155–156 us`（中位数 `155 us`），NPU `2494 cycles`、执行/跳过组 `592/0`；live run `20260913T182626Z` 为 `16/16 PASS`，窗口 `1384–1387 us`（中位数 `1386 us`），NPU `1606 cycles`、执行/跳过组 `296/296`，累计 `mask_us≈19700 us`；static mixed run `20260913T182853Z` 为 `16/16 PASS`，窗口 `152–154 us`（中位数 `153 us`）。三种模式协议错误均为零，早期 warm-up 失败 run 不纳入比较。
- B3-22 第一轮判定及 K=16 复判均已完成：第一轮 live 相对 dense 的端到端中位数约 `8.94×` 更慢；复判中 dense 完整窗口均值/中位数约 `155.5/155 us`，live K=16 约 `229.7/153 us`，首样本约 `1.38 ms`。局部 NPU 节省 `888 cycles` 未转化为完整窗口系统级加速，`B3-SPEED-GATE` 保持 OPEN。
- B3-20.1 已完成首轮实板验证：dense `20260914T002537Z` 为 `155–156 us`；live K=1 `20260914T002627Z` 为 `1384–1388 us`、`mask_us=19701 us`；live K=16 `20260914T002938Z`/`20260914T003122Z` 均 `16/16 PASS`，首样本 `1380/1381 us`、后续 `153–154 us`、中位数 `153 us`、`mask_us=1225/1226 us`。每样本 fence、epoch、CRC、`296/296` 与协议检查均通过；失败的“省略 fence”尝试 `20260914T002715Z` 仅作失败证据。该结果仍不足以关闭速度门。
- B3-18c 优化后复测：同一 bit/XSA/JTAG 条件和 64 个不同输入下，live `20260914T062138Z` 为 `64/64 PASS`、epoch `2→65`、执行/跳过 `296/296`、协议错误 `0`、端到端 `722–727 us`、累计 `mask_us=36324 us`；同源 dense `20260914T062313Z` 为 `64/64 PASS`、端到端 `155–159 us`、执行/跳过 `592/0`。证据目录位于 `boards/hellozynq/b2_sw/build/17d07727c73845e51c22a7835eac94e04cb22fa7/direct/runs/b3_speed/`。

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
- [live L0 缓存三次实板证据](../artifacts/logs/b3_live_l0_cache_20260913_82b079e/README.md)

## 尚未完成

- clean worktree 重建，确认最终可复现 manifest。
- B2-06～B2-10 的多 packet、完整错误矩阵、复位账本、统一时间戳和正式机器证据包。
- B2-GATE 发布门。
- B3-MVP-GATE 已关。`B3-SPEED-MEASURED`、`B3-17C`、B3-20.1、B3-20.2、B3-18a/b/c 和两轮 `B3-22` 判定已完成；`B3-SPEED-GATE` 因完整窗口端到端加速未证明而保持打开。64 样本多输入 dense/live 对称实测已完成，但 live 仍明显慢于 dense；当前主动任务为固定协议开销与批量切片评审。1024 样本成对采集和 v2 输出保持报告已完成：`output_preservation` 通过，`task_accuracy` 因模型/任务适配性未证明而保持 `MODEL_TASK_FIT_UNVERIFIED`；当前 fixture 另判 `GATE_VACUOUS / MODEL_UNDER_DETERMINED`。在精度门或速度门通过前不转入正式功耗线。功耗仪器合同已冻结但仍是 `POWER_NOT_MEASURED`；`B3-POWER-MEASURED` 与 `B3-POWER-GATE` 都未关闭。B2-GATE 挡网口发布。
- 计数器对外仍保持 32 位 AXI-Lite 读口；核心内部加法收窄为 24 位，可覆盖 B3-13 的 10000 样本上限（`592 * 10000 = 5,920,000 < 2^24`）。
- Pulse-Mini-L/L2 集成。它们是冻结的候选/历史支线，不是当前日常门。

旧软件状态区 `0x01008000` 没有由 packet smoke 初始化，当前读取值不可作为账本证据。

## 下一步

1. 执行 `B3-22.1a/b/c/d`：完成 64 样本多输入 dense/live 对称实测，并按模式相关 epoch 合同核对每个样本。
2. 执行 `B3-22.1e/e1/f`：运行 `b3_accuracy_dataset.py` 生成至少 1000 个带标签样本的 64 样本分块，逐块完成 dense/live 板端 logits 采集，用 `b3_accuracy_merge.py` 合并，再计算 Top-1 一致率、dense/live 准确率差、logit 误差和每类召回率；speed 账本的 `result_crc` 不足以做精度证明。目标为观测一致率 `≥99%` 且 Wilson 95% 下界也 `≥99%`，准确率绝对下降 `≤1.0` 个百分点且配对差值 95% 上界也 `≤1.0` 个百分点。
   本地统计入口：`python b3_accuracy_report.py <accuracy_samples.json|jsonl> -o b3_accuracy_report.json`。输入顶层 `identity` 必须绑定 `model`、`preprocess`、`bitstream_sha256`、`xsa_sha256`、`elf_sha256`；样本必须含 `sample_id`、输入身份、`mask_epoch`、dense/live logits、标签和协议/CRC 校验字段。工具输出 `status=PASS` 且 `accuracy_gate=ACCURACY_NEAR_DENSE` 才可进入门判定；该门仅表示 output_preservation（与 dense 输出一致），不代表任务精度通过。
3. 执行 `B3-22.1c/d`：在同一板卡、bit/XSA、JTAG、warm-up 和统计口径下完成至少 3 组 dense/live 对称实测；精度门或速度门未通过时按证据优化并回到 B3-22.1，二者都通过后才进入功耗测量。`82b079e` 的 `ps_us=827/829/828` 只证明 Host 诊断改善，仍不代表端到端加速；不得把 888 cycle 写成端到端加速，不得用 Vivado 估算冒充板上功耗。

## 文档口径

`task_plan.md`、`findings.md`、`progress.md` 是历史规划与执行日志，不是当前状态的唯一入口。当前结论以本页、`WORKFLOW_STATE.md` 和对应 manifest/原始日志为准。

2026-09-14 补记（B3-22.2 与 1024 样本输出保持）：

- B3-22.2 实板拆分（同一 `be84596` bit/XSA、64 样本）：live `20260914T092629Z` 的 `mask_us=36345 us` 中 compute `32160 us`（502/样本，88.5%）、submit `4156 us`（65/样本，11.5%）；同源 dense `20260914T092552Z` 中位数 `157 us`、`2494 cycles`、`592/0`，live `725 us`、`1606 cycles`、`296/296`，协议错误均为 0。
- B3-22.1f 1024 样本（16×64 dense/live 板级采集）输出保持：`prediction_agreement=1.0`（Wilson 95% 下界 `0.99626`）、`logit_exact_match=1024/1024`、logit 误差 0、`accuracy_drop_pp=0`；解析修复后的 v2 报告 `artifacts/results/b3_accuracy_1024_board_report_v2.json` 为 `PASS / ACCURACY_NEAR_DENSE`（仅 output_preservation），与 Python golden 逐项 `1024/1024` 一致。dense/live 准确率均 `11.23%`，任务精度判 `MODEL_TASK_FIT_UNVERIFIED`，不自动归因标签语义。

2026-09-14 补记（B3-22.3 零决策成本上限）：

- 512 样本校准 mask（`majority_vote_top2_stable_index_v1`，296 组）在 64 个 held-out 输入上与 dense 同源 A/B：中位数 `157→154 us`（约 `2%`）、DMA `58–59→55–56 us`、NPU `2494→1606 cycles`、执行/跳过 `592/0→296/296`，输出 `64/64` logits 一致，协议错误 0。
- 结论：决策成本为 0 时当前协议下剪枝上限约 `2%`；主要开销是每样本约 `150 us` 的固定路径，不是 mask 决策。产物 `artifacts/results/b3_calibrated_static_ab.json`。

2026-09-14 补记（B3-22.4 固定协议开销实验）：

- `submit_frame` 改为 256 字节 guard 区缓存维护、去掉重复 invalidate、`usleep(10→2)`、移除调用方全帧 invalidate；帧格式与逐样本 fence/epoch/CRC/fail-closed 语义不变。
- held-out 64 样本三组对称 A/B：dense 中位数 `157→63/64/63 us`（约 `2.45×`）、calibrated `154→60/60/60 us`（约 `2.57×`）；`fence_us` `69→18 us/样本`、DMA `58→22 us`、`result_us` `17→11 us`，输出与基线 `64/64` 逐位一致，协议错误 0。
- 产物 `artifacts/results/b3_fixed_overhead_ab.json`；速度门保持 OPEN，剩余瓶颈为 fence/result 与 DMA 往返，继续压缩需批量帧新合同。

2026-09-14 补记（优化路径 live 基线）：

- 优化后软件路径上 3 组 dense/live 对称 A/B（64 个不同输入、K=1）：dense 中位数均 `64 us`，live 均 `623 us`（`9.73×`）；live 构成 compute `501.5 us`（80.5%）、submit `56.9 us`（9.1%）、fence `18.1 us`、DMA `20 us`、PS `8 us`、result `11 us`。
- 输出 `64/64` logits 与 dense 一致、`1606 cycles`、`296/296`、协议错误 0；`B3-SPEED-GATE` 保持 OPEN，下一步为 B=4 批量协议合同。产物 `artifacts/results/b3_live_optimized_ab.json`。
