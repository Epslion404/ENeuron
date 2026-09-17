# B3 架构与压缩路线评审（2026-09-15）

## 文档性质

本文是一轮**离线分析 + 本机 Python 实验**的汇总，不含任何新的板级运行。所有板级数字均引用既有 manifest / Vivado 报告；所有新实验均为本机可复现的纯 Python，产物列于第 6 节。

本文不关闭任何门。`B3-SPEED-GATE`、`B3-POWER-GATE`、`B3-ACCURACY-GATE`、`B3-GOAL-GATE` 状态不变。

## 1. 摘要

四条主要结论，按证据强度排序：

1. **剪枝的功耗收益在物理上低于噪声**——不是测量方法问题。Vivado routed 报告实读 4 个 DSP48E1 合计 `0.004 W`，剪掉一半 MAC 上限省 `2 mW`，而实测重复性噪声为 `11.2 mW`。
2. **模型规模是当前唯一能让剪枝研究脱离固定开销主导区的杠杆**，且不需要任何 RTL 改动：固定协议开销 `50.5 us` 与模型规模无关，剪枝端到端价值随规模从 `7.0%` 升到约 `35%`。
3. **无损位宽压缩优于有损剪枝，两者可叠加**：QAT 模型 L0 权重取值仅 `[-2,3]`，3 bit 即位精确无损，压缩 `2.35x` 零代价；叠加静态 2:4 + 微调后为 `3.44x / -3.02 pp`。
4. **BRAM 有 `128/140` tile 完全空闲，而权重在 LUTRAM**。迁移可把模型容量上限从当前 2.5 KB 提到 576 KiB。但仓库存在一次 `ram_style` 被 Vivado 忽略的失败先例，本项须按三级阶梯实测，不得凭结构分析宣称成功。

## 2. 对既有结论的更正

### 2.1 已由仓库修复的项（本文只作记录）

- `run_b3_speed_benchmark.ps1` 的 `Get-I32` 符号 bug 已修（显式 `[uint32]2147483648` 常量）。该 bug 曾使全部板端 logits 被减 `2^32`，导致 `dense_accuracy` 记为 `9.86%`（真值 `11.23%`）且 `per_class_recall` 呈现「class 1 = 0.971、其余全 0」的伪影。
- `docs/reports/B3_ACCURACY_EVALUATION.md` 已加入 `GATE_VACUOUS / MODEL_UNDER_DETERMINED` 与 `MODEL_TASK_FIT_UNVERIFIED` 口径。
- commit `6d59ca8` 已建立 canonical QAT manifest 与 `b3_qat_pruning_eval.py`。

### 2.2 本轮分析中被推翻的自身判断

| 原判断 | 更正 | 依据 |
|---|---|---|
| 端到端基线 `157 us` | **已过时**，B3-22.4 后为 `63-64 us` | `artifacts/results/b3_fixed_overhead_ab.json` |
| NPU 占端到端 `7.9%` | 新基线下为 **`19.6%`** | `12.47 / 63.5` |
| 功耗「信噪比不足，需改进测量」 | **归因错误**，应为「信号量级低于噪声，物理上不可测」 | DSP 合计 4 mW（routed 报告） |
| 「剪枝不是压缩手段，位宽才是」 | **过于绝对**。静态 2:4 + 微调仅 `-3.02 pp` | `finetune_24.py` 实测 |
| `model_staging` 占 2436 LUT | **归因错误**。2436 是整板合计，其中约 1408 来自 `b2_packet_ingress` | NPU 核心 OOC 基线为 `2126 LUT / 1014 LUTRAM` |
| `ram_style="block"` 是 drop-in、风险低 | **过于乐观**，仓库有失败先例 | 见 5.1 |
| 「最复杂层双缓冲装不下，必须分块」 | 粒度假设错误。按**单个输出神经元**双缓冲只需几 KB | 评审指出 |

### 2.3 需要纠正的外部事实引用

- NVIDIA Ampere 2:4 元数据为**每个存活元素 2 bit**，即每组 4 权重 `4 bit`，不是「每组 2 bit」。
- 「2:4 不微调则精度崩溃」是该技术路线的**已知前提**（NVIDIA 文档明确要求稀疏化后微调），不是本项目的新发现。
- `group_4way` 是**块级**稀疏，NVIDIA 是**元素级**稀疏。此区别仓库「不可声称」清单早有记录。

## 3. 实测数据汇总

