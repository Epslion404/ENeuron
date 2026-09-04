# 传统 NPU + ENeuron 单时钟 RTL 时序修复 V2 审核稿

状态：`REVIEW_REQUIRED / RTL_CHANGES_BLOCKED`

日期：2026-09-04

## 1. 为什么需要 V2

TR1-TR6 已完成实现与验证：四条共享 signed 8×8 lane 被 Vivado 2024.1 映射为恰好 4 个 `DSP48E1`，单时钟专项 8/8、固定 `20×100` 随机逐 beat 和完整仓库 473/473（1 skipped）均通过。

同一实现提交 `50550733e4af4779f3d6933738fa043ecb919970` 的 XC7Z020、100 MHz OOC 结果仍是 setup 失败：`WNS=-0.673 ns`、`TNS=-6.462 ns`、22 个失败端点；hold、route、DRC 和四 DSP 结构门均通过。因此 V1 不能签核为 100 MHz 收敛，但它已把旧版 `WNS=-5.087 ns`、244 个失败端点缩小到新的两类局部路径。

## 2. 新关键路径分类

第一类也是最差路径：`compute_group_index` 选择当前四个激活值，经过一个 `DSP48E1` 乘法和四乘积求和 carry chain，到达 `lane_sum_latched`。最差数据路径 10.651 ns，含 11 级逻辑：3 个 LUT、1 个 DSP48E1、2 个求和 LUT 和 5 个 CARRY4。该路径说明仅增加最终 WRITEBACK 不足以解决当前首要瓶颈。

第二类路径从 `compute_group_index` 到 `logit_values` 分布式存储写使能，最差约 `-0.071 ns`，逻辑延迟不大但布线占主导。第一类路径修复后，它会成为新的签核阻断项。

## 3. 方案比较

### 方案 A：锁存激活操作数，并增加统一 WRITEBACK（推荐）

- 在每个启用组的 `FETCH` 拍同时锁存四个 signed 8-bit 激活值；权重继续锁存在现有 `model_word_latched`。
- `EXECUTE` 只读取锁存后的四个激活值和权重，不再用 `compute_group_index` 动态访问 `input_pixels` 或 `hidden_values`。
- L0/L1 各增加一个 WRITEBACK 状态。最后启用组在 COMMIT 形成最终值后进入 WRITEBACK；最后关闭组在 FETCH 锁存当前累加值后进入同一 WRITEBACK。数组写使能只由 WRITEBACK 状态产生。
- 继续强制恰好 4 个 DSP48E1；不增加乘法器，不改变 INT32、mask、epoch、背压、freeze/clear 或外部端口。

预估代价：约增加 64 个寄存器（四个激活值 32 bit、最终值 32 bit）和少量状态/选择逻辑；每样本固定增加 42 拍，对 V1 全开周期 1860 拍约增加 2.26%。100 MHz 下理论计算上限由约 53.8k 降到约 52.6k samples/s。实际资源与时序仍必须由 Vivado 报告裁定。

### 方案 B：再增加乘积寄存拍

四个 DSP 先把 16-bit 乘积写入寄存器，下一拍再进行四路求和。它更容易获得时序余量，但每个启用组再增加一拍：全开样本额外增加 592 拍，吞吐代价明显高于方案 A。只有方案 A 重跑后仍未收敛时才进入审核。

### 方案 C：手工实例化 DSP48E1 级联

用 DSP 级联通路完成乘积累加，可能减少通用布线，但会把当前简单推断式 RTL变成器件专用结构，验证、符号扩展和级联布局风险更高。当前仅差 0.673 ns，不建议在 A 未验证前采用。

## 4. 待管理员批准的六项裁定

### TR7：FETCH 锁存四个激活操作数

对启用组，在 FETCH 同时锁存四个 signed 8-bit 激活值和现有 32-bit 权重 word。关闭的非末组继续直接推进，不进入 EXECUTE。

### TR8：EXECUTE 禁止动态数组索引

四个 DSP48E1 的两个操作数必须都来自 FETCH 后稳定的寄存器；EXECUTE 到 `lane_sum_latched` 的路径不得再包含 `compute_group_index` 驱动的输入/隐藏数组选择器。

### TR9：统一独立 WRITEBACK

L0/L1 每个神经元只在各自 WRITEBACK 状态写 `hidden_values` 或 `logit_values`。最后启用组和最后关闭组都必须经过 WRITEBACK，禁止从 FETCH/COMMIT 直接写数组。

### TR10：精确周期合同更新

每个样本固定增加 42 个 WRITEBACK 周期；C1/C2/C3/C4 的计算延迟分别由 `1860/1856/676/1858` 更新为 `1902/1898/718/1900`。启用组数和 DSP 执行次数仍为 `592/590/0/591`。

### TR11：四 DSP 硬门继续有效

综合 utilization 必须 `DSP=4`，实现网表必须 `DSP48E1_COUNT=4`。不能因修复时序把乘法退回 LUT，也不能额外使用 DSP 实现求和、计数器或写回。

### TR12：验证和停止条件

先更新 C1-C4 的周期与白盒状态合同，再修改 RTL；随后依次运行单时钟专项、固定 `20×100`、完整仓库回归和同器件同约束 Vivado OOC。只有 `DSP=4`、setup/hold 失败端点均为 0、route/DRC error 为 0 才能签核。若方案 A 仍失败，保留完整报告并重新审核方案 B，不自动继续加流水。

## 5. 审核停止点

当前仅形成 V2 方案和任务边界，不修改 RTL、不更新测试周期。等待管理员批准 TR7-TR12；批准后才按“测试 RED → 最小 RTL → 功能回归 → Vivado OOC”执行。
