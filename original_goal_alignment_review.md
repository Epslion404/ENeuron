# 原始 Goal 对齐审核稿

日期：2026-08-14（星期五）  
状态：`APPROVED`  
批准记录：用户于 2026-08-14 明确回复“批准原始 Goal M1-M4 四项决策”。

## 1. 原始 Goal

本项目的原始目标是：

> 只研究数字电路神经元和数字神经网络；允许片外/上位机生成目标、标签、奖励、探索和训练调度；片上数字神经元以本地状态和可塑规则完成权重更新，并组成可训练、可推理、可复制扩展的 AI 硬件基石。

这里的“自训练”不要求第一版只靠纯全局 reward，也不要求片上实现损失函数或反向传播。必要边界是：Host 可以决定神经元级训练信号，但不能在正式训练区间直接计算并写入每条突触的最终答案。

## 2. 当前已经证明的内容

1. `digital_lif_engine.sv` 已实现数字 LIF、pre/post trace、每突触 eligibility、快照和延迟 signed modulator 提交。
2. 权重学习方程在核内执行：`weight = saturate(weight + (modulator * eligibility_snapshot >> LEARNING_SHIFT))`。
3. 固定 `4 -> 2 -> 2` Tile 已实现四核事务、单槽 commit、一 tick 跨层路由和 TRAIN/INFER 隔离。
4. Host Bridge、controller 和双异步 FIFO 已形成可综合命令/响应数字前端。
5. Python/RTL 协同仿真、有限 BMC 和 Vivado 2024.1 post-route 已证明当前固定规模实现可工作并满足既定时序。

## 3. 批准后完成的原始 Goal 缺口

### 3.1 训练来源可审计

Host Bridge 仍保留初始化和诊断用 `WEIGHT_WRITE`，但正式 M3 命令计划从首个 TRAIN `EP_START` 到最终 INFER 结束没有任何 `WEIGHT_WRITE`。957 条实际响应形成 canonical SHA-256 账本和逐记录 hash chain，四次成功 `MOD_COMMIT` 与 `weight_epoch=4` 精确对应。

原始 Goal 假设 Host 是训练系统的一部分，不要求抵抗恶意 Host。第一版不必为此修改协议或增加硬件封印，只需冻结并验证正式运行阶段：

```text
RESET/LOAD -> WEIGHT_INIT/READBACK -> TRAIN -> INFER
```

- 训练开始前允许初始化、checkpoint 恢复和回读。
- 从第一个 TRAIN `EP_START` 到最终 INFER 结束，canonical 命令账本中 `WEIGHT_WRITE` 出现数和成功数均为 0。
- 四次提交的 eligibility 快照、signed modulator、`>>> 3` 定点增量和 `[-7,+7]` 饱和后权重已逐突触冻结，共覆盖 48 次更新。
- 每次提交后立即通过公开协议读回全部 12 个权重；`weight_epoch` 严格为 `0 -> 1 -> 2 -> 3 -> 4`。

一次性 `RUN_SEAL`、`direct_write_count` 和硬件角色权限可以增强防误用能力，但不属于证明可信 Host 闭环的必要条件，暂不抢占主线。

### 3.2 真实 RTL 任务闭环

现已在同一真实 Host Bridge + Tile RTL run 中完成：

```text
硬复位初态
-> TRAIN episode
-> eligibility snapshot
-> Host 产生神经元级 modulator
-> MOD_COMMIT
-> 权重读回
-> INFER 冻结
-> 未参与训练的留出输入
-> 输出与独立 oracle 一致
```

本次 run 共 957 条命令：训练前两类均严格 abstain；两轮四次提交后 clean 预测为 `(0,1)`，`seed=3` 的 20 个未训练扰动样本全部正确；最终推理后权重与第四次提交读回完全相同。命令 SHA-256 为 `191d7c588411515f4386685b6dfcd8ce7e3894a21f87ff3a54a40de2f9989c09`，响应账本 SHA-256 为 `cb63bcc596843607cdb7c774a91a8ffd38d9b21ee304cd266ecd33e2974a5256`。

## 4. 原始 Goal 的核心完成条件

原始 Goal 面向“数字神经元最小单位作为训练与推理基石”，不是要求第一版同时完成实用规模加速器和产品化板卡。核心完成条件应冻结为：

1. **M1 单元成立**：数字神经元在 RTL 中保存动力学与局部可塑状态，Host 只提供神经元级训练信号，权重增量由片上 eligibility 决定。当前已证明。
2. **M2 网络成立**：多个单元组成至少两层网络，层间路由、训练提交和推理冻结正确。固定 `4 -> 2 -> 2` 已完成协议和实现验证。
3. **M3 任务闭环成立**：同一真实 Host Bridge + Tile RTL run 完成初始化、训练、`MOD_COMMIT`、权重读回、冻结推理和未参与训练输入测试；结果与独立 oracle 一致，命令账本证明训练期无直接权重写入。当前已证明。
4. **M4 硬件可实现**：当前网络在目标 FPGA 器件上完成综合、布局布线及时序签核。当前已证明。