### 3.1 端到端时间账本（B3-22.4 后，`b3_fixed_overhead_ab.json` pair2/3）

| 段 | 时间 | 占比 | 性质 |
|---|---|---|---|
| DMA（含 NPU 12.47） | 22.0 us | 34.9% | 其中约 9.5 us 为 DMA 固定开销 |
| fence | 18.0 us | 28.6% | 协议边界，三种模式下恒定 |
| result 读回 | 10.0 us | 15.9% | |
| ps 帧构建 | 7.5 us | 11.9% | |
| 残差 | 5.5 us | 8.7% | |
| **合计** | **63.0 us** | | 其中 NPU 计算 12.47 us = **19.6%** |

固定协议开销 = `50.5 us`，与模型规模无关。

fence 为 RTL 硬约束：`npu_zynq7020_t1_wrapper.sv:254-277` 规定只有消费 `RSP_FENCE` 才置 `sample_window_open_host`，收满 8 beat 立即关闭，即**一次 fence 恰好授权一笔样本**。跳过 fence 会使 `host_sample_ready` 拉低、ingress 在 `ST_SAMPLE_OUT` 挂死。摊销 fence 必须改 wrapper RTL。

### 3.2 周期账本（FSM 反推，精确命中实测）

```
dense  = 32x(2 + 16x4 + 1) + 10x(2 + 8x4 + 1)              = 2494  (实测 2494)
2:4    = 32x(2 + 8x4 + 8x1 + 1) + 10x(2 + 4x4 + 4x1 + 1)   = 1606  (实测 1606)
```

每执行组固定 4 拍（FETCH/EXECUTE/COMMIT/ACCUM），每跳过组 1 拍，每神经元额外 3 拍。真正做 MAC 只在 EXECUTE 那 1 拍，**DSP 利用率 23.7%**。

因跳过组仍花 1 拍，2:4 的周期上限为 `1 - 1606/2494 = 35.6%`；若用优先编码器使跳过免费则为 `47.8%`。

### 3.3 功耗（`design_1_wrapper_power_routed.rpt` 实读）

| 项 | 功率 | 占比 |
|---|---|---|
| PS7 | 1.286 W | 74.7% |
| Static | 0.142 W | 8.3% |
| MMCM | 0.107 W | 6.2% |
| Clocks | 0.079 W | 4.6% |
| Signals | 0.034 W | 2.0% |
| I/O | 0.029 W | 1.7% |
| Slice Logic | 0.027 W | 1.6% |
| Block RAM | 0.013 W | 0.8% |
| **DSPs** | **0.004 W** | **0.23%** |
| 合计 | 1.721 W | |

剪枝上限省 `2 mW`；B10 表标称不确定度 `3.2 mW`；实测 dense 两轮重复性差 `11.2 mW`。现有 5 点差分读数中观测到 dense2 `1.569 W` < static `1.567 W` < live `1.565 W`，即**加负载功率下降**，物理上不可能，证实慢漂移支配。

按功效分析，检出 `2 mW` 需 `n ≈ (1.96+0.84)^2 / (2/11.2)^2 ≈ 246` 次配对测量才有 80% 功效。

### 3.4 资源余量（`design_1_wrapper_utilization_placed.rpt` 实读）

| 资源 | 已用 | 可用 | 占比 |
|---|---|---|---|
| Slice LUT | 9836 | 53200 | 18.5% |
| LUT as Distributed RAM | 2436 | 17400 | 14.0% |
| Slice Register | 12239 | 106400 | 11.5% |
| **Block RAM Tile** | **12** | **140** | **8.6%** |
| DSP48E1 | 4 | 220 | 1.8% |

`WNS = +0.045 ns`（0.9% 余量）——任何增加逻辑深度的 RTL 改动都有时序失败风险。

### 3.5 中断端口已存在但未连到 PS（已核实）

`npu_status_irq` 在 RTL 各层均已引出：

- `npu_zynq7020_t1_wrapper.sv:27` 声明，`:252` 由 `assign host_status_irq = host_rsp_valid;` 驱动
- `b2_npu_packet_adapter.sv:31 / :263` 透传
- `b2_npu_axis_top.v:42` 引到顶层输出，`:71` 完成连接

但 `boards/hellozynq/b2_hw/build_b2.tcl` 中**不存在任何 `IRQ_F2P` / interrupt 连接**——该信号止步于顶层端口，未接入 PS7。

