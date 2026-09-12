# ENeuron NPU 局部自动剪枝与动态门控计划

状态：`NP4B_COMPLETED / NP6_PARTIAL / NP7_SIGNED_OFF / NPU_V2_FUNCTIONAL_GREEN / T3_CLG400_EVIDENCE_RECORDED / B2_PACKET_NPU_PHYSICAL_PASS / B2_PACKET_PATH_SMOKE_PASS / B2_08_BOARD_READ_PARTIAL / B3_FIXED_VECTOR_PASS / B3_COUNTER_BOARD_592_0_PASS / CLG484_2_FINAL_PHYSICAL_COMPLETE`

日期：2026-09-12

范围：规划与验收合同；NP0-NP7 已执行，当前转入传统 NPU + ENeuron 集成和 `xc7z020clg484-2` 板级路线；不直接改写已签核神经元 RTL。Pulse-Mini-L/L2 的 NP1-NP7 材料保留为历史对照，不作为当前日常门。

当前物理边界：现有单时钟和 T3 OOC 证据绑定 `xc7z020clg400-1`，只能作为结构/协议参考；目标 `xc7z020clg484-2` 的最终 routed 证据已在 2026-09-12 完成。

当前集成边界：最新计数器物理修复采用 `Performance_ExploreWithRemap`、post-route `AggressiveExplore` 和 route `Explore`；B2/NPU 合同回归已通过。`xc7z020clg484-2` 顶层 Vivado 2024.1 routed timing 全绿（`WNS=+0.008 ns`、`TNS=0`、`WHS=+0.036 ns`、`THS=0`、setup/hold 失败端点为 0、route/DRC hard error 为 0、DSP48E1=4），bit/XSA 已生成；合法 packet path、`0x40430000` 状态块和 execute/skip=`592/0` 均已有同源实板证据。B2-GATE 仍是发布门；B3 dense/full-open/bypass 固定向量已完成，静态 `2:4` 和 ENeuron A/B 尚未完成。

## 1. 目标

分别验证 ENeuron、Pulse-Mini-L、Pulse-Mini-L2 的局部时间证据能否为 NPU 产生硬件友好的结构化稀疏掩码，并证明掩码不仅减少非零权重，还能减少实际权重读取、计算发射、周期或动态功耗。

首版只回答四个问题：

1. 本地证据是否比随机掩码更能保留任务精度？
2. 它是否不差于简单的权重绝对值剪枝？
3. 每四条连接保留两条的掩码能否由小型硬件稳定地产生？
4. 共享计算通道能否利用该掩码真正跳过工作？

项目声明限定为“局部结构化剪枝控制器与动态门控原型”。它不等于通用 NPU 优化器、全局最优剪枝、神经架构搜索或任意第三方 DPU 的直接插件。

## 2. 非目标

- 第一版不做任意位置、任意稀疏率的逐权重压缩。
- 第一版不在一张图片或一个逻辑 tick 中途改变网络结构。
- 第一版不让 Host 在 TRAIN 中直接指定最终保留哪两条连接。
- 第一版不从当前失败的 D2 数字识别结果推导剪枝有效性。
- 第一版不实现全局排序、跨层预算优化、反向传播梯度或片上损失函数。
- 第一版不承诺 `2:4` 必然获得两倍速度；必须以实际权重读取、发射周期、吞吐和活动功耗证明收益。
- 动态恢复连接属于后续可选阶段，不能阻塞第一版剪枝闭环。

## 3. 第一性原理结论

### 3.1 为什么选择四条一组、保留两条

当前神经元天然有四个输入，`2:4` 不需要全层排序，每组只比较四个候选。固定每组恰好保留两条还具有三个工程优势：

- 地址和吞吐可预测；
- 可以用两个权重加四位掩码存储，或导出成两个权重加位置编码；
- 每组工作量恒定，适合共享 lane 和流水线。

自由稀疏虽然可能保留更高精度，但会引入索引、负载不均和不规则 BRAM 访问。第一版不选择它。

### 3.2 剪枝和动态门控必须分开

本计划定义两类掩码：

```text
structural_mask：训练阶段在安全边界产生，四位中恰好两位为 1
activity_mask：每个 tick 根据实际非零输入产生

issue_mask = structural_mask AND activity_mask
```

- `structural_mask` 决定模型结构。
- `activity_mask` 决定本 tick 是否有必要读取和计算。
- `issue_mask=0` 时，不读取该组权重；只推进必要的神经元泄放、阈值和时间状态。

