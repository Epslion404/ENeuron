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
