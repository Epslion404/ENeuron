# 单时钟 NPU 时序修复测试合同 V1

状态：`PREPARED / BLOCKED_BY_TR1_TR6_APPROVAL`

日期：2026-09-04

## 1. 用途

本合同把 `NPU_SINGLE_CLOCK_TIMING_REPAIR_V1.md` 的 TR1-TR6 转成可执行测试要求。它只冻结批准后的测试改动，不授权当前修改业务 RTL，也不把准备完成误写成 100 MHz 已收敛。

## 2. 不变的黑盒合同

以下既有测试必须继续通过，且不得通过放宽期望值适配新流水：

- `test_npu_single_clock_skeleton.py`：模型配置、8-beat 输入、10-beat 输出、错误响应与结果背压。
- `test_npu_single_clock_mask.py`：mask staging/publish、首拍 epoch 激活和连续样本边界。
- `test_npu_single_clock_control.py`：abort、clear、freeze、运行期阻塞和冻结推理。
- `test_npu_single_clock_compute.py`：隐藏饱和、INT32 logit、两层最后一组和 mask 实际门控。
- `test_npu_single_clock_random.py`：固定 `20×100` 逐 beat bit-exact、结果 metadata、背压和 mask 轮换。

这些测试均以 ready/valid 或 `result_valid` 推进，不把旧的 1268 拍计算延迟当成外部协议。现有 `repeat(10)` 用于消费十个结果 beat，不是固定计算等待。

## 3. 最小白盒观察方式

只扩展 `tb_npu_eneuron_single_clock_compute.sv`，通过 testbench 层次读取 `dut.compute_state`、`dut.compute_unit_index`、`dut.compute_group_index`、`dut.model_word_latched` 和 `dut.lane_sum_latched`。不为验证新增综合端口，不改变外部 ready/valid 接口。

观察统一放在时钟边沿后的稳定采样点，并维护每个样本独立的：

- 计算起始与 `result_valid` 首次出现的周期计数；
- L0/L1 `EXECUTE` 次数；
- L0/L1 `COMMIT` 次数；
- 当前启用组在 `EXECUTE` 时锁存的 unit/group/model word。

## 4. 必须先形成的 RED

在 RTL 增加新状态前，测试应因缺少 `EXECUTE/COMMIT` 三拍合同而失败，不能先修改 RTL 再补同向测试。RED 只证明测试命中了待实现行为，不进入完整回归或 Vivado。

## 5. 四组确定性样本

### C1：默认全开 mask

沿用样本 `0x101`。两层共有 `32×16 + 10×8 = 592` 个启用组。

V1 必须满足：

- `EXECUTE=592`，`COMMIT=592`；
- 从第 8 个输入 beat 接受到结果槽建立的计算延迟为 1860 拍；
- 结果保持既有 `logit0=137`、`logit9=59`。

### C2：关闭 L0 bit0 与 L1 bit79

沿用样本 `0x102` 和 epoch 1，启用组数为 590。

V1 必须满足：

- `EXECUTE=590`，`COMMIT=590`；
- 计算延迟为 1856 拍；
- 被关闭的 L0 unit0/group0 与 L1 unit9/group7 不得进入 `EXECUTE/COMMIT`；
- 结果保持既有 `logit0=-117`、`logit9=-1`。

### C3：全关闭 mask

增加 epoch 2 和样本 `0x103`，19 个 mask word 的有效位全部为 0。

V1 必须满足：

- `EXECUTE=0`，`COMMIT=0`；
- 计算延迟为 676 拍；
- 所有组都在 `FETCH` 直接跳过；
- bias 仍然有效，结果为 `logit0=3`、`logit1=-5`、`logit9=-1`，其余为 0。

### C4：L0 最后一组关闭且已有非零累加