如果 RTL 仍读取全部权重、完成全部加法后才把结果清零，只能称为数值门控，不能称为 NPU 加速。

### 3.3 为什么不能直接用带符号资格迹当重要性

资格迹表达局部时间关系，正负证据可能抵消。接近零既可能表示“完全无关”，也可能表示“强烈但方向相反的证据互相抵消”。因此必须先比较多种低成本评分，而不是预设资格迹一定优于权重幅度。

候选评分固定为：

| 编号 | 评分 | 用途 |
|---|---|---|
| S0 | `abs(weight)` | 必须存在的低成本基线 |
| S1 | 当前 `abs(eligibility_snapshot)` | 检验单次局部时间证据 |
| S2 | 4 位饱和累计的资格迹绝对值 | 检验多 episode 稳定证据 |
| S3 | 先按 S2，再以 `abs(weight)`、输入编号破同分 | 组合候选，不预设为赢家 |

S2 的首版更新规则保持简单：非零调制提交时，将资格迹绝对值量化为 `0..3`；旧分数先向零减一，再加入量化值并饱和到 `0..15`。确切移位和量化边界由固定向量与小范围扫描选择，审核后冻结。

## 4. 推荐 V1 架构

```text
ENeuron / NPU 局部学习事件
  weight[3:0]
  eligibility_snapshot[3:0]
  mod_commit
          │
          ▼
四路 4-bit utility score
          │
          ▼
四选二确定性选择器
          │
          ▼
structural_mask[3:0]
          │
          ├── 与 activity_mask 相交
          ├── 控制 BRAM 读请求
          └── 控制 MAC/突触 lane 发射
```

### 4.1 每四条连接新增状态

| 状态 | 位数 | 说明 |
|---|---:|---|
| `utility[0..3]` | 16 | 四路各 4 位无符号饱和分数 |
| `structural_mask` | 4 | 初始为 `1111`；剪枝后必须恰好两位为 1 |
| `mask_valid` | 1 | 区分未剪枝和已提交状态 |

合计 21 位/四连接组，不含共享的 commit ID、观察窗口计数和控制状态。

对于约 101632 条连接的代表性 `784→128→10` 网络，共 25408 组，仅上述分数和掩码约需 533568 bit，原始容量约 15 个 RAMB36。该数字是存储位数估算，不是 Vivado 映射结果。

### 4.2 确定性四选二

四种方法的比较键分别冻结为：

- S0：`abs(weight)`，再以更小输入编号破同分；
- S1：最新一次非零调制对应的证据等级，再以更小输入编号破同分；
- S2：累计 `utility`，再以更小输入编号破同分；
- S3：累计 `utility`，再以 `abs(weight)`、更小输入编号破同分。

S2 不使用权重破同分，否则会与 S3 退化成同一算法，失去消融意义。

选择前两名。相同输入、相同状态和相同命令序列必须得到相同掩码，不允许依赖 Python 容器顺序或 RTL 的未定义比较结果。

RTL 推荐使用四拍扫描维护当前第一名和第二名，不在一个周期内构造完整排序网络。这样容易控制时序，也适合未来 BRAM/lane 复用。

### 4.3 状态与命令边界

- 硬复位：分数清零，掩码恢复 `1111`，`mask_valid=0`。
- 样本 `STATE_CLEAR`：保留分数和结构掩码，只清样本动态状态。
- `PRUNE_CLEAR`：只允许 CONFIG，清分数并恢复稠密掩码。
- `PRUNE_COMMIT`：只允许 TRAIN、核心空闲、没有未消费资格快照或调制提交时接受。
- 每次成功的本地证据观察携带严格递增的 16 位 observation ID；重复、倒序或越界观察拒绝，防止同一快照重复累计。
- `MASK_READ`：任意空闲模式可读。
- `MASK_WRITE`：只允许 CONFIG，用于初始化、测试和恢复；TRAIN/INFER 必须拒绝。
- INFER：结构掩码冻结；动态活动门控仍按每 tick 输入工作，但不得改变分数或结构。
- 每个已接受的剪枝命令恰好产生一个响应；重复 commit ID 或忙时命令不得改变状态。
- V1 在 `mask_valid=1` 后拒绝第二次剪枝提交；只有 CONFIG 的 `PRUNE_CLEAR` 能恢复稠密状态并开启下一轮，禁止被剪连接在 TRAIN 中自动长回。

Host 可以决定“何时请求评估”，但不能在 TRAIN 中提供掩码内容。最终选择必须由片上分数和确定性规则生成。

