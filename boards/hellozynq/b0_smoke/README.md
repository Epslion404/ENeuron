# HelloZynq B0 smoke

该工程只验证 `xc7z020clg484-2` 的 PL 配置链、M19 50 MHz 输入和 P20 LED。它不实例化 PS7、DDR、Ethernet、ILA 或 NPU。

## 连接

```text
M19 / sys_clk_50m
  -> 26-bit free-running counter
  -> counter[25]
  -> P20 / led
```

50 MHz 下 LED 完整亮灭周期约为 `2^26 / 50_000_000 = 1.34217728 s`。

## 构建

```powershell
.\boards\hellozynq\b0_smoke\run_b0_build.ps1
```

构建必须使用 Vivado 2024.1 和目标 `xc7z020clg484-2`，并在 `build` 目录生成实现报告、bitstream、SHA-256 manifest 与 `B0_BUILD_PASS` 标记。

## JTAG 下载

```powershell
.\boards\hellozynq\b0_smoke\run_b0_program.ps1
```

脚本只通过 Hardware Manager 配置链上的 `xc7z020`，不会写入 QSPI 或 SD 卡。下载后仍需现场确认 P20 连续闪烁；program 命令成功不能代替 LED 观测。

每次正式下载后、下一次下载前，应先固化当前机器原始证据：

```powershell
.\boards\hellozynq\b0_smoke\archive_b0_program_run.ps1 -RunLabel <唯一运行标识>
```

归档会写入 `artifacts/logs/hellozynq_b0/<唯一运行标识>/`，保存下载结果、完整 transcript、构建 manifest及各文件 SHA-256。已存在的运行目录会被拒绝，避免后一次测试覆盖前一次证据。现场 LED观察仍需另行记录，归档 manifest在确认前保持 `observation_status=PENDING`。
