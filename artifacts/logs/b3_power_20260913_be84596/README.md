# B3-POWER 状态（2026-09-13，RTL `be84596`）

结果：`POWER_NOT_MEASURED / POWER_GOAL_NOT_PROVEN`。`B3-POWER-MEASURED` 与 `B3-POWER-GATE` 均保持 `[ ]`。

历史环境快照（仅用于解释本目录为何未测量）：当时未发现 USBTMC / VISA / pyvisa / 具名功率计。未发明仪器，未用 Vivado 估算冒充板上功耗。

合同：`tools/repro/b3_power_instrument_contract.json`、`docs/planning/NPU_B3_POWER_INSTRUMENT_CONTRACT_V2.md`。

dense/static/live 行复用已归档 SPEED 实板 identity，不含 `external_power_w`。

即使后续补齐外部 trace 和正数功率，也只表示测量完成；在重复性、板级平均功率、每次正确推理能耗和仪器不确定度门限冻结并实际达标前，不得写 `power_gate=PASS`。