### 4.4 被剪连接的 V1 行为

- 保留原权重只用于审计和 CONFIG 恢复，数据路径将其视为零。
- 被剪连接不再更新权重、trace、eligibility 或 utility。
- 提交掩码时清除被剪连接的学习历史，避免旧资格迹污染后续训练。
- V1 不允许 TRAIN 自动恢复被剪连接；恢复只能回到 CONFIG 或执行 `PRUNE_CLEAR`。

这对应“稠密预热 → 局部剪枝 → 剩余连接微调 → 冻结推理”。动态恢复放到 NP8，避免第一版同时处理不可观察连接的评分问题。

## 5. 三种实现方案比较

| 方案 | 精度潜力 | 硬件规律性 | 真正加速难度 | 结论 |
|---|---|---|---|---|
| 任意逐权重稀疏 | 最高 | 差 | 高 | 不进入 V1 |
| 每组固定 `2:4` | 中高 | 高 | 低 | V1 主线 |
| 整神经元/通道关闭 | 风险较高 | 最高 | 最低 | 作为 NP7 对照 |

整神经元门控可能带来更明显的周期收益，但一次错误决策会删除完整特征。必须在 `2:4` 已建立可靠基线后再比较。

## 6. 任务和证据矩阵

### B0：评分与协议微测试

- 枚举四路分数、权重同分和输入编号破同分。
- 覆盖全部 16 种掩码输入以及非法 `0/1/3/4` 保留数。
- 覆盖饱和、衰减、清除、重复提交、忙时提交和模式错误。
- 用手算向量证明每次提交恰好选择两条。

### B1：现有 `4→2→2` 小网络

- ENeuron、Pulse-Mini-L、Pulse-Mini-L2 使用同一数据拆分、seed、剪枝时点、微调预算和解码规则，各自独立运行并报告。
- 只剪两个隐藏神经元的四输入组，输出层两输入连接保持稠密。
- 复用已有训练账本和 20 个留出扰动样本。
- 比较 dense、随机 `2:4`、S0、S1、S2、S3。
- 训练前、剪枝前、剪枝后、微调后和 INFER 后分别冻结权重、分数和掩码指纹。

B1 只能证明协议和局部任务可行，不能证明复杂 NPU 模型剪枝有效。

B1 已完成（2026-08-28）：三种神经元均从各自同一稠密 checkpoint 分支 dense/random/S0-S3；S0-S3 都保持 20/20，随机相同掩码均为 10/20。四种评分全部选择 `0011/0011`，因此 B1 通过协议闭环，但不具备评分辨识力。完整结果见 `docs/reports/LOCAL_PRUNE_B1_REPORT.md` 和 `artifacts/results/local_prune_b1_results.json`。

B1 的全网络发射计数减少仅为 ENeuron 18.21%、Pulse-Mini-L/L2 19.78%，未达到 NP7 的 45% 系统收益门；这是只剪隐藏层且输出层保持稠密时的真实结果，不按理论 50% 稀疏率虚报。

### B2：冗余网络压力任务

新增至少一个每组包含冗余与干扰连接的 `4→8→2` 或等价固定小网络。任务必须满足：

- 稠密模型在多种子留出集稳定通过；
- 随机 `2:4` 明显弱于有信息评分；
- 至少存在两种等价或近等价局部路径，避免任务只能由唯一连接完成；
- 掩码不能从标签或样本 ID 直接推导。

B2 已完成首轮 10-seed 压力实验（2026-08-28）：冻结为 `4→8→2`，每类四个四输入 detector，输出至少需要 3/4 detector 响应。ENeuron/L2 的 S2/S3 均为 median BAcc 100%，Pulse-Mini-L 为 0%；完整报告见 `docs/reports/LOCAL_PRUNE_B2_REPORT.md`。

ENeuron/L2 的 S2 分别比随机 median 高 25/75 个百分点，且 10/10 seed 不低于随机；L 比随机低 25 个百分点，仅 3/10 seed 不低于随机。S3 相对 S2 为 0 个百分点，因此候选降级为更简单的 S2。

保持精度的 ENeuron/L2 全网络读取只减少 33.33%，未达到 45% 门；L 的 66.67% 伴随 BAcc 0%，不计为有效收益。三线当前均为 `RTL_NO_GO`。

