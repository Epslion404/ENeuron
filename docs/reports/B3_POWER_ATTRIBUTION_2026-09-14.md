# B3 剪枝后设备功率归因报告（2026-09-14）

生成工具：`b3_power_attribution.py`（只读、fail-closed）。冻结结果：
`artifacts/logs/b3_power_attribution_20260914_7cb5a4e/b3_power_attribution.json`。
本报告的每个数字都能由该工具从已绑定哈希的输入复算，不接受手填值。

## 0. 一句话结论

`POWER_ATTRIBUTION_NOT_ESTABLISHED`。剪枝（static/live，296 执行 + 296 跳过，1606 cycles）相对 dense
（592 执行，2494 cycles）在 Type-C 整板测点上**没有可分辨的功率下降**：观测到的整板差只有
`-0.49%`（static）与 `-0.63%`（live），而同一 dense 配置两轮之间的重复性差就有 `0.71%`，
idle 基线又高于所有负载窗口。每次正确推理能耗确实降 `6.64%`，但那几乎全部来自吞吐上升
`6.43%`，不是整板功率下降。`B3-POWER-MEASURED`、`B3-POWER-GATE`、`B3-GOAL-GATE` 全部保持 OPEN。

## 1. 输入与身份

| 项 | 值 |
|---|---|
| 比特流 RTL 身份 | `be84596`（200 MHz，`WNS=+0.045 ns`，DSP48E1=4） |
| bitstream SHA-256 | `0ecbe76274c39418f2a60a88358d3ff6f09f5a2ed73a44a3a419c34eb91d3a11` |
| XSA SHA-256 | `135d979d61c629922ee5419e51dd97ef045d9bab79930432816d09f109291d1a` |
| 功率读数 | `artifacts/logs/b3_power_20260913_be84596/manual_meter_observations_20260913.json` |
| 周期身份 | `artifacts/logs/b3_power_20260913_be84596/b3_power_report.json` |
| 逐窗口有效推理计数 | `inputs/valid_inferences_from_pr96.json`，转录自未合并分支 `codex/b3-power-manual-meter@2de122c` |
| 仪表 | B10 Type-C 串入式表，标称 `<0.2%`，V/A/W 5 位小数，mAh/mWh 整数 |
| 测点 | Type-C 5 V 输入，**整板**，非 PL 电源轨 |

主线 rollup 只带 live 窗口的 `valid_inferences`。dense 两轮与 static 的计数在主线不可得，因此本
报告的能耗/吞吐行使用 PR #96 分支产物，并逐条绑定 blob SHA-1 与 canonical-LF SHA-256；工具会拒绝
任何没有来源绑定的裸计数输入。

## 2. 整板功率与增长率

`dP/idle` 以 idle `1.5759960649 W` 为基线；`dP/dense` 以 dense 两轮均值 `1.57469888 W` 为基线。

| 窗口 | 时长 s | ΔmWh | 平均功率 W | 有效推理 | inf/s | NPU cycles | NPU 占空比 | 增长率 dP/idle % | 增长率 dP/dense % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| b3_idle | 2033 | 890 | 1.57599606 | 0 | – | – | – | 0.000 | +0.082 |
| b3_dense_round_1 | 1663 | 730 | 1.58027661 | 8,499,751 | 5111.10 | 2494 | 6.37% | +0.272 | +0.354 |
| b3_dense_round_2 | 1684 | 734 | 1.56912114 | 8,412,993 | 4995.84 | 2494 | 6.23% | -0.436 | -0.354 |
| b3_static_mixed | 1576 | 686 | 1.56700508 | 8,093,983 | 5135.78 | 1606 | 4.12% | -0.570 | **-0.489** |
| b3_live_eneuron | 1691 | 735 | 1.56475458 | 9,094,863 | 5378.39 | 1606 | 4.32% | -0.713 | **-0.632** |

## 3. 每次正确推理能耗（合同 V2 主指标）

`EPI = delta_mWh * 3600 / valid_inferences`，单位 mJ/次。

| 模式 | EPI mJ | 增长率 vs dense 均值 % | 分解：功率项 | 分解：吞吐项 |
|---|---:|---:|---:|---:|
| dense round 1 | 0.3091855 | -0.79 | +0.354% | +1.14% |
| dense round 2 | 0.3140856 | +0.79 | -0.354% | -1.14% |
| static_mixed | 0.3051155 | **-2.09** | -0.489% | +1.63% |
| live_eneuron | 0.2909335 | **-6.64** | -0.632% | +6.43% |

dense 两轮本身的 EPI 离散是 `1.57%`，大于 static 相对 dense 的全部改善（`2.09%`），也大于 live
改善量的四分之一。也就是说：`EPI_live < EPI_dense` 的方向成立，但幅度里只有一小截可能是功率，
其余是“同样的整板功率在单位时间里多做了推理”。

## 4. 为什么这 -0.63% 不能记在剪枝头上

1. **同配置重复性比信号大**：dense 两轮差 `11.16 mW`（`0.71%`），live 相对 dense 均值只差
   `9.94 mW`。方向由单轮决定，任何一条腿换一轮就可能翻转。
2. **idle 基线倒挂**：idle `1.57599606 W` 高于 dense 第二轮、static、live 三个负载窗口，最高差
   `11.24 mW`。负载窗口比空转更省电在物理上不成立，说明窗口间漂移（供电/温度/仪表累计量）
   已经在 10 mW 量级主导读数。
