# ENeuron 1.0

发布日期：2026-08-19

## 版本定位

ENeuron 1.0 是原始 Goal M1-M4 的已验证硬件基线。它证明了一个数字神经元能够在 FPGA RTL 中保存局部动态和学习状态，接受片外神经元级训练信号，在片上计算逐突触权重变化，并组成固定 `4 -> 2 -> 2` 小网络完成训练和冻结推理。

本版本不是通用 AI、实用规模神经网络加速器或已经上板的产品。

## 包含内容

- 可综合多周期数字 LIF 核 `digital_lif_engine.sv`
- 固定 `4 -> 2 -> 2` Tile、一拍隐藏层路由和原子事务屏障
- Host Bridge、控制器和双异步 FIFO 数字前端
- TRAIN/INFER 隔离、eligibility 快照、延迟调制提交和权重读回
- Python 黄金模型、RTL 协同仿真、有限形式验证和 Vivado 2024.1 签核脚本
- 真实双时钟 M3 任务闭环及命令/响应账本审计

## 冻结证据

- 169 项软件与协同仿真回归通过
- 单核 20000 个随机混合事务通过
- Tile 10000 个随机混合事务通过
- Tile 24 拍、Controller 20 拍有限 BMC 通过
- M3 连续执行 957 条真实双时钟命令，训练区间 `WEIGHT_WRITE=0`
- 4 次 `MOD_COMMIT` 后逐次读回并核对 48 个局部权重更新
- 训练后 20/20 个未参与训练的扰动样本推理正确，推理期间权重冻结
- 固定 Tile：3152 LUT、1972 FF、0 BRAM、0 DSP，100 MHz WNS `+0.213 ns`
- Host Bridge 系统：3682 LUT、2486 FF、4 RAMB36、0 DSP；Host 50 MHz 与 Tile 100 MHz 均无 setup/hold 违例
- XC7Z020 单核补充容量探针：4 输入 818 LUT / 544 FF，2 输入 718 LUT / 380 FF，均为 0 BRAM / 0 DSP；该探针用于后续容量估算，不是 1.0 的 M4 主签核器件

完整机器摘要见 `m3_signoff_summary.txt`、`t0_signoff_summary.txt`、`vivado_tile_reports/signoff_summary.txt` 和 `vivado_host_bridge_reports/signoff_summary.txt`。

## 验证

```powershell
python verify_goal.py
```

该命令重跑回归、M3 双时钟闭环、有限形式验证和 Tile 压力测试，并审计当前工作区中冻结的 Vivado 报告。Git 不保存文件修改时间；全新检出首次验证时应运行 `python verify_goal.py --rerun-vivado`，先重建 Tile、真实 XPM 和系统实现证据，再执行新鲜度审计。

## 明确不包含

- 共享 RAM 或共享流水线的大规模网络实现
- 参数化 Host V2 网络协议
- 指定开发板的 top、XDC、bitstream 和在板闭环
- 真实活动文件驱动的功耗签核
- 纯全局奖励下的隐藏层信用分配
- G4 多任务、持续学习或通用 AI 能力结论
