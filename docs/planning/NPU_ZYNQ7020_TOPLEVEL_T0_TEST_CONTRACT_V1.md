# XC7Z020 顶层 T0 测试合同 V1

状态：`APPROVED / T1_AUTHORIZED`

日期：2026-09-05

关联决策：`NPU_ZYNQ7020_TOPLEVEL_T0_DECISION_ADDENDUM_V1.md`

## 1. 目的

本合同把已批准的 A1-A7 转换为可执行的 T1/T2/T3 验收项。它只授权创建 T1 RTL；不把现有单时钟核心测试当作双时钟顶层证据。

## 2. 测试分层

| 层 | 被测对象 | 必须证明 |
|---|---|---|
| T1 | 纯 RTL wrapper、四条 FIFO、AXI shim | 字段映射、握手、固定 beat、fence、错误和复位 |
| T2 | T1 + 可变 host/npu 时钟 | CDC 不丢失、不重复、不乱序，背压和复位可重入边界正确 |
| T3 | XC7Z020 OOC | 四个 FIFO 与 wrapper 的实际资源、时序、route、DRC 可归因 |

## 3. A1 命令格式

- 合法向量覆盖 `0x1..0x9` 全部 opcode、合法/非法 flags、epoch、word index 和保留位。
- 采用当前 skeleton/PORT_TABLE 的高位 4-bit opcode；低位 8-bit Oracle V3 格式必须被明确拒绝或在测试中标记为不适用，不能静默解释成另一条命令。
- 每条命令只允许一次 FIFO 消费；非法 opcode/字段必须进入 128-bit 错误响应，不能改变模型、mask、epoch 或动态状态。

## 4. A2 framing 与 sideband

- 合法样本必须是 8 个 beat，合法结果必须是 10 个 beat；数据位级比较采用 V2 nibble 顺序。
- T1 将 `TLAST` 视为外层提示并忽略其值；在 beat 数仍完整的向量中改变 TLAST，不得改变核心结果。严格 TLAST/包完整性检查不属于本 wrapper，由外层 packetizer 验证。
- `TKEEP/TSTRB`、`TID/TDEST` 使用冻结 tie-off；T1 不在已进入核心的部分帧上承诺回滚或伪造 framing error。
- beat 间 `sample_id` 改变必须按 A2 sideband 合同处理：若选择逐 beat 检查，必须在首 beat 前缓存整帧；在 T0 未批准该额外缓存前，不得声称已有错误回滚能力。
- 合法 AXI tie-off：32-bit 流 `TKEEP/TSTRB=4'b1111`，128-bit 流 `TKEEP/TSTRB=16'hffff`，`TID/TDEST=0`。

## 5. A3 跨流 fence

- 在不同 host/npu 相位下并发提交 `MASK_COMMIT`、`STATE_CLEAR`、`FREEZE_SET` 与样本 FIFO，验证未完成配置不会被样本首 beat 使用。
- `SAMPLE_FENCE` 的 `fence_id` 固定为 `cmd_payload[31:0]`，成功响应类别固定为 `0xD`，错误使用 `0xE`；fence 前 `sample_ready=0` 且 sample FIFO 不得预填，成功后只授权一个 8-beat 窗口。
- fence 只有在此前命令已经核心握手、核心 `sample_ready=1`、没有 `result_valid/rsp_valid`、wrapper 没有开放中的样本窗口且模型/mask staging 事务已闭合时才成功；测试必须覆盖已发布 mask 等待首 beat 的状态，不能把 `runtime_idle=0` 误判为不可 fence。无 fence 的样本必须保持反压，不能按 FIFO 到达偶然放行。
- 结果必须用 `sample_id`/`mask_epoch` 与 fence 账本匹配；不能假定 response FIFO 与 result FIFO 全局有序。

## 6. A4 复位与 CDC

- 覆盖 host/npu 同频、整数频比、非整数频比和随机相位；两域 busy 任一为 1 时禁止新事务握手，但非复位期间已呈现的 valid/payload 必须稳定。
- 在命令、样本和结果的每个 beat 位置注入 reset，确认半事务按合同丢弃，复位后不泄漏旧 payload 或旧状态。
- 验证 `bridge_rst` 至少覆盖两个域各 4 个上升沿，域状态同步后连续 2 个本地沿才重新开放 ready。

## 7. A5 FIFO 与资源

- 四个 XPM 异步 FIFO 固定 depth=16、FWFT、read latency=0、CDC stages=2、`SIM_ASSERT_CHK=1`、memory type=`auto`；sample/result payload 分别 64/96 bit。
- 覆盖空读、满写、同时 push/pop、回绕、长背压和 reset-busy；检查 valid/ready 稳定性。
- T3 必须分别给出 command/response/sample/result FIFO 的 LUT、FF、BRAM、CDC synchronizer、WNS/TNS/WHS/THS、route 和 DRC；禁止沿用旧 `xc7a35tcpg236-1` 报告。

## 8. A6 状态、错误和中断

- 验证 Host 域看到的单 bit 状态来自同步摘要；`mask_epoch` 只从 result FIFO/fence 响应的原子 payload 获取，不做逐 bit CDC；error/IRQ sticky 和清除规则逐项验证。
- 验证 response FIFO 只报告错误、fence 确认和核心既有响应；result FIFO 只传结果及 sideband。
- 对每个错误注入向量检查 sticky/清除规则、IRQ 触发条件和 response 背压。

## 9. A7 物理基线

- T1 基线：`host_clk=npu_clk=100 MHz`、目标 `xc7z020clg400-1`。
- T2 使用至少三组非整数频比和三组随机相位；T3 使用 XC7Z020 专用 XDC 与真实时钟约束。
- 只有资源、setup/hold、route、DRC 全部通过，才允许把 wrapper 成本合并到 NPU 顶层报告；不报告板级吞吐或功耗。

## 10. 停止条件

任何一项 A1-A7 未获批准、字段/时序语义仍存在两种解释、或 T1/T2 任一负向测试没有确定结果时，保持 `T1_BLOCKED`，不得用“仿真跑通”替代合同裁定。