因此 PS 侧只能忙等待轮询（`wait_dma()` 内 `usleep(POLL_INTERVAL_US=1)` 循环）。接通 IRQ 后 PS 可在 NPU 计算的 12.47 us 窗口内进入 WFI，这是唯一量级（约 18 mW）超过测量噪声地板（11.2 mW）的功耗杠杆，且只需改 BD 连线 + PS 软件，**完全规避 WNS 风险**。

注：剪枝使 NPU 更快完成（12.47 → 8.03 us），反而**缩短 PS 可 WFI 的时间**。在此能效语义下剪枝为负收益——此推论为量级估计，需实测确认。

## 4. 本轮新实验（纯 Python，本机可复现）

### 4.1 真实 QAT 模型

`train_qat.py` 在 NPU 精确语义（`hidden = clamp(b0 + sum(uint4_px * int8_w), 0, 127)`）上做量化感知训练：

- **test 93.45% / train 95.57%**（397 / 1400 样本，seed 20260914）
- 非零组 `533/592`；**非零组数 >= 3 的 meta 为 `137/148 = 92.6%`**

对比退化 fixture：19/634 非零 word、11/592 非零组、每 meta 非零组 <= 2 —— 剪枝在结构上不可能改输出，精度门平凡真。

> 与仓库独立诊断 `b3_qat_pruning_diagnostic.json` 相互印证：该文件报 dense `90.625%` / live `32.8%` / tie 率 `69.6%`（64 held-out），本文报 `93.45%` / `37.53%` / `74.7%`（397 test）。集合与规模不同，趋势一致。

### 4.2 证据规则消融（`quantize_eligibility` 是崩溃根因）

| 证据规则 | 准确率 | Top-1 一致 | tie 率 |
|---|---|---|---|
| 当前：台阶 16, 2-bit | 37.53% | 39.3% | 74.5% |
| 台阶 4, 2-bit | 38.79% | 41.3% | 59.6% |
| 台阶 4, 4-bit | 42.32% | 44.6% | 48.4% |
| **不量化：直接用 \|v\| 排序** | **83.12%** | **84.1%** | **38.4%** |
| 不量化且保留符号 | 36.78% | 39.0% | 43.9% |

去掉量化让准确率从 `37.5%` 跳到 `83.1%`；调台阶最多只到 `42%`。

第一性原理：4 选 2 是**纯序决策**，只需组内排序不需绝对刻度。量化到 2-bit 把 4 个实数压进 4 个桶必然产生大量并列，并列由 index 决胜——这是「动态剪枝退化为静态」的机制性根因。硬件上，对 4 个 4-bit utility 求 top-2 用 6 个比较器 + 一级译码，**比当前量化+累加通路更便宜**。

### 4.3 廉价代理假设（动态决策的价值检验）

| 代理 | 乘法次数 | 准确率 |
|---|---|---|
| 真实贡献 \|v\| | 4（完整 MAC） | 83.12% |
| `sum\|w\| x max(a)` | 1 | 78.59% |
| **`sum\|w\|` 纯静态** | **0** | **76.57%** |
| `sum(a)` 纯激活 | 0 | 65.99% |

零成本静态权重范数拿到完整 MAC 的 **92%**。动态性只值 6.5 个百分点，而其成本是 `502 us/样本`（端到端的 8 倍）。

### 4.4 输入置换 + 精确无损跳过（`exact_pruning_eval.py`）

像素到「组」的映射是自由设计参数，只要权重同步重排即输出不变。选择使零像素聚集的置换：

| 置换 | 全零激活组率（held-out） |
|---|---|
| 自然顺序（行主序） | 5.2% |
| 按非零频率排序 | 29.8% |
| 贪心交换优化 | **32.7%** |

完整跳过分解（397 样本，逐样本断言 logits 完全相同）：

| 类别 | 占比 | 判定机制 |
|---|---|---|
| 零激活组 | 32.7% | 16 次 16-bit OR-reduce，一拍组合逻辑，32 个隐藏单元共用 |
| 零权重组 | 5.7% | 离线已知 |
| ReLU 区间界早停 | 1.1% | `v_k <= -S+_k`（必为 0）或 `v_k >= 127 - S-_k`（必饱和） |
| **合计精确跳过** | **39.6%** | **输出逐 bit 不变，不需要精度门** |

