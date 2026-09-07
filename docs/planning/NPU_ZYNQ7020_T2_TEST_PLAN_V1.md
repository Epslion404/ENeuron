# XC7Z020 顶层 T2 双时钟协同测试计划 V1

状态：`VARIABLE_CLOCK_SLICE_GREEN / CONCURRENT_EPOCH_SLICE_GREEN / EXTENDED_CLOCK_SLICE_GREEN / FIFO_MATRIX_SLICE_GREEN / INTERLEAVE_RESET_SLICE_GREEN / T3_XPM_XSIM_PASS / T3_XC7Z020_OOC_PASS / FULL_MATRIX_PENDING`

日期：2026-09-07

## 范围

T2 在已通过的 T1 wrapper 上改变 `host_clk` 与 `npu_clk` 的频率和相位，验证四条异步 FIFO 的事务完整性。首个切片不修改 RTL，不引入 AXI-Lite、DMA、Ethernet 或 PS7，也不把本机仿真外推为板级吞吐。

## 已通过切片

同一参数化 testbench `tb_npu_zynq7020_t2_variable_clocks.sv` 已在以下三组配置通过：

| 配置 | NPU 半周期 | 初始相位 | 结果 |
|---|---:|---:|---|
| T2-A | 7 ns | 2 ns | `T2_VARIABLE_CLOCKS_PASS` |
| T2-B | 9 ns | 1 ns | `T2_VARIABLE_CLOCKS_PASS` |
| T2-C | 4 ns | 3 ns | `T2_VARIABLE_CLOCKS_PASS` |
| T2-D | 5 ns | 0 ns | `T2_VARIABLE_CLOCKS_PASS` |
| T2-E | 11 ns | 4 ns | `T2_VARIABLE_CLOCKS_PASS` |
| T2-F | 3 ns | 1 ns | `T2_VARIABLE_CLOCKS_PASS` |

每组均覆盖：复位门控、跨域错误响应背压、634-word 模型顺序装载、mask 发布、fence ID/epoch、fence 前禁止样本、完整 8-beat 样本、结果 10-beat sideband、结果长背压、无新 fence 不重开窗口和复位重入清空旧 payload。

## 并发 epoch 切片

在同一 testbench 中增加了跨域并发场景：首个样本的 8 个 beat 已进入 Host→NPU FIFO 后，Host 立即发送下一组 mask（epoch=2），而 NPU 同时计算当前样本。结果逐 beat 仍回显 sample `CAFE_0001`、epoch=1；随后 fence 响应仍回显 active epoch=1，下一样本才回显 epoch=2。该场景在三组可变时钟配置下均通过，证明 pending mask 不会穿透当前样本，也不会被 fence 提前激活。

## wrapper 有限全矩阵

`verify_repository.py --t2-full-matrix` 复用同一 T2 wrapper testbench，运行 16 组确定性时钟/相位组合：半周期覆盖 2--11 ns，包含相位为 0、末相位、接近 Host 和明显快/慢于 Host 的组合。每组仍执行完整模型装载、mask/fence、8/10 beat、背压、并发 epoch 和复位重入场景；本轮本机结果为 `REPRO_G2_T2_FULL_MATRIX_PASS`。

该矩阵是有限的可复现实验，不是所有频率/相位的数学穷举；真实 AMD XPM/xsim 与 XC7Z020 OOC 证据已经在 T3 独立通过。

## 固定种子随机矩阵

`verify_repository.py --t2-random-matrix` 使用固定种子 `20260907` 生成 24 组唯一的半周期/相位组合，半周期范围为 2--17 ns。每组复用同一个完整 wrapper 场景，包含模型装载、mask/fence、并发 epoch、8/10 beat、背压和复位重入；本机结果为 `REPRO_G2_T2_RANDOM_MATRIX_PASS`。

结果等待窗口按 `2000 + 400 × NPU_HALF` 个 Host 周期计算，覆盖模型装载和约 1900 个 NPU 周期的最慢组合。该窗口修正了固定 5000 周期在慢时钟下过早超时的问题；它只改变观察预算，不改变 DUT 或功能判据。

## FIFO 独立压力矩阵

`tb_xpm_fifo_async_matrix.sv` 对命令、响应、样本和结果四条通道分别记录实际写入序列和实际读出序列，在末尾逐项比对。固定矩阵为 8 组 NPU 半周期/初始相位（`(2,0)`、`(3,1)`、`(4,3)`、`(5,0)`、`(7,2)`、`(9,1)`、`(11,4)`、`(13,5)`）× 3 个固定 seed（`1/7/29`），共 24 次。每次包含填满、排空、随机读写、读端长背压和中途 reset 后重复测试，四通道均返回 `T2_FIFO_MATRIX_PASS`。

统一入口：`python -X utf8 tools/repro/verify_repository.py --t2-fifo-matrix`。该矩阵是固定的伪随机样本，不是所有频率/相位的数学穷举；也只验证 Icarus 接口等价模型。

## wrapper 交错与复位切片

`tb_npu_zynq7020_t2_interleave_reset.sv` 在 4 组 `(NPU_HALF,NPU_PHASE)=(2,0),(3,1),(7,2),(11,4)` 下验证：模型装载中途复位不会提交半模型；同一 Host 时间段内 mask 命令和 sample beat 可交错接受；结果背压中复位会丢弃未消费结果；sample 第 4 beat 前复位不会泄漏半帧。入口是 `python -X utf8 tools/repro/verify_repository.py --t2-interleave-reset`，返回 `REPRO_G2_T2_INTERLEAVE_RESET_PASS` 后仍保留 T2 全矩阵待完成状态。

## 观察窗口

核心固定计算最坏约 1900 个 NPU 周期；较慢 NPU 配置下，结果等待上限必须按 NPU 周期预算换算，不能使用过短的 Host 周期上限。曾出现的 600 Host 周期超时是 testbench 观察窗口错误，修正为 5000 后三组均通过；该记录不构成 RTL 缺陷。

## 尚未完成

- 八组配置×三个 seed 的 FIFO 独立 scoreboard 已通过；wrapper 交错命令/sample 与三类 reset 切片也已通过；这些都不是所有频率/相位的数学穷举。
- T3 的真实 AMD XPM/xsim 和 `xc7z020clg400-1` OOC 已完成并通过；证据绑定 `c2bc03f`，不覆盖 AXI/DMA/PS7/Ethernet、bitstream、板级 I/O、吞吐、功耗或首次完整端到端运行。
- 固定种子随机矩阵已通过，但它仍不是频率/相位数学穷举；仍需补齐更广泛的并发命令/样本交错和多位置 reset，外层 AXI-Stream shim 若实现，也必须单独验证 TLAST 语义。

统一入口：

```powershell
python -X utf8 tools/repro/verify_repository.py --t2
```
