# NPU + ENeuron Python Oracle 冻结审核

状态：`OF1-OF6_V3_APPROVED / OF1A_UINT4_CORE_GREEN / OF1B_FIXED_MODEL_GREEN / OF3_MASK_ORDER_COST_GREEN / OF4A_MODEL_WORD_MAP_GREEN / OF4B1_MASK_WORD_MAP_GREEN / OF4B2_COMMAND_PORT_GREEN / OF4B2B_RUNTIME_COMBINATION_GREEN / IMPLEMENTATION_IN_PROGRESS`

适用范围：传统 `64→32→10` INT8 NPU 与 ENeuron 四权重整组门控的 Python 参考模型。OF1-OF6 V3 已于 2026-09-04 获管理员批准；本文冻结进入单时钟 RTL 前必须明确的语义。完整 oracle 冻结和 RTL 设计审核完成前，不创建集成业务 RTL，不运行新的 Vivado。

## 1. 已证明的行为

当前参考模型与协议测试已覆盖：

- 旁路和全开门控结果逐字段一致；
- 全关门控保留 bias，并且不产生权重组读取或 MAC；
- Python 核心严格接受 `0..15` 的真正整数，权重严格为 INT8，bias 受两层安全窗口约束；隐藏层执行 ReLU/`0..127` 饱和，logits 平局时 abstain；
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
7. 原 V1 建议让正常模型依赖 INT32 回绕，并使用任意地址 mask/model 配置；反审计表明这会引入分类翻转风险和 19/634 bit 完整性 bitmap，并非最简硬件合同。

## 3. OF1-OF6 建议裁定

### OF1：数值合同

- 核心输入只接受 `0..15` 的 uint4；任意外部灰度值的裁剪属于 Host/输入适配器，不进入 NPU 核心数据路。
- Python 核心输入只接受 `type(value) is int` 且值域为 `0..15`；`bool`、浮点数、字符串、`None` 和其他可被 `int()` 隐式转换的对象均拒绝。输入校验必须先于任何乘加或 epoch 状态提交。
- 权重必须为 `type(value) is int` 且处于 signed INT8；Python 配置越界或类型不符一律拒绝，不调用 `int()`、不静默裁剪。RTL 权重配置字节的任意位型天然是合法 INT8。
- 为保证所有合法输入、权重和 mask 下都不发生 INT32 溢出，第一层 bias 只接受 `[-2147360768, 2147361727]`，第二层 bias 只接受 `[-2146963456, 2146967519]`。
- 非法 bias 在配置边界拒绝且零副作用。二补码低 32 位仍作为故障兜底定义，但任何已提交模型不得依赖回绕得到正常分类。
- 隐藏层完成累加后再执行 ReLU 和 `0..127` 饱和；输出层保留 signed INT32 logits。

推导：第一层 64 个 `uint4×INT8` 的总贡献范围为 `[-122880, 121920]`；第二层 32 个 `0..127×INT8` 的总贡献范围为 `[-520192, 516128]`。上述 bias 窗口保证数学整数结果与 INT32 结果相同，只排除整个 INT32 空间约 0.0057% 和 0.0241% 的极端值。

代价：配置路径复用两次 32-bit 常量比较；MAC/DSP 反馈路径不增加逐拍饱和比较器或 mux。逐拍饱和因非结合且依赖累加顺序，不采用。

### OF2：V1 参数域

- V1 只接受 `input=64`、`hidden=32`、`output=10`、`group=4`。
- 其他组合在构造时拒绝；参数化扩展留到 RTL V2，不让未测试配置进入当前声明范围。

### OF3：mask 位序与含义

- 第一层使用 `mask0[h*16+g]`，其中 `h=0..31`、`g=0..15`。
- 第二层使用 `mask1[o*8+g]`，其中 `o=0..9`、`g=0..7`。
- 每个 mask bit 控制连续四个权重全部读取或全部跳过；V1 不称为严格 `2:4`。
- 使用单 bit 和跨层混合 mask 的手算向量独立验证 logits、组读取数与 MAC 数。
- V1 不做数据相关零跳过。只要 mask bit 为 1，即使对应四个激活全为 0，也固定计 1 次组读取和 4 次 MAC；因此 `mac_count=4*group_reads`。只有 mask bit 为 0 才能跳过该组。

### OF4：单时钟流与配置边界

