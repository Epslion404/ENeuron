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

所有路径均以仓库根目录为基准。除明确标注为标准输出的 B0 摘要外，生成器应直接写入 `artifacts/results/`；调用方保存 B0 摘要时也应使用表中路径。不得在根目录创建兼容副本。
