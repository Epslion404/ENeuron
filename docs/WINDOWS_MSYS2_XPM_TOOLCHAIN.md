# Windows + MSYS2 UCRT64 专项测试工具链注明（Host Bridge XPM CDC wrapper）

适用范围：`test_host_bridge_xpm_wrapper.py`、`.github/workflows/pr-gate.yml`。
依据：PR #6 review `5087208884`（2026-09-02T08:14:00Z）与仓库 admin 裁定
`issue comment 5506790489`（2026-09-02T08:33:27Z）。裁定**允许**继续使用固定路径
`C:\msys64\ucrt64\bin\iverilog.exe` / `C:\msys64\ucrt64\bin\vvp.exe`，条件是该依赖必须在
代码和文档中显式注明 4 点，且 PR Gate 要么用 Windows runner 执行该测试，要么在非 Windows
明确显示 `SKIPPED/NOT APPLICABLE` 并给出原因——不能让必需检查无说明地失败。本文即第 2、4
两条的文档落点，第 1、3 条的代码落点在 `test_host_bridge_xpm_wrapper.py` 的模块 docstring。

## 1. 依赖本体

| 项 | 值 |
| --- | --- |
| 工具包 | `mingw-w64-ucrt-x86_64-iverilog`（MSYS2 UCRT64；上游当前 13.0-2） |
| 编译器 | `C:\msys64\ucrt64\bin\iverilog.exe`（常量：`test_host_bridge_xpm_wrapper.py:62`） |
| 仿真器 | `C:\msys64\ucrt64\bin\vvp.exe`（常量：`test_host_bridge_xpm_wrapper.py:63`） |
| 安装布局 | `<msys2>/ucrt64/{bin,include,lib,share}`，`vvp.exe` 需与同目录 DLL 一起在 PATH 中 |
| 平台范围 | **仅 Windows + MSYS2 UCRT64 专用路径，不是跨平台默认路径** |
| 用途 | 编译 `xpm_fifo_async_sim.sv` + `digital_snn_host_bridge.sv` + 内联 SV testbench 并运行 |
| 与 Vivado 的关系 | 无关。`xpm_fifo_async_sim.sv` 是 `xpm_fifo_async` 的接口等价模型，本测试不需要 Vivado 安装或其 XPM 库 |
| 其余仓库测试 | 走 `find_tool()`/PATH 发现，不在本文件的固定路径约束范围内 |

## 2. 裁定 4 点要求的逐条落位（文件 + 行号）

| 裁定要求 | 落位 | 行号 |
| --- | --- | --- |
| ① 声明这是 Windows + MSYS2 UCRT64 专用路径、非跨平台默认 | 模块 docstring 第 1 点；常量上方注释；常量本体 | `test_host_bridge_xpm_wrapper.py:1-44`、`:59`、`:61-65` |
| ② 声明工具名称、安装布局与用途 | 模块 docstring 第 2 点（包名/布局/`iverilog`+`vvp` 各自职责）；包名常量；环境通告函数 | `:1-44`、`:64`、`:102`（打印 `XPM_TOOLCHAIN ...`） |
| ③ Ubuntu runner 不得把“路径不存在”误报成代码功能失败 | `toolchain_unavailability()` 返回原因（平台分支 + 工具缺失分支）、`require_windows_msys2_toolchain()` 抛 `unittest.SkipTest`、前缀常量 `SKIPPED/NOT APPLICABLE: ` | `:86`、`:126`、`:66` |
| ④ PR Gate 相应调整（Windows 执行 / 非 Windows 明确跳过） | 新增 `windows-xpm-cdc` 作业：`windows-latest` + `msys2/setup-msys2@v2` + `msystem: UCRT64` + 安装该包 + 执行测试 + 守卫；ubuntu 作业安装 apt `iverilog`/`yosys` 并打印 NOT APPLICABLE notice | `.github/workflows/pr-gate.yml:62`、`:64`、`:79`、`:81`、`:83`、`:85`、`:94`、`:103`、`:106`；ubuntu 侧 `:32`、`:42`、`:50` |

补充：`test_windows_msys2_toolchain_dependency_is_declared`（`:439`）在**所有平台**
都会执行，逐项断言上面 4 点确实写在 docstring、workflow 和本文档里。任何人删掉注明、删掉
Windows 作业或漏掉 `msys2` 包名，CI 会直接失败，而不是靠人工 review 记忆。

