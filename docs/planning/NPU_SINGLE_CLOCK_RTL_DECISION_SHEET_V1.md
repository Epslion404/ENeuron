# 单时钟 RTL 设计裁定表 V1

状态：`ADMIN_REVIEW_REQUIRED`。以下是 OF6 签核后、RTL 开工前的建议裁定，不代表已经冻结。

## 1. 样本输入流

**建议批准**：单一 `sample_valid/sample_ready` 流，固定 8 个 beat；每 beat 32 bit，低位优先打包 8 个 uint4；`beat_index=0..7`，只有 beat 7 允许 `last=1`。样本 ID 在首 beat 的独立 32-bit sideband 中传输，并在整个未握手期间保持稳定。

**硬件影响**：256-bit 输入缓存、3-bit beat 计数器、8 次握手；不需要可变长度解析器。

## 2. 结果输出流

**建议批准**：单一 `result_valid/result_ready` 流，固定 10 个 beat；每 beat 32 bit signed INT32 logit，`beat_index=0..9`，beat 9 带 `last=1`。sample ID、mask epoch 和 `model_epoch` 在首 beat sideband 锁存，整个结果槽背压期间保持不变。

**硬件影响**：320-bit 结果槽、4-bit beat 计数器；Host 仍在片外计算 prediction/abstain。

## 3. 配置流拓扑

**建议批准**：外部只有一条统一 128-bit `cmd_valid/cmd_ready` 和一条 128-bit `rsp_valid/rsp_ready`。内部可有模型、mask 两个状态机，但不得向 Host 暴露两套相互竞争的 ready。

**硬件影响**：一个命令解码器和一个响应槽；减少同拍双写和错误响应排序歧义。

## 4. 双提交同拍行为

**建议批准**：同拍出现 `MODEL_COMMIT`、`MASK_COMMIT` 和样本首 beat 时，优先级为 `MODEL_COMMIT > MASK_COMMIT > sample`。未获授权的输入保持 `valid` 和 payload，直到下一拍重新握手；不得丢弃或自动重排命令。

**硬件影响**：只需一个仲裁器；上游遵守标准 ready/valid 保持规则。

## 5. `mask_valid` 语义

**建议批准**：复位后 active mask 物理值为全开，`mask_valid=0` 仅表示“尚无用户发布版本”，不表示样本不可推理。样本执行总是读取 active bank；首次发布版本在样本首 beat 边界替换 active 后将 `mask_valid` 置 1。

**硬件影响**：不增加推理路径门控；该位只用于诊断和 Host 状态读取。

## 6. 未提交模型的样本行为

**建议批准**：`model_valid=0` 时 `sample_ready=0`，不接受样本，也不产生错误响应；完成模型提交后下一拍开放 `sample_ready`。这样保持 fail-closed 且避免部分样本事务。

**硬件影响**：一个 ready 门控，不需要回滚输入缓存。

## 7. runtime idle 定义

**建议批准**：`runtime_idle = !sample_partial && !sample_running && !result_valid && !model_commit_pending && !mask_commit_pending`。只有 `runtime_idle && model_state∈{EMPTY,COMMITTED} && mask_state=EMPTY` 才允许进入或退出冻结。

**硬件影响**：由现有状态位组合产生，不增加历史计数器；应对该组合加入断言。

## 8. 周期级验证门

**建议批准**：先冻结每个状态的 `ready/valid`、同步 RAM 读延迟和 `last` 生成规则，再写 RTL。每个命令至少有正常、背压、非法和 reset 四条逐拍轨迹；20 个随机 seed 做 Python/RTL bit-exact 对照后，才申请 Vivado OOC。

## 建议裁定顺序

优先裁定 1、2、3、4；它们决定顶层端口形状。随后裁定 5、6、7；最后确认 8 的验证门。全部批准后，第一份代码只能是端口/状态骨架和 RED 测试，不引入网口、DMA、训练调度器或板级约束。
