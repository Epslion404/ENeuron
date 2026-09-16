# 当前状态

更新时间：2026-09-17

## CP5a 纯 PL replay 正式实板（2026-09-17）

已新增编译期可选的 `B3_PL_REPLAY_BENCHMARK`：Host 仍按既有 packet 合同装载模型并提交一个已验证 QAT 样本，`npu_clk` 域缓存该 8-beat 样本，完成 1000 次预热和 10000 次正式计量；中间结果在 PL 内消费，只把最后一次 10-beat 结果送回既有结果 FIFO。默认 dense/lossless 构建不定义该宏，正常推理路径保持原样。状态块在冻结的 `0x00–0x60` 之后新增只读 `0x64 status / 0x68 completed / 0x6C measured_cycles`。

CP5a 已完成正式实板 A/B。dense/lossless replay 完整 wrapper 均在 `xc7z020clg484-2`、200 MHz 通过物理门：dense `WNS/WHS=+0.004/+0.036 ns`，lossless `+0.005/+0.010 ns`，两者 TNS/THS、route、DRC hard error 为 0、DSP48E1=`4`。QAT `sample_index=201` 在相同 `1000` 次预热、`10000` 次计量口径下，dense=`2512 cycles/sample`、`79,617.834 samples/s`，lossless=`2302 cycles/sample`、`86,880.973 samples/s`，纯 PL 吞吐提升 `1.091225x`、延迟下降 `8.3599%`。两者 replay 固定开销均为 `18 cycles/sample`；最终结果帧、10 维 logits、CRC 完全一致，协议错误为 0，组计数均精确覆盖 `11001×592`。

CP5a 的 `1.091225x` 与该样本的核心周期比 `2494/2284=1.091944x` 一致，差异来自两侧相同的 18-cycle replay 输入/结果开销。正式证据为 `artifacts/results/b3_qat_cp5a_pl_replay_board_pair.json`。该结果只关闭单个代表性样本的 CP5a bring-up；CP5b 仍需 397 样本 PL 内循环、至少 5 轮交替 A/B，才能判定分布吞吐和 `B3-SPEED-GATE`。

附带物理修复记录：首轮 lossless replay 为 `WNS=-0.074 ns`，最差路径在 packet egress 的超宽 `response_word_count` 清零网络。该计数器真实上限为 254，收窄为 8 位后 lossless replay 达到 `WNS=+0.005 ns`；相关 egress/adapter/T1 回归通过。提交 `ac499d4` 的非 replay dense 三次 `WNS=-0.072 ns` 历史复现失败保留，不影响 CP4 或本轮 replay 的独立物理证据。

## QAT CP4 无损零组跳过实板（2026-09-16）

clean HEAD `e155091` 上，dense 与 lossless 两条完整 wrapper 均在 `xc7z020clg484-2`、200 MHz 通过物理门：dense `WNS=+0.004 ns`，lossless `WNS=+0.008 ns`，两者 `TNS=0`、`WHS=+0.036 ns`、`THS=0`、route/DRC hard error=0、DSP48E1=`4`。使用 QAT-v3 的 397 个 held-out 样本，两轮均为 `397/397 PASS`；sample ID、输入 CRC、结果 CRC、协议状态和 10 维 logits 逐样本一致，logit element mismatch=`0`、prediction mismatch=`0`、任务准确率均为 `88.665%`、下降 `0 pp`。

lossless 实板平均 `2290.272 cycles/sample`、执行/跳过组 `524.091/67.909`、跳过率 `11.4712%`，相对 dense `2494 cycles` 的核心加速为 `1.088954x`。完整 PS/DMA 单样本窗口均值为 dense `63.826 us`、lossless `63.307 us`，仅 `1.008196x`；p50=`64→63 us`、p95=`65→64 us`、p99=`66→64 us`。这说明无损跳过已在纯 PL 核心兑现，但单样本 packet 路径仍被固定开销稀释。证据为 `artifacts/results/b3_qat_cp4_lossless_zero_group_board_397.json`。

