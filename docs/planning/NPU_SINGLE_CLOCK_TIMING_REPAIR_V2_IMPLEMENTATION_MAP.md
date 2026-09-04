# 传统 NPU + ENeuron 单时钟 RTL 时序修复 V2 实施地图

状态：`REVIEW_READY / RTL_CHANGES_BLOCKED`

日期：2026-09-04

基线：`main@bef5979`

## 1. 结论

TR7-TR12 的两个核心动作仍然正确：FETCH 锁存四个激活操作数，最终结果统一经过 WRITEBACK。但 KISS 审计发现无需新增 32-bit `writeback_value_latched`；现有 signed 32-bit `mac_accumulator` 可以同时承担累加和最终写回值寄存器。

因此 V2 的逻辑新增状态从原估计约 64 bit 降为约 32 bit：只增加四个 signed 8-bit 激活锁存器。两个 WRITEBACK 状态仍可放入现有 4-bit 状态编码，不增加状态寄存器宽度。准确综合增量必须由实施后的 Vivado 报告裁定。

本文件只把批准后的修改位置和验证门冻结清楚，不修改 RTL、testbench 或周期常量。

## 2. 为什么可以复用 `mac_accumulator`

最后物理组启用时，COMMIT 执行：

```text
mac_accumulator <= mac_accumulator + lane_sum_latched
compute_state   <= WRITEBACK
```

下一拍 WRITEBACK 读取非阻塞赋值已经更新的 `mac_accumulator`。最后物理组关闭时，FETCH 不写 `mac_accumulator`，直接进入 WRITEBACK，因此它自然保持此前累加值或 bias。

该结构复用当前所有非末组 COMMIT 已经存在的加法路径。对 DSP V1 routed checkpoint 的 32 个 `mac_accumulator[*]/D` 端点执行定向 setup 报告，最差路径为：

- source：`lane_sum_latched_reg[0]/C`
- destination：`mac_accumulator_reg[2]/D`
- slack：`+5.272 ns`
- data path delay：`4.381 ns`
- logic levels：3
- 定向报告 SHA-256：`E0725B14C16150406347101814C6CA067359DBF102BFCCB68947256275833D36`
- 仓库外报告位置：`C:\Users\Epsilon\AppData\Local\Temp\eneuron_v2_accumulator_setup.rpt`

这证明当前 routed 实现中的累加寄存路径有明显余量，支持“复用 accumulator”作为优先候选；它不保证修改并重新布局后仍有同样余量，最终仍由新的完整 OOC 裁定。

工具说明：直接启动用户给出的 `unwrapped/win64.o/vivado.exe` 在当前 PowerShell 环境以 `-1073741515` 退出且无工具日志；改用同一 Vivado 2024.1 安装的 `bin/vivado.bat` 初始化运行环境后，checkpoint 和定向报告正常完成。报告头主机时间为未来的 `2026-09-05 03:45:40`，仅视为主机时钟元数据；证据身份使用 checkpoint 与报告哈希。

## 3. RTL 精确实施地图

### 3.1 状态和寄存器

- 新增 `COMPUTE_L0_WRITEBACK = 4'd11`。
- 新增 `COMPUTE_L1_WRITEBACK = 4'd12`。
- 新增四个 signed 8-bit 激活锁存器，共 32 bit。
- 保留 `model_word_latched` 作为四个权重的 FETCH 锁存器。
- 保留 `mac_accumulator` 作为中间累加值和最终写回值，不新增第二个 32-bit 最终值寄存器。
- 继续保留四个 signed 16-bit、分别带 `use_dsp="yes"` 的乘积信号；不得给 accumulator 或求和信号添加 DSP 属性。

### 3.2 状态转移

| 当前状态 | 动作 | 下一状态 |
|---|---|---|
| L0 FETCH，组启用 | 同拍锁存模型 word 和四个零扩展 input pixel | L0 EXECUTE |
| L0 FETCH，非末组关闭 | 只推进 group | L0 FETCH |
| L0 FETCH，物理末组 15 关闭 | accumulator 保持，unit 不推进 | L0 WRITEBACK |
| L0 EXECUTE | 四个 DSP 使用锁存操作数，锁存 `lane_sum_latched` | L0 COMMIT |
| L0 COMMIT，非末组 | accumulator 加组和并推进 group | L0 FETCH |
| L0 COMMIT，物理末组 15 启用 | accumulator 加组和，unit 不推进 | L0 WRITEBACK |
| L0 WRITEBACK | 唯一写入 `hidden_values[unit]`，执行 ReLU/127 饱和后推进 unit | 下一 L0 BIAS 或 L1 BIAS |
| L1 FETCH，组启用 | 同拍锁存模型 word 和四个零扩展 hidden value | L1 EXECUTE |
| L1 FETCH，非末组关闭 | 只推进 group | L1 FETCH |
| L1 FETCH，物理末组 7 关闭 | accumulator 保持，unit 不推进 | L1 WRITEBACK |
| L1 EXECUTE | 四个 DSP 使用锁存操作数，锁存 `lane_sum_latched` | L1 COMMIT |
| L1 COMMIT，非末组 | accumulator 加组和并推进 group | L1 FETCH |
| L1 COMMIT，物理末组 7 启用 | accumulator 加组和，unit 不推进 | L1 WRITEBACK |
| L1 WRITEBACK | 唯一写入 `logit_values[unit]`；unit9 同拍建立结果槽 | 下一 L1 BIAS 或 IDLE |

