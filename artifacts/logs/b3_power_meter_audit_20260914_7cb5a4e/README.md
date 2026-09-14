# B3 功率计读数级审计（2026-09-14，RTL `be84596`）

结果：`POWER_METER_READING_AUDIT_COMPLETE`。本目录只回答一件事——主线已归档的整板读数**能不能**支撑
“剪枝降低设备功率”这个结论。答案是不能，且读数本身有一处可复算的转录缺陷。本工具**只报告缺陷与
可辨识性，不改写任何证据文件，也不关闭任何门**：`b3_power_measured=POWER_NOT_MEASURED`、
`power_gate=OPEN`、`power_goal_status=NOT_PROVEN`、`gate_closure_authority=none` 由代码固定。

## 输入绑定

| 文件 | 角色 | canonical-LF SHA-256 |
|---|---|---|
| `../b3_power_20260913_be84596/manual_meter_observations_20260913.json` | 主线 5 个窗口的逐条读数（V/A/W/mAh/mWh） | `04b2e408245aba11936607b91f612cea3c44fdf70827f35cb81b0aec5d0f265a` |
| `b3_power_meter_audit.json` | 本目录冻结的审计结果（只由输入与两个命令行常数决定） | `873b1d6a362146fc28f887d41a0c613e686c44de00ac7b89ca7c10edcc6b85e7` |

输入文件已由 `b3_power_attribution.json` 的 `input_bindings` 绑定同一哈希，因此**任何改写都会同时打破
两份证据的绑定关系**。审计工具以只读方式打开它，`--observations` 指向别的文件时输入哈希随之改变。

命令行常数只有两个，且都写进结果 JSON：`sigma_pair_mw = 11.15547`（同配置 dense 两轮的功率差）与
`effects_mw`（Vivado 外推/原始、观测 live/static 四个效应量）。

## 复算

```powershell
python -X utf8 b3_power_meter_audit.py --sigma-pair-mw 11.15547 --effects "vivado_extrapolated_200mhz=3.487,vivado_raw_100mhz=1.743,observed_live=9.944,observed_static=7.694" -o artifacts\logs\b3_power_meter_audit_20260914_7cb5a4e\b3_power_meter_audit.json
python -X utf8 -m unittest -v test_b3_power_meter_audit
```

## 五条结论（详见 `docs/reports/B3_POWER_ATTRIBUTION_2026-09-14.md` §8）

1. `delta_mWh` 5/5 与自身 readings 首末差一致；`delta_mAh` 4/5 矛盾（隐含电压 15.3–19.7 V，Type-C 上
   不可能）。所有功率与能耗数字只走 `delta_mWh`，所以**已发布数字不变**，但该字段不可引用。
2. dense 第二轮内部读数 `20:04:13` 的单点抄录误差 `+16.75 mWh = 60.3 J`；同样的误差落在窗口端点即
   `±35.8 mW`，是观测处理差 `9.94 mW` 的 3.6 倍、同配置重复性 `11.16 mW` 的 3.2 倍。
3. 显示功率只有 7 个离散值，电流 LSB 约合 `26.6 mW` > 效应；能量累加器 1 mWh 约合 `2.13–2.28 mW`、
   端点 ±0.5 计数仅 `±0.885–1.142 mW`；仪表 `0.2%` 是乘法增益误差，对配对差只有约 `0.02 mW`。
   量化不是瓶颈。
4. 剪枝等级与测量时刻秩完全共线（反序对=0），两种合法去漂移口径让 static/live 残差符号相反：
   `TREATMENT_NOT_IDENTIFIABLE_FROM_WINDOW_MEANS`。
5. 以 `sigma_pair = 11.16 mW`（1 个自由度）计，5 配对轮的可分辨下限 `13.98 mW`，分辨 Vivado 外推的
   `1.7–3.5 mW` 需要约 81–322 对。

## 边界

- 测点是 Type-C 整板 5 V 输入，不是 PL 电源轨。
- 本工具不读取任何 Vivado `power_impl.rpt`，也不 import `b3_power_attribution`；它只审计仪表读数。
- 输入不满足前提（窗口集合不符、`readings` 不足两条、段时长非正、`delta_mWh` 与 readings 不一致）时
  直接抛 `AuditInputError`，不产出结论。