NP2 后续量化扫描已修正 Pulse-Mini-L 的结论：固定把二值非零证据映射到等级 2 后，L 的 S2 BAcc/coverage 恢复到 100%，10/10 seed 不低于随机。三模型最小合格 gain 分别为 ENeuron/L/L2=`1/2/1`，完整证据见 `docs/reports/LOCAL_PRUNE_NP2_REPORT.md` 和 `artifacts/results/local_prune_np2_results.json`。三线仍因全网读取只减少 33.33% 而保持 `RTL_NO_GO`。

### B2.1：输出侧结构剪枝与通道门控

目的不是继续调四输入隐藏组，而是消除 B2 已定位出的输出层瓶颈。稠密全网为 240 次读取，隐藏层 S2 后为 80 次隐藏读取加 80 次输出读取；45% 系统门要求总读取不超过 132，因此输出侧最多允许 52 次读取。

候选按 KISS 顺序执行：

1. **输出层 `2:4`**：八个 detector 全部保留，只在每个四输入输出组中保留两条连接。若活动分布不变，预计为 80 次隐藏读取加至多 40 次输出读取，总计至多 120，理论减少至少 50%。这是首选，因为可复用同一个本地 `2:4` 控制器。
2. **整 detector `3:4` gate**：每类关闭一个 detector，并同步关闭对应输出连接。按当前活动分布预计为 60 次隐藏读取加至多 60 次输出读取，总计至多 120；三条保留输出连接的权重和仍可达到原阈值，可能不需要稀疏微调，但会增加通道 enable 和路由门控。
3. **整 detector `2:4` gate**：每类只启用两个 detector，并同步关闭对应输出连接。预计为 40 次隐藏读取加至多 40 次输出读取，总计至多 80，理论减少约 66.67%；但它同时改变隐藏计算量和输出动力学，作为更激进的第三候选。

上述数字只是固定 B2 活动分布下的预算，不是验收结果；三种候选都必须由同一计数器重新测量。最终选择通过全部硬门且控制状态、比较器、路由门控和微调需求最少者，不预设理论读取最少的方案获胜。

软件合同：

- ENeuron、Pulse-Mini-L、Pulse-Mini-L2 全部运行；分别冻结 NP2 选出的 gain=`1/2/1`，不得借用其他模型结果。
- 输出 utility 只能来自 detector 发放、输出响应和延迟调制的本地 TRAIN 账本；禁止使用标签、样本 ID 或 Host 直接写 mask。
- 输出掩码、detector enable 和输入活动必须在权重读取/计算发射前相交；分别统计结构跳过、通道关闭和输入本来为零，禁止重复记账。
- 输出稀疏后不得直接改阈值或覆盖权重；只能用既有训练事务微调保留连接。若两条保留连接无法通过正常训练恢复发放，则该候选失败。
- 比较 dense、hidden-S2、hidden-S2+output-2:4、hidden-S2+detector-3:4、hidden-S2+detector-2:4，以及共享随机 mask、过早提交、分数打乱和错误符号负对照。
- 至少 10 个固定 seed；记录 BAcc、coverage、逐层读取/发射、微调样本数、mask 同分率/饱和率/稳定性、拒绝计数和 INFER 冻结摘要。

B2.1 通过门：

- median BAcc ≥98%，median coverage ≥98%，且相对各自 dense 下降均不超过 2 个百分点；
- 全网络实际读取和计算发射均减少至少 45%，即当前固定任务中均不超过 132；
- 至少 8/10 seed 不低于共享随机对照；若只与随机并列，只能称为“冗余通道消除”，不能宣称输出 utility 优于随机；
- TRAIN 中 Host 直接写 mask/被剪权重为 0，INFER 中权重、utility、mask 和 enable 全部冻结；
- 若多个候选通过，按“无需直接参数改写、微调更少、控制状态更少、路由更简单”的顺序选一个；其余只保留为对照，不并入 RTL。

B2.1、NP2 剩余统计和 NP3 负对照未同时通过前，禁止启动 NP4-NP7。

B2.1 已完成（2026-08-28）：三模型的 output-2:4、detector-3:4、detector-2:4 均保持 BAcc/coverage 100%；全网读取/发射分别为 120/120/80，10/10 seed 不低于共享随机 mask。按 KISS 冻结 output-2:4，因为它复用既有控制器且不新增跨层 channel enable。软件联合门允许启动 NP4，但不代表 RTL 已证明。完整证据见 `docs/reports/LOCAL_PRUNE_B21_REPORT.md` 和 `artifacts/results/local_prune_b21_results.json`。

### B3：图像任务

当前 D2 稠密 ENeuron 测试 BAcc 只有 4.74%，不能作为剪枝正向基线。只有在修订后的稠密图像模型先达到原门槛后，才允许加入剪枝比较：

