# 单时钟 RTL 设计裁定表 V2

状态：`APPROVED_BY_ADMIN / RTL_RANDOM_GATE_GREEN / VIVADO_OOC_100MHZ_PASS`。管理员已于 2026-09-04 批准以下 8 项裁定；V2 单时钟 RTL 已完成实现和 OOC。实现提交为 `f744bff2bdde68e138a7b2b348ce103bec1ab469`，板级验证仍后置。

当前物理结果：`2126 LUT / 1916 FF / 0 BRAM / 4 DSP48E1`，100 MHz post-route `WNS=+0.060 ns / TNS=0 / WHS=+0.040 ns / THS=0`，setup/hold/route/DRC 零失败。详细报告见 `artifacts/results/npu_single_clock_ooc_manifest.json`。

## 1. 样本输入流

建议采用固定长度流：每个样本恰好接受 8 个 32-bit beat，每拍低位优先打包 8 个 uint4，像素映射为 `pixel[8k+j] = beat_data[4*j +: 4]`。beat 序号由 DUT 内部 3-bit 计数器产生，不作为外部字段；不使用可选 `last`，第 8 次握手自动结束样本。`sample_id[31:0]` 只在首 beat 采样并锁存。

这种方式把 framing 错误排除在 V1 可恢复输入之外：上游必须保证固定 8 beat；复位可随时丢弃部分样本。这样 mask 在首 beat 切换不会与后续 `last` 错误发生回滚冲突。

## 2. 结果输出流

固定输出 10 个 32-bit signed INT32 beat，内部 4-bit 计数器自动结束，不额外传输 `last`。结果槽保存 320-bit logits，另存 32-bit sample ID 和 32-bit mask epoch；这两个 sideband 在 10 拍输出期间保持稳定。V1 不引入 `model_epoch`，因为模型只在 hard reset 后重新装载，当前 oracle 没有模型版本计数。

## 3. 配置流拓扑

外部只有一条 128-bit `cmd_valid/cmd_ready` 和一条 128-bit `rsp_valid/rsp_ready`。模型与 mask 在内部使用各自状态机，但所有命令先经过同一个解码器和单槽响应仲裁。必须继续补齐 opcode、成功响应、错误来源和序号字段表。

## 4. 配置与样本同拍行为

统一命令流下，`MODEL_COMMIT` 与 `MASK_COMMIT` 不可能由 Host 同拍到达，不能伪造二者之间的优先级。V1 只定义：当一条配置命令握手请求与样本首 beat 同拍出现时，配置命令优先，样本 `ready=0`；上游保持样本 `valid/payload`，下一拍重试。若未来增加内部多源请求，必须另立裁定。

## 5. `mask_valid` 语义

复位后 active mask 为全开、`mask_valid=0`；该位只表示“尚无用户发布版本”，不阻止推理。固定 8-beat 样本的首 beat 接受沿原子锁存 active mask 和 epoch；之后 published mask 不能影响当前样本。协议违规由上游保证，不在 V1 设计可恢复错误范围内。

## 6. 未提交模型

`model_valid=0` 时 `sample_ready=0`，不接受样本、不启动计算、不产生半成品错误响应。`MODEL_COMMIT` 成功的时钟沿完成模型发布，下一周期才允许样本握手；`sample_valid` 持续为高时，Host 必须遵守 ready/valid 保持规则。

## 7. `runtime_idle` 定义

建议定义为：没有部分输入、没有运行中计算、没有部分结果输出、结果槽为空、没有待消费错误响应、统一命令/响应槽为空、模型不在 loading/complete、mask 不在 loading/complete/published，且当前周期没有更高优先级握手。freeze、STATE_CLEAR 和 commit 的安全判断在同拍仲裁之后进行。

## 8. 验证门

先冻结每个状态的 ready/valid 和同步 RAM 延迟，再写 RTL。至少使用 20 个固定 seed、每个 100 个样本（不少于 2000 个），并逐拍覆盖：全开/全关/mixed mask、负权重、bias 边界、epoch 回绕、错误同索引重试、reset、背压、freeze/clear、统一响应路由和负向 mutation。绑定确切提交 HEAD 与 Vivado 版本后，才允许 OOC。

## V1 到 V2 的关键修正

- 删除未在 OF6 oracle 中定义的 `model_epoch`。
- 删除统一命令流中不可能同时出现的 `MODEL_COMMIT > MASK_COMMIT` 假想竞争。
- 用固定 8/10 beat 计数消除 `last` 早到/晚到的回滚歧义。
- 把 pending error、partial output、FIFO 占用和同拍握手纳入 idle。
- 将验证门从“20 个随机 seed”改为 20 个固定 seed × 100 个样本。
