# OF4c：单时钟端口与逐拍协议合同

状态：设计审核稿，尚未进入 RTL。

## 1. 范围

本稿把 OF1–OF6 V3 的 Python oracle 映射为单时钟、同步复位的集成端口。它只冻结可观察的端口与时序合同，不定义 AXI、网口、DMA、PS 侧协议，也不宣称硬件资源、时序或吞吐结果。

## 2. 时钟与复位

- 所有端口在同一个 `clk` 上采样。
- `rst` 为同步高有效复位；复位拍不接受命令，不产生响应。
- 复位后模型参数无效、active mask 为全开、epoch 为 0、结果槽为空。
- 复位不要求物理清零 BRAM；对外只保证 `model_valid=0` 和 `mask_valid=0`。

## 3. 端口表

| 端口 | 方向 | 宽度 | 合同 |
|---|---|---:|---|
| `cmd_valid/cmd_ready` | 流入 | 1/1 | 仅在二者同时为 1 的上升沿接受一条命令 |
| `cmd_payload` | 流入 | 128 | 命令字段固定，`opcode` 保留完整 8 bit |
| `rsp_valid/rsp_ready` | 流出 | 1/1 | 响应槽单深度；背压时 payload 和状态不变 |
| `rsp_payload` | 流出 | 128 | 与命令同构，错误由 `status` 表示 |
| `busy` | 输出 | 1 | 有运行样本、待提交 mask 或待发送响应时为 1 |
| `model_valid` | 输出 | 1 | 最近一次模型原子提交成功后为 1 |
| `mask_valid` | 输出 | 1 | active mask 已存在；复位后为 0，首次样本前可使用全开默认值 |
| `active_epoch` | 输出 | 32 | 当前已发布 mask 版本 |
| `last_commit_id` | 输出 | 16 | 最近一次已完成训练提交的 ID |
| `status_irq` | 输出 | 1 | 复位门控后的 `rsp_valid`，不携带额外语义 |

## 4. 命令地址与字段

`cmd_payload[7:0]` 为 opcode，`[15:8]` 为 flags，`[31:16]` 为命令序号，`[63:32]` 与 `[95:64]` 为参数，`[127:96]` 保留且必须为零。响应沿用同一布局，`[15:8]` 改为 status。

模型镜像地址为 0..633，mask 镜像地址为 0..18。非法地址必须正常握手并返回错误，不得把 `ready` 拉低形成死锁；RAM、计数器、epoch 和 valid 位均不得改变。

## 5. 逐拍优先级

同一拍只允许一次命令握手。优先级固定为：

1. 复位；
2. 响应槽清空（`rsp_valid && rsp_ready`）；
3. 已运行样本的完成/结果入槽；
4. 合法命令接受；
5. 非法命令接受并写入错误响应槽。

若响应槽未清空，`cmd_ready=0`。错误响应也占用完整单槽，直到握手消费；错误期间不得接受新命令。

## 6. 样本与门控版本

- 样本输入采用一条 `sample_valid/sample_ready` 流，payload 为 64 个 uint4 输入和 32-bit sample ID。
- 样本接受沿锁存 active mask 与 epoch；之后 mask 变化不得影响该样本。
- hidden 到 output 的路由固定增加一拍；不得让 hidden 当拍组合穿透到 output。
- 结果只有在 `result_valid && result_ready` 时对 Host 提交；背压期间 logits、prediction、epoch 和 sample ID 逐拍稳定。
- `MASK_COMMIT` 只产生 published 版本；下一样本首 beat 才交换 active。

## 7. 错误优先级与零副作用

错误检查顺序固定为：冻结状态、opcode/保留位、地址范围、状态组合、epoch/commit 单调性、payload 范围。任一检查失败立即生成一个错误响应；不得部分写入镜像、推进 word index、清除 snapshot 或改变 active epoch。

## 8. 审核门

进入 RTL 前必须完成：端口字段机器可读表、每条命令的逐拍轨迹、响应背压轨迹、非法命令零副作用测试、模型和 mask 的同拍仲裁测试，以及 Python oracle 与该表的独立交叉审计。本稿通过后才允许创建单时钟 RTL；仍不包含 Vivado 物理实现。

## 9. OF4e 组合补充

模型配置端口与 mask 端口共同受 runtime 的全局冻结合同约束。只要模型 staging 非空，或 runtime 正在运行、结果槽有背压、mask staging/pending 非空，进入或退出冻结都必须拒绝；完全 idle 且两端 staging 为空时才同步切换。OF4e 定向测试已通过 `45/45`（含既有回归）。

## 10. OF4f 同拍仲裁

单时钟实现不得在同一上升沿同时发布模型、交换 mask 和接受样本。固定顺序为：复位 > 响应消费 > 完成入槽 > 配置提交 > 样本首拍。若配置提交与样本首拍同时请求，样本 `ready` 必须为 0；提交只在该拍生效，样本下一拍重新握手并锁存新版本。若结果槽正在释放，仍须先完成响应消费，再允许下一条命令，避免旧结果与新配置交叉可见。

## 11. OF4g 边界回归

已提交模型处于 `committed`，不再属于 staging 占用，可以进入推理冻结；只有 `loading` 和 `complete` 阶段阻止冻结切换。冻结后模型仍可参与推理，但配置和动态清除继续拒绝。该边界修正由 `47/47` 相关回归覆盖。
