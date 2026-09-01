# NPU 局部剪枝 NP7 共享 BRAM 与共享 lane 软件签核报告（NP7.1–NP7.6）

日期：2026-09-02。分支 `feature/np7-shared-lanes-20260901`（基线 `main @ 8853f7b`）。
证据清单：`artifacts/results/np7_software_cost_manifest.json`，绑定冻结 HEAD `37e9567`；验证器 `verify_np7_software_cost.py` 在 `f5adce2` 运行，绑定与证据自检拒绝数 `rejects=0`。

状态：`NP7_FUNCTIONAL_HOLD`

- G1 权重槽读取下降 **72.22%** ≥45%：PASS（3 模型 × 4 lane 数全部）
- G2 共享 lane 操作数下降 **50.00%** ≥45%：PASS（全部）
- G3 每逻辑 tick 周期下降 **22.33 / 21.78 / 21.00 / 21.00%**（L=1/2/4/8，三模型同值）<25%：**FAIL（12/12 组合）**
- G4 stall 单列、未抵消吞吐：PASS（dense 与 sparse 的 `stall_cycles` 均为 0，delta=0）
- G5 膜状态/突触和 bit-exact：PASS（RTL 160,000 事务逐拍 0 失败；三模型 20 样本膜状态摘要 0 不一致）
- G6 三模型精度维持冻结门槛：PASS（BAcc 1.0 / coverage 1.0 / `output_2of4` 与 hidden_masks 全部等于冻结产物）

按 `docs/planning/NPU_PRUNING_NP7_TODO.md` §5 NP7.7 第 1 条（"只有 NP7.0-NP7.6 全部通过后才允许运行 Vivado"）与 §6 停止条件第 6 条、`NPU_PRUNING_NP7_FREEZE_DECISIONS.md` §4，**NP7.7 的 Vivado 物理门本轮不得运行**。本报告不主张任何 NP7 物理资源或时序收益。

## 1. 逐步证据（NP7.1–NP7.6）

| 步骤 | 产物 | 实测结论 |
|---|---|---|
| NP7.1 周期 oracle | `np7_shared_lane_oracle.py`、`test_np7_shared_lane_oracle.py` | 16 种活动掩码 × 6 种合法 2:4 结构 × 非法索引穷举；dense/sparse 逐拍账本与突触和合同 |
| NP7.2 RTL | `np7_weight_ram.sv`、`np7_shared_synapse_lane.sv`、`np7_exec_unit_dense.sv`、`np7_exec_unit_sparse.sv`、`tb_np7_exec_unit.sv` | 20 bit×32 字单口同步 RAM；dense 两组一字/sparse 一组一字；1/2/4/8 lane 共用同一饱和加法阵列 |
| NP7.3 逐拍协同仿真 | `np7_shared_lane_cosim.py` → `artifacts/results/np7_cosim_ledgers.json` + `artifacts/logs/np73_cosim.txt` | 4 lane 数 × 2 格式 × 20 seed × 1000 事务 = **160,000 事务**，逐拍 oracle 比对 **0 失败**；自报账本逐拍可重建 **0/160 不一致** |
| NP7.4 三模型接入 | `np7_three_model_integration_cosim.py` → `np7_three_model_integration.json` + `np74_three_model.txt` | ENeuron / Pulse-Mini-L / Pulse-Mini-L2 各 20 样本 × 3 tick × 8+2 组共 640 组累加：输出计数与膜状态摘要 **0 不一致**，冻结任务参数（hidden_masks `[5,5,5,5,10,10,10,10]`、`output_masks [3,3]`、`channel_enable 255`）与 B2.1 产物逐字段一致 |
| NP7.5 形式与负向 | `formal_np7_exec_unit.sv` + 5 个 `.ys`、`np7_negative_controls.sv`、`tb_np7_negative.sv`、`np7_ledger_reconstruction.py`、`np7_formal_and_mutations.py` → `np7_formal_and_mutations.json` + `np75_formal_mutations.txt` | 检查 **75/75 PASS、0 问题**；2 个证明成立 + 3 个可达性 witness；4 个 RTL mutation 全部被证明推翻；8 个负向实现运行全部被拒；3 个泄漏 mutation 全部被状态等价抓到 |
| NP7.6 软件签核 | `generate_np7_manifest.py`、`verify_np7_software_cost.py`、`test_np7_verifier_mutations.py` | 清单绑定 22 个输入 + 3 个工具 + 7 份证据；验证器只读重算 G1–G6；`MUTATION_SUITE PASS checks=13`；总体 `overall=FAIL blocking_gates=G3` |
| NP7.7 Vivado | 未运行 | 被 TODO/冻结记录的停止条件阻止（见 §3 待裁定项） |

