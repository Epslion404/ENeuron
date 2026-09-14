# B3 剪枝后整板功率归因（2026-09-14，RTL `be84596`）

结果：`POWER_ATTRIBUTION_NOT_ESTABLISHED`。本目录只回答“剪枝后设备功率到底变了多少、能否归因”，
不关闭 `B3-POWER-MEASURED`、`B3-POWER-GATE` 或 `B3-GOAL-GATE`。

## 输入绑定

| 文件 | 作用 | canonical-LF SHA-256 |
|---|---|---|
| `../b3_power_20260913_be84596/manual_meter_observations_20260913.json` | 主线已归档的 B10 整板读数（5 个窗口） | 见 `b3_power_attribution.json` 的 `input_bindings` |
| `../b3_power_20260913_be84596/b3_power_report.json` | 四模式 NPU 周期与 bitstream 身份 | 同上 |
| `inputs/valid_inferences_from_pr96.json` | 逐窗口有效推理计数 | 同上 |

主线 rollup 只带 `b3_live_eneuron` 的 `valid_inferences`；其余三个负载窗口的计数转录自未合并分支
`codex/b3-power-manual-meter@2de122c` 的 `measurement_summary.json`，每条都绑定 blob SHA-1 与
canonical-LF SHA-256，可用 `git show` 复核。`b3_power_attribution.py` 拒绝无来源绑定的裸计数输入。

## 复算

```powershell
python -X utf8 b3_power_attribution.py --extra-counts artifacts\logs\b3_power_attribution_20260914_7cb5a4e\inputs\valid_inferences_from_pr96.json
```

## 边界

- 测点是 Type-C 整板 5 V 输入，不是 PL 电源轨；读数含 PS、DDR、稳压损耗和仪表自身。
- 本工具不读取任何 Vivado `power_impl.rpt`。Vivado 无向量估算只作上界核对，不替代板上读数。
- 报告生成器固定 `power_gate=OPEN / power_goal_status=NOT_PROVEN / gate_closure_authority=none`。