- 至少 8/10 validation seeds 通过；
- test BAcc ≥70%；
- coverage ≥90%；
- 标签打乱和固定权重对照失败。

剪枝不能用来掩盖稠密模型本身没有学会的问题。

## 7. 验收门槛

### 7.1 功能和来源

- 每个有效组严格 `2:4`，任何非法掩码均被拒绝。
- 同一输入和事务序列 bit-exact、确定性复现。
- TRAIN 中成功的 `MASK_WRITE=0`；结构改变只来自本地分数和 `PRUNE_COMMIT`。
- INFER 中权重、分数、结构掩码和学习状态冻结。
- 完整账本记录 commit ID、四路分数、权重、旧掩码、新掩码和破同分原因。

### 7.2 任务能力

- B1：微调后保持原有 20/20 留出正确率；随机同稀疏率结果只作报告，不用这个过小任务强判评分优劣。
- B2：至少 10 个固定 seed；微调后 balanced accuracy 相对稠密基线下降不超过 2 个百分点，coverage 下降不超过 2 个百分点。
- B2 中，入选本地评分的 median BAcc 必须比随机 `2:4` 高至少 5 个百分点，并在至少 8/10 seeds 上不低于随机；否则先判定 B2 缺少评分辨识力，不进入 RTL。
- 先在 S0 与 S2 中选出满足上述任务门的更简单候选；S3 只有在 median BAcc 比该候选高至少 2 个百分点，或用不超过该候选 75% 的微调样本达到与其相差不超过 1 个百分点的 BAcc 时，才值得增加权重破同分路径。否则保留 S0/S2 中通过门且成本更低者。
- 报告立即剪枝损失和微调恢复量，禁止只展示恢复后的最好结果。

### 7.3 稀疏和真实工作量

- 结构权重密度固定为 50%。
- 稠密激活条件下，发出的权重读取和突触/MAC 操作至少减少 45%。
- 稀疏激活条件下单独报告 `issue_mask` 的实际减少量，不把输入本来为零造成的跳过归功于结构剪枝。
- 通用候选目标是共享 lane 版本每组处理周期减少 35%；正式 NP7 专用验收门槛以 NP7 合同为准，即同 lane 数 dense 基线至少减少 25%。若周期不降，只能报告存储或活动收益。
- 导出格式至少比较：32 bit 稠密四权重，与 16 bit 两权重 + 4 bit 掩码。后者原始权重存储减少 37.5%，不是 50%。

### 7.4 RTL 与物理实现

- Python/RTL 对全部可见状态和 mask 逐事务一致。
- 至少 20 seeds × 1000 个混合事务。
- 有限形式检查覆盖 exact-two、非法命令无副作用、INFER 冻结、重复提交和原子 mask 切换。
- XC7Z020、Vivado 2024.1、100 MHz routed：WNS ≥0、TNS=0、setup/hold 零失败、DRC Error/Critical Warning 为 0。
- 单组/单核分别报告基线和新增 LUT、FF、BRAM、DSP；资源减少不能只由删除功能获得。
- 功耗比较必须使用相同活动序列生成的 SAIF/VCD。vector-less 估算不作为门控收益证据。

## 8. 实施 TODO

### NP0：审核冻结八项决策（已批准）

- [x] 冻结 V1 为每连续四条连接恰好保留两条。
- [x] 冻结结构掩码只在 TRAIN 的安全边界改变，INFER 期间冻结。
- [x] 冻结动态门控为 `structural_mask & activity_mask`，并要求在 BRAM/MAC 发射前生效。
- [x] 冻结 S0/S1/S2/S3 四组评分对照，S3 只是候选而非预定赢家。
- [x] 冻结每组 4×4 位 utility、4 位 mask 和 1 位 valid 的状态预算。
- [x] 冻结 V1 被剪连接不自动恢复；动态恢复单列 NP8。
- [x] 冻结 B0/B1/B2 顺序；D2 稠密任务未过门前禁止做图像剪枝声明。
- [x] 冻结精度、真实工作量、RTL、时序和功耗四类证据必须同时报告。

批准附加范围：ENeuron、Pulse-Mini-L、Pulse-Mini-L2 三种神经元必须分别完成 NP1-NP3 软件实验；只有各自软件证据明确后，才决定对应的 NP4-NP7 硬件实现路线。

### NP1：黄金模型与不可作弊计数器

