# B3-POWER 人工功耗测量合同 V2

日期：2026-09-13
状态：`FROZEN_V2 / RUNNER_READY / POWER_NOT_MEASURED / MEASUREMENT_OPEN / GOAL_GATE_OPEN`

本合同冻结板上 NPU packet 路径的人工功耗测量协议。机器副本为 `tools/repro/b3_power_instrument_contract.json`；执行入口为 `boards/hellozynq/b2_sw/run_b3_power_manual.ps1`，汇总入口为 `build_b3_manual_power_report.py`。

## 测点与仪表

- 固定 5 V Type-C 电源，串联型功率计接在电源与开发板 Type-C 供电输入之间，测量整板输入。
- 全部轮次保持相同 JTAG 物理连接。启动和结果读取允许使用 JTAG；积分窗口内 XSCT、`hw_server` 和扫描必须全部停止。
- V/A/W 均为 1 位整数加 5 位小数；mAh/mWh 为最多 7 位整数，分辨率为 `1 mAh / 1 mWh`。
- 每次正式运行记录仪表型号、标称准确度和固定电源说明；未知准确度不能关闭 `B3-POWER-GATE`。

## 模式与顺序

- 统一 ELF 运行 `b3_idle / b3_dense / b3_static_mixed / b3_live_eneuron` 四种模式。
- 奇数轮顺序：idle → dense → static → live；偶数轮顺序反向。
- 至少完成 5 个完整轮次。负载模式先运行至少 1000 个预热样本，预热不计入正式窗口。

## 窗口与证据

- 每个窗口至少 `300 s`，累计 `delta_mWh >= 200`；负载模式还需至少 `10000` 个正确推理。
- idle 模式模型已加载但不发送推理请求；dense/static 在初始 mask 激活后连续发送样本；live 每个样本现场计算、提交并激活 ENeuron mask。
- 窗口起止记录 V/A/W/mAh/mWh 与照片；窗口中每 60 秒记录一次 V/A/W。
- 每个窗口保存板端结果 manifest、仪表 trace、照片、bit/XSA/ELF/源码/合同哈希。24-bit execute/skip 计数只作末态诊断，不作为长窗口总执行次数。
- 主指标为每次正确推理总能耗：`delta_mWh * 3600 / valid_inferences`，单位 mJ；同时报告整板平均功率和扣除同轮 idle 后的动态功率。

## 门限边界

完成五轮四模式、全部窗口门限、正确性门和证据哈希后，只能把 `B3-POWER-MEASURED` 改为完成。当前已有 idle 基线和 dense 部分观察，但尚未形成完整合同窗口，因此仍不能关闭 `B3-POWER-MEASURED`。禁止用 Vivado 功耗估算替代板上读数。

`B3-POWER-GATE` 比较 live 与 dense 的五轮“每次正确推理总能耗”中位数；只有 live 更低，且差值严格超过按本次仪表标称准确度计算的保守不确定度界限，才能另行人工审核关闭。报告生成器固定输出 `power_goal_status=NOT_PROVEN / power_gate=OPEN`，不会自动越权。`B3-GOAL-GATE` 仍要求速度门与功耗门都实际通过。
