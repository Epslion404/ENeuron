# NPU + ENeuron Python Oracle 冻结审核

状态：`OF1-OF6_REVIEW_REQUIRED`

适用范围：传统 `64→32→10` INT8 NPU 与 ENeuron 四权重整组门控的 Python 参考模型。本文只冻结进入单时钟 RTL 前必须明确的语义；未批准前不创建集成业务 RTL，不运行新的 Vivado。

## 1. 已证明的行为

当前参考模型与协议测试已覆盖：

- 旁路和全开门控结果逐字段一致；
- 全关门控保留 bias，并且不产生权重组读取或 MAC；
- 4 bit 输入裁剪、隐藏层 ReLU/`0..127` 饱和与 logits 平局 abstain；
- active/pending epoch 在样本接受边界切换；
- 结果背压阻止下一样本，非法样本无状态副作用；
- `STATE_CLEAR` 保留 active epoch，推理冻结拒绝 mask 更新和动态清除；
- 连续全关/全开/全关版本不会混用 mask；pending 单槽满时拒绝覆盖。

这些测试证明了当前函数级模型的若干边界，但不足以冻结逐位数值和 RTL 接口。

## 2. 冻结阻断证据

1. 当前累加使用 Python 无限精度整数。bias 未限制为 INT32，也未定义溢出策略；构造接近上界的 bias 后，输出可超过 `2^31-1`。
2. `NpuConfig` 未限制正数和整除关系。非四整除尺寸会在推理循环中触发 `IndexError`，而不是在配置边界 fail-closed。
3. mask 位序只隐含在实现中。全开、全关和整版切换不能发现层号、输出通道或组号接错。
4. 当前协议把一次推理压缩为函数调用，尚未冻结输入/输出流、配置地址、mask 分段写入、复位和 epoch 回绕合同。
5. `InferenceResult` 虽为 frozen dataclass，但 `logits` 仍是可变 list；调用者可以在结果背压期间修改内容。
6. pending mask、推理冻结、动态清除和 hard reset 的组合转移尚未完整定义。

## 3. OF1-OF6 建议裁定

### OF1：数值合同

- 权重必须处于 signed INT8，bias 必须处于 signed INT32；越界配置一律拒绝，不静默裁剪。
- 每次乘加按 signed INT32 二进制补码回绕，确保 Python 与普通 32-bit 硬件加法逐位一致。
- 隐藏层完成累加后再执行 ReLU 和 `0..127` 饱和；输出层保留 signed INT32 logits。

代价：需要显式的 INT32 归一化函数和边界测试，但不增加饱和累加器硬件。

### OF2：V1 参数域

- V1 只接受 `input=64`、`hidden=32`、`output=10`、`group=4`。
- 其他组合在构造时拒绝；参数化扩展留到 RTL V2，不让未测试配置进入当前声明范围。

### OF3：mask 位序与含义

- 第一层使用 `mask0[h*16+g]`，其中 `h=0..31`、`g=0..15`。
- 第二层使用 `mask1[o*8+g]`，其中 `o=0..9`、`g=0..7`。
- 每个 mask bit 控制连续四个权重全部读取或全部跳过；V1 不称为严格 `2:4`。
- 使用单 bit 和跨层混合 mask 的手算向量独立验证 logits、组读取数与 MAC 数。

### OF4：单时钟流与配置边界

- 样本输入按索引 `0..63` 接受，输出 logits 按索引 `0..9` 发出；所有流使用 `valid/ready`。
- 输出阻塞期间，logit、index、epoch 和结束标志必须稳定；结果退出前不接受下一样本。
- 592 个 pending mask bit 分为 19 个 32-bit word：第一层 16 word，第二层 3 word，最后一 word 仅低 16 bit 有效。
- 19 个 word 全部写过后才允许 `MASK_COMMIT`；已发布版本仅在下一样本首元素接受边界切换。
- 权重和 bias 使用独立配置地址空间，完成写入后由 `MODEL_COMMIT` 发布。

### OF5：epoch、冻结、清除与复位

- epoch 为 32 bit；`MASK_COMMIT` 只接受 `active_epoch+1 mod 2^32`。
- pending 已发布但尚未生效时，拒绝进入推理冻结，避免隐藏的未来状态变化。
- `STATE_CLEAR` 清动态事务计数，保留 active/pending mask、epoch、模型配置和冻结状态。
- hard reset 丢弃运行事务、结果和 pending，active mask 恢复全开、epoch 恢复 0、冻结关闭；模型必须重新 `MODEL_COMMIT` 后才能推理。

### OF6：冻结验收

- `logits` 改为不可变 tuple，背压稳定性按值与对象内容共同检查。
- 增加 INT32 正负溢出、权重/bias 越界、固定参数拒绝、单 bit/mixed mask、负权重、负 bias、局部最高值并列和组合状态矩阵。
- 形成端口表、状态转移表和逐拍测试计划后，才把 Python oracle 标记为冻结并提交 RTL 设计审核。

## 4. 当前允许动作

- 可以提交不依赖 OF1-OF6 的既有最坏情况测试、审计文档和知识库更新。
- 可以继续编写会在当前实现上失败的 RED 测试，但不能先选择溢出、复位或协议语义来修改业务实现。
- OF1-OF6 未批准前，不创建集成业务 RTL，不运行 Vivado，不宣称集成吞吐、资源、功耗或准确率收益。

## 5. 批准后的执行顺序

1. 先提交数值、参数和不可变结果 RED 测试。
2. 实现最小参考模型修正并通过定向测试。
3. 提交 mask 位序手算向量和状态组合矩阵。
4. 冻结单时钟端口表、地址表、状态转移表和逐拍测试计划。
5. 独立审计通过后，提交 RTL 设计稿供管理员审核。
