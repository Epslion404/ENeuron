# ENeuron 机器产物索引

本目录保存当前活动主线可由仓库脚本重建的机器产物。历史实验和旧物理证据已移入 `archive/legacy/`，不再作为日常门或当前器件的证明。

## 普通实验结果

| 结果文件 | 主要生成入口 |
|---|---|
| `results/local_prune_b0_results.json` | `python local_prune_b0_signoff.py`（摘要输出到标准输出，由调用方捕获） |
| `results/rtl_smoke_results.json` | `python rtl_smoke.py` |
| `results/np7_cosim_ledgers.json` | `python -X utf8 np7_shared_lane_cosim.py` |
| `results/np7_formal_and_mutations.json` | `python -X utf8 np7_formal_and_mutations.py` |
| `results/np7_software_cost_manifest.json` | `python -X utf8 generate_np7_manifest.py` |
| `results/npu_single_clock_ooc_manifest.json` | Vivado 2024.1 单时钟 NPU + ENeuron OOC 资源/时序/route/DRC 与报告 SHA-256 清单（`VIVADO_OOC_PASS`） |
| `results/hellozynq_b0_smoke_summary.json` | HelloZynq B0 当前构建身份、run-1下载/LED周期、完整断电和剩余run-2硬门摘要；当前状态为run-1与断电通过、重新上电后的第二次下载/观察 pending |
| `results/hellozynq_b1b_uart_ddr_summary.json` | HelloZynq B1B正式UART与低地址1 MiB DDR三次冷启动机器摘要；高地址DDR、PHY和UDP仍未关闭 |
| `results/hellozynq_b1a_hw_summary.json` | HelloZynq B1A 可重建PS7/DDR/UART/GEM/GMII-to-RGMII硬件定义、Vivado 2024.1实现指标和bitstream/XSA哈希；不代表B1实板门通过 |
| `results/b2_packet_memory_ooc_manifest.json` | B2 packet ingress/egress 在 `xc7z020clg484-2` 的 OOC BRAM 映射与资源报告；仅为综合证据 |
| `results/b3_accuracy_reference_only.json` | Python 参考模型 dense/live 对照输入（`identity=reference-only`，非实板） |
| `results/b3_accuracy_reference_only_report.json` | `b3_accuracy_report.py` 的 1000 样本参考对照；`status=PASS` 只证明参考模型 dense/live 无差异，不是实板精度门证据 |
| `results/b3_accuracy_chunk00_board_pairs.json` | `b3_accuracy_merge.py` 合并的 chunk00 64 样本 dense/live 成对实板输入 |
| `results/b3_accuracy_chunk00_board_report.json` | chunk00 64 样本实板中间报告；`status=FAIL`（样本 < 1000），仅过程证据 |
| `results/b3_accuracy_chunk00_01_board_report.json` | chunk00+01 共 128 样本实板中间报告；`status=FAIL`（样本 < 1000），仅过程证据 |
| `results/b3_accuracy_256_board_pairs.json` | `b3_accuracy_merge.py` 合并的 256 样本 dense/live 成对实板输入 |
| `results/b3_accuracy_256_board_report.json` | 256 样本实板中间报告；`status=FAIL`（样本 < 1000），仅过程证据 |
| `results/b3_accuracy_1024_board_pairs.json` | **SUPERSEDED**（解析修复前数据，保留审计）：16 chunk dense/live 合并；logits 曾被 `Get-I32` 错误包裹为 `-4294967xxx`，不得用于正式结论 |
| `results/b3_accuracy_1024_board_report.json` | **SUPERSEDED**（解析修复前报告，保留审计）：其 agreement/logit 字段由坏值产生，结论作废 |
| `results/b3_accuracy_1024_board_pairs_v2.json` | 由 32 个 run 的 `probe.log` 十六进制重建的 1024 样本 dense/live 成对输入；与 Python golden 逐项一致 |
| `results/b3_accuracy_1024_board_report_v2.json` | v2 报告：`agreement=1.0`、`logit_exact_match=1024/1024`、dense/live 与 golden 逐项零误差、协议 2048/2048 PASS；`accuracy_gate` 仅表示 output_preservation；任务精度 `MODEL_TASK_FIT_UNVERIFIED`（模型/任务适配性未证明） |
| `results/b3_calibrated_static_ab.json` | B3-22.3 零决策成本上限：512 样本校准 mask 在 64 个 held-out 输入上的 dense/calibrated 板级 A/B（中位数 157→154 µs、输出 64/64 不变）；仅输出对照与上限证据，不代表任务精度或已关闭速度门 |
| `results/b3_fixed_overhead_ab.json` | B3-22.4 固定协议开销实验：RX guard/缓存/usleep 路径修正后三组对称 A/B（dense 157→63/64/63 µs、calibrated 154→60 µs，fence 69→18 µs/sample，输出逐位一致）；协议未变，不代表速度门关闭 |
| `results/b3_live_optimized_ab.json` | B3-22.4 后 live 基线：优化路径上三组 dense/live 对称 A/B（dense `64 µs` vs live `623 µs`，compute 占 80.5%、submit 9.1%，输出 `64/64` 一致）；速度门保持 OPEN，下一步 B=4 批量协议 |
| `results/b3_pruning_diagnostic.json` | 只读剪枝诊断（1024 输入）：非零权重 19 word / 11 group；删除非零权重实例 35、删除非零贡献实例 0/11015；live mask 3 种且与校准 mask 差异 3.42%；判定 `GATE_VACUOUS / MODEL_UNDER_DETERMINED` |
| `results/b3_qat_pruning_diagnostic.json` | QAT-v3 模型（549/592 非零组）397 held-out 剪枝仿真：dense `88.665%` → live `40.302%`（−48.363pp）、calibrated `29.471%`（−59.194pp）；删除非零贡献组 `57976`；判定 `FALSIFIABLE` 且当前动态剪枝精度门失败；Python 语义层，不是板级 |
| `results/b3_qat_pl_auto_mask_sim.json` | standalone PL auto-mask 引擎在 QAT-v3 模型上的 Icarus 仿真：`397/397` 与 Python live mask 逐 bit 一致、`1861 cycles/样本`（预算 2048）；未接主 NPU、无 200 MHz 时序、非板级 |
| `../tools/repro/b3_qat_model_manifest.json` | QAT-v3 canonical 634-word 模型与 397 个 held-out 样本清单；1200/200 train-validation 划分、packing、训练整数 forward 和 Python reference 已逐元素对齐；不代表板级接线或剪枝精度通过 |
| `results/b3_qat_cp1_dense_64_board.json` | B3-PAPER-CP1：QAT-v3 dense 64 样本实板装载与逐位对拍；输入/结果 CRC、sample ID、epoch、协议状态和 10 维 logits 全部通过；不代表剪枝精度或纯 PL 吞吐通过 |
| `results/b3_qat_lossless_skip_diagnostic.json` | QAT-v3 397 样本可证明无损动态跳过基线；训练集内输入置换 + 全零激活/权重 + L0 ReLU 早停，平均跳过 35.48% 组、核心估算约 1.338x，输出逐位无损；mask 不满足严格 2:4，未接入 RTL/板级 |
| `results/b3_qat_lossless_zero_group_rtl_sim.json` | B3-PAPER-CP3b：主 NPU `LOSSLESS_ZERO_GROUP_SKIP` 公开端口级 Icarus 对拍；397/397 logits 逐位一致，跳过率 34.6207%，平均 1879.136 cycles，核心估算约 1.3272x；不包含 L0 ReLU 后缀早停，不是实板速度证据 |
| `results/b3_qat_lossless_zero_group_ooc.json` | B3-PAPER-CP3c：修复轮在 `xc7z020clg484-2`、200 MHz 通过 setup/hold、route 与 DRC，`WNS/WHS=+0.158/+0.070 ns`、`1 RAMB36`、`4 DSP48E1`；历史失败轮保留在 attempts 中，OOC 不替代完整 wrapper 或实板证据 |
| `results/b3_qat_cp4_lossless_zero_group_board_397.json` | B3-PAPER-CP4 开发证据：397 样本 dense/lossless 实板逐位 logits、CRC、sample ID 和协议一致；核心周期约 `1.089x`，端到端均值约 `1.005x`；两组 ELF 来自 dirty worktree，clean rerun pending |