- [x] 新建 `local_prune_reference.py`，实现分数更新、四选二、命令状态和确定性日志。
- [x] 新建 `test_local_prune_reference.py`，完成 B0 枚举与协议测试。
- [x] 增加 `weight_reads_issued`、`synapse_ops_issued`、`groups_skipped`、`mask_commits` 和非法命令计数。
- [x] 明确“逻辑上乘零”和“没有发出读取/计算”是不同计数。
- [x] 固定黄金向量和源文件 SHA-256。

NP1 签核证据（2026-08-28）：19 项测试通过；固定摘要见 `artifacts/results/local_prune_b0_results.json`。工作量账本同时记录稠密请求、实际读取、结构节省、全零不活动组和被结构完全跳过组，避免把输入本来为零误算成剪枝收益。

硬门：所有 B0 手算向量通过；非法路径不改变任何架构状态。

### NP2：评分方法软件消融

- [x] ENeuron、Pulse-Mini-L、Pulse-Mini-L2 分别在 B1/B2 上比较 dense、随机 `2:4`、S0、S1、S2、S3。
- [x] 预注册 seed、训练预算、剪枝时点、微调预算和解码规则。
- [x] 扫描最小量化参数，不允许为每个测试 seed 单独调参。
- [x] 输出精度、coverage、掩码分布、同分率、分数饱和率和掩码稳定性。
- [x] 对 S3 相对 S0/S2 合格候选做逐 seed 配对比较。

B1/B2 和最小量化扫描已完成。三模型分别选择 S2 gain=`1/2/1`，BAcc/coverage 都为 100%；入选配置边界同分、clip 和最终占满率均为 0%，前缀稳定性与误导保持率均为 100%。S3 相对 S2 没有收益，删除额外权重破同分硬件。NP2 完成。

停止条件：若 S3 不满足 7.2 的明确收益条件，则不实现 S3 的额外权重破同分路径；保留 S0/S2 中通过任务门且成本更低者。当前 B2 结果选择 S2，不回退到已失败的 S0。

### NP3：剪枝—微调闭环

- [x] 固定 `dense warm-up → PRUNE_COMMIT → sparse fine-tune → INFER` 流程。
- [x] TRAIN 账本证明 Host 未直接写掩码或被剪权重。
- [x] 剪枝提交时清理被剪连接的 trace、eligibility 和 snapshot。
- [x] 比较一次剪到 50% 与分两次渐进剪枝；若一次剪枝精度同样稳定，保留更简单流程。
- [x] 增加错误符号调制、分数打乱、随机掩码和过早剪枝负对照。

硬门：B1/B2 满足 7.2，且稀疏微调期间结构掩码不被意外覆盖。

B1/B2/NP3 闭环已完成。三模型从同一父 checkpoint 运行一次、软件渐进和错误符号分支；一次与渐进均为 100%，错误符号均为 0%，因此选择一次剪枝。账本证明零 Host mask 写入、每 detector 一次 commit、两次公平微调、被剪权重/历史冻结和同分支 INFER 指纹不变。完整证据见 `docs/reports/LOCAL_PRUNE_NP3_REPORT.md`。

当前硬门结论：三模型已通过 NP2/NP3，B2.1 output-2:4 将全网读取/发射降到 120，减少 50%；NP4B 已完成正式接入，NP5 已完成协同仿真和形式检查，NP6 的七配置物理结论为 `PARTIAL`，NP7.0-NP7.7 已签核。当前执行入口已转为传统 NPU + ENeuron 单时钟 V2 时序修复审核；历史软件、NP6 或 NP7 证据不能替代当前集成 RTL 的 100 MHz OOC。

### NP4：局部剪枝 RTL

- [x] 用户审核并冻结 B2.1 推荐的六项 NP4 V1 接口决定。
- [x] 新建独立 `local_prune_gate_2of4.sv`，暂不侵入已签核核心。
- [x] 使用多周期四路扫描生成前两名，明确每条命令的精确延迟。
- [x] 接入 ENeuron snapshot/mod commit 旁路或测试适配器，不复制神经元方程。
- [x] 提供 `OBSERVE / PRUNE_CLEAR / PRUNE_COMMIT / MASK_READ`；CONFIG 测试口单独控制。
- [x] 所有状态只使用主时钟和同步使能，不生成门控时钟。
- [x] 添加定宽综合审计端口，综合版本不依赖字符串日志。
- [x] 同一控制器支持隐藏层组和输出层分账；V1 不实现整 detector channel enable。
- [x] 三模型固定 evidence gain=`1/2/1`，控制器不存在直接权重恢复写口。
- [x] Pulse-Mini-L/L2 wrapper 在 FEEDBACK 接受沿锁存 evidence、成功响应后提交 OBSERVE。
- [x] 建立真正四输入的输出分组 wrapper；没有用原 `4→2→2` tile 的两输入输出核冒充输出 `2:4`。

