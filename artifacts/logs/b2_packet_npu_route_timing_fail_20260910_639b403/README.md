# B2 packet-NPU routed timing failure: `639b403`

- 日期：2026-09-10
- 目标器件：`xc7z020clg484-2`
- Vivado：2024.1
- 顶层：`design_1_wrapper`
- 源码提交：`639b4036b5dc9871bb21e3d13a38faba725672ce`
- 时钟：`clk_fpga_0`，200 MHz，5.0 ns
- route errors：`0`
- DRC hard errors：`0`（报告仅含 warnings/advisories）
- 时序：失败，`WNS=-1.287 ns`、`TNS=-384.021 ns`、`1942` 个 setup failing endpoints，`WHS=+0.051 ns`、`THS=0`
- 最差路径：本轮摘要需以 `timing_impl.rpt` 为准；该构建未达到 200 MHz 签核条件
- bit/XSA：已生成，仅用于失败分析，禁止下载到目标板

本轮 carry-select MAC 累加器虽通过定向功能回归，但没有解决完整 packet-NPU 顶层的 200 MHz setup timing。B2-06～B2-10 和 B2-GATE 保持未完成。