ReLU 早停的数学：因 uint4 激活非负，符号完全由离线权重决定，`c_g in [15*neg_g, 15*pos_g]`，后缀界可离线预计算。sat-stop 是本设计特有（上钳位派生），标准 SnaPEA 只做负侧。

### 4.5 batching 与激活稀疏的张力（负面结论）

| batch | 省带宽 | 省周期 |
|---|---|---|
| 1 | 33.0% | 33.0% |
| 8 | 19.5% | 33.0% |
| 64 | 10.3% | 33.0% |
| 256 | 6.2% | 33.0% |

一个组只要对批内任一样本非零，其权重就必须加载。**周期收益与 batch 无关，带宽收益随 batch 指数衰减。**唯一与 batching 兼容的是恒零结构（`3/64 = 4.7%` 像素在 1797 样本上恒为 0，可在设计期删除）。

因 16+ DSP 在流式下必须配 batching，**DSP 扩展与激活稀疏的带宽收益直接冲突**。

### 4.6 压缩方案最终账本（`finetune_24.py`）

| 方案 | bit | 压缩 | 准确率 | 代价 |
|---|---|---|---|---|
| dense INT8 | 18944 | 1.00x | 93.45% | — |
| **无损位宽 L0 3b / L1 6b** | 8064 | **2.35x** | **93.45%** | **0** |
| 静态幅度 3:4 全层 | — | 1.31x | 85.89% | -7.6 pp |
| 静态幅度 2:4 仅 L0 | — | 1.70x | 86.90% | -6.6 pp |
| 静态幅度 2:4 全层，不微调 | 9916 | 1.91x | 62.47% | -31.0 pp |
| ENeuron 动态 2:4，不微调 | 9916 | 1.91x | 37.53% | -55.9 pp |
| per-row INT4 权重 | — | 2.00x | 92.95% | -0.5 pp |
| **静态 2:4 + 微调** | 9916 | 1.91x | **90.43%** | -3.02 pp |
| **静态 2:4 + 微调 + 无损位宽** | 5500 | **3.44x** | 90.43% | -3.02 pp |

关键发现：

- QAT 模型 L0 权重取值仅 `{-2,-1,0,1,2,3}`，**3 bit 位精确无损**；L1 范围 `[-20,24]`，6 bit 无损。INT8 表示浪费了 L0 的 5 bit/权重。
- 微调（60 epoch，简单 SGD）把 2:4 从 `-31 pp` 救回到 `-3.02 pp`，曲线在 88.7-90.4% 震荡，已近平台但受超参限制。更好的调参可能再收一部分。
- 顺序有讲究：**必须先剪枝微调，再测存活权重位宽**。微调改变了位宽需求（L0 `[-2,3]` 3bit → `[-3,4]` 4bit）。截断到 L0 4bit/L1 6bit 后准确率仍为 `90.43%`，确认无损。
- L1 只占 13.5% 权重却对剪枝极度敏感（2:4 仅 L0 为 86.90%，全层为 62.47%）。
- 静态幅度 2:4（62.47%）比 ENeuron 动态 2:4（37.53%）好 25 pp，且省 502 us/样本决策成本。

### 4.7 模型规模 vs 剪枝端到端价值

| 模型 | 权重数 | 端到端 dense | 端到端 2:4 | 剪枝收益 |
|---|---|---|---|---|
| 当前 64→32→10 | 2,368 | 63.0 us | 58.6 us | **7.0%** |
| 256→128→10 | 34,048 | 229.8 us | 166.0 us | 27.8% |
| 784→256→10 | 203,264 | 1120.9 us | 739.8 us | 34.0% |
| 784→512→256→10 | 535,040 | 2868.1 us | 1864.9 us | **35.0%** |

固定开销在 2.5 KB 模型上占 80%，在 522 KB 模型上占 7%。渐近值 35.6%（受 3.2 节周期上限约束）。

三条路线对比：

| 路线 | 剪枝价值 | 成本 |
|---|---|---|
| 优化协议（fence 批量化） | 7% → 约 14% | 改 wrapper RTL + Vivado |
| 优化微结构（流水化） | 7% → **2.4%**（反向） | 1 周 + 时序风险 |
| **放大模型** | 7% → **35%** | 零 RTL 改动 |

注：流水化（2494 → 718 拍）会把 NPU 占比从 19.6% 降到约 6%，**使剪枝收益更不可见**。这是一个真实的优化目标冲突，须在「证明剪枝有用」与「做一个快的 NPU」之间先定目标。

## 5. 权重存储与流式架构评估