裁定：`B3-PAPER-CP4`、当前无损候选的 `B3-ACCURACY-GATE` 和 `B3-PAPER-CP5a` 已关闭。`B3-SPEED-GATE` 仍保持 OPEN，下一步是 CP5b 397 样本分布 PL 内循环与至少 5 轮交替 dense/lossless；功耗在分布吞吐负载冻结后执行。

## QAT 无损零组跳过 RTL/OOC（2026-09-15）

主 NPU 已实现 `LOSSLESS_ZERO_GROUP_SKIP` 最小切片，当前只跳过全零激活组和全零权重组，不包含 L0 ReLU 后缀早停；默认未定义宏时 dense 行为保持不变。QAT-v3 公开端口级 Icarus 对拍 `397/397` logits 逐位一致，平均 `1879.136 cycles/sample`、跳过率 `34.6207%`，相对 dense `2494 cycles` 的核心估算约 `1.3272x`。

目标器件 `xc7z020clg484-2`、200 MHz OOC 已完成五轮历史探测及一轮修复后重建。修复轮模型存储落到 `1 RAMB36`，最终 `WNS=+0.158 ns`、`TNS=0`、`WHS=+0.070 ns`、`THS=0`、route/DRC hard error=0，资源 `2068 LUT / 2848 FF / 1 BRAM36 / 4 DSP48E1`。当前状态为 `OOC_PASS_TIMING`，CP3c 已通过；该证据仍只覆盖 NPU core，不得直接当作完整 bit/XSA、板级吞吐或功耗证据。证据为 `artifacts/results/b3_qat_lossless_zero_group_rtl_sim.json` 和 `artifacts/results/b3_qat_lossless_zero_group_ooc.json`。

## QAT 新基线（2026-09-15）

QAT canonical 634-word `qat-v3-val200-temp400-150ep-seed20260914` 模型及 397 个 held-out 样本已完成 packing、训练整数 forward 与 Python reference 的逐元素对齐；对应合同测试与训练划分合同通过。重训使用 1200 train + 200 validation，397 held-out 只在训练结束后评估，最终 `train=92.50%`、`validation=90.50%`、`test=88.665%`。397 样本 Python 剪枝诊断为 dense `88.665%`、live `40.302%`、calibrated `29.471%`，分别下降 `48.363 pp`、`59.194 pp`，因此当前动态剪枝精度门失败。standalone PL auto-mask 已完成 `397/397` 仿真一致和 `1861 cycles/sample`，尚未接入主 NPU、完成 200 MHz 时序或板级验证。旧 fixed-vector 的 `output_preservation=PASS` 不能外推为 QAT 精度结论。

## QAT CP1 dense 实板（2026-09-15）

QAT dense 已在同一 `xc7z020clg484-2` bit/XSA 下完成 8 样本 smoke 和 64 样本正式对拍。64/64 样本的 sample ID、输入 CRC、结果 CRC、epoch=`1`、协议状态和 10 维 logits 均通过；logit 与 QAT manifest 逐位一致，NPU=`2494 cycles`、执行/跳过=`592/0`、端到端=`63–66 us`。证据为 `artifacts/results/b3_qat_cp1_dense_64_board.json`。该结果只关闭 QAT dense 装载/输出链，不代表剪枝精度、纯 PL 吞吐或任务准确率。

## 当前裁定（QAT 重基线后）

`B3-22.2`、`B3-22.3` 与 `B3-22.4` 首轮均已完成，但不再是当前优先级。CP0/CP1/CP3a/b/c/CP4 与 CP5a 已完成；严格 2:4 live/static 精度失败，主候选为可证明无损的零组跳过。下一步执行 CP5b 397 样本 PL 内循环、至少 10000 个正式样本和 5 轮交替 dense/lossless，测分布稳态吞吐并冻结随后功耗负载。`B3-SPEED-GATE`、`B3-POWER-GATE`、`B3-GOAL-GATE` 仍保持 OPEN。

## 结论