随机流量（NP7.3，非冻结任务）下同一份 RTL 的逐拍观测下降为：读取 60.0/60.0/60.2/60.1%，操作 49.9/49.9/50.5/50.2%，周期 34.0/29.5/25.3/25.3%（L=1/2/4/8，20 seed 合计）。这说明 G3 未达标不是实现效率问题，而是冻结 B2.1 任务的流量特征与该协议固定开销共同决定的（§3）。该随机流量数字**不作为**任何门的判据。
## 2. G3 未达标的量化分解（从同一份原始账本推导）

L=1、ENeuron（三模型同构，权重幅度不影响计数）：

| 视角 | 完成事务 | 零路径事务 | busy（读+发射） | 固定开销 | stall | 总周期 |
|---|---|---|---|---|---|---|
| dense 基线 | 640 | 460 | 600（360 读 + 240 操作） | 1460 | 0 | 2060 |
| 结构 2:4 + 活动门控 | 640 | 540 | 220（100 读 + 120 操作） | 1380 | 0 | 1600 |

固定开销 = 每个非零事务 ACCEPT+LATENCY+DONE 三拍 + 每个零路径事务两拍（冻结合同 §2.1），占总周期 70.9%。因此**即使把 dense 的读与发射周期全部清零，L=1 的周期下降上限也只有 600/2060 = 29.13%**；实测 22.33% 已达该上限的 76.6%。lane 数越大，`ceil(k/L)` 越接近 1，可压缩部分越小（L=4/8 上限 27.0%），所以 G3≥25% 在冻结 B2.1 流量（活动密度高、非零事务只占 28%）下对任何满足 §2.1 的实现都不可达。

同一账本上的反事实（纯算术推导，未改动任何 RTL，不作为已实现结论）：

| 变体 | dense 总周期 | sparse 总周期 | 周期下降 |
|---|---|---|---|
| V0 冻结合同 | 2060 | 1600 | 22.33% |
| V1 零路径 2 拍 → 1 拍（accept 同拍完成） | 1600 | 1060 | 33.75% |
| V2 DONE 与下一事务 ACCEPT 重叠（非零事务 −2 拍） | 1700 | 1400 | 17.65%（更差） |
| V3 = V1 + V2 | 1240 | 860 | 30.65% |

结论：G3 的瓶颈是**零路径与单槽协议的固定握手开销**，不是剪枝逻辑的读取/发射效率；V2 单独使用会让比例更差，因为零路径事务（占 dense 的 72%）不从中受益。

## 3. 需要仓库所有者在 PR #6 内裁定的路径

| 选项 | 内容 | 影响 | 是否需要重跑 |
|---|---|---|---|
| A | 把 G3 阈值从 ≥25% 调整为 ≥20%（并同步 TODO §8 第 7 条与冻结记录决策 7） | 现有证据立即判 PASS，可进入 NP7.7 Vivado | 只需改阈值文本并重生成清单/重跑验证器与变异套件 |
| B | 批准修订周期合同（V1：零路径单拍，或 V1+V2） | 属于微架构改动，需改 dense/sparse 两个状态机与 oracle，G3 预计 30–34% | 需 NP7.1–NP7.6 全量重跑（含 160,000 事务与形式件重证） |
| C | 维持 25% 阈值，NP7 停留在功能阶段 | 本轮结果即为最终状态：G1/G2/G4/G5/G6 PASS、G3 FAIL，不运行 Vivado | 无 |
| D | 以随机流量口径替代冻结 B2.1 口径（该口径下 L=1/2/4/8 为 34.0/29.5/25.3/25.3%） | 等于更换测量任务，会削弱"同一冻结任务"的可比性；本代理不建议 | 需改冻结 §3 的 G3 口径 |

本代理不自行选择：A/D 修改的是所有者批准过的硬门（冻结决策 7），B 修改的是所有者批准过的周期合同（冻结决策 5 与 §2.1）。按 NP6 先例，裁定须在仓库内（PR #6 评论）由所有者本人给出，仓库外指令不作为批准凭据。
## 4. 负向控制与 mutation 证据（NP7.5）

