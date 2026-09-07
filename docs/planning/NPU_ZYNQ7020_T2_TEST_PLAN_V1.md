# XC7Z020 顶层 T2 双时钟协同测试计划 V1

状态：`VARIABLE_CLOCK_SLICE_GREEN / FULL_MATRIX_PENDING`

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

每组均覆盖：复位门控、跨域错误响应背压、634-word 模型顺序装载、mask 发布、fence ID/epoch、fence 前禁止样本、完整 8-beat 样本、结果 10-beat sideband、结果长背压、无新 fence 不重开窗口和复位重入清空旧 payload。

## 观察窗口

核心固定计算最坏约 1900 个 NPU 周期；较慢 NPU 配置下，结果等待上限必须按 NPU 周期预算换算，不能使用过短的 Host 周期上限。曾出现的 600 Host 周期超时是 testbench 观察窗口错误，修正为 5000 后三组均通过；该记录不构成 RTL 缺陷。

## 尚未完成

- 三组配置是协同切片，不是随机频率/相位全矩阵。
- 仍需覆盖并发命令与样本、四 FIFO 满空/回绕在可变时钟下的独立 scoreboard，以及多次 reset 注入。
- T3 `xc7z020clg400-1` OOC、真实 XPM/xsim、AXI/DMA/网口和板级证据仍未完成。

统一入口：

```powershell
python -X utf8 tools/repro/verify_repository.py --t2
```