当前项目状态为：`FUNCTIONAL_PASS / B3_MVP_GATE_PASS / B3_QAT_CP4_BOARD_FORMAL_PASS / B3_QAT_CP5A_PL_REPLAY_FORMAL_PASS / B3_ACCURACY_GATE_PASS_LOSSLESS / B3_SPEED_GATE_OPEN / B3_POWER_NOT_MEASURED / B3_POWER_GATE_OPEN / B3_GOAL_GATE_OPEN / B3_STRICT_DEFERRED_STRUCTURAL / PL_AUTO_MASK_BOARD_DEFERRED / B2_GATE_PENDING`。

主线是 `xc7z020clg484-2` 上部署 NPU，并用可证明无损的组级动态跳过验证推理加速与功耗下降。历史 PS 在环 live 路径仍保留为负结果：64 样本 live `722–727 us`、dense `155–159 us`，PS mask 计算是主要瓶颈；它不代表当前纯 PL 候选。当前 QAT lossless 已在 clean 397 样本实板上完成输出与任务精度保持，`B3-ACCURACY-GATE` 通过；外部功耗未测，`B3-SPEED-GATE` 和功耗门仍 OPEN。严格连接级 `2:4` 仍是精度失败的结构实验，不是当前加速硬门。

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
- B3-MVP-GATE、QAT CP4 与无损候选的 `B3-ACCURACY-GATE` 已关；`B3-SPEED-GATE` 因连续流吞吐尚未测量而保持打开。当前主动任务是 CP5 的纯 PL 连续吞吐，B3-22.5 批量协议、严格 2:4 和独立 PL-auto 均后置。功耗仪器合同已冻结但仍是 `POWER_NOT_MEASURED`；`B3-POWER-MEASURED` 与 `B3-POWER-GATE` 都未关闭。B2-GATE 挡网口发布。
- 计数器对外仍保持 32 位 AXI-Lite 读口；核心内部加法收窄为 24 位，可覆盖 B3-13 的 10000 样本上限（`592 * 10000 = 5,920,000 < 2^24`）。
- Pulse-Mini-L/L2 集成。它们是冻结的候选/历史支线，不是当前日常门。

旧软件状态区 `0x01008000` 没有由 packet smoke 初始化，当前读取值不可作为账本证据。

## 下一步

1. **CP5 连续吞吐。** 增加不保存逐样本 logits 的长跑记录区与 fail-closed 汇总，预热至少 1000 样本、正式至少 10000 样本，做 5 轮交替 dense/lossless；同一输入循环、同一 JTAG 状态，报告稳态 samples/s、核心周期、首样本和错误计数。
2. **功耗负载冻结。** CP5 工具通过后，冻结 dense/lossless bit/XSA/ELF、输入流、预热和持续运行脚本，形成四种可重复状态：dense idle/full、lossless idle/full。
3. **CP8 paired 功耗。** 按 B10 仪器合同执行至少 5 组交替测量，结合 CP5 有效推理数计算整板平均功率和每次正确推理能耗；严格 2:4、独立 PL auto-mask 和批量协议均为后置支线。

## 文档口径

`task_plan.md`、`findings.md`、`progress.md` 是历史规划与执行日志，不是当前状态的唯一入口。当前结论以本页、`WORKFLOW_STATE.md` 和对应 manifest/原始日志为准。

2026-09-14 补记（B3-22.2 与 1024 样本输出保持）：

- B3-22.2 实板拆分（同一 `be84596` bit/XSA、64 样本）：live `20260914T092629Z` 的 `mask_us=36345 us` 中 compute `32160 us`（502/样本，88.5%）、submit `4156 us`（65/样本，11.5%）；同源 dense `20260914T092552Z` 中位数 `157 us`、`2494 cycles`、`592/0`，live `725 us`、`1606 cycles`、`296/296`，协议错误均为 0。
- 历史 fixed-vector B3-22.1f（16×64 dense/live 板级采集）输出保持：`prediction_agreement=1.0`（Wilson 95% 下界 `0.99626`）、`logit_exact_match=1024/1024`、logit 误差 0；该报告只证明旧 fixture 的 output preservation。当前 QAT-v3 的任务/剪枝事实以 `artifacts/results/b3_qat_pruning_diagnostic.json` 为准：dense `88.665%`、live `40.302%`、calibrated `29.471%`，两种剪枝均未过精度门。

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