- 样本固定为 8 个 32-bit beat，每个 beat 按低位优先打包 8 个 uint4 像素；beat `k` 对应像素 `8k..8k+7`。输出固定为 10 个 32-bit signed logit beat，索引 `0..9`。
- 输入、输出和配置流均以 `valid && ready` 为唯一接受条件；样本首 beat 是 mask epoch 的原子切换边界。
- 配置命令或数据值是否合法不能反向组合控制 `ready`。非法配置命令/beat 仍完成一次握手并产生恰好一个错误响应，但不得写 RAM、推进顺序计数器或改变 staging/model 状态；Host 可在同一隐式索引重试。错误响应在下游背压期间保持稳定，未被接受前不再接受下一配置事务。后续端口表必须给出错误响应通道和稳定错误码，不能让非法 `valid` 造成永久背压；下表中的“拒绝”均采用这一握手后报错、零副作用语义。
- 输出阻塞期间，logit、index、epoch 和结束标志必须稳定；结果退出前不接受下一样本。
- V1 模型只在 hard reset 后顺序装载一次，共 634 个 32-bit word：第一层权重 512 word、第一层 bias 32 word、第二层权重 80 word、第二层 bias 10 word；每个权重 word 低字节优先打包 4 个 INT8。
- 模型 word 的线性映射固定如下，byte `j` 始终对应 `data[8*j +: 8]`：
  - `word=16*h+g`（`0..511`）的 byte `j` 为 `w0[h][4*g+j]`；
  - `word=512+h`（`512..543`）为 `bias0[h]` 的完整 32-bit 二补码；
  - `word=544+8*o+g`（`544..623`）的 byte `j` 为 `w1[o][4*g+j]`；
  - `word=624+o`（`624..633`）为 `bias1[o]` 的完整 32-bit 二补码。
- 顺序计数到 634 且全部 bias 合法后才允许 `MODEL_COMMIT`；提交后模型配置口锁定，避免复制第二份约 20 Kbit 模型 RAM。
- mask 使用 active/staging 两个 592-bit bank。`MASK_BEGIN(epoch)` 后按固定顺序接收 19 个 word，再由 `MASK_COMMIT` 把 staging 标为 published pending；published 仅在后续样本首 beat 接受时翻转为 active。
- canonical packing：word0.bit0=`mask0[0]`，word15.bit31=`mask0[511]`，word16.bit0=`mask1[0]`，word18.bit15=`mask1[79]`；word18[31:16] 必须为 0，否则该 beat 拒绝且零副作用。
- mask word 索引使用 5-bit 顺序计数器，不接收显式地址，因此不存在重复、漏写或乱序歧义。`MASK_ABORT` 只在 loading/complete、尚未 published 时清除 staging 计数。
- staging bank 的命令矩阵固定为：

| 当前状态 | `MASK_BEGIN` | mask data | `MASK_COMMIT` | `MASK_ABORT` |
|---|---|---|---|---|
| empty | 接受并进入 loading | 拒绝 | 拒绝 | 拒绝 |
| loading | 拒绝 | 接受；第 19 个合法 word 后进入 complete | 拒绝 | 接受并回到 empty |
| complete | 拒绝 | 拒绝 | 合法 epoch 时接受并进入 published | 接受并回到 empty |
| published | 拒绝 | 拒绝 | 拒绝 | 拒绝 |

- 部分样本输入中、当前样本计算中或结果背压中，只要未冻结且 staging 命令矩阵允许，仍可装载并发布下一版本 mask；它绝不能影响已由首 beat 锁存 epoch 的样本。后续样本首 beat 接受时以 active/staging 指针交换采用 published bank，不复制 592 bit，并把旧 active bank 变为 empty staging。
- `MASK_COMMIT` 与样本首 beat 同时有效时固定由 commit 获得优先级：该周期样本 `ready=0`，commit 握手完成后，样本只能在后续边沿接受并采用新 epoch。
- `prediction/abstain` 由 Host 根据 10 个 logits 的唯一最大值计算。Python 可以保留这两个派生诊断字段，但它们不属于 V1 RTL bit-exact 输出端口，也不能作为输出流验收的替代证据。

### OF5：epoch、冻结、清除与复位

- epoch 为 32 bit；`MASK_COMMIT` 只接受 `active_epoch+1 mod 2^32`。
- epoch 只是 modulo tag，不宣称跨 `2^32` 次提交仍全局唯一；输出结果始终携带其样本接受时锁存的 epoch。
- 推理冻结只允许在完全 idle、没有部分输入样本、没有运行中样本、没有待消费结果且 staging bank 为 empty 时切换。运行中、部分输入或结果背压期间，进入或退出冻结均拒绝。
- frozen 状态下拒绝模型配置、`MASK_BEGIN`、mask data、`MASK_COMMIT`、`MASK_ABORT` 和 `STATE_CLEAR`；样本输入与结果输出仍按正常背压合同工作。
- `STATE_CLEAR` 仅在 idle、无待消费结果且未冻结时接受；它只清运行统计，保留 active mask、epoch、模型以及 mask loading/complete/published 状态，不承担事务恢复或 mask abort。
- hard reset 是唯一事务 abort：丢弃部分样本、运行结果、mask staging/pending，active mask 恢复全开、epoch 恢复 0、冻结关闭、模型置 invalid。
- hard reset 不承诺物理清零模型 RAM；旧内容视为不可用。必须重新顺序装载完整 634 word 并 `MODEL_COMMIT` 后才能推理。

### OF6：冻结验收

- `logits` 改为不可变 tuple，背压稳定性按值与对象内容共同检查；`prediction/abstain` 只验证为 logits 的派生诊断。
- 增加两层 bias 安全范围四个边界及其 ±1、权重越界、核心 uint4 类型/范围拒绝、固定参数拒绝、单 bit/mixed mask、负权重、负 bias、open+全零固定计数和局部最高值并列测试。
- 增加 634-word 精确线性映射、非法配置握手后同索引重试、mask 保留位、19-word 长度、四状态命令矩阵、运行中装载下一 mask、abort、commit 优先于首 beat、partial staging→freeze、结果背压期间 freeze 切换拒绝、epoch `0xffffffff→0`、reset 后旧 RAM 不可推理和完整 model commit 测试。
- 形成端口表、状态转移表和逐拍测试计划后，才把 Python oracle 标记为冻结并提交 RTL 设计审核。

## 4. V3 逻辑成本边界

- 输入样本缓存为 256 bit，单槽输出 logits 为 320 bit；两者可先映射为寄存器或小型分布式 RAM，物理选择留给后续综合。
- active/staging mask 共 1184 bit；19-word 顺序流只需 5-bit word counter 和少量状态位，不需要 19-bit written bitmap。
- 模型配置共 634 word；顺序流只需 10-bit word counter，不需要 634-bit 完整性 bitmap，也不需要双份模型 RAM。
- bias 合法性检查只位于低频配置路径；正常 MAC、权重读取、门控和输出路径不增加饱和逻辑。
- 以上是逻辑规模推导，不是 LUT/FF/BRAM/DSP 或时序结果；OF1-OF6 和 RTL 设计获批前不运行 Vivado。

## 5. 当前允许动作

- OF1a 已完成严格 uint4 核心输入与非法样本零副作用；OF1b 已完成严格 INT8 权重、两层安全 bias、固定 V1 参数、原子模型 reload 和不可变 logits。
- OF3 已用内部单 bit、两层首尾 mixed mask 和 open+全零向量冻结位序与固定工作量账本；现实现本已符合，因此只增加测试证据、不修改业务代码。
- OF4a 已冻结完整 634-word uint32 镜像、512/32/80/10 段映射、低字节优先 signed 解码和原子载入；它是完整镜像 API，不冒充逐拍配置状态机。
- OF4b1 已冻结完整 19-word uint32 mask 镜像：word0..15 对应 `mask0[0..511]`，word16..18 的低 80 bit 对应 `mask1[0..79]`，统一采用 LSB-first；`word18[31:16]` 为保留位且必须为零。解码结果为独立不可变 tuple，定向测试 2/2、完整 oracle 27/27，并经独立审计 PASS。
- OF4b2a 已实现最小 Python 命令端口：四态 staging、单槽错误响应、非法配置零副作用、同索引重试和样本边界激活；当前相关测试 6/6 通过，独立审计和完整状态矩阵仍待完成。
- OF4b2 已完成独立审计：7/7 定向测试、完整 oracle 34/34 通过；BEGIN/COMMIT 均要求 `active_epoch+1 mod 2^32`，覆盖 `0xffffffff→0` 回绕，错误消费拍不接受新命令。端口级实现不替代上层 runtime 的全局 idle/freeze 检查。
- OF4b2b 已完成状态矩阵与 runtime 组合冻结：状态矩阵 9/9、runtime 组合 5/5、完整 oracle 41/41。`NpuEpochRuntime.bind_mask_port()` 在运行中、结果背压、runtime pending 或端口 staging 非空时拒绝 freeze，完全 idle 时同步两端；frozen 仍允许推理但拒绝配置和动态清除。状态矩阵为基于既有实现的回归补强，不伪称 RED。
- 后续按第 6 节顺序，以独立 RED→GREEN 切片实现已批准的 19-word mask 配置、错误响应、状态组合和逐拍协议合同。
- 完整 oracle 冻结并通过独立审计后，才提交单时钟 RTL 设计稿供管理员审核；审核通过前不创建集成业务 RTL、不运行 Vivado，也不宣称集成吞吐、资源、功耗或准确率收益。

## 6. 批准后的执行顺序

1. OF1a 只提交核心 uint4 类型/范围 fail-closed 与非法样本零副作用测试，再做最小实现；本切片不触碰 bias、mask、协议或 RTL。
2. 提交 INT8 权重、安全 bias、固定参数和不可变结果 RED 测试，再完成最小参考模型修正。
3. 提交 mask 位序手算向量、open+全零计数和状态组合矩阵。
4. 冻结单时钟端口表、634/19-word 地址表、错误响应、状态转移表和逐拍测试计划。
5. 独立审计通过后，提交 RTL 设计稿供管理员审核。
