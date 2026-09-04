# 单时钟 RTL 端口字段表 V1

状态：`IMPLEMENTATION_SUBCONTRACT`。本表由已批准的 V2 八项裁定派生，只补齐命令/响应字段，不改变 8/10 beat、单命令流、mask epoch 或 idle 语义。

## 外部端口

| 端口 | 宽度 | 语义 |
|---|---:|---|
| `cmd_payload` | 128 | 配置命令；字段见下表 |
| `cmd_valid/cmd_ready` | 1/1 | 单一配置命令流；只有握手沿产生副作用 |
| `rsp_payload` | 128 | 错误响应槽；成功命令不产生响应 |
| `rsp_valid/rsp_ready` | 1/1 | 响应槽背压期间 payload 和 valid 保持 |
| `sample_data` | 32 | 每拍 8 个 uint4，低 nibble 先到 |
| `sample_id` | 32 | 仅首 beat 采样 |
| `sample_valid/sample_ready` | 1/1 | 固定 8 beat；命令有效时首拍让路给配置 |
| `result_data` | 32 | signed INT32 beat；骨架阶段为零占位 |
| `result_sample_id` | 32 | 结果槽锁存的 sample ID |
| `result_mask_epoch` | 32 | 结果槽锁存的 active mask epoch |
| `result_valid/result_ready` | 1/1 | 固定 10 beat；背压期间全部结果字段稳定 |
| `runtime_idle` | 1 | 严格空闲条件的公开摘要 |
| `model_valid` | 1 | 已完成 `MODEL_COMMIT` 才为 1 |
| `mask_valid` | 1 | 至少一个用户 mask 已在样本首 beat 激活；复位后的默认全开 mask 保持 0 |

## 命令字段

| 位段 | 含义 |
|---|---|
| `[127:124]` | `opcode` |
| `[123:120]` | flags/reserved，当前必须为 0 |
| `[119:88]` | mask epoch（模型命令忽略） |
| `[87:32]` | reserved，当前必须为 0 |
| `[31:0]` | word payload；`MODEL_DATA`/`MASK_DATA` 使用 |

当前 opcode：

| 值 | 名称 |
|---:|---|
| `0x1` | `MODEL_BEGIN` |
| `0x2` | `MODEL_DATA` |
| `0x3` | `MODEL_COMMIT` |
| `0x4` | `MASK_BEGIN` |
| `0x5` | `MASK_DATA` |
| `0x6` | `MASK_COMMIT` |
| `0x7` | `MASK_ABORT` |
| `0x8` | `STATE_CLEAR` |
| `0x9` | `FREEZE_SET`（`flags[0]` 为目标值） |

## 响应字段

| 位段 | 含义 |
|---|---|
| `[127:124]` | 响应类别；`0xE` 表示错误 |
| `[123:120]` | 错误码 |
| `[119:116]` | 被拒绝命令 opcode 回显 |
| `[115:112]` | 产生错误时的内部状态 |
| `[111:80]` | 内部隐式 word index，低 10 位有效 |
| `[79:48]` | 当前 epoch；模型错误时为 0 |
| `[47:0]` | 保留，必须为 0 |

当前骨架已实现 `MODEL_BEGIN/DATA/COMMIT`、`MASK_BEGIN/DATA/COMMIT` 和通用错误槽。mask 使用 19-word staging，`MASK_COMMIT` 只形成 published 版本；下一样本首 beat 才激活 epoch 并置 `mask_valid=1`。`MASK_ABORT`、clear、freeze 和真实门控计算仍在后续垂直切片接入。