### 5.1 BRAM 迁移：可行但有失败先例

`npu_eneuron_single_clock_skeleton.sv:148` 的 `model_staging[0:633]` 无 `ram_style` 属性，被推断为分布式 LUTRAM。时序修复文档（`TIMING_REPAIR_V1.md:15`、V2 实施地图）只被动记录「0 BRAM」为综合结果，从未将其作为设计决策讨论。

**失败先例**：`b2_packet_ingress.sv:67-70` 标了 `(* ram_style = "block" *)`，但 `artifacts/logs/b2_packet_memory_ooc_20260910_bram/b2_packet_ingress_utilization.rpt` 实读为 `RAMB36=0 / RAMB18=0 / LUTRAM=1408`——属性被忽略。

根因（逐行核对确认）：

```systemverilog
// ingress bank0 被读到两个不同目的寄存器，地址表达式也不同：
cmd_data_reg    <= payload_mem_bank0[output_index];        // line 182
sample_data_reg <= payload_mem_bank0[output_index >> 2];   // line 186
```

1 写 + 2 独立读 = 3 端口，超出 BRAM 原语预算（SDP 1 写 1 读 / TDP 2 端口），退回 LUTRAM。

`model_staging` 结构不同——4 个读点（line 523/538/600/615）全部收敛到**同一个** `model_word_latched`，是 1 写 1 读，物理上落在 BRAM 能力内。且写侧早在 commit `b4b95fa`（"register model writes before BRAM update"）已拆成三级寄存。

**但这只证明物理可行，不证明 Vivado 会认。** 仓库有失败案例，无成功案例。

**兜底方案**：显式收敛读地址，把「应该会成功」变成「构造上必然成功」：

```systemverilog
logic [9:0] model_read_addr;
always_comb case (compute_state)
    COMPUTE_L0_BIAS_FETCH:  model_read_addr = 512 + compute_unit_index;
    COMPUTE_L0_GROUP_FETCH: model_read_addr = compute_model_addr;
    COMPUTE_L1_BIAS_FETCH:  model_read_addr = 624 + compute_unit_index;
    default:                model_read_addr = compute_model_addr;
endcase
model_word_latched <= model_staging[model_read_addr];
```

**三级验证阶梯（不得跳级）**：

| 级 | 动作 | 成本 | 通过标准 |
|---|---|---|---|
| 1 | `python test_npu_single_clock_compute.py` | 几分钟 | 现成断言 |
| 2 | OOC synth-only + `report_utilization -hierarchical` | 0.5-1 人时 | **出现 >= 1 RAMB36 且该层 LUTRAM 归零** |
| 3 | 完整 Vivado 取 placed WNS | 几十分钟 | WNS 仍 > 0 |

第 2 级是分水岭；若仍 0 BRAM 即复现 ingress 失败模式。

**回归风险**：RAMB36E1 有可选输出寄存器。若 Vivado 插入该级，`地址周期 N → 数据周期 N+1` 会变成 N+2。logits 仍完全正确，只比结果看不出来。门已现成：`tb_npu_eneuron_single_clock_compute.sv:517` 的 `start_contract(592, 512, 80, 2494)` 直接断言 `last_compute_cycles == 2494`。

**资源核算**：`model_staging` 估约 650-750 LUT（depth 634 需 `ceil(634/64)=10` 级联叠，SDP 每 bit 2 个 LUT6，32 bit → 640 为存储本体）。迁移后占 1 个 RAMB36E1（SDP 1024x36，634<=1024、32<=36）。此估算为自底向上推导，非报告实读，应作数量级看待。

### 5.2 容量上限与流式必要性

128 空闲 tile x 36864 bit = **576.0 KiB = 589,824 个 INT8 权重**。

`784→512→256→10` = 535,040 权重（522.5 KB）**落在上限内，整块放片上，不需要流式**。叠加 3.44x 压缩后门槛再推远 3 倍。

**结论：流式只在 > 576 KiB 时才必要。** 用户设想的「从 RAM 加载权重」对当前及中期规模的模型均非必需；BRAM 迁移（5.1）已覆盖全部现实需求。

### 5.3 roofline（若将来确需流式）

```
4 DSP x 200 MHz = 800 M MAC/s
batch=1 MLP 无片内权重复用 → 每 MAC 需 1 B INT8 权重 → 800 MB/s
单 AXI HP 口 (64-bit @ 150 MHz) = 1.2 GB/s
机器平衡点 = 0.67 MAC/B  <  算术强度 1.0 MAC/B  → compute-bound
```

