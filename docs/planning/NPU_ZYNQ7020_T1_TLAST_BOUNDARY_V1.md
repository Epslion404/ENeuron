# T1-09 TLAST 边界裁定 V1

状态：`NA_FOR_T1_WRAPPER / OUTER_SHIM_PENDING`

日期：2026-09-07

## 结论

当前 `npu_zynq7020_t1_wrapper` 是四条内部 ready/valid 流和四个异步 FIFO 的纯 RTL 适配器，端口表没有 `TLAST/TKEEP/TSTRB/TUSER` 端口。根据已批准的 A2，固定 8 beat 样本和 10 beat 结果由内部计数器决定，T1 wrapper 不读取、修改或验证 TLAST。

因此 T1-09 对当前 DUT 的结果是 **N/A**，不是通过也不是失败。改变、提前或缺失 TLAST 的测试必须在未来的外层 AXI-Stream shim 或 packetizer 落地后单独执行；当前不能把该测试外推为 T1 wrapper 证据。

## 证据

- [npu_zynq7020_t1_wrapper.sv](../../npu_zynq7020_t1_wrapper.sv) 的公开端口只包含 `valid/ready/data` 和已冻结的 `sample_id/result sideband`。
- [NPU_ZYNQ7020_TOPLEVEL_T0_DECISION_ADDENDUM_V1.md](NPU_ZYNQ7020_TOPLEVEL_T0_DECISION_ADDENDUM_V1.md) A2 已批准：TLAST 为外层提示，不参与 8/10 beat 计数。
- [NPU_ZYNQ7020_T1_TEST_PLAN_V1.md](NPU_ZYNQ7020_T1_TEST_PLAN_V1.md) 将外层 TLAST 检查列为独立边界，不把它混入当前 wrapper 仿真。

## 后续门

外层 shim 实现并冻结端口后，新增独立仿真：在同一组完整 8/10 beat 事务中改变、提前和缺失 TLAST，确认核心结果只由固定 beat 合同决定；严格包完整性错误由 packetizer 负责。