M1-M4 现已全部成立，可以准确声明：已得到一个允许片外产生目标/奖励、由片上局部可塑机制学习并可组成小网络的数字神经元硬件基石。该声明不等于通用 AI、大规模加速器或板级产品已经完成。

## 5. 后续增强，不作为当前核心完成门

### 5.1 资源可扩展架构

当前 Tile 是四个寄存器型核心的固定实例：权重、pre trace、eligibility 和 snapshot 都位于每核寄存器数组。它证明最小网络可组合、可综合，但不能外推出更大网络的资源效率。

最小扩展架构应限定为参数化 dense 两层网络，不先做任意图或 NoC：

- 同步 RAM 保存突触状态和神经元状态。
- 单 lane 共享 read/modify/write 流水线扫描突触。
- 参数化输入、隐藏和输出数量。
- 保持固定一 tick 层间路由、snapshot/commit 和 INFER 禁写语义。
- Host V2 提供 `layer/neuron/synapse` 地址和逐神经元 modulation staging。

后续扩展阶段可验收 `4 -> 2 -> 2`、`16 -> 16 -> 2`、`64 -> 32 -> 2` 三个参数点。小参数点与当前并行 Tile 在事务边界 bit-exact；更大参数点实际使用 BRAM，并报告每 tick 周期数、持续事件率、commit 延迟和 Host 带宽上限。

### 5.2 板级闭环

当前已有 OOC 工程证据。若后续要声称具体 FPGA 板级系统完成，还需要确定目标板和物理 Host 链路，补齐 top、XDC、I/O delay、时钟/复位源、bitstream，以及在板 TRAIN -> MOD -> 权重读回 -> INFER golden loop。用户尚未指定板卡，因此它不是当前最小基石结论的必要门槛。

### 5.3 更强学习能力研究

以下内容有研究价值，但不是当前最小基石的前置硬门：

- 纯全局 reward 对隐藏层的信用分配。
- task-aware no-replay 持续学习。
- 六种任务排列、GEM 指标和 joint-training upper bound。
- 10000 次置换、复杂 bootstrap 和隔离 worker bundle。
- WTA、任意拓扑 NoC、多槽 snapshot 和多执行 lane。

它们保留在 G4/T3 研究规格中，但不再阻塞核心硬件主线。Teacher 或 Host 产生的神经元级目标调制可以作为第一版训练信号，只要正式训练账本证明初始化后 Host 没有直接写逐突触权重。

## 6. 建议重新排序的主线

1. **C1 最小任务合同**：冻结一个不依赖复杂统计的训练集、未参与训练的扰动测试集、初态、epoch 数、神经元级 Teacher modulator 和严格输出解码。
2. **C2 真实 RTL 任务闭环**：复用现有 Host Bridge + Tile，不改神经元方程；完成训练、局部权重提交、权重读回、冻结推理和独立 oracle 对照。
3. **C3 学习来源审计**：保存接受命令哈希链；证明初始化后无成功 `WEIGHT_WRITE`，并逐次验证每个 `MOD_COMMIT` 的定点权重转移。
4. **C4 核心结论签核**：把 C1-C3 纳入独立验收器，并与现有 Vivado/协议证据组合成 M1-M4 的窄结论。
5. **S1 可选扩展**：之后再实现共享 RAM/Host V2 和多参数点扩展性。
6. **B1 可选板级**：用户确定板卡后实施 bitstream golden loop。
7. **R1 可选研究**：纯 reward、持续学习、no-replay 和复杂统计作为能力上界研究，不代偿 C1-C4。

## 7. 请求审核的四项决策

1. 将原始 Goal 的核心完成条件冻结为 M1-M4；共享 RAM 大规模化和具体板级部署不作为当前最小基石的必要条件。
2. 允许第一版使用片外神经元级目标/误差信号；训练真实性由完整命令账本和逐次本地权重方程证明，不新增 `RUN_SEAL` 协议。
3. 将 T3 十二项规格保留为可选 G4 研究分支，暂停其正式 runner 实现。
4. 下一实施阶段直接执行 C1-C4：用现有 Host Bridge + Tile 建立任务级 RTL 训练与冻结推理闭环；完成后再单独审核 S1、B1 或 R1。

本文四项决策已经批准并完成实施。C1-C4 全部通过，且没有修改神经元方程、Host 协议、controller 或 RTL；M3 由现有接口直接闭合。后续 S1、B1、R1 仍需单独立项和审核，不属于本次 M1-M4 签核。
