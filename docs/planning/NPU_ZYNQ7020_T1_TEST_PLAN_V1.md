# XC7Z020 顶层 T1 纯 RTL 验证方案 V1

状态：`PROTOCOL_SLICE_GREEN / FULL_MATRIX_PENDING`

日期：2026-09-06

关联合同：

- `docs/planning/NPU_ZYNQ7020_TOPLEVEL_T0_DECISION_ADDENDUM_V1.md`
- `docs/planning/NPU_ZYNQ7020_TOPLEVEL_T0_TEST_CONTRACT_V1.md`
- `docs/planning/NPU_SINGLE_CLOCK_RTL_PORT_TABLE_V1.md`

## 1. 范围

本方案只验证 T1 纯 RTL 适配器：四条异步 FIFO、命令仲裁、SAMPLE_FENCE、固定 8/10 beat、错误响应、ready/valid 稳定性和复位丢弃。它不验证 AXI-Lite、DMA、Ethernet、PS7 或板级吞吐，也不修改 `npu_eneuron_single_clock_skeleton.sv`。

当前已完成同频 100 MHz 协议切片：Icarus 编译和仿真均返回 0，并输出 `T1_PROTOCOL_SKELETON_PASS`。该切片覆盖 T1-01、T1-03、T1-04、T1-05、T1-07、T1-08、T1-10、T1-11 的主要路径；T1-02、T1-06、T1-09、T1-12 仍需独立测试，不得写成完整 T1 通过。不同频比与随机相位属于 T2。

## 2. 推荐 DUT 端口

测试骨架假定模块名为 `npu_zynq7020_t1_wrapper`，端口保持核心字段语义，不把 AXI-Lite 或 DMA 混入适配器：

| 方向 | 端口 | 宽度 | 说明 |
|---|---|---:|---|
| in | `host_clk`, `npu_clk`, `bridge_rst` | 1 | 双时钟和同步复位请求 |
| Host→NPU | `host_cmd_valid/ready`, `host_cmd_data` | 1/1/128 | 命令 FIFO 写侧 |
| NPU→Host | `host_rsp_valid/ready`, `host_rsp_data` | 1/1/128 | 响应 FIFO 读侧 |
| Host→NPU | `host_sample_valid/ready`, `host_sample_data`, `host_sample_id` | 1/1/32/32 | sample FIFO 写侧，固定 8 beat |
| NPU→Host | `host_result_valid/ready`, `host_result_data`, `host_result_sample_id`, `host_result_mask_epoch` | 1/1/32/32/32 | result FIFO 读侧，固定 10 beat |
| status | `runtime_idle`, `host_model_valid`, `host_mask_valid`, `host_infer_frozen`, `host_status_irq`, `host_error` | 1 | 本域同步摘要，不承担数据传输 |
| internal/probe | 四 FIFO 的 `wr_rst_busy/rd_rst_busy` | 1×8 | 当前初版可先用层次探针或仿真断言观察；若作为正式端口公开，必须单独更新端口裁定 |

若实现把 AXI-Stream `TLAST/TKEEP/TSTRB/TUSER` 放在更外层，T1 DUT 不需要这些端口；另一个 AXI shim 的 TLAST 测试应独立完成。若 T1 DUT 暴露 TLAST，测试必须把它当外层提示并改变其值后重跑同一 8/10 beat 事务，结果不得变化。

## 3. FIFO 与 framing 固定项

- command：128 bit、depth 16、FWFT、read latency 0、CDC stages 2、`SIM_ASSERT_CHK=1`、memory `auto`。
- response：同上，方向相反。
- sample：完整 payload 为 `{sample_id, sample_data}`，64 bit、depth 16。
- result：完整 payload 为 `{mask_epoch, sample_id, result_data}`，96 bit、depth 16。
- 一个样本严格 8 次 `host_sample_valid && host_sample_ready` 握手；一个结果严格 10 次 `host_result_valid && host_result_ready` 握手。
- sample 的 `sample_id` 只在首 beat 绑定；result 的两个 sideband 在全部 10 beat 保持不变。

## 4. T1 测试矩阵

