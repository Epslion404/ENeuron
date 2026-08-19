# 可塑单神经元硬件基石模拟

当前稳定版本为 **ENeuron 1.0**，版本号见 `VERSION`，冻结范围和证据见 `RELEASE_1.0.md`。该版本已完成原始 Goal M1-M4：片外提供神经元级训练信号，片上执行局部权重更新，并在固定 `4 -> 2 -> 2` 双时钟 RTL 网络中完成训练和冻结推理；共享 RAM 扩展、板级闭环和通用 AI 不属于 1.0 声明。

本目录用本机 Python 比较三种适合数字硬件的单神经元候选：

1. `counter_if`：原始无泄漏计数器 IF 基线。
2. `pair_stdp_lif`：有符号 LIF 加二因子 STDP。
3. `three_factor_lif`：有符号 LIF、pre/post 迹线、每突触资格迹线和有符号调制端口。

## 运行

```powershell
python neuron_sim.py --epochs 30
python run_sweep.py
python run_network_experiment.py
python run_network_sweep.py
python -m unittest discover -v
python -m unittest -v test_m3_rtl_closure.py test_m3_acceptance.py
python rtl_tile_cosim.py --seed 0 --transactions 500
.\run_formal_tile.ps1
.\run_formal_host_bridge_controller.ps1
python verify_goal.py
.\run_vivado_xpm_wrapper_sim.ps1
.\run_vivado_host_bridge_system_ooc.ps1
```

单神经元结果写入 `simulation_results.json` 和 `sweep_results.json`；两层网络结果写入 `network_results.json` 和 `network_sweep_results.json`。

## 实验任务

正负样本包含相同数量的脉冲，只使用不同输入通道。训练调制信号为正样本 `+1`、负样本 `-1`，模拟局部奖励/误差信号。这样可以检验单元是否具备任务导向的权重调整能力，而不是只依赖总脉冲数。

## 历史单元实验结果

在 30 个 epoch、10 种训练顺序下：

| 候选 | 区分成功率 | 状态位代理 | 结论 |
|---|---:|---:|---|
| counter_if | 0% | 84 | 只能积分发放，不能学习 |
| pair_stdp_lif | 0% | 108 | 会增强相关活动，但没有任务调制时会同时增强两类 |
| three_factor_lif | 100% | 169 | 能接收延迟调制并冻结权重做推理 |

推荐的最小设计是 `three_factor_lif`。资格迹线比二因子 STDP 多占状态，但它是处理延迟奖励或局部误差的关键；如果只做无监督聚类，可以移除资格迹线，退化为 `pair_stdp_lif`。

## 两层数字网络与片外训练

当前网络级黄金模型为：

```text
4 输入事件轴 -> 2 隐藏可塑 LIF -> 1 tick 路由 -> 2 输出可塑 LIF
```

片外 `HostTrainingController` 负责目标和 signed modulator，片上网络只负责资格迹线、权重提交和推理。episode 结束时 eligibility 由 `commit_id` 锁存，片外通信延迟不会覆盖待提交状态。

以下 20 个训练种子结果来自历史受控实验，尚未由当前 V3 多任务数据合同重建，因此不属于当前一键 Goal 签核：

| Host 协议 | 干净任务成功率 | 扰动任务平均准确率 |
|---|---:|---:|
| 可寻址目标调制 | 100% | 100% |
| 隐藏层全局 reward + WTA | 0% | 22.5% |
| 目标塑造隐藏层 + reward 训练输出层 | 100% | 100% |

当前推荐采用两阶段 Host 协议：先用可寻址目标调制塑造并冻结隐藏特征，再由 Host 用 epsilon 探索和标量 reward 训练输出动作层。全局 reward 的失败说明 WTA 本身仍不能解决隐藏层信用分配。

## RTL 与 FPGA 证据

`digital_lif_core.sv` 是单周期行为参考；`digital_lif_engine.sv` 是可时序收敛的多周期核；`digital_snn_tile_4x2x2.sv` 并行实例化四核；`digital_snn_host_bridge_system.sv` 进一步集成 Host Bridge、命令控制器、两条 XPM async FIFO 和真实 Tile。

Icarus/Python 协同仿真已经覆盖：

