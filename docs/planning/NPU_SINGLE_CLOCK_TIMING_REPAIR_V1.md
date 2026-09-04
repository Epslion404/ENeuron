# 传统 NPU + ENeuron 单时钟 RTL 时序修复 V1 审核稿

状态：`RTL_GREEN / VIVADO_PENDING / DSP_REQUIRED`

日期：2026-09-04

## 1. 目标与边界

目标是在不改变外部协议和数值合同的前提下，使 `npu_eneuron_single_clock_skeleton.sv` 在 `xc7z020clg400-1`、100 MHz OOC 条件下通过 setup/hold、route 和 DRC 硬门。

本轮只处理当前 `64→32→10` INT8 计算路径的内部时序。不得删除或弱化以下合同：INT32 累加、四权重整组 mask、mask epoch 样本边界原子切换、8-beat 输入、10-beat 输出、单槽结果背压、freeze/clear 语义及模型/掩码错误处理。XC7Z020 顶层、DMA、PS、网口、动态功耗和持续学习收益不属于本轮。

## 2. 已有物理证据

Vivado 2024.1 已完成 OOC 综合、优化、布局、布线、setup/hold 分析和 DRC。资源为 2672 LUT、1879 FF、0 BRAM、0 DSP；route/DRC 无错误，hold 为 `WHS=+0.098 ns`、0 个失败端点；setup 为 `WNS=-5.087 ns`、`TNS=-421.539 ns`、244 个失败端点。因此当前状态只能是 `VIVADO_OOC_SETUP_FAIL / TIMING_REPAIR_REQUIRED`。

最差路径从 `compute_group_index_reg[1]_rep` 到 `hidden_values` 的分布式存储写入端，数据路径 14.775 ns，其中逻辑 6.884 ns、布线 7.891 ns，共 23 级逻辑。前 20 条最差 setup 路径属于同一类路径。

这条路径在一拍内穿过：组号选择输入像素、四个窄乘法、四路求和、32 位累加、末组 ReLU/127 饱和和隐藏值写回。问题是结构性的组合链过长，不是单纯修改 Vivado 参数即可可靠解决。

## 3. 最小修复方案

把每个启用的四权重组从现有两拍拆成三拍：

```text
FETCH -> EXECUTE -> COMMIT
```

- `FETCH`：只读取并锁存当前四个权重。
- `EXECUTE`：按当前组号读取四个输入，完成四个乘法和组内求和，把结果锁存到新增的 `lane_sum_latched`。
- `COMMIT`：只把已锁存的组和加入 INT32 累加器；若为最后一组，则用“旧累加器 + 已锁存组和”完成隐藏层饱和或输出 logit 写回。

关闭的 mask 组继续直接跳过，不读取权重、不执行乘加，也不额外进入 `EXECUTE/COMMIT`。因此剪枝后的周期节省合同保持成立。

## 4. 管理员已批准的六项裁定

### TR1：新增组和寄存器

新增一个 signed 32-bit `lane_sum_latched`，L0/L1 共用；增加 L0/L1 的 `EXECUTE` 状态。管理员附加要求：四条并行乘法 lane 必须使用 XC7Z020 的 DSP48E1，不接受 LUT 乘法实现。

### TR2：外部协议不变

保持所有 ready/valid、命令、样本、结果和错误响应字段不变。允许内部计算延迟增加；Host 不得依赖固定计算拍数，只依赖既有握手和结果有效信号。

### TR3：组三元组保持一致

对启用组，`compute_unit_index`、`compute_group_index` 和对应的 `model_word_latched` 从 `FETCH` 接受该组起，经过 `EXECUTE`，直到 `COMMIT` 完成前必须保持对应关系；只在 `COMMIT` 完成后推进组号或神经元号。对关闭组，允许在 `FETCH` 直接推进；若关闭的是最后一组，则在 `FETCH` 使用当前累加器完成写回并推进神经元。

### TR4：最后一组不丢失

最后一组必须用 `mac_accumulator + lane_sum_latched` 生成隐藏值或 logit，不能只读取旧累加器。关闭的最后一组仍直接用当前累加器写回。

### TR5：强制四个 DSP48E1

四条并行 lane 使用共享的 signed 8-bit 激活输入和 signed 8-bit 权重输入，以显式 `*` 表达乘法，并对四个乘积信号施加 `(* use_dsp = "yes" *)`。L0 的 uint4 和 L1 的 uint7 激活都先零扩展到 signed 8-bit；L0/L1 复用同一组四个乘法器。

Vivado 物理门要求实现报告 `DSP=4`。属性存在但 DSP 仍为 0、DSP 少于 4，或因错误作用域把加法器/累加器也塞入 DSP 导致超过 4，均不得签核。若 100 MHz 仍失败，先重新分类新的最差路径；写回链优先审核独立 `WRITEBACK` 状态，其他路径另行审核，不能静默扩大架构。

### TR6：验收门不降级

修复必须依次通过：五项单时钟定向 RTL 测试、固定 `20×100` 随机逐 beat bit-exact、完整仓库回归、Vivado 2024.1 同器件同约束 OOC。最终硬门是 `DSP=4`、setup/hold 失败端点均为 0、route/DRC error 为 0，且报告和 manifest 重新绑定修复后的 RTL 哈希。

## 5. 预期代价与收益

全开 mask 时共有 592 个四权重组，新增 `EXECUTE` 会增加约 592 个计算周期。按当前约 1268 cycles/sample 的计算估算，修复后约为 1860 cycles/sample；100 MHz 下计算上限约 53.8k samples/s。当前失败实现若按 WNS 粗略折算到约 66.3 MHz，约为 52.3k samples/s，因此分拍后即使周期数增加，只要实现 100 MHz，吞吐量级仍可能近似持平。

以上仅是周期模型，不是板级或网口端到端实测。稀疏 mask 会跳过 `EXECUTE/COMMIT`，实际周期取决于启用组数。

预计新增状态主要是 32-bit 组和寄存器和两个状态编码，并固定占用 4 个 DSP48E1。准确 LUT/FF、功耗与布线收益必须由修复后的 Vivado 报告裁定。

## 6. 批准后的实施顺序

1. 先更新定向测试，使其只依赖握手，不假定旧计算周期；增加“启用组在 `EXECUTE/COMMIT` 内 unit/group 稳定、关闭组不进入这两个状态、两层最后一组不丢失”的检查。
2. 实现 `lane_sum_latched`、两层 `EXECUTE` 状态和四条共享 DSP 乘法 lane，保持外部端口与数值合同不变。
3. 同步更新 `COMPUTE_COMPLETE` 仿真日志的完成状态条件，再运行四项定向门和固定 `20×100` 随机门；任何 bit-exact 差异立即停止。
4. 运行完整仓库回归并更新机器证据。
5. 使用同一 Vivado 版本、器件、100 MHz 约束重跑 OOC；先确认 `DSP=4`，再裁定时序。若 DSP 数不符或 setup 仍失败，保留失败报告并进入 V2 设计审核，不直接扩展范围。

## 7. 当前停止点

三拍 RTL、共享四乘法 lane、C1-C4 白盒合同、固定 `20×100` 和完整 473 项回归已通过；两路最终反审计无 RTL blocker，测试覆盖 blocker 也已闭合。当前只剩把实现提交冻结为报告基线并运行 Vivado 2024.1 OOC；在实现报告同时满足 `DSP=4` 和 100 MHz 前，不生成物理通过声明。