| 编号 | 场景 | 必须观察 |
|---|---|---|
| T1-01 | 复位门控 | 任一 reset-busy 时四条 Host-facing ready/valid 不泄漏；释放后至少两个本地沿才重新开放 |
| T1-02 | 合法命令转发 | `0x1..0x9` 每条命令最多消费一次，payload 原样到 NPU 域 |
| T1-03 | 非法字段 | 未知 opcode、`[123:120]` 非零、`[87:32]` 非零各自产生一个 `0xE` 错误；不改模型、mask、epoch、动态状态 |
| T1-04 | 响应背压 | `host_rsp_valid && !host_rsp_ready` 时响应 payload/valid 稳定；响应槽满时命令不被错误响应替代 |
| T1-05 | fence 前禁止样本 | 未成功 fence 前 `host_sample_ready=0`；即使 sample valid 保持，sample FIFO 不得预填 |
| T1-06 | fence 成功 | 仅在此前命令已完成、核心 sample-ready、无结果/响应、staging 闭合时接受 `0xA`；返回类别 `0xD`，携带 fence ID 和 active epoch |
| T1-07 | 单样本窗口 | fence 成功后只接受 8 个 sample beat；第 8 个握手后立即关闭下一窗口，未再次 fence 不得接受第 9 beat |
| T1-08 | 结果固定帧 | 每样本输出恰好 10 beat；结果背压时 data/sample_id/mask_epoch/valid 全部稳定 |
| T1-09 | TLAST 外层提示（若有） | 在 beat 数完整时改变、提前或缺失 TLAST 不改变 T1 核心结果；严格包错误不在本 DUT 断言 |
| T1-10 | mask 首 beat 边界 | 已发布 mask 在 fence 后、样本首 beat 才绑定；样本进行中提交的新 mask 不影响当前 10-beat 结果 |
| T1-11 | 复位重入 | 在命令、样本第 1/4/8 beat、结果第 1/5/10 beat 注入 bridge_rst；半事务丢弃，复位后不得泄漏旧 payload/epoch |
| T1-12 | 四 FIFO 边界 | 空读、满写、同时 push/pop、回绕、长背压；每条流无丢失、重复、乱序 |

## 5. Scoreboard 规则

1. 命令 ledger 的登记点是 `host_cmd_valid && host_cmd_ready`，不是 producer 拉高 valid 的时间。
2. NPU 域命令观察只用于顺序核对；response 与 result 两条 FIFO 不假定全局先后。
3. sample ledger 在首 beat握手时锁存 `sample_id`，随后要求同一事务的 8 beat 完整消费。
4. result ledger 在首 beat出现时创建，要求 10 beat、同一 `sample_id` 和 `mask_epoch`；每拍按 `host_result_valid && host_result_ready` 提交。
5. 数值结果由 `npu_eneuron_reference.py` 在同一模型和 mask 下生成；T1 协同 testbench 只比较结果 beat/sideband/顺序，核心算术已由单时钟回归覆盖。
6. 任何错误响应被消费前，响应字段和 `rsp_valid` 必须保持；错误响应不能改变 ledger 中的模型/mask/epoch 账本。

## 6. 运行方式

待 DUT 文件落地后，MSYS2 UCRT64 下使用允许的固定工具路径：

```powershell
C:\msys64\ucrt64\bin\iverilog.exe -g2012 -Wall -s tb_npu_zynq7020_t1_wrapper `
  -o artifacts\t1_wrapper.vvp `
  xpm_fifo_async_sim.sv npu_eneuron_single_clock_skeleton.sv `
  npu_zynq7020_t1_wrapper.sv tb_npu_zynq7020_t1_wrapper.sv
C:\msys64\ucrt64\bin\vvp.exe artifacts\t1_wrapper.vvp
```

这条固定路径只适用于 Windows + MSYS2 UCRT64，不能作为 Linux CI 的默认工具链。Vivado 2024.1 xsim 运行时必须替换 `xpm_fifo_async_sim.sv` 为 AMD XPM 库，并保留同一 testbench 判据。

## 7. T1 通过门

- 当前协议切片已通过；T1-01～T1-12 全量签核仍要求每项有独立确定结果，负向场景必须确实失败于被测错误，而不是 testbench 超时。
- 同频 100 MHz 下逐 beat、sideband、错误和 reset 行为通过；数值结果与单时钟参考模型一致。
- 不把 T1 结果写成 T2 CDC 全覆盖或 T3 XC7Z020 资源/时序通过。
- T1 未通过前不得实施资源裁剪、接入 DMA/Ethernet 或合并板级结论。
