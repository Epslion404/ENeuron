# NPU 局部剪枝 NP6 Runner 静态审计（NP6.1 草案，未调用 Vivado）

状态：`NP6_REVIEW_REQUIRED`（本文档仅为静态审计与冻结草案，不构成执行授权）

日期：2026-09-01

审计基线：`main` @ `9fe1403`（docs: sync workflow state after nexus update）

## 1. 范围与方法

- 依据 `docs/planning/NPU_PRUNING_NP6_TODO.md` 第 3 节六类配对对象，只读盘点仓库现有 Vivado runner、约束、报告目录与 NP4B 冻结 RTL，逐一映射并识别缺口。
- 未调用 Vivado：按 `WORKFLOW_STATE.md`，在用户批准 TODO 第 7 节冻结决策前只允许静态审计与文档维护。
- 本审计不改任何 RTL、约束或 runner；所有结论可由 `git show`/文件清单复核。

## 2. 现有 runner 盘点（part / top / 时钟 / 证据目录）

| runner | part | top | 时钟 | 证据目录 | 备注 |
|---|---|---|---|---|---|
| `vivado_synth.tcl` | xc7a35tcpg236-1（代理） | `digital_lif_core` | 100 MHz | `vivado_reports` | ENeuron 单元；注释明示代理 part |
| `vivado_engine_synth.tcl` | xc7a35tcpg236-1（代理） | `digital_lif_engine` | 100 MHz | `vivado_engine_reports` | 同上 |
| `vivado_zynq7020_engine_synth.tcl` | xc7z020clg400-1 | `digital_lif_engine` | 100 MHz | `vivado_zynq7020_engine_n2/n4_reports` | `N_INPUTS` 参数化 |

| `vivado_pulse_original_synth.tcl` | xc7z020clg400-1 | `pulse_original_core` | 100 MHz | `vivado_pulse_original_reports` | 成本/缺陷基线 |
| `vivado_pulse_mini_synth.tcl` | xc7z020clg400-1 | `pulse_mini_core` | 100 MHz | `vivado_pulse_mini_reports` | |
| `vivado_pulse_mini_l2_synth.tcl` | xc7z020clg400-1 | `pulse_mini_l2_core` | 100 MHz | `vivado_pulse_mini_l2_reports` | |
| `vivado_pulse_mini_array.tcl` | xc7z020clg400-1 | `pulse_mini_array` | 100 MHz | `vivado_pulse_mini_array_reports` | `N_CORES` 参数化 |
| `vivado_tile_synth.tcl` | xc7a35tcpg236-1（代理） | `digital_snn_tile_4x2x2` | 周期参数化 | `vivado_tile_reports` | |
| `vivado_host_bridge_system_ooc.tcl` | xc7a35tcpg236-1（代理） | `digital_snn_host_bridge_system` | host/tile 双时钟参数化 | `vivado_host_bridge_reports` | 含层次化利用率与 CDC 报告 |
| `vivado_xpm_wrapper_sim.tcl` | xc7a35tcpg236-1 | `digital_snn_host_bridge` | host 20 ns / tile 14 ns | `vivado_xpm_wrapper_sim` | XSim + 综合 |
| `run_local_prune_gate_vivado.py` | （仅 XSim，不综合） | testbench | - | - | NP4B 三模型对比仿真 |

报告约定（既有证据目录一致遵守，NP6 沿用）：每配置含 `drc_synth/impl`、`timing_synth/impl`、`utilization_synth/impl`、`power_impl`、机器可读 `signoff_summary.txt`；系统级另含 `route_status`、`methodology`、层次化利用率与 CDC 报告。

## 3. 六类配对映射与缺口

