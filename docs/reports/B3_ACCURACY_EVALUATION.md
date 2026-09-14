# B3 精度保持验证

## 当前结论

精度门尚未关闭。输出保持（output_preservation）与任务精度（task_accuracy）是两个独立结论：1024 样本 dense/live 输出保持已完成（agreement 1.0、与 Python golden 逐项一致），但任务精度为 `MODEL_TASK_FIT_UNVERIFIED`；当前 fixture 还判 `GATE_VACUOUS / MODEL_UNDER_DETERMINED`。

仓库现已提供 `b3_accuracy_report.py`。`archive/legacy/digit8x8/digit8x8_fixture.json` 含 1797 个带标签、每样本 64 个 `uint4` 像素的输入，可作为输出保持/协议压力的候选评测集；但当前模型在其上的 dense 参考准确率只有 `11.23%`（8/10 类召回为 0），且非零权重组仅 11/592，因此当前集合只能用于输出保持/协议证据；任务精度标记为 `MODEL_TASK_FIT_UNVERIFIED`（模型/任务适配性未证明），不自动归因标签语义。

先生成 1000 个样本的 64 样本分块：

```powershell
python b3_accuracy_dataset.py -o .\artifacts\results\b3_accuracy_chunks_20260914 --samples 1000
```

该命令生成 16 个板端 run manifest（最后一块 40 个样本）。每个分块都要分别运行 dense 和 live；运行结果中的 `accuracy_capture` 再按 `sample_id`、输入 SHA-256、标签和 CRC 配对。正式提交前还必须检查 dense 基线是否与当前模型/标签语义匹配；不能因为 live 与一个低质量 dense 基线一致，就宣称任务精度足够：

```powershell
python b3_accuracy_merge.py `
  --dense .\dense\b3_speed_benchmark.json `
  --live .\live\b3_speed_benchmark.json `
  -o .\accuracy_samples.json
python b3_accuracy_report.py .\accuracy_samples.json -o .\b3_accuracy_report.json
```

注意：每个分块都会重新 warm-up，因此 dense 正式样本的 `dense_mask_epoch` 全为 `1`，live 正式样本的 `live_mask_epoch` 从 `2` 开始递增；不能把分块内的 live epoch 当作全局连续 epoch。

当前生成的 `artifacts/results/b3_accuracy_reference_only_report.json` 仅是 Python 参考模型对照，`status=PASS` 只表示参考 dense/live 没有差异，不是实板精度门证据。

## 输入合同

正式输入使用 JSON 对象，顶层必须绑定同一轮实验身份：

```json
{
  "identity": {
    "model": "model-id-or-sha256",
    "preprocess": "preprocess-contract-id",
    "bitstream_sha256": "...",
    "xsa_sha256": "...",
    "elf_sha256": "..."
  },
  "samples": [
    {
      "sample_id": "sample-0000",
      "input_identity": "input-sha256",
      "mask_epoch": 1,
      "protocol_errors": 0,
      "result_crc_match": true,
      "input_match": true,
      "label": 0,
      "dense_logits": [0, 0],
      "live_logits": [0, 0]
    }
  ]
}
```

每个样本必须来自同一个输入在 dense 和 live 两种模式下的对照；不得复用上一个样本的 mask、epoch 或结果。`dense_logits`、`live_logits` 的类别顺序必须一致，`label` 必须来自评测集，而不是由 dense 预测反推。

## 执行与判定

```powershell
python b3_accuracy_report.py .\accuracy_samples.json -o .\b3_accuracy_report.json
```

工具输出：

- Top-1 prediction agreement 及 Wilson 95% 置信区间；
- dense/live accuracy 及 Wilson 95% 置信区间；
- `accuracy_drop_pp` 及同一输入配对差值的 95% 区间 `accuracy_drop_ci95_pp`；
- logit 绝对/相对误差的 p50/p95/p99/max；
- 每类召回率；
- `failed_checks` 和 `accuracy_gate`。

只有同时满足以下条件才可将 `B3-ACCURACY-GATE` 标记为 `ACCURACY_NEAR_DENSE`（该标记仅表示 output_preservation，不代表任务精度通过）：

1. 样本数不少于 1000；
2. agreement 不低于 99.0%；
3. live 相对 dense 的准确率绝对下降不超过 1.0 个百分点；
4. agreement 的 Wilson 95% 置信区间下界仍不低于 99.0%；
5. 配对准确率差值的 95% 置信区间上界仍不高于 1.0 个百分点；
6. identity、输入配对、mask/epoch、CRC 和协议校验全部通过。

因此，1000 个样本中即使观测到的 Top-1 一致率达到 99%，只要统计区间仍可能低于 99%，本轮也不能宣称“几乎不影响”。这是一项保守的证明门，不是对所有未来数据分布的数学保证。

脚本通过不代表已有实测数据。speed runner 默认仍只归档结果 CRC；需要显式开启板端逐样本 logits 采集：

```powershell
.\boards\hellozynq\b2_sw\run_b3_speed_benchmark.ps1 -Mode dense -Samples 64 -CaptureLogits
.\boards\hellozynq\b2_sw\run_b3_speed_benchmark.ps1 -Mode live_eneuron -Samples 64 -CaptureLogits
```

两次运行必须绑定同一 bit/XSA、模型、预处理、输入 manifest 和样本顺序；dense/live 因编译模式不同允许使用不同 ELF，但必须分别记录并由合并器保存两份 ELF SHA-256。随后按 `sample_id`/输入 SHA-256 合并 dense/live 结果与外部真实标签。2026-09-14 已完成 1024 样本 dense/live 成对采集并由 `probe.log` 重建（`b3_accuracy_1024_board_report_v2.json`：agreement 1.0、golden 逐项 1024/1024、协议 2048/2048，`output_preservation=PASS`）。任务精度判 `MODEL_TASK_FIT_UNVERIFIED`；CRC 只用于原始帧校验，logits 结论必须来自数值解析与 golden 对照。