增加 epoch 3 和样本 `0x104`：除 L0 bit15 外全部启用。该 bit 对应 hidden0 的最后一组；hidden0 已由 group0 累加到 600，因此可定向检查“关闭的最后一组在 `FETCH` 用当前累加器完成饱和写回”。

V1 必须满足：

- `EXECUTE=591`，`COMMIT=591`；
- 计算延迟为 1858 拍；
- L0 unit0/group15 不进入 `EXECUTE/COMMIT`，但 hidden0 仍饱和为 127；
- 结果保持 `logit0=137`、`logit9=59`。

## 6. 启用组三拍稳定断言

每次观察到 L0/L1 `EXECUTE` 时，记录 unit、group 和已锁存模型 word；下一计算状态必须是同层 `COMMIT`，且三者保持不变。`lane_sum_latched` 只允许在同层 `EXECUTE` 写入，`COMMIT` 只能读取。

每次同层 `COMMIT` 完成后：

- 非最后组推进到下一 group 的 `FETCH`；
- 最后组推进到下一神经元 bias，或从 L0 进入 L1，或由 L1 最后神经元建立结果槽。

关闭组不得经过 `EXECUTE/COMMIT`。关闭的最后一组必须在 `FETCH` 使用当前累加器完成写回。

## 7. 周期模型

令 `E` 为两层合计启用的四权重组数：

```text
固定 bias 与组扫描 = 32×(2+16) + 10×(2+8) = 676 cycles
当前两拍实现       = 676 + E
V1 三拍实现         = 676 + 2E
```

因此：

| mask | E | 当前实现 | V1 |
|---|---:|---:|---:|
| 全开 | 592 | 1268 | 1860 |
| 关闭两组 | 590 | 1266 | 1856 |
| 仅关闭 L0 最后一组 | 591 | 1267 | 1858 |
| 全关 | 0 | 676 | 676 |

周期计数只覆盖第 8 个输入 beat 接受后到结果槽建立，不包含模型/mask 配置、8-beat 输入传输、10-beat 输出传输或 Host 背压。

## 8. Watchdog 预算

现有 watchdog 不作为功能期望，只用于防止仿真死锁。当前 testbench 的 Icarus 完成时刻与按 V1 增加的启用组拍数给出以下预算：

- skeleton：当前 2605 拍，V1 预计 3197 拍，相对 5000 拍 watchdog 约余 1802.5 拍；
- mask：当前 2722 拍，V1 预计 2724 拍，相对 5000 拍 watchdog 约余 2275.5 拍；
- control：当前 2588 拍，V1 预计 3180 拍，相对 6000 拍 watchdog 约余 2819.5 拍；
- compute：现有两样本当前 3858.5 拍，V1 预计 5040.5 拍；加入 C3/C4 后仍低于 9000 拍 watchdog，并应保留不少于 1200 拍裕量；
- random：最慢的现有固定 seed 43 当前 108709 拍，V1 预计 141485 拍，相对 3,000,000 拍 watchdog 约余 2,858,514.5 拍。

RTL 实施后必须记录真实完成周期；如果超过上述门槛，应先解释新增状态或握手停顿，不能只盲目放大 watchdog。

## 9. 日志与完成条件

`COMPUTE_COMPLETE` 仿真日志必须同时覆盖：最后一个 L1 组启用时从 `COMMIT` 完成，以及最后一个 L1 组关闭时从 `FETCH` 完成。日志不参与综合，也不替代 `result_valid` 和 bit-exact 检查。

测试切片完成的必要条件：

1. 旧 RTL 上新增三拍断言形成预期 RED；
2. V1 RTL 上 C1-C4 的状态次数、延迟和结果全部 GREEN；
3. 五项 NPU 单时钟测试全部通过；
4. 固定 `20×100` 和完整仓库回归通过后，才允许运行 Vivado OOC。

## 10. 当前停止点

TR1-TR6 未获管理员批准。当前只提交本测试合同，不创建 RED testbench、不修改 RTL、不运行 Vivado。