- 单核 20000 个随机混合事务。
- Tile 10000 个随机混合事务。
- 一 tick 跨层路由、非零 eligibility、真实权重更新、推理冻结、非法/过期 commit、busy 隔离和精确事务延迟。
- Controller + Tile 单时钟协同仿真：定向 64 命令和 20 seeds x 1000 命令 bit-exact。
- 双时钟系统协同仿真：20 seeds x 2000 flit，共 40000 命令，覆盖随机非整数时钟比、相位、双向背压和 hard reset。
- 当前完整 discovery 回归 169 项通过，并包含真实 M3 双时钟任务闭环、训练账本/eligibility 反例、非法高优先级命令隔离、XPM/系统 CDC 摘要严格解析和 G4 Temporal 数据反例。
- Yosys 0.56 对真实四核 Tile 完成 24 拍敌对输入协议 BMC，无反例；这不是无限时域或全状态等价证明。
- Yosys 对 Host Bridge controller 完成 20 拍 safety BMC；负向环境可复现反例，6 类独立 witness 均可达。

真实 Vivado 2024.1 XPM xsim 测得两条 depth-16 FWFT FIFO 的外部可见容量均为 17；双向填满/排空、64 字回绕、背压与 hard reset 均通过，且仿真专用 reset 断言未进入综合网表。

Vivado 2024.1 对 `xc7a35tcpg236-1` 的最终 OOC post-route 结果：

| 实现 | LUT | FF | BRAM | DSP | 100 MHz WNS | 最差 hold |
|---|---:|---:|---:|---:|---:|---:|
| 多周期单核 | 813 | 544 | 0 | 0 | +0.469 ns | 无失败端点 |
| 4->2->2 Tile | 3152 | 1972 | 0 | 0 | +0.213 ns | +0.026 ns |
| Host Bridge + Controller + Tile | 3682 | 2486 | 4 RAMB36 | 0 | Tile +0.081 ns | +0.058 ns |

系统约束为 Host 50 MHz、Tile 100 MHz：Host WNS/WHS 为 `+14.306/+0.105 ns`，Tile WNS/WHS 为 `+0.081/+0.058 ns`，两域 TNS/THS、setup/hold violations、route errors、DRC Error/Critical Warning 均为 0。8 条 CDC 报告项全部位于官方 XPM 内部，XPM 外 Critical/Unsafe/Warning 为 0。系统功耗 `0.112 W` 只是无真实活动文件的 Medium-confidence OOC 估算。

`python verify_goal.py` 会重跑完整回归、M3 的 957 命令真实双时钟训练闭环、Tile 24 拍 BMC、Controller 20 拍 BMC、20 seeds x 500 个 Tile 事务，并独立解析 Tile、真实 XPM 与完整系统 routed 报告。M3 会生成 `m3_signoff_summary.txt`，绑定命令和响应账本哈希。独立 Tile 当前冻结资源预算为 `LUT <= 3200`、`FF <= 2000`、`BRAM/DSP = 0`。脚本成功表示原始 Goal M1-M4 最小硬件基石门槛通过；共享 RAM 扩展、板级闭环和通用 AI 仍不在该结论内。

Pulse-Mini 的完整执行清单见 `TODO.md`，当前状态为 `APPROVED` / `P7_CAPACITY_BOUNDARY_DOCUMENTED`。单核已完成黄金模型、RTL、形式、任务和 XC7Z020 routed 闭环；固定 `4 -> 2 -> 2` 网络已完成 Python 与 RTL 协同仿真。P7 还提供 `python pulse_mini_array_metrics.py`、`python pulse_mini_lane_model.py` 和 `python verify_pulse_mini_p7.py`：广播阵列的单条逻辑 TICK 响应延迟为 1 个周期，但单槽协议持续接受率为 0.5 命令/周期；32 核是当前 100 MHz routed 已证明的最大并行规模，64/128 核的简单广播阵列 setup 未通过。共享 lane 数字结果是周期模型，不是物理容量声明。

Git 不保存报告文件的修改时间。全新检出第一次复验应使用 `python verify_goal.py --rerun-vivado` 重建 Vivado 证据；已有同一工作区可直接运行默认命令审计现存报告。

V3 Temporal development cohort 已实现 5 个固定 split、1312 个唯一语义输入、四阶 motif、精确输入 schema、全局冻结 burst width、IID/OOD 间隔域和生成器重放认证。`g4_temporal_development_manifest.json` 使用 manifest V2，同时绑定输入哈希、完整样本哈希和实际 `g4_benchmark.py` 源码；所有 model seeds 共享同一数据集，统计口径为 paired model-seed。该产物仍只是 development cohort，不代表三任务 P0a/P0b 或 G4 通过。

## 设计边界

当前证据已支持用户批准的原始 Goal M1-M4：片外 Host 提供神经元级训练信号，片上局部 eligibility 完成权重更新，并在固定 4->2->2 双时钟 RTL 网络中完成训练和冻结推理。它不支持“通用 AI 自训练已经解决”。尚缺无限时域/全状态形式等价、共享 RAM 大规模扩展、真实板级 I/O/bitstream 闭环、活动率功耗和多任务信用分配验证，详见 `goal_audit.md`。
