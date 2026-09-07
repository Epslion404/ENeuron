# ENeuron 机器产物索引

本目录保存可由仓库脚本重建的机器产物。`results/` 中是历史实验或普通回归结果，不是最终签核摘要；NP4B、M3、T0、Pulse 和 Vivado 的正式签核文件仍保留在仓库根目录或原证据目录。

## 普通实验结果

| 结果文件 | 主要生成入口 |
|---|---|
| `results/simulation_results.json` | `python neuron_sim.py` |
| `results/sweep_results.json` | `python run_sweep.py` |
| `results/network_results.json` | `python run_network_experiment.py` |
| `results/network_sweep_results.json` | `python run_network_sweep.py` |
| `results/comparison_simulation_results.json` | `python compare_simulation.py` |
| `results/digit8x8_d1_results.json` | `python digit8x8_experiment.py` |
| `results/digit8x8_d2_results.json` | `python run_digit8x8_d2.py` |
| `results/local_prune_b0_results.json` | `python local_prune_b0_signoff.py`（摘要输出到标准输出，由调用方捕获） |
| `results/local_prune_b1_results.json` | `python run_local_prune_b1.py` |
| `results/local_prune_b2_results.json` | `python run_local_prune_b2.py` |
| `results/local_prune_b21_results.json` | `python run_local_prune_b21.py` |
| `results/local_prune_np2_results.json` | `python run_local_prune_np2.py` |
| `results/local_prune_np3_results.json` | `python run_local_prune_np3.py` |
| `results/pulse_mini_protocol_experiments.json` | `python pulse_mini_protocol_experiments.py` |
| `results/rtl_smoke_results.json` | `python rtl_smoke.py` |
| `results/np6_physical_cost_manifest.json` | `python -X utf8 generate_np6_manifest.py`（NP6 物理清单） |
| `results/np7_cosim_ledgers.json` | `python -X utf8 np7_shared_lane_cosim.py` |
| `results/np7_three_model_integration.json` | `python -X utf8 np7_three_model_integration_cosim.py` |
| `results/np7_formal_and_mutations.json` | `python -X utf8 np7_formal_and_mutations.py` |
| `results/np7_software_cost_manifest.json` | `python -X utf8 generate_np7_manifest.py` |
| `results/np7_vivado_xsim_summary.json` | `python -X utf8 run_np7_vivado_xsim.py`（需 Vivado 2024.2 受控机） |
| `results/np7_vivado_ooc_summary.json` | `python -X utf8 run_np7_vivado_ooc.py`（需 Vivado 2024.2 受控机） |
| `results/npu_single_clock_ooc_manifest.json` | Vivado 2024.1 单时钟 NPU + ENeuron OOC 资源/时序/route/DRC 与报告 SHA-256 清单（`VIVADO_OOC_PASS`） |
| `results/hellozynq_b0_smoke_summary.json` | HelloZynq B0 当前构建身份、run-1下载/LED周期、完整断电和剩余run-2硬门摘要；当前状态为run-1与断电通过、重新上电后的第二次下载/观察 pending |

所有路径均以仓库根目录为基准。除明确标注为标准输出的 B0 摘要外，生成器应直接写入 `artifacts/results/`；调用方保存 B0 摘要时也应使用表中路径。不得在根目录创建兼容副本。

HelloZynq B0 每次正式下载或断电探测的原始机器证据保存在 `logs/hellozynq_b0/<唯一运行标识>/`。program目录包含下载结果、完整transcript、构建manifest和归档manifest；power-off目录包含只读探测结果、完整transcript和哈希manifest。机器记录与现场LED/供电观察必须在摘要中分别绑定。
