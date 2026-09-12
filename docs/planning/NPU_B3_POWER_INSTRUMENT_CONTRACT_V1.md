# B3-POWER 仪器合同 V1

日期：2026-09-13
状态：`FROZEN / POWER_NOT_MEASURED / MEASUREMENT_OPEN / GOAL_GATE_OPEN`

本合同冻结板上 NPU packet 路径功耗测量的六个字段。机器可读副本：`tools/repro/b3_power_instrument_contract.json`。

## 冻结字段

| 字段 | 当前值 |
|---|---|
| 仪器 | 未发现（无 USBTMC / VISA / pyvisa / 具名功率计） |
| 测点 | 未接 |
| 采样率 | 未设 |
| 空闲基线 | 未采 |
| 负载同步 | 未接 UART `B2_PACKET_BEGIN` |
| 积分窗口 | 未开 |

COM15/COM35 是 CH340 UART。COM32（VID_04D8）和 FTDI `0403:6014` 是 JTAG，不是功耗仪。

## 关闭条件

dense vs static vs live 必须在同一 `group_4way` bitstream（RTL `be84596`）上各有非空 `power_source`、外部 `external_trace` 和有限正数 `external_power_w`；六个仪器字段必须全部填写。满足这些条件只关闭 `B3-POWER-MEASURED`，不自动关闭降功耗目标。禁止 Vivado 功耗估算。无仪器则保持 `POWER_NOT_MEASURED`。

`B3-POWER-GATE` 还需在测量前补冻重复次数、目标量（板级平均功率并同时报告每次正确推理能耗）、统计量和超过仪器不确定度的最小改善门限；只有 live 相对 dense 达标且正确性保持才可关闭。`B3-GOAL-GATE` 只在该目标门与 `B3-SPEED-GATE` 都通过后才能关闭。
