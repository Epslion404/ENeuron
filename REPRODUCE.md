# ENeuron 复现入口

在全新 clone 或 `git archive HEAD` 快照根目录执行（不依赖 GitHub Actions）：

```powershell
python -X utf8 tools/repro/verify_repository.py --t1
python -X utf8 -m unittest -v test_ci_fast_v1 test_artifact_layout test_reproducibility
```

Windows T1 明确使用 `C:\msys64\ucrt64\bin\iverilog.exe` 与 `C:\msys64\ucrt64\bin\vvp.exe`。通过标记仅代表 T1 协议切片，不代表 T1-01～T1-12、T2、T3 或板级闭环全部通过。

Vivado 2024.1 不放入仓库。设置 `VIVADO_ROOT` 后运行：

```powershell
$env:VIVADO_ROOT = 'G:\Xilinx\Vivado\2024.1'
.\run_vivado_npu_single_clock_ooc.ps1 -VivadoRoot $env:VIVADO_ROOT
```

物理门只覆盖单时钟 OOC，不覆盖网口、DMA、PS、板级吞吐或功耗。当前额度耗尽后不再把 GitHub-hosted Actions 作为验收依赖；本机结果必须绑定 Git HEAD 并保留命令输出。