| DSP 数 | 需带宽 | 判定 |
|---|---|---|
| 4 | 0.80 GB/s | 单口可行 |
| 8 | 1.60 GB/s | 需多口 |
| 16 | 3.20 GB/s | **超 DDR3 实际上限（约 2.8 GB/s），必须 batching** |

分块设计要点（评审修正）：权重双缓冲应以**单个输出神经元（1~8 个）**为粒度，不是整层——按此粒度双缓冲只需几 KB，不存在「392 KB 层装不下」的问题。tile 流式可复用现有 `OP_MODEL_DATA` 命令，不需新开权重 DMA 通道。

### 5.4 数据流分类（前人工作定位）

用户设想（逐层执行 + 权重流式 + 累加器常驻）在 Eyeriss 分类法（Chen et al., ISCA 2016）中属 **output-stationary + weight streaming**；当前 NPU（每权重每样本读一次、累加器持久）同属 output-stationary / no-local-reuse。

Xilinx 生态两条路线：FINN 为权重全片上的 dataflow 架构（高吞吐，模型必须装得下）；DPU 为权重流式的 overlay 架构（通用，带宽受限）。**本项目 576 KiB 空闲 BRAM 已覆盖路线图上全部模型规模，应优先 FINN 式全片上驻留，暂不考虑 DPU 式流式。**

分块 + 逐层加载是 TPU/DPU 及所有 tiled accelerator 的标准做法，Timeloop/Interstellar 已将其形式化为 mapping space 的一个维度。技术是标准的；新的是在本平台特定约束下的量化结论。

## 6. 本轮产物

| 文件 | 内容 | 状态 |
|---|---|---|
| `train_qat.py` | NPU 精确语义下的量化感知训练 | 未提交 |
| `int8_model_qat.json` | 93.45% 的真实 INT8 模型 | 未提交 |
| `exact_pruning_eval.py` | 输入置换 + 精确无损跳过评估 | 未提交 |
| `exact_skip_result.json` | 置换表与 39.6% 跳过率分解 | 未提交 |
| `finetune_24.py` | 静态 2:4 掩码微调 | 未提交 |
| `int8_model_24_finetuned.json` | 90.43% 的 2:4 微调模型 | 未提交 |

## 7. 建议与优先级

| 优先级 | 动作 | 成本 | 依据 |
|---|---|---|---|
| **P0** | 加模型可证伪性检查（每 meta 非零组数 >= 3 的比例），门输出 `VACUOUS` 而非 `PASS` | 1 小时 | 4.1 |
| **P0** | 修 `test_b3_speed_report_contract.py:212` 硬编码日期断言 `generated_at.date()=='2026-09-13'` | 1 小时 | 8.2 |
| **P0** | 用 `int8_model_qat.json` 替换 fixture，重跑所有门 | 半天 | 一次性解除四个退化 |
| **P1** | 混合位宽无损压缩（逐层实测 `max\|w\|`，取 `ceil(log2(max\|w\|))+1` 位） | 1 天 | 2.35x，零精度损失 |
| **P1** | 接 `npu_status_irq` + PS WFI | 1-2 天，无 Vivado | 约 18 mW，唯一越过噪声地板的功耗杠杆；见 3.5 |
| **P1** | `model_staging` 加 `ram_style` + 地址 mux，按三级阶梯验证 | 1-2 人时 + 1 次 OOC | 5.1 |
| **P1** | 去掉证据量化，改为直接比较 | 2 天 | 37.5% → 83.1%，且硬件更便宜 |
| **P2** | 放大模型到 200-500 KB（BRAM 内，不需流式） | 2-3 天 | 剪枝价值 7% → 34% |
| **P2** | 2:4 目标改为「仅 L0 + 微调」，L1 保持 dense | 1 天 | 4.6 |
| **P2** | fence 批量授权（改 wrapper RTL） | 1 周 + Vivado | 端到端最大剩余余量 28.6% |
| **P3** | PS 开 D-cache（`packet_main.c:1170` 全程 `Xil_DCacheDisable()`） | 半天 | live mask 502 us 的瓶颈是未缓存访存 |
| **P3** | NPU 流水化 | 1 周 + 时序风险 | **会稀释剪枝收益，需先定研究目标** |
| **不做** | DDR 权重流式 | — | 5.2：576 KiB 已覆盖全部规模 |
| **不做** | 锁相/调制功耗测量 | — | 3.3：待测信号物理上不存在 |
| **不做** | 64-DSP 放大外推 | — | 改变被测对象，且必然破 WNS |

