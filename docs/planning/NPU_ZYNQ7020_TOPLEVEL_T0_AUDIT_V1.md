# XC7Z020 顶层 T0 审计与待裁定项 V1

状态：`AUDIT / ADMIN_REVIEW_REQUIRED / T1_BLOCKED`

日期：2026-09-05

关联文档：

- `docs/planning/NPU_ZYNQ7020_TOPLEVEL_DECISION_SHEET_V1.md`
- `docs/planning/NPU_ZYNQ7020_TOPLEVEL_INTEGRATION_V1.md`
- `docs/planning/NPU_SINGLE_CLOCK_RTL_PORT_TABLE_V1.md`
- `docs/planning/NPU_SINGLE_CLOCK_RTL_DECISION_SHEET_V2.md`
- `docs/planning/NPU_ORACLE_SINGLE_CLOCK_CONTRACT_V3.md`
- `docs/planning/NPU_ZYNQ7020_TOPLEVEL_T0_DECISION_ADDENDUM_V1.md`

## 1. 审计结论

方案 A 的总体方向仍然合理，但当前 T0 文档还不能唯一指导 T1 RTL。四条独立 FIFO 只解决各流跨时钟传输，不自动解决跨流顺序、配置生效边界、复位汇合和命令字段解释。因此当前状态保持 `P15_T0_REVIEW_REQUIRED / NO_RTL_AUTHORIZATION`。

## 2. 必须先冻结的高优先级问题

### 2.1 命令字段布局冲突

`npu_eneuron_single_clock_skeleton.sv` 和 `NPU_SINGLE_CLOCK_RTL_PORT_TABLE_V1.md` 使用 `[127:124]` 的 4-bit opcode、`[119:88]` 的 epoch 和 `[31:0]` 的 word；`NPU_ORACLE_SINGLE_CLOCK_CONTRACT_V3.md` 却规定 `[7:0]` 的 8-bit opcode、`[15:8]` flags、`[31:16]` txn_id 和两个 32-bit 参数。

T0 必须明确选择“以当前 skeleton/PORT_TABLE 为线级合同”或先更新 RTL 与 Oracle。T1 不得自行猜测字段映射，也不得把两套格式同时支持。

### 2.2 V1/V2 framing 与字段冲突

历史 V1 裁定曾要求内部 `last` 和 `model_epoch`；已签核的 V2 则明确由 8/10 beat 计数决定边界并删除这些内部字段。P15 的 AXI `TLAST` 只能作为外层提示，不能重新接入核心 `last` 或把旧 `model_epoch` 映射进 V2 端口。T0 必须点名 V2/PORT_TABLE 为唯一权威，V1 和 Oracle V3 的冲突字段只能作为历史资料。

### 2.3 命令与样本的跨 FIFO 顺序

命令、样本分别进入独立 FIFO 后，不能仅靠各自 FIFO 的有序性证明 `MASK_COMMIT`、`STATE_CLEAR`、`FREEZE_SET` 已在样本首 beat 前生效。当前核心在 NPU 时钟域接收样本首 beat 时才绑定 active mask，且成功配置命令没有统一成功 response 作为 fence。

T0 必须冻结显式 fence/状态完成信号，或冻结 wrapper 的样本准入规则；同时定义“首 beat”以 NPU 核心实际握手沿为准，而不是 Host 写入 FIFO 的时间。

### 2.4 reset-busy 与 ready 的跨域汇合

“任一域 reset-busy 时四条流 ready=0”需要明确实现为两侧 busy 的同步汇合，而不是直接组合读取远端 XPM 状态。现有 Host Bridge 的 ready 只门控本地 FIFO 方向，不能直接作为新四流的完整合同。

T0 必须冻结：两域 busy/domain-up 的同步器、ready 重新开放条件、复位释放最小时序，以及半包/半结果的丢弃语义。

### 2.5 AXI 帧与 sideband 错误语义

当前合同规定 8/10 beat 由内部计数决定，但没有定义 TLAST 早到、晚到或缺失时的行为，也没有冻结 `TKEEP/TSTRB/TID/TDEST` 的 tie-off。核心只在首 beat 采样 `sample_id`，后续 beat 改变不会自动报错。

T0 必须选择严格帧检查或明确忽略 TLAST/后续 sideband，并规定错误如何进入 128-bit response 流；32-bit 样本数据的 nibble 顺序也必须引用 V2 的 `pixel[8*k+j]=beat_data[4*j +: 4]` 规则。

### 2.6 FIFO 参数和资源归因

当前只冻结了逻辑流宽度：命令/响应 128 bit、样本完整 payload 64 bit、结果完整 payload 96 bit。深度、`READ_MODE`、`FIFO_MEMORY_TYPE`、FWFT 延迟和 reset-busy 参数还未成为 T0 机器可读合同。

T0 至少需要冻结四个 FIFO 的 depth、完整 payload 宽度、读模式和复位参数；T1/T3 仍必须以 Vivado 报告实际归因，不能用理论 BRAM 数代替实测。

### 2.7 器件与时钟约束边界

P15 目标是 `xc7z020clg400-1`，但旧 Host Bridge OOC 计划和 runner 使用 `xc7a35tcpg236-1`。两者不能互相替代资源或时序证据。T3 必须重新冻结 XC7Z020 的器件、封装速度级、Host/NPU 时钟频率和 XDC；旧 Artix-7 结果只能作为历史参考。

## 3. 次级但必须记录的边界

- 成功配置命令无响应时，Host 如何知道模型或 mask 已完成，必须由 fence/status 合同补足。
- `model_valid`、`mask_valid`、`infer_frozen`、`mask_epoch`、错误状态和 IRQ 的方向、宽度、时钟域及同步方式尚未完整冻结。
- 命令/响应 FIFO 与样本/结果 FIFO 之间不承诺全局顺序；应使用明确的 fence、`sample_id` 和 `mask_epoch` 匹配，不能依赖 FIFO 到达先后。
- AXI 32-bit 流建议固定 `TKEEP/TSTRB=4'b1111`，128-bit 流固定 `TKEEP/TSTRB=16'hffff`；`TID/TDEST` 是否 tie-off 仍需管理员裁定。

## 4. 放行条件

只有完成上述字段格式、版本权威、跨流排序、复位汇合、AXI 错误语义、FIFO 参数和器件约束七项裁定，管理员才可批准 T0 并开放 T1 纯 RTL 薄封装。本文只记录审计证据和阻断项，不授权修改计算核或创建顶层 RTL。
