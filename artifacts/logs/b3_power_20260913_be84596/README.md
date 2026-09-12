# B3-POWER 状态（2026-09-13，RTL `be84596`）

结果：`POWER_NOT_MEASURED`。`B3-POWER` 保持 `[ ]`。

本机发现：无 USBTMC / VISA / pyvisa / 具名功率计。COM15 与 COM35 是 CH340 UART；COM32（VID_04D8）与 FTDI `0403:6014` 是 JTAG。未发明仪器，未用 Vivado 估算冒充板上功耗。

合同：`tools/repro/b3_power_instrument_contract.json`、`docs/planning/NPU_B3_POWER_INSTRUMENT_CONTRACT_V1.md`。

dense/static/live 行复用已归档 SPEED 实板 identity，不含 `external_power_w`。