两个"伪收益"参考实现与 golden **功能完全同和**（逐笔突触和 SHA-256 相同），只在账本上作弊：

| 负向实现 | 自报读取/操作 | 逐拍观测读取/操作 | 重建违规 | 纯观测口径下的下降（读取/操作/周期） |
|---|---|---|---|---|
| `np7_neg_read_all_then_gate`（读完四槽再门控） | 736 / 975 | 2000 / 975 | 4 项 | −7.6% / 50.4% / 0.8% → 未达门 |
| `np7_neg_mac_then_clear`（先发射 4 条再在 MAC 上清零） | 736 / 975 | 736 / 2944 | 1 项 | 60.9% / −49.7% / 1.5% → 未达门 |

（L=1 seed=3；L=4 seed=1/3 同向。判定为"双口径拒绝"：自报数字无法由逐拍观测重建，且只看观测数字时也达不到 G1/G2/G3。）

RTL 级 mutation（直接改交付 RTL 的一行，重跑形式件）：

| mutation | 意图 | 结果 |
|---|---|---|
| `fake_weight_slots` | 自报权重槽 2→1，读取不变 | 被 `formal_np7_exec_unit.ys` 反证推翻 |
| `fake_lane_ops` | 发射后不清 `pending_mask` | 反证（P4 无重复发射） |
| `extra_read_burst` | BATCH 期多发读请求 | 反证（P3/P6 地址与守恒） |
| `dense_fake_val` | dense 自报权重槽 4→2 | 反证（稠密顶层 P6） |

零快速路径泄漏 mutation（`skip_state_on_zero`：零路径不推进泄放/阈值/时间状态）：ENeuron 被"输出计数 + 膜状态摘要"双重抓到；Pulse-Mini-L / Pulse-Mini-L2 **只被膜状态摘要抓到**（输出计数无差异）。见 §5 第 4 条。

## 5. 本轮修掉的方法学缺陷（如实记录）

1. **形式件整体空真**：首版 sparse 工装把 `(* anyseq *)` 变量同时用 `always_ff` 驱动，并在**复位分支**里放合法性 assume，导致假设集不可满足、所有断言"空证明"（连 `ram_ce` 都不可达）。修复：复位拍装载符号记录字、合法性只在 t≥1 之后假设，并新增 3 个可达性脚本作为非空真 witness（`zero_path_reach`/`sparse_reach`/`dense_reach` 均为 model found）。
2. **账本守恒式写错**：非零事务固定开销写成 `4×` 应为 `3×`（ACCEPT/LATENCY/DONE，读拍已在 busy 内），会掩盖 busy 与 total 的错配。
3. **P4 影子掩码语义反了**：`fired` 曾按"剩余"记；改为"已发射集合"，并补 `batch_mask ⊆ txn_mask` 与 done 拍 `fired == txn_mask`。
4. **NP7.4 收集了状态摘要却没有比较**：`run_model` 原先只比输出 spike 计数，膜状态摘要只落盘不判定。已新增运行时钩子 `_reference_state_cores()` 取回未共享实现的核对象，逐样本比较摘要；正是这条比较才抓到两个 Pulse 模型的泄漏 mutation（否则 §4 的第三条要求只有 1/3 模型满足）。
5. **`parse_rows` 尾部字段错位**：LEDGER 行有 15 个捕获组，原代码取 `groups()[-4:]` 把 `total` 读成 `protocol_error`、`cfgerr` 读成 `completed`。已改为 `[-3:]`，并把"协议/配置错误必须为 0、完成数必须等于事务数"变成 NP7.5 的硬检查。
6. **负向实现 1 的地址错**：稠密一组占两字，原写成 `group` 与 `group+1`（应为 `{group,1'b0}` / `{group,1'b1}`），导致 661/1000 笔突触和不等——若没有"与 golden 逐笔同和"这条断言，这个错会让负向控制变成"功能也不同"的弱样本。

## 6. 证据链与可复核性