| # | 配对对象 | 未剪枝侧现状 | 剪枝侧现状 | 缺口与处置建议 |
|---|---|---|---|---|
| 1 | `local_prune_gate_2of4` 独立 OOC | 不适用（gate 为新增组件） | `local_prune_gate_2of4.sv`（NP4B 冻结） | **无综合 runner**：需新建 Tcl，part/时钟按冻结决策 |
| 2 | ENeuron wrapper 对 | `digital_lif_core` 已有，但 part 为 xc7a35 代理 | `eneuron_local_prune_wrapper.sv` | 未剪枝侧需 xc7z020 版本；剪枝侧无 runner |
| 3 | Pulse-Mini-L wrapper 对 | `pulse_mini_core`（xc7z020 ✓） | `pulse_mini_l_prune_wrapper.sv` | 剪枝侧无 runner |
| 4 | Pulse-Mini-L2 wrapper 对 | `pulse_mini_l2_core`（xc7z020 ✓） | `pulse_mini_l2_prune_wrapper.sv` | 剪枝侧无 runner |
| 5 | `4→8→2` 网络对 | **不存在未剪枝 4→8→2 顶层**（`pulse_mini_network_4x2x2` 是 4x2x2 拓扑） | `eneuron/pulse_mini_l/l2_pruned_network_4x8x2.sv` + barrier/scheduler | 未剪枝基线缺失：需裁定 构建仅测量用未剪枝顶层（不改冻结 RTL）或标 `NOT_COMPARABLE` |
| 6 | Host Bridge + Tile 系统对 | `digital_snn_host_bridge_system`（xc7a35 代理） | 无剪枝 sideband 系统版本 | 按 TODO §3.6 建议直接标 `NOT_COMPARABLE`，不新建系统 RTL |

## 4. 冻结草案（NP6.0 草案，待批准）

- **器件**：`xc7z020clg400-1`（与 TODO §2 一致）。现有 6 个 runner 已用该 part；5 个 runner（ENeuron 单元、engine、tile、host bridge 系统、xpm wrapper）当前用 xc7a35 代理 part，需按决策 6 处置。
- **时钟**：单时钟对象 100 MHz（10 ns）；Host/Tile 双时钟 50/100 MHz（20/10 ns）。注意既有 xpm 仿真用 20/14 ns、系统 OOC 为参数化——以冻结值为准，不复用旧参数。
- **策略**：Vivado 默认综合与默认实现策略、`out_of_context`；不做策略扫描（控制变量），如批准后再议。
- **工具版本**：TODO §2 写的是评审机 Vivado 2024.1（`G:\Xilinx\Vivado\2024.1\...`）；本 PR 提交方机器只有 Vivado 2024.2（`C:/Users/MGL/Documents/Codex/Vivado2024_2`）。需用户裁决在哪台机器、哪个版本上冻结执行（或两套分别记录、分别绑定）。
- **记录合同**（落实 TODO §2/§5 证据门）：每个配置记录 Git HEAD、`git status --porcelain`、Vivado 版本、完整 Tcl、逐步退出码、全部报告文件的 SHA-256；报告生成时间必须晚于冻结 HEAD 中被测 RTL/约束/Tcl/runner/verifier 的最后修改时间（新鲜度门）。
- **验证器**（NP6.7 设计）：独立 fail-closed verifier，校验配对完整性、器件/时钟一致、报告新鲜度、解析成功；任一缺失即拒绝签核。

## 5. 请求用户裁定的事项

TODO §7 的五项决策仍然全部有效（进入 NP6 与 Vivado 授权、器件、时钟、比较矩阵、vector-less 功耗定位）。本审计另发现四项需一并裁定：

6. 既有 5 个 xc7a35 代理 runner：直接改用 `xc7z020clg400-1`，还是保留代理证据、另建 xc7z020 平行运行？（直接改会使既有证据失去 part 上下文）
7. 配对 5 的未剪枝 `4→8→2` 基线：允许构建仅测量用的未剪枝顶层（同拓扑实例化既有冻结神经元、无 gate），还是标 `NOT_COMPARABLE`？
8. 配对 6 直接标 `NOT_COMPARABLE`（剪枝系统版本不存在、不新建系统 RTL），请确认。
9. Vivado 版本与执行机冻结：2024.1（评审机）或 2024.2（提交方机器），或两套独立证据。

## 6. 停止条件自查（对照 TODO §6）

- 未发现拓扑/器件/时钟/约束的既成不一致——全部差异已列为待冻结决策项，不在冻结前运行。
- 无 runner 引用陈旧 RTL：main 头部为 NP4B 冻结源 + V1 归档后状态，源哈希与签核链一致。
- 本审计为静态文档工作，未产生任何 Vivado 输出。
