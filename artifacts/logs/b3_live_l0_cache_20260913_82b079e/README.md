# B3 live L0 contribution 缓存实板复测

本证据包绑定提交 `82b079e49f46bd20c6ea0893f61f58967553b45b`、签核 RTL `be84596`、COM15 和 Vitis 2024.1。

- bit SHA-256：`0ecbe76274c39418f2a60a88358d3ff6f09f5a2ed73a44a3a419c34eb91d3a11`
- XSA SHA-256：`135d979d61c629922ee5419e51dd97ef045d9bab79930432816d09f109291d1a`
- ELF SHA-256：`cc3744e6447320bf5e948235be1154a0b70bb4e730b67a86b95740505cc7aa40`
- `packet_main.c` SHA-256：`e5fca8f5a5070490838c9e05215f4afb0bb75b440d90f3263f023c81cf03493b`
- 构建 manifest：`git_worktree_clean=true`

三次运行均为 `PASS`：logits=`165,-18,14,0,0,0,0,0,0,153`，execute/skip=`296/296`，NPU=`1606 cycles`，protocol errors=`0`，DMA=`56 us`。Host `ps_us` 为 `827/829/828`，中位数 `828 us`；历史单次基线为 `996 us`，诊断差值 `-168 us`（约 `-16.9%`）。

该结果证明 16 项局部缓存候选在当前冻结样本上保持板级可见行为并降低 Host 决策时间。它仍是小样本诊断：没有冻结不含 UART 的重复端到端窗口，也没有外部功耗数据，因此 `B3-SPEED-GATE`、`B3-POWER-MEASURED`、`B3-POWER-GATE` 和 `B3-GOAL-GATE` 均保持打开。

原始证据位于 `run-1/`、`run-2/`、`run-3/`；每组保留 run manifest、UART、XSCT 和状态探针日志。`b3_live_l0_cache_comparison.json` 保存机器可读摘要与 canonical-LF 文件哈希，避免 Git 换行规范化导致跨平台误报。
