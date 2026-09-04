# 单时钟 RTL 设计审核前静态审计 V1

日期：2026-09-04

结论：`REVIEW_WITH_ACTIONS`。Python oracle 已签核，但设计稿仍有几处必须在 RTL 开工前明确的接口细节。它们不是当前 Python 回归失败，而是从函数级模型进入逐拍硬件时的规格缺口。推荐裁定见 `NPU_SINGLE_CLOCK_RTL_DECISION_SHEET_V1.md`，机器可读草案见 `npu_single_clock_contract_provisional.json`；该 JSON 明确标记为 provisional，不是冻结合同。

## 已对齐部分

| 项目 | 证据 | 结论 |
|---|---|---|
| 模型镜像 | 634 word，512/32/80/10，低字节优先 | 一致 |
| mask 镜像 | 19 word，LSB-first，592 bit | 一致 |
| 数值域 | uint4、INT8、两层 bias 安全窗口、hidden 饱和 | 一致 |
| 结果槽 | 不可变 logits、背压稳定、单槽 | 一致 |
| 版本切换 | mask 在样本首 beat 激活，epoch 随结果锁存 | 一致 |
| 复位/冻结 | hard reset 清事务；committed 模型可冻结并推理 | 一致 |
| 错误路径 | 非法配置握手后报错、同索引重试、零副作用 | 一致 |

## 必须补齐的规格项

1. **样本逐拍格式尚未冻结**：需要明确 8 个 beat 的 `beat_index`、`last`、低位优先打包、首 beat 的 mask 交换时刻，以及中途 `ready=0` 时 payload 是否保持。建议固定为 8×32 bit，beat 0..7 对应像素 0..63，只有 beat 7 带 `last=1`。
2. **结果逐拍格式尚未冻结**：需要明确 10 个 logit beat 的 `beat_index`、`last`、signed INT32 编码，以及 sample ID/epoch 是否只在首 beat 或独立元数据中出现。建议首 beat 携带 sample ID 和 epoch，其余 beat 只携带 logit 与索引。
3. **配置端口拓扑有歧义**：设计稿同时提到统一命令解码和模型/mask 独立状态机，但未说明外部是单一 `cmd_valid` 还是两条配置流。V1 应固定为一条统一命令流，避免两个 ready 在同拍互相覆盖；内部仍可保留两个状态机。
4. **同拍提交优先级需要可观测化**：`MODEL_COMMIT > MASK_COMMIT > sample` 已写入文字，但尚未定义两个 commit 同时请求时的响应、被延后的请求是否保持 valid，以及命令源是否必须保持 payload。应增加逐拍轨迹和一个负向测试。
5. **`mask_valid` 语义需澄清**：复位后 active mask 是全开，但 `mask_valid=0`；因此必须明确“全开默认 mask 可推理”和“mask_valid=0 的诊断含义”不能被 RTL 当作禁止推理条件。建议 `mask_valid` 表示“至少一次非默认 mask 已发布”，而样本执行依据 active bank。
6. **模型有效性与样本 ready 的关系需冻结**：已绑定模型端口且 `model_valid=0` 时，Python runtime 拒绝样本；顶层必须明确 `sample_ready=0` 还是接受后返回 `MODEL_INVALID`。按现有 fail-closed 合同，建议 `sample_ready=0` 仅用于未提交模型，避免接受后产生部分事务。
7. **配置与 runtime 空闲条件需有硬件信号**：`MODEL_COMMIT`/`MASK_COMMIT` 的 idle 检查不能只由 Python 方法调用顺序表达；需要 `runtime_idle`、`result_empty`、`sample_partial` 等内部条件的组合定义，并加入断言。
8. **周期合同尚未可综合验证**：设计稿暂不冻结精确吞吐是合理的，但必须先冻结每个状态的 `ready/valid` 和 RAM 读延迟，再开始 RTL；否则 bit-exact 结果无法定位到具体拍。

## 开工门槛

在管理员批准前，只允许补充上述接口字段、状态表、逐拍测试计划和 Python 事务轨迹；不得创建集成业务 RTL 或运行 Vivado。批准后第一片应是纯端口/状态骨架加 RED 测试，不得同时引入网口、DMA 或训练逻辑。