不依赖仿真工具、因此在任何平台都真实执行的用例：`:479`、`:439`。
只有两条需要跑仿真的用例才可能跳过：`:492`、`:497`（合计 `:505` 行文件里
的 2/4）。

## 3. 本机（Windows）实测的工具链缺陷矩阵

测量环境：host `Chan-an`，Windows，Python 3.14.7；两套 Icarus 安装：

- **A** = `C:\msys64\ucrt64\bin`，`iverilog -V` = `Icarus Verilog version 12.0 (stable) ()`；
  实测该目录只有 12 个文件、`ucrt64\lib` 下没有 `vvp` 模块目录，**是局部拷贝而不是完整 MSYS2 安装**。
- **B** = `C:\iverilog\bin`，`iverilog -V` = `Icarus Verilog version 12.0 (devel) (s20150603-1539-g2693dd32b)`，
  完整安装。

| # | 安装 | 操作 | 退出码 | stdout / stderr 字节 | 结论 |
| --- | --- | --- | --- | --- | --- |
| 1 | A | `iverilog -g2012 -Wall` 编译空 testbench（`$display`+`$finish`） | 0 | 0 / 0 | 正常 |
| 2 | A | `iverilog -g2012 -Wall` 编译本设计（xpm 模型 + host bridge + transport tb） | 3221225477 = 0xC0000005 | 0 / 0 | **崩溃且无任何诊断输出** |
| 3 | A | `iverilog -g2012`（去掉 `-Wall`）编译同一设计 | 0 | 0 / 0 | `-Wall` 是该构建的触发条件 |
| 4 | A | `vvp.exe` 跑 #1 生成的空网表 | 3221225477 = 0xC0000005 | 0 / 0 | **A 的 vvp 连空 testbench 都跑不了** |
| 5 | A | `vvp.exe` 跑 #3 生成的本设计网表（已注入 `ucrt64\bin` 到 PATH） | 3221225477 = 0xC0000005 | 0 / 0 | 同上，与工程内容无关 |
| 6 | B | `iverilog -g2012 -Wall` 编译本设计 | 0 | 0 / 447 | 只有 `no explicit time unit` warning |
| 7 | B | `vvp.exe` 跑 #6 的网表 | 0 | 末行含 `XPM_WRAPPER_TRANSPORT_PASS`，`$finish called at 4790000 (1ps)` | 被测设计本身通过 |
| 8 | B | 同上，但编译/运行 `test_illegal_reset_reentry_is_rejected` 的负向 tb | 编译 0；`vvp` rc=1 | stdout 含 `FATAL: digital_snn_host_bridge.sv:196: RESET_REENTRY_ERROR  Time: 316000  Scope: tb.dut` | 负向用例按预期报错（有输出，因此不会被当成工具缺陷跳过） |

由此得到两条边界，都必须写在这里，否则容易再次误判：

1. 本机固定路径（A）下的运行结果只能是 `SKIPPED/NOT APPLICABLE: toolchain_defect ...`，
   它**不是** RTL 功能失败的证据；同一份 testbench 在完整安装（B）上通过，说明被测设计无回归。
   在固定路径上“真正执行本测试”的环境是 CI 的 `windows-xpm-cdc` 作业（全新 MSYS2 安装）。
2. `-Wall` 在 A 上会触发无输出崩溃。代码**保留 `-Wall` 优先**，只在命中
   “非 0 退出 + 退出码属于 `68` 列出的崩溃状态 + stdout/stderr 全空”
   （`is_silent_abnormal_exit()` `:76`）这一特征时，打印
   `TOOLCHAIN_DEFECT=iverilog_compile_silent_crash return_code=0x... retry_without=-Wall`
   （`:176`）并去掉 `-Wall` 重试一次（`:179`）。
   任何**有输出**的非 0 结果继续 `raise RuntimeError`（`:186`），真实语法错误不会被吞。
   编译或仿真仍无输出崩溃时转成 SkipTest（`:185`、`:202`），
   消息同时包含 `SKIPPED/NOT APPLICABLE:` 与 `toolchain_defect`。
3. 为防止“用跳过冒充通过”：`windows-xpm-cdc` 作业的输出里只要出现 `NOT APPLICABLE` 或
   `TOOLCHAIN_DEFECT` 就判定失败（`:103`、`:106`）。也就是说在 Windows
   runner 上，本测试要么真实跑过，要么让 PR Gate 变红。

## 4. CI 执行环境与工具版本