## 8. 方法学建议

### 8.1 MAE < MDE 作为门的 vacuity 判据

统一判据：**最大可达效应（MAE）< 最小可测效应（MDE）⟹ 门为 VACUOUS**，CI 应阻断而非报 PASS。

| 门 | MAE | MDE | 判定 |
|---|---|---|---|
| 精度门（fixture） | 0（每 meta 非零组 <= 2） | 0.01 | **VACUOUS** |
| 功耗门 | 2 mW | 11.2 mW | **VACUOUS** |
| 速度门 | 7.05%（888 cycles / 63 us） | — | 非 vacuous，受 Amdahl 限 |

配套四值判词 `{PASS, FAIL, VACUOUS, INSUFFICIENT}`，用 Kleene 吸收律修复「vacuous 子门被聚合成有意义 PASS」的病理。

### 8.2 工作流负债量化

- 7 个核心账本共 **8365 行**；最近 40 提交累计 **139 次账本编辑**（3.5 次/提交）
- `test_b3_speed_report_contract.py` 有 **32 个 `assertIn` + 9 个 `assertNotIn` = 41 处字符串断言直接锁定中文散文**，且 line 212 硬断言 `generated_at.date().isoformat() == "2026-09-13"`（已核实）——任何在该日期后重新生成 nexus concept_model 都会红灯。**这是账本重构的第一块绊脚石，应最先修。**
- `build/` 树 **633 MB**，25 个 git-HEAD 目录各含一整套重复 BSP
- BSP 按 git HEAD 键控（`run_b2_sw_build.ps1:12`），而正式证据要求 clean worktree = 必须 commit = 每次正式 run 吃满约 7 分钟 BSP 重建税。热路径 2-3 分钟 vs 冷路径 9-10 分钟，形成「越正式越慢」的反常激励。建议 BSP 抽到 `build/bsp/<xsaSha>/` 共享层（注意 buildRoot 在 5 个脚本中同构重算，是多文件一致性修改）

### 8.3 Amdahl 预算门

建议在每个 campaign 启动前用现有分段实测算天花板，低于门限则不进入板级迭代。代价一小时纸面计算。若 B3-22 系列启动前有此门，会立刻发现「NPU 仅占 7.9%，剪枝上界 7.9%」，从而先做协议优化（B3-22.4 实测 2.45x）再做剪枝 A/B。

项目已从该弯路转出（`WORKFLOW_STATE.md` 显示已收敛到固定开销线），本建议为防下一次。

## 9. 不可声称

- 不得把本文任何数字当作板级证据：本轮**无任何新的板级运行**。
- 不得把 `39.6% 精确跳过` 写成端到端加速：它是 L0 组级跳过率，端到端影响需按 3.1/3.2 折算。
- 不得把 `93.45%` / `90.43%` 当作板上结果：这些是本机 Python 在 NPU 精确语义下的仿真，尚未经 RTL 或板级复现。
- 不得把 `2.35x` / `3.44x` 压缩写成已实现：当前 RTL 仍是 4 x INT8/word 格式，位宽压缩需改 word 布局。
- 不得据 5.1 的结构分析宣称 BRAM 迁移成功：必须有第 2 级 OOC 报告显示非零 RAMB36。
- 不得把 `18 mW` WFI 收益当作实测：那是基于 PS7 1.286 W 的量级估计，需实测确认。
- 不得把 `650-750 LUT` 当作报告实读：那是自底向上估算。
- 本文所有准确率均绑定 `seed 20260914` 的 1400/397 划分与 `digit8x8_fixture.json`；换划分或换数据集需重测。

## 10. 状态

本文不改变任何门状态。当前仍为：

```
B3_ACCURACY_GATE_OPEN / B3_SPEED_GATE_OPEN / B3_POWER_NOT_MEASURED /
B3_POWER_GATE_OPEN / B3_GOAL_GATE_OPEN / B3_STRICT_DEFERRED_STRUCTURAL /
B2_GATE_PENDING
```

建议新增状态位 `B3_POWER_GATE_NOT_RESOLVABLE_BY_CONSTRUCTION`（依据 3.3），以区分「尚未测量」与「在当前微结构与测点下物理上不可测」。