硬门：不修改原 ENeuron 与 Pulse-Mini 的冻结行为；新模块可独立旁路。

NP4 V1 六项决定已于 2026-08-29 获用户批准并冻结：隐藏层和输出层统一严格 `2:4`；三模型 evidence gain 固定为 `1/2/1`；每组只允许一次原子 `PRUNE_COMMIT`；不实现整 detector/channel enable；输出稀疏后的恢复只走既有 TRAIN/FEEDBACK；`issue_mask` 必须在权重读取和计算发射前形成，并分别统计隐藏层与输出层结构节省。批准只开放 NP4/NP5 实现，不代表 RTL、资源、时序或功耗已经通过。

NP4A 公共控制器已于 2026-08-29 通过：四拍扫描、原子双位 mask、固定 gain 适配器、读取前 `issue_mask` 和层级分账均已实现。NP4B 八项实现决定同日获用户批准并已完成实施：ENeuron 导出正式 committed snapshot，Pulse wrapper 在 FEEDBACK 清除前锁存 evidence，并建立真正四输入的输出分组。NP4B 完成边界见 `docs/planning/NPU_PRUNING_NP4B_TODO.md`；`docs/reports/LOCAL_PRUNE_RTL_REPORT.md` 只保留 NP4A 的历史基线，不作为 NP4B 当前状态来源。

NP6 已完成并合并：7 个配置均实现完成、route/DRC error 为 0，但只有 gate 与 ENeuron 剪枝封装通过 100 MHz，因此状态为 `NP6_PHYSICAL_COST_PARTIAL`。NP7 共享 BRAM/lane 已完成并合并，当前剪枝主线进入传统 NPU + ENeuron 集成的 OOC 物理门。

### NP5：协同仿真和形式检查

- [x] 建立 Python/Icarus 逐事务协同仿真：三模型各 20×1000，总计 60000 个混合事务。
- [x] 覆盖 utility/evidence 边界、完全同分、忙时、重复/倒退 observation ID 和第二次 commit；S2-only 不再引入已淘汰的权重绝对值比较器。
- [x] 证明 mask 只原子切换，不出现瞬时 `1:4`、`3:4` 或未知位。
- [x] 证明 INFER 不写 utility/mask，非法命令不改变状态。
- [x] 建立负向实现，去掉原子提交或反转 tie-break 均产生固定反例。
- [x] 完成 depth=32 有限形式检查，并额外证明一次真实成功 commit 可达，排除空证明。

NP5 当前签核范围仅为独立公共控制器；三核心 wrapper 完成后仍需重新做端到端逐事务协同仿真，不能直接沿用本次结果替代集成验证。

### NP6：单组物理成本

- [x] 对独立剪枝模块、ENeuron 和 Pulse-Mini-L/L2 的冻结矩阵完成 7 次综合与实现。
- [x] 报告 LUT/FF/BRAM/DSP、WNS/WHS、TNS/THS、失败端点、DRC、route status 和 vector-less 功耗。
- [x] 对可比 wrapper 报告物理增量；ENeuron 不同微架构配对明确标 `NOT_COMPARABLE`。
- [x] 建立只读 manifest verifier、冻结字节三方绑定和 12 项 mutation 负向控制。

硬门结果：未全通过，阶段结论为 `PARTIAL`。不得把 NP6 写成整体 100 MHz 签核成功；下一阶段必须独立证明共享 lane 的周期收益。

### NP7：真正跳算的共享 lane

- [x] 建立四权重稠密组与“两权重 + 两个 2-bit 位置索引”的稀疏格式；结构掩码由索引唯一重建，不保存第二份真值。
- [x] 调度器只为 `issue_mask` 中有效连接产生读请求和 lane 操作。
- [x] `issue_mask=0` 时走零突触快速路径，但仍保持神经元时间状态 bit-exact。
- [x] 比较 1/2/4/8 lane 的周期、持续吞吐、存储读取和输出拥塞。
- [x] 增加“全读后门控”和“MAC 后清零”负向版本，证明性能 verifier 能拒绝伪收益。
- [x] 与稠密参考逐 tick、逐膜状态、逐输出 bit-exact。

