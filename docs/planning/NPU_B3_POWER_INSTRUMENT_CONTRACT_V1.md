# B3-POWER 仪器合同 V1

日期：2026-09-13
当前态更新：2026-09-17
状态：`FROZEN / POWER_NOT_MEASURED / MEASUREMENT_OPEN / GOAL_GATE_OPEN`

本合同冻结板上 NPU 功耗测量的六个字段与 CP8 正式口径。机器可读副本：`tools/repro/b3_power_instrument_contract.json`。

`POWER_NOT_MEASURED / MEASUREMENT_OPEN` 表示合同已冻结但 CP8 尚未执行；它不表示缺少仪器。仪器已具备。

## 仪器与测点

- 仪器：B10 高精度 Type-C 多功能无线充测试 USB 电压电流表 PD3.2 充电检测仪，标称精度 `<0.2%`。
- 显示精度：V/A/W 小数点后 5 位（共 6 位），mAh/mWh 为 7 位整数。
- 测点：仪表串联在 Type-C 供电与开发板之间，测得的是整板输入功率，**不是纯 NPU 功率**，不得写成“纯 NPU 功耗”。
- 采样方式：人工读数并拍照记录时间；每轮记录起止照片、时间、V/A/W、mAh/mWh、有效正确推理数和持续时间。
- JTAG 仅用于通信；dense/lossless 四态测量必须保持相同的 JTAG/PS 状态。

## 冻结字段

| 字段 | 当前值 |
|---|---|
| 仪器 | B10 高精度 Type-C 多功能无线充测试 USB 电压电流表 PD3.2 充电检测仪，精度 `<0.2%` |
| 测点 | 仪表串联在 Type-C 供电与开发板之间（整板输入，非纯 NPU 功率） |
| 采样率 | 仪表不提供机器采样接口；按人工定时拍照形成离散读数，V/A/W 小数点后 5 位（共 6 位），mAh/mWh 7 位整数 |
| 空闲基线 | `dense idle` / `lossless idle`：相同 bit/XSA/ELF、模型已装载、JTAG/PS 状态一致、replay 未启动或停在冻结 idle |
| 负载同步 | `dense/lossless continuous full` 复用 CP5b 397 样本 PL-internal distribution replay，1000 warmup 后持续运行，PS 不参与逐样本决策 |
| 积分窗口 | 用 `ΔmWh/Δt` 计算窗口平均整板功率，`ΔmAh/Δt` 只作平均电流交叉核对；同时以有效正确推理数计算整板总能耗/推理和 mode-matched 增量能耗/推理；至少 5 组交替 paired rounds |

COM15/COM35 是 CH340 UART。COM32（VID_04D8）和 FTDI `0403:6014` 是 JTAG，不是功耗仪。

## CP8 正式测量对象与口径

正式对象只有四态，均使用已通过 CP5b 的 dense/lossless 两个候选：

1. `dense idle`
2. `dense continuous full`
3. `lossless idle`
4. `lossless continuous full`

- full 复用 CP5b 397 样本 PL-internal distribution replay，1000 warmup 后持续运行；PS 不参与逐样本决策。
- idle 使用相同 bit/XSA/ELF、模型已装载、JTAG/PS 状态一致，replay 未启动或停在冻结 idle。
- 至少 5 组 paired rounds，交替顺序；同一 Type-C 串联 B10 仪表、相同 JTAG/PS 状态。
- 记录照片/时间、V/A/W、mAh/mWh、有效正确推理数和持续时间。
- 必须同时报告：
  - 整板平均功率；
  - mode-matched `idle → full` 增量功率；
  - 整板总能耗/正确推理：`P_full / throughput`，并用 `ΔmWh / valid_inference_count` 交叉核对；
  - mode-matched 增量能耗/正确推理：`(P_full - P_idle) / throughput`；
  - 仪器精度/量化导致的可分辨性（B10 标称 `<0.2%`，显示分辨率 V/A/W 5 位小数、mAh/mWh 7 位整数）。
- 允许的现实结论是“平均功率不可分辨，但因吞吐提高而每次推理能耗下降”；不得把整板功率称为纯 NPU 功率。
- static/PL-auto/strict 2:4/双引擎不属于本轮 CP8，只有各自精度和速度门通过后才追加。

## 关闭边界

`B3-POWER-MEASURED` 在四态各有非空 `power_source`、照片/人工观察 manifest 路径 `external_trace` 和有限正数 `external_power_w`，且六个仪器字段全部填写后才可关闭。满足这些条件只关闭 `B3-POWER-MEASURED`，不自动关闭降功耗目标。禁止 Vivado 功耗估算。CP8 未执行前保持 `POWER_NOT_MEASURED / MEASUREMENT_OPEN`。

`B3-POWER-GATE` 还需在测量前补冻重复次数、目标量（整板平均功率并同时报告每次正确推理能耗）、统计量和超过仪器不确定度的最小改善门限；只有 lossless 相对 dense 达标且正确性保持才可关闭。`B3-GOAL-GATE` 只在该目标门与 `B3-PL-SPEED-GATE` 都通过后才能关闭；目标范围只声称“可重复纯 PL 推理吞吐提升 + 外部整板功率/能耗改善 + 正确性保持”，若论文声称 packet/end-to-end 加速，必须另有重复实测。

## 历史工程观察

2026-09-13 `artifacts/logs/b3_power_20260913_be84596/` 下的 dense/static/live 人工读数是历史工程观察（`POWER_ENGINEERING_OBSERVATIONS_INCOMPLETE_CONTRACT`），必须保留，不得改写为 CP8 正式证据。