这里的“末组”始终表示物理末组 L0 group15 / L1 group7，不是 mask 中最后一个启用组。

### 3.3 必须删除的旧行为

- L0 最后关闭组不得再在 FETCH 直接写 `hidden_values`。
- L0 最后启用组不得再在 COMMIT 直接写 `hidden_values`。
- L1 最后关闭组不得再在 FETCH 直接写 `logit_values` 或建立结果槽。
- L1 最后启用组不得再在 COMMIT 直接写 `logit_values` 或建立结果槽。
- EXECUTE 不得动态读取 `input_pixels` 或 `hidden_values`；这些数组只能在 FETCH 为激活锁存器提供数据。
- unit 索引必须保持到 WRITEBACK 完成后再推进，否则会把最终值写入下一神经元。

### 3.4 日志语义

`COMPUTE_COMPLETE` 只在最终 `L1_WRITEBACK && unit==9` 输出，此时结果槽真正建立。日志仍保留 `path=COMMIT` 与 `path=MASK_BYPASS`，直接读取当前样本稳定的最终 active-mask 位区分两种来源；日志位于 `ifndef SYNTHESIS`，不新增硬件状态。

## 4. V2 测试实施地图

V1 测试合同保持冻结历史证据。TR7-TR12 获批后新增独立 V2 合同，并先让下列要求在旧 RTL 上 RED：

- 每个启用组的四个激活锁存值必须与 FETCH 地址对应，并在 EXECUTE/COMMIT 期间稳定。
- EXECUTE 源码和运行时观测均不得再使用动态输入/隐藏数组作为 DSP 操作数。
- 最后启用组：COMMIT 后必须进入 WRITEBACK，且 accumulator 等于旧 accumulator 加组和。
- 最后关闭组：FETCH 后必须进入 WRITEBACK，且 accumulator 保持。
- 每个样本必须恰好出现 32 次 L0 WRITEBACK 和 10 次 L1 WRITEBACK，无重复、无遗漏。
- hidden/logit 的运行时变化只能发生在对应 WRITEBACK 后；再用静态源码门确认计算状态机中各数组只有一个赋值位置。
- 最终 L1 WRITEBACK 建立结果槽；WRITEBACK 之前不得提前出现 `result_valid`。
- testbench 中的状态编号与 DUT 必须由静态测试同步核对，不能只靠两份人工硬编码碰巧一致。
- 四个 DSP 属性和 Vivado `DSP=4 / DSP48E1_COUNT=4` 双重门继续保留。

## 5. 周期和 watchdog

每个神经元固定增加一个 WRITEBACK，共 `32+10=42` 拍；启用组仍各有 EXECUTE/COMMIT 两个附加拍。因此：

```text
V2 latency = 676 + 42 + 2E = 718 + 2E
```

| 合同 | 启用组 E | V2 计算延迟 |
|---|---:|---:|
| C1 全开 | 592 | 1902 |
| C2 关闭两组 | 590 | 1898 |
| C3 全关 | 0 | 718 |
| C4 仅关闭 L0 末组 | 591 | 1900 |

使用 MSYS2 UCRT64 Icarus 12.0 的 `vvp -v` 实测当前 V1 testbench 完成时刻，再按每个样本增加 42 拍推导 V2 预算：

| testbench | 当前完成拍 | 样本数 | V2 预计完成拍 | 当前 watchdog | 预计余量 |
|---|---:|---:|---:|---:|---:|
| skeleton | 3197 | 1 | 3239 | 5000 | 1761 |
| mask | 2724 | 2 | 2808 | 5000 | 2192 |
| control | 3180 | 1 | 3222 | 6000 | 2778 |
| compute | 7709.5 | 4 | 7877.5 | 9000 | 1122.5 |

前三个 watchdog 无需调整。compute 虽不会超时，但低于 V1 合同要求的 1200 拍规划余量；获批后将其定向调整为 9500 拍，预计余量 1622.5 拍。精确周期断言继续负责拒绝多余停顿，因此这一调整不放宽功能合同。

## 6. 批准后的执行顺序

1. 新建独立 V2 测试合同。
2. 更新 C1-C4 和白盒状态检查，证明旧 RTL 精确 RED。
3. 最小修改计算 RTL，复用 accumulator，不改变外部协议。
4. 运行单时钟定向测试和固定 `20×100` 随机逐 beat。
5. 运行完整仓库回归。
6. 仅在功能门全部通过后运行 Vivado 2024.1 OOC。
7. 只有恰好 4 DSP、setup/hold 零失败、route/DRC 零错误时签核；否则保存报告并重新审核，不自动增加流水。