QAT 当前裁定：CP0 无泄漏重基线与 CP1 dense 板级对拍已通过；严格 2:4 live/static 精度失败。无损零组跳过已通过 Python/RTL 语义对拍，但 200 MHz OOC setup 失败；下一步是 CP3c 模型取数路径物理修复，当前不得生成 bit/XSA 或进入板级速度测量。
| `results/simulation_results.json` | `python neuron_sim.py` 的三种单神经元候选结果 |
| `results/sweep_results.json` | `python run_sweep.py` 的单神经元候选 sweep 结果 |
| `results/network_results.json` | `python run_network_experiment.py` 的两层网络受控实验结果 |
| `results/network_sweep_results.json` | `python run_network_sweep.py` 的两层网络 sweep 结果 |

B3 精度中间报告必须由 `b3_accuracy_report.py` 的 `identity`（model/preprocess/bitstream/XSA/ELF）绑定；样本数不足 1000 的 `FAIL` 只是过程状态，不代表 `B3-ACCURACY-GATE` 判定。

OOC 原始报告和 checkpoint 保存在 `logs/b2_packet_memory_ooc_20260910_bram/`；报告只证明综合资源映射，不证明完整 BD 的 routed timing 或实板运行。

所有路径均以仓库根目录为基准。除明确标注为标准输出的 B0 摘要外，生成器应直接写入 `artifacts/results/`；调用方保存 B0 摘要时也应使用表中路径。不得在根目录创建兼容副本。