| 作业 | runner / Python | 工具来源 | 本测试的结果 |
| --- | --- | --- | --- |
| `Python and syntax` | ubuntu-latest / 3.12 | apt `iverilog` + `yosys`（`:32`） | `:479`、`:439` 真实执行；`:492`、`:497` 显示 `skipped "SKIPPED/NOT APPLICABLE: host platform is ...not win32...cannot run on an Ubuntu runner"`，notice 由 `:50` 打印到作业日志 |
| `XPM CDC wrapper (Windows MSYS2 UCRT64)` | windows-latest / 3.12 | `msys2/setup-msys2@v2`（`msystem: UCRT64`，`install: mingw-w64-ucrt-x86_64-iverilog`）→ 落到固定路径 | 4 条用例全部真实执行，0 跳过；作业日志含 `XPM_TOOLCHAIN platform=win32 ...` 与 `XPM_WINDOWS_GATE=PASS` |
| `NP7 functional and evidence gate` | ubuntu-latest / 3.12 | apt `iverilog` + `yosys` | 与本文件无关，不受影响 |
| `NP7 physical evidence integrity` | ubuntu-latest / 3.12 | 纯 Python 校验 | 与本文件无关 |

Ubuntu 侧的跳过原因由 `toolchain_unavailability()`（`:86`）的第一个分支生成，内容指向
`C:\msys64\ucrt64\bin` 这个 Windows-only 布局；它不再抛 `RuntimeError`，因此必需检查
不会再因为“路径不存在”而失败。

## 5. 本地复现命令（Windows，仓库根目录）

```powershell
# 固定路径工具链缺陷 => 2 ok + 2 skipped(NOT APPLICABLE)，并打印 TOOLCHAIN_DEFECT= 行
python -X utf8 -m unittest -v test_host_bridge_xpm_wrapper

# 单跑平台无关的源码检查
python -X utf8 -m unittest -v test_host_bridge_xpm_wrapper.HostBridgeXpmWrapperTests.test_xpm_configuration_is_frozen
```

非 Windows 分支可在不修改文件的前提下本地模拟（把 `sys.platform` 改成 `linux` 后再加载模块）：

```powershell
python -X utf8 -c 'import sys, unittest; sys.platform="linux"; import test_host_bridge_xpm_wrapper as m; unittest.main(module=m, argv=["x","-v"], exit=False)'
```


上面这条命令实测输出 2 条 `skipped "SKIPPED/NOT APPLICABLE: host platform is 'linux' ..."` 与 2 条 `ok`，与 Ubuntu runner 上 `Python and syntax` 作业看到的行为一致（本机 Windows 固定路径运行结果见 `artifacts/logs/xpm_wrapper_windows_fixed_path.txt`）。
仓库内固化的三份证据日志：

| 文件 | 内容 |
| --- | --- |
| `artifacts/logs/xpm_wrapper_windows_fixed_path.txt` | 本机固定路径下 `python -X utf8 -m unittest -v test_host_bridge_xpm_wrapper` 的完整输出：`Ran 4 tests ... OK (skipped=2)`，含 `XPM_TOOLCHAIN ...` 与 4 条 `TOOLCHAIN_DEFECT=...` |
| `artifacts/logs/xpm_wrapper_nonwindows_notice.txt` | 本机模拟非 Windows 平台（`sys.platform='linux'`）的输出：2 条 `skipped "SKIPPED/NOT APPLICABLE: host platform is ..."` + 2 条 `ok`，即 Ubuntu runner 应看到的行为 |
| `artifacts/logs/xpm_toolchain_defect_matrix.txt` | 第 3 节缺陷矩阵的原始测量输出（A/B 两套 Icarus 的编译/仿真退出码与字节数） |。

## 6. 维护规则

1. 以后凡是需要固定路径/专用安装的测试，必须照本文件模式做齐 4 件事：docstring 注明、
   `SkipTest` 带 `SKIPPED/NOT APPLICABLE: ` 前缀与具体原因、专用 OS 的 PR Gate 作业、
   该作业里的“跳过即失败”守卫；并且要有 1 条平台无关的用例断言这些注明仍然存在。
2. 不得把固定路径改写成跨平台默认，也不得用 `self.fail()` / `RuntimeError` 表达“工具没装”。
3. 不得反向利用本机制：`TOOLCHAIN_DEFECT` 只在“无输出崩溃”时出现，任何有诊断输出的错误都必须失败。
4. 若 CI 的 MSYS2 包版本升级导致 `-Wall` 行为变化，应更新本文第 3 节矩阵并注明版本与日期。