硬门已通过：NP7.3 共 160 配置、160,000 事务逐拍比对零失败；NP7.7 的 dense/sparse × 1/2/4/8 lane 八种配置在其绑定的 Vivado 2024.2、`xc7z020clg400-1`、100 MHz OOC 条件下 8/8 收敛。该结论只证明共享执行原型，不外推到当前单时钟集成 RTL、板级 DMA/网口吞吐或真实功耗。权威边界见 `docs/planning/NPU_PRUNING_NP7_TODO.md` 与 `docs/reports/LOCAL_PRUNE_NP7_SHARED_LANE_REPORT.md`。

### NP8：可选动态恢复

状态：`DEFERRED_OPTIONAL`。动态恢复不属于当前 ZYNQ7020 NPU MVP，也不计入活动 TODO；首次板上 dense/static-2:4/live-ENeuron A/B 完成后，仅在静态结构精度损失确有需要时重新立项。

- 候选合同保留为：固定探测窗口或单连接轮换探测，不允许每 tick 随机抖动结构。
- 恢复连接只能使用确定性初始化；每个观察窗口最多替换一条，并限制最小驻留时间和掩码变化率。
- 后续若立项，必须报告相对静态 `2:4` 的精度收益、额外计算、掩码 churn 和恢复失败率。

停止条件：若恢复不能带来稳定精度收益，保留静态 V1，不为“动态”名称增加硬件。

### NP9：网络与板级签核

NP9 已并入 `docs/planning/TODO.md` 的 P16-B2/B3/B4，避免维护第二套板级任务。当前器件固定为 `xc7z020clg484-2`：B2 关闭 DMA/协议，B3 关闭 NPU + ENeuron 功能与 routed/CDC/DRC，B4 在同权重、输入和时钟下完成 dense、static `2:4`、live-ENeuron 的吞吐与板上功耗 A/B。图像剪枝仍以后续独立任务处理，不进入当前 MVP。

## 9. Go / No-Go

进入 RTL 的条件：

1. B1/B2 稠密任务本身稳定通过。
2. S0/S2 至少一个通过任务门；S3 只有相对其中更简单的合格候选有明确收益才允许增加额外路径。
3. 随机同稀疏率对照明显更差，证明选择不是无关紧要。
4. 精度恢复不依赖 TRAIN 中直接写掩码或权重。

可以声明“NPU 局部自动剪枝与动态门控原型”的条件：

1. 结构始终合法 `2:4`。
2. 精度和覆盖率满足任务门。
3. 权重读取与计算发射真实减少。
4. RTL、形式检查和 100 MHz routed 均通过。
5. 活动文件或板测支持功耗结论。

任一条件失败时必须降级声明：

- 只有精度与稀疏率：称“结构化掩码实验”。
- 读取减少但周期不降：称“带宽/活动门控”，不称加速。
- 只有 vector-less 功耗：称“功耗估算”，不称节能实测。
- S3 不优于更简单的合格候选：删除 S3 的额外权重破同分路径；当前 B2 保留 S2，不能回退到已失败的 S0。

## 10. 推荐实施顺序

```text
NP0 用户审核
→ NP1 黄金模型和不可作弊计数
→ NP2 S0/S1/S2/S3 消融
→ NP3 剪枝—微调闭环
→ NP4/NP5 局部 RTL 与验证
→ NP6 XC7Z020 单组物理成本
→ NP7 共享 lane 真正跳算
→ NP8 动态恢复（可选）
→ NP9 系统/板级签核
```

## 11. 资料依据

- [AMD Vitis AI UG1414：Fine-Grained Pruning](https://docs.amd.com/r/en-US/ug1414-vitis-ai/Fine-Grained-Pruning)：细粒度剪枝需要跳零和压缩硬件；支持连续权重块的 N:M 结构。
- [AMD Vitis AI UG1414：Iterative Pruning](https://docs.amd.com/r/en-US/ug1414-vitis-ai/Iterative-Pruning)：迭代剪枝采用稠密基线、逐步剪枝和微调，避免一次删除过多导致无法恢复。
- [NVIDIA TensorRT：Sparsity](https://docs.nvidia.com/deeplearning/tensorrt/latest/inference-library/data-formats-tensors.html#sparsity)：结构化稀疏要求每四个权重至少两个为零；满足格式不代表运行时一定选择稀疏策略。
- [Structured RigL](https://arxiv.org/abs/2305.02299)：非结构化动态稀疏难以获得真实硬件收益，固定扇入的结构化动态稀疏更适合执行硬件。