3. **NPU 只占 4–6% 占空比**：每推理墙钟 `186–200 us`，其中 NPU 计算只有 `2494/200 MHz = 12.47 us`
   （dense）与 `1606/200 MHz = 8.03 us`（剪枝），其余是 PS 协议路径（每样本 fence、
   `usleep(100)`、DMA 往返、结果校验）。这直接回答了 B3-19 的前置问题：**NPU 没有持续满载**，
   整板功率主要被 PS 与静态部分吃掉。
4. **量级不自洽**：Vivado 无向量估算（`archive/legacy/np6_physical/*/power_impl.rpt`，
   `Simulation Activity File = ---`，Confidence Medium，`clk` 约束 10.0 ns 即 100 MHz）给 unpruned
   动态 `40 mW`、pruned `18 mW`、静态恒为 `103 mW`。把动态差按频率线性外推到 200 MHz
   （`80`/`36 mW`）再乘实测 NPU 占空比（dense 均值 `6.30%`、static `4.12%`、live `4.32%`），
   剪枝在整板只解释得了 `3.5–3.6 mW` 的下降（不外推则 `1.7–1.8 mW`）；反过来，若把观测到的
   `7.7–9.9 mW` 全记给 NPU 门控，就要求这个 4 个 DSP48E1 的核在计算窗口里烧掉 `187–502 mW`，
   是 Vivado 同一规模估算外推到 200 MHz 后 `80 mW` 的约 2 到 6 倍（不外推则 5 到 13 倍）。
   也就是说偏差是几倍、不是一个到两个数量级，但观测值仍然明显大于模型期望，而观测值本身
   又小于同配置重复性，两条一起否掉了“整板 -0.63% 就是剪枝省下的功率”。
5. **测量点错配**：Type-C 输入含 PS（ARM 忙等）、DDR、USB-PD、稳压损耗与仪表自身。合同 V1/V2
   又禁止用 Vivado 估算替代板上读数，所以两头都不能替代 PL 轨级证据。

## 5. live 窗口的真实形态（必须写清的边界）

`B3_POWER_BENCH` 的 live 只在启动时调用一次 `compute_live_group4way_mask()`，整个积分窗口复用同一
mask/epoch，窗口循环只做 fence + 样本提交。所以这条曲线测的是**固定 mask 的稳态**，不是逐样本
现场决策的动态流；仓库自身结论也是“固定输入重复不能代表通用动态流”。叠加 `82b079e` 的 L0
contribution 缓存与 `e750df8` 的 live mask epoch 复用，live 相对 dense 的 `6.43%` 吞吐优势更可能
来自 PS 侧协议路径变短，而不是 NPU 跳过 296 组。

## 6. 门状态与允许表述

允许：`同一 be84596 bitstream 上，剪枝把每次正确推理的整板输入能耗从 0.3091855/0.3140856 mJ 降到
0.2909335 mJ（-6.64%），该改善与 +6.43% 吞吐同步；整板平均功率差 -0.63% 未超过同配置重复性
0.71%，剪枝降功率未证明。`

禁止：`剪枝降低板上功耗 x%`、`power_gate=PASS`、`B3-POWER-MEASURED 完成`、把 Vivado 估算当板上实测。

本报告不构成任何门的关闭证据；`B3-POWER-GATE` 仍要求五轮四模式配对、窗口门限、照片/trace、统一
负载同步，且改善必须严格超过按仪表准确度算出的不确定度界限。

## 7. 下一步才能拿到可分辨的功率证据

按“改动最小、先使信号超过噪声”的顺序：

1. 先解 occupied-duty 问题：在批量 frame/fence（即 B3-22.5 待评审合同）之后测功率，让 NPU 计算
   占空比从现在的 4–6% 提到 50% 以上。占空比 50% 时，同样的 PL 动态差会在整板上给出 `11–22 mW`，
   才第一次超过 `0.2%`（`3.15 mW`）仪表精度。
2. 加“等墙钟”对照：dense 与 live 都在相同推理数与相同 PS 工作量下比较，避免把速度红利记成功耗红利。
3. 若要归因到 NPU 本身：用 XSim 生成的 VCD/SAIF 对 dense 与 pruned mask 做 activity-driven Vivado
   估算，作为**上界补充**（合同禁止它替代板上读数）。这需要维护者明确授权，因为当前合同状态仍是
   `POWER_NOT_MEASURED`。
4. 若坚持整板测点：需要标称优于 `0.1%`、且有起止照片与 trace 的重复测量，或直接测 PL 电源轨。
5. 补齐 idle 单调性判据：任何负载窗口低于 idle 的轮次都应判为无效窗口，而不是取平均。

## 8. 复核

```powershell
python -X utf8 b3_power_attribution.py --extra-counts artifacts\logs\b3_power_attribution_20260914_7cb5a4e\inputs\valid_inferences_from_pr96.json
python -X utf8 -m unittest -v test_b3_power_attribution test_b3_power_report_contract
```

工具会在下列情况直接抛错而不是给结论：仪器准确度缺失、`delta_mWh * 3600 / duration` 与记录功率不
自洽、缺 idle 基线、缺 `last_compute_cycles`、计数输入没有来源哈希绑定。