NP7 当前活动门只保留 oracle、逐周期协同仿真、形式/突变和软件账本；旧 Vivado/XSim 物理摘要已归档。重新进行物理签核时，必须由 `verify_np7_physical_cost.py` 或 `vivado_np7_*` 显式触发，并绑定实际器件和报告。

HelloZynq B0 每次正式下载或断电探测的原始机器证据保存在 `logs/hellozynq_b0/<唯一运行标识>/`。program目录包含下载结果、完整transcript、构建manifest和归档manifest；power-off目录包含只读探测结果、完整transcript和哈希manifest。机器记录与现场LED/供电观察必须在摘要中分别绑定。

HelloZynq B1B 的 UART/DDR 原始机器证据保存在 `logs/hellozynq_b1b/<唯一运行标识>/`；本次 B1-06B6 复测目录为 `logs/hellozynq_b1b/20260908T202605Z_df56180_b1-06b6_uart_no_marker/`，其中 program/download/CPU run 通过但 UART 终止标记缺失。

## B2 packet-NPU 现场证据

以下三组用户提供的原始日志已作为当前 B2 调查证据纳入仓库；其中 `PASS` 仅表示对应 UART/JTAG/XSCT 运行通过，不等价于 packet-NPU 顶层完成 XC7Z020 routed timing 或实板验证：

| 证据目录 | 结论 |
|---|---|
| `logs/b2_backpressure_pass_20260909_e26c7c1/` | 早期背压运行；JTAG pressure/backpressure 通过，但 UART 终止 marker 缺失 |
| `logs/b2_backpressure_timing_fail_20260909_a404a8e/` | `xc7z020clg484-2` timing/route 失败证据，保留 Vivado 原始日志与报告 |
| `logs/b2_backpressure_uart_pass_20260909_55822ae/` | 交换 TX/RX 后 UART/JTAG/XSCT 正式通过，manifest 状态为 `PASS` |