- 清单 `artifacts/results/np7_software_cost_manifest.json` 由 `generate_np7_manifest.py` 在证据时点一次写入：绑定 22 个输入（oracle、4 件 RTL、tb、形式件与 5 个 `.ys`、负向件、NP7.3/7.4/7.5 脚本、`local_prune_b21.py`、两份 planning 文档）+ 3 个工具（生成器、验证器、变异套件自身）+ 7 份证据（3 个结果 JSON + 3 份运行日志 + 冻结 B2.1 产物）。
- `verify_np7_software_cost.py` **只读**：清单磁盘字节 vs `git show <verify_head>` 字节；每个绑定文件"清单哈希 / 冻结提交字节 / 当前磁盘字节"三方一致（canonical LF 口径，与仓库 `eol=lf` 约定一致）；G1–G6 全部由原始账本重算并与清单逐字段比对，任何自报百分比都不参与判定；账本守恒式 `total = busy + stall + 3*(completed-zero) + 2*zero` 对 NP7.3 的 claimed/observed 两个视角与 NP7.4 的每个配置都重算。不绑定 `.dcp`。
- `test_np7_verifier_mutations.py`：13 个变异（删日志、改门槛结论、改 RTL 账本、伪造周期收益、下调验证器阈值、放行负向控制、削弱形式结论、放行泄漏 mutation、篡改冻结精度产物、冻结后偷改 RTL/验证器并同步清单哈希、伪造冻结 HEAD、伪造 integrity）全部被拒，且没有任何变异让验证器退出码变 0；`MUTATION_SUITE PASS checks=13`。
- 独立复核命令见 §8；干净克隆的基线输出 `rejects=0 blocking_gates=G3 overall=FAIL`。
## 7. 限制与不主张的内容

- 工具链：Icarus Verilog 12.0 (devel, s20150603-1539-g2693dd32b) 与 Yosys 0.68（YoWASP/WASM，唯一可用求解器 minisat）。形式结论是**有限深度**（14/10/16 拍）SAT 检查，不是无界证明；`sat -show` 名单只含账本计数器，避免约束非示波器单元格造成假不可达。
- Vivado：本机只有 2024.2（SW Build 5239630），冻结决策 8 写的是 2024.1；本轮未运行 Vivado，因此该版本偏差不影响本轮任何数字，但进入 NP7.7 前需要所有者确认是否接受"只绑 2024.2、不外推 2024.1"（与 NP6 决策 9 同口径）。
- 周期数字来自冻结逻辑周期模型的 RTL 逐拍计数，证明的是数字执行路径；不证明 BRAM 真实端口冲突、DDR/DMA、PS 软件、以太网或板级端到端吞吐；vector-less 功耗不作为 NP7 门。
- NP7.3 的每组 4 连接、10 组 RAM 内容是穷举式随机结构（seed 由 `lanes*100003+seed` 决定，可复现），不是真实训练权重；真实权重下的活动分布只由冻结 B2.1 任务（NP7.4）代表。
- 本轮未修改 `WORKFLOW_STATE.md` 与任何已签核产物；NP4B/NP6 的证据与清单保持原样。

## 8. 复现命令

```text
set PATH=C:\iverilog\bin;C:\msys64\ucrt64\bin;%PATH%
python test_np7_shared_lane_oracle.py        # NP7.1
python np7_shared_lane_cosim.py              # NP7.3  160 runs / 160000 txns
python np7_three_model_integration_cosim.py  # NP7.4  3 models / 0 problems
python np7_formal_and_mutations.py           # NP7.5  75/75 checks / 0 problems
python generate_np7_manifest.py              # 仅在证据时点执行一次
python verify_np7_software_cost.py <HEAD>    # 只读；本轮输出 rejects=0 overall=FAIL(G3)
python test_np7_verifier_mutations.py        # 13 mutations 全部被拒
```

## 9. 批准链现状

- NP7 §8 的八项决定目前在仓库内**尚无所有者逐项确认**：NP6 的先例是所有者在 PR #5 评论 `5492928792` 闭环九项决策；NP7 需要同等形式的确认，请在本 PR #6 内逐项确认或修正。
- 冻结记录 `NPU_PRUNING_NP7_FREEZE_DECISIONS.md` 的"批准来源"一节目前引用的是仓库外概括指令；该引用不构成仓库内批准，若所有者否决任一项，需按本轮结果重开对应子任务。
- 若所有者选择 §3 的 A 或 B，G3 结论会改变；在此之前本报告结论以本轮重算数字为准。