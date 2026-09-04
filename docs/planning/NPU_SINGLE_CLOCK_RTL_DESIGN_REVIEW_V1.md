# 传统 NPU + ENeuron 单时钟 RTL 设计审核 V1

状态：`REVIEW_REQUIRED`。本文仅为设计稿，尚未创建集成业务 RTL，也未运行 Vivado。

## 目标与边界

实现一个固定 `64→32→10` INT8 推理核，按四权重组读取，并由 ENeuron 生成的 592-bit mask 控制整组是否执行。V1 只负责片上单时钟计算、模型配置、mask 双 bank 和结果流；网口、DMA、AXI、PS 软件、训练算法与 mask 生成器均留在边界外。

## 模块划分

1. `npu_eneuron_top`：唯一外部接口、命令解码、响应单槽和全局仲裁。
2. `npu_model_store`：634-word 顺序配置，提交后锁定；模型 RAM 不复制。
3. `npu_mask_store`：两个 592-bit bank，active/staging 指针交换，19-word 顺序配置。
4. `npu_sample_buffer`：8 个 32-bit beat，低位优先解包 64 个 uint4 输入。
5. `npu_group_engine`：复用 NP7 的四 lane 加法结构，每次处理一个四权重组；V1 不复用 NP7 的 12-bit 饱和累加器，而使用 32-bit 累加寄存器以符合 OF1。
6. `npu_scheduler`：依次执行 32×16 个第一层组和 10×8 个第二层组，保存 32 个 uint7 hidden 值。
7. `npu_result_buffer`：保存 10 个 signed INT32 logits、sample ID 和 active epoch，输出背压期间稳定。

## 存储规划

- 第一层权重：2048 byte；第一层 bias：128 byte。
- 第二层权重：320 byte；第二层 bias：40 byte。
- 模型合计 2536 byte，按 634×32 bit 统一线性空间配置。
- mask 双 bank：1184 bit。
- 输入缓存：256 bit；hidden：224 bit；输出缓存：320 bit。
- 具体映射为 BRAM、LUTRAM 或寄存器由综合结果决定；设计稿不预先宣称资源数量。

## 状态机

顶层状态保持小而明确：`RESET`、`IDLE`、`LOAD_SAMPLE`、`L0_READ`、`L0_ACC`、`L1_READ`、`L1_ACC`、`PUBLISH_RESULT`、`HOLD_RESULT`。模型和 mask 配置各有独立小状态机，但所有副作用由顶层单拍仲裁统一授权。

每组采用同步 RAM 一拍读取，再在下一拍执行四个 `uint4×int8` 或 `uint7×int8` 乘加。第一层每个输出完成 16 组后执行 ReLU 和 `0..127` 饱和；第二层每个输出完成 8 组后直接保留 signed INT32。

## 仲裁与原子性

- 全局优先级：同步复位 > 响应消费 > 结果入槽 > 配置提交 > 样本首 beat > 普通配置 data。
- `MODEL_COMMIT` 和 `MASK_COMMIT` 不能同拍生效；模型提交优先。
- `MASK_COMMIT` 与样本首 beat 冲突时，样本 `ready=0`，下一拍采用新 epoch。
- 样本首 beat 接受沿锁存 active bank 指针和 epoch，运行期间 published mask 不得影响当前样本。
- 结果槽未消费时不接受下一样本；错误响应也占同一个响应槽。
- 非法配置仍握手并返回错误，RAM 写使能、索引和版本状态保持不变。

## 复位与冻结

同步复位丢弃部分样本、运行结果、模型 staging、mask staging/published 和错误响应；active mask 恢复全开，epoch=0，`model_valid=0`。模型 RAM 旧位无需物理清零，但不可读取为有效模型。

冻结只允许在 runtime idle、响应槽空、模型非 staging、mask staging 为空时切换。冻结后允许推理，拒绝模型/mask 配置和 `STATE_CLEAR`。

## 周期与吞吐声明

V1 采用一个四 lane 共享引擎。忽略配置和背压时，每样本至少处理 592 个权重组槽位，其中关闭组仍由调度器跳过，不发 RAM 读和 lane 操作。实际周期取决于开放组数量、同步 RAM 延迟和层间控制；在 RTL 协同仿真前不冻结精确吞吐，在 Vivado 前不声明频率。

## 验证顺序

1. 端口/状态 RED 测试与 Icarus elaboration。
2. 模型 634-word、mask 19-word、8-beat 输入、10-beat 输出的逐拍定向协同仿真。
3. Python oracle 与 RTL 逐样本 bit-exact，包括负权重、bias 边界、全开/全关/mixed mask、epoch 回绕和结果背压。
4. 非法命令零副作用、同拍仲裁、hard reset 和冻结负向测试。
5. 至少 20 seeds 的随机事务协同仿真与机器摘要。
6. 独立审计通过后再批准 Vivado OOC；不得用 Icarus 代替 Vivado 物理结论。

## 待管理员裁定

1. 批准一个四 lane 共享引擎作为 V1，优先控制资源而非单样本延迟。
2. 批准模型 RAM 单份、提交后锁定，重装必须 hard reset。
3. 批准模型提交优先于 mask 提交，mask 提交优先于样本首 beat。
4. 批准 hidden 缓存使用 32×7 bit，输出缓存使用 10×32 bit。
5. 批准精确周期在 RTL 协同仿真阶段冻结，不在设计稿中预设。
6. 批准先用 Icarus 完成功能闭环，再单独申请 Vivado OOC 门。
