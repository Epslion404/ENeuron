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

| 证据目录 | 结论 |
|---|---|
| `logs/b2_packet_npu_route_timing_fail_20260909_1bfeb12/` | 保持槽切片后的 route/bit/XSA 结果；200 MHz setup 失败，`WNS=-2.750 ns` |
| `logs/b2_packet_npu_route_timing_fail_20260910_8d57e7e/` | egress CRC 分拍后的 route/bit/XSA 结果；route/DRC 通过但 setup 失败，`WNS=-1.958 ns`，最差路径已迁移到 NPU 核心控制网络 |
| `logs/b2_packet_npu_route_timing_fail_20260910_89cbbf6/` | 局部 group mask 缓存后的完整 route/bit/XSA 结果；route/DRC 通过但 setup 失败，`WNS=-1.168 ns`、`TNS=-1001.103 ns`，最差路径为 `compute_unit_index -> model_staging RAM -> model_word_latched -> DSP48` |

这些 bit/XSA 仅用于失败分析，不得作为时序签核或实板下载输入。
