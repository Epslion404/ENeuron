# T3 真实 Vivado 签核

verified_at: 2026-09-07
evidence_head: `c2bc03f`

## 结果

- 真实 AMD XPM/xsim：`RESULT=PASS`。
- Vivado OOC：`PHYSICAL_GATE=PASS`。
- 工具/器件：Vivado 2024.1，`xc7z020clg400-1`。
- 时钟：host 与 NPU 均为 100 MHz，setup/hold failing endpoints 为 0，route errors 为 0，DRC errors 为 0。
- 资源：顶层 `2467 LUT / 2301 FF / 6 RAMB36 / 1 RAMB18 / 4 DSP48E1`；`DSP48E1_COUNT=4` 与预期一致。本报告的关键摘要还包括 host `WNS=3.639 ns / WHS=0.105 ns`、NPU `WNS=0.214 ns / WHS=0.042 ns`。
- CDC：wrapper 外部 `EXTERNAL_CDC_CRITICAL=0`、`EXTERNAL_CDC_WARNING=0`。XPM 原语内部仍有 8 个 `CDC-6` warning；这是工具对异步 FIFO 灰码指针同步的分类，不是 wrapper 外部 CDC 失败。

证据文件：`vivado_npu_zynq7020_t3_xsim/xsim_signoff_summary.txt`、`vivado_npu_zynq7020_t3_ooc_reports/signoff_summary.txt`。xsim 明确使用 `XPM_LIBRARIES=XPM_FIFO` 与真实 `AMD_XPM_FIFO` 模型。

## 边界

本次 T3 只覆盖“核心 + 适配器 + 四条真实 XPM 异步 FIFO”的协同仿真和 XC7Z020 OOC。它不覆盖 AXI/DMA/PS7/Ethernet、bitstream、板级 I/O/吞吐、功耗或首次完整端到端运行。GitHub Actions 已关闭，远端 checks 为空，不作为本次签核证据。

OOC DRC 仍有建议性 warning（DSP 内部流水建议、无负载提示、OOC 未实例化 PS7），但 `DRC_ERRORS=0`，不改变 `PHYSICAL_GATE=PASS`。