三组目录中的 `*.log` 为审计所需原始输出，使用 Git 强制跟踪；其他历史运行日志仍遵循 `.gitignore`，不自动进入提交。

## B2 packet-NPU 物理构建证据

| `logs/b2_packet_npu_route_timing_fail_20260910_0bacdea/` | MAC low-carry register 后的完整 route/bit/XSA 结果；route/DRC 通过但 setup 失败，`WNS=-0.489 ns`、`TNS=-121.268 ns`、`885` 个 setup failing endpoints；最差路径为 `mask_active_epoch_reg[1]_replica -> rsp_payload_reg[85]` |
| `logs/b2_packet_npu_route_timing_fail_20260910_2f2ce03/` | `mask_next_epoch` 预计算后的完整 route/bit/XSA 结果；route/DRC 通过但 setup 失败，`WNS=-0.279 ns`、`TNS=-8.283 ns`、`141` 个 setup failing endpoints；最差路径迁移到 egress `output_index -> response_mem ENARDEN` |

| 证据目录 | 结论 |
|---|---|
| `logs/b2_packet_npu_route_timing_fail_20260909_1bfeb12/` | 保持槽切片后的 route/bit/XSA 结果；200 MHz setup 失败，`WNS=-2.750 ns` |
| `logs/b2_packet_npu_route_timing_fail_20260910_8d57e7e/` | egress CRC 分拍后的 route/bit/XSA 结果；route/DRC 通过但 setup 失败，`WNS=-1.958 ns`，最差路径已迁移到 NPU 核心控制网络 |
| `logs/b2_packet_npu_route_timing_fail_20260910_89cbbf6/` | 局部 group mask 缓存后的完整 route/bit/XSA 结果；route/DRC 通过但 setup 失败，`WNS=-1.168 ns`、`TNS=-1001.103 ns`，最差路径为 `compute_unit_index -> model_staging RAM -> model_word_latched -> DSP48` |
| `logs/b2_packet_npu_route_timing_fail_20260910_b4b95fa/` | model-write staging 后的完整 route/bit/XSA 结果；route/DRC 通过但 setup 失败，`WNS=-0.589 ns`、`TNS=-45.751 ns`，最差路径为 `mac_accumulator_reg[0] -> mac_accumulator_reg[28]` |
| `logs/b2_packet_npu_route_timing_fail_20260910_f7ab94b/` | 分段高/低 16 位累加器实验；route/DRC 通过但 setup 失败，`WNS=-1.598 ns`、`TNS=-1152.961 ns`，已证明该拆分方案退化 |
| `logs/b2_packet_npu_route_timing_fail_20260910_639b403/` | carry-select MAC 累加器后的完整 route/bit/XSA 结果；route/DRC 通过但 setup 失败，`WNS=-1.287 ns`、`TNS=-384.021 ns`，`1942` 个 setup failing endpoints |
| `logs/b2_packet_npu_route_timing_fail_20260910_70e8caf/` | 响应 epoch 副本后的完整 route/bit/XSA 结果；route/DRC 通过但 setup 失败，`WNS=-1.595 ns`、`TNS=-1103.714 ns`，`3304` 个 setup failing endpoints；最差路径回到 MAC 高位累加器链 |
| `logs/b2_packet_npu_route_timing_fail_20260910_074ed56/` | egress BRAM 预取后的完整 route/bit/XSA/日志结果；route/DRC 通过但 setup 失败，`WNS=-0.052 ns`、`TNS=-0.134 ns`、6 个 setup failing endpoints；最差路径为 `compute_unit_mask_latched -> compute_group_index`，manifest 标为 `analysis_only_no_download` |

这些 bit/XSA 仅用于失败分析，不得作为时序签核或实板下载输入。
