# B3-POWER 仪器合同 V1

日期：2026-09-13
状态：`FROZEN / POWER_NOT_MEASURED / GATE_OPEN`

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

dense vs static vs live 必须在同一 `group_4way` bitstream（RTL `be84596`）上各有外部 traces，且 `external_power_w` 为数值。禁止 Vivado 功耗估算。无仪器则保持 `POWER_NOT_MEASURED`，`B3-POWER` 不打勾。

`B3-GOAL-GATE` 只在 `B3-POWER` 实际关闭后才能关。
