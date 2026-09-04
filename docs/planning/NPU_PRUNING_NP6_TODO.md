# NPU 局部剪枝 NP6 物理成本 TODO

状态：`NP6_PHYSICAL_COST_PARTIAL / NP7_SIGNED_OFF / NPU_INTEGRATION_NEXT`

日期：2026-09-01

## 1. 目标与边界

NP6 只测量 NP4B 已签核剪枝结构在指定 FPGA 上的综合、实现、资源和时序成本。它不改变神经元方程、Host 协议、剪枝 gate 语义或 `4→8→2` 拓扑。

本阶段允许声明：指定 Vivado 版本、器件、约束和源码冻结点下的 LUT/FF/BRAM/DSP、时序裕量、DRC/路由结果，以及相对基线的资源增量。

本阶段禁止声明：真实 BRAM 跳读、共享 lane 周期下降、板级吞吐提升、动态功耗下降、完整 bitstream 可用性或通用 AI 训练能力。BRAM 跳读和共享 lane 属于 NP7；板级测量另行进行。

## 2. 工具与冻结条件

- 实际证据环境：协作者本机 Vivado 2024.2（SW Build 5239630）。项目本机另有 Vivado 2024.1，但本阶段最终报告只绑定 2024.2，不跨版本外推。
- 目标器件：`xc7z020clg400-1`；若项目板卡约束要求不同封装，必须在审核时单独冻结。
- 目标时钟：100 MHz；Host/Tile 双时钟版本保持既有 50/100 MHz 合同。
- 每个被测配置必须记录 Git HEAD、工作树状态、Vivado 版本、Tcl 命令、退出码和报告 SHA-256。
- 运行 Vivado 前必须由用户明确批准本 TODO 的冻结决策；批准前只允许静态审计和文档维护。

## 3. 比较矩阵

每个对象至少构建一组未剪枝基线和一组 NP4B 剪枝版本，使用相同器件、时钟、综合策略和实现策略：

1. `local_prune_gate_2of4`：gate 独立 OOC。
2. ENeuron：未剪枝 wrapper 对比剪枝 wrapper。
3. Pulse-Mini-L：未剪枝 wrapper 对比剪枝 wrapper。
4. Pulse-Mini-L2：未剪枝 wrapper 对比剪枝 wrapper。
5. `4→8→2` 网络：未剪枝对比十 gate 剪枝网络。
6. Host Bridge + Tile System：未剪枝控制路径对比接入剪枝 sideband 的系统版本；若未剪枝系统不存在可比实现，必须标为 `NOT_COMPARABLE`，不得用不同拓扑硬比。

## 4. 执行任务

- [x] NP6.0：九项冻结决策已获用户批准，器件为 `xc7z020clg400-1`、单时钟对象为 100 MHz、Vivado 为协作者本机 2024.2。
- [x] NP6.1：完成 runner、顶层、报告目录和约束的静态审计。
- [x] NP6.2：完成 7 个配置的结构预检；每次实现均绑定冻结 HEAD `7023b15`。
- [x] NP6.3：按冻结矩阵构建 gate、ENeuron 两侧、Pulse-L 两侧和 Pulse-L2 两侧；网络与系统配对按批准决定标 `NOT_COMPARABLE`。
- [x] NP6.4：7 个配置均完成 Vivado 2024.2 综合和实现，route error=0、DRC error=0；vector-less 功耗只作附带估算。
- [x] NP6.5：独立解析资源、WNS/WHS、TNS/THS、失败端点、DRC 和 route status；配对 2 因微架构不同标 `NOT_COMPARABLE`。
- [x] NP6.6：固定每配置 9 件报告并绑定 SHA-256；RTL/runner 与冻结提交字节三方一致，未绑定未提交 DCP。
- [x] NP6.7：只读 fail-closed verifier 正向通过；12 项 mutation 均被正确接受或拒绝，验证后 manifest 与工作树不变。
- [x] NP6.8：PR #5 已以 merge commit `241b1d0` 合并；NP7 后续共享 BRAM/lane 已签核，阶段状态收口为 `NP6_PHYSICAL_COST_PARTIAL / NP7_SIGNED_OFF / NPU_INTEGRATION_NEXT`。

## 4.1 实际阶段结论

- 7 个实现均完成且没有 route/DRC error。
- `local_prune_gate_2of4` 与 `eneuron_local_prune_wrapper` 通过 100 MHz。
- `digital_lif_core` 以及 Pulse-Mini-L/L2 两侧未通过 100 MHz，因此不能记为 `NP6_PHYSICAL_COST_PASS`。
- Pulse-Mini-L 可比增量为 `+297 LUT / +356 FF`；Pulse-Mini-L2 为 `+349 LUT / +360 FF`。
- NP6 只证明指定环境下的物理成本和部分时序结果，不证明 BRAM 跳读、周期缩短、实际功耗下降或板级加速。

## 5. 验收门

- 所有成功配置：综合退出码 0、实现退出码 0、route error=0、DRC error=0。
- 时序门：setup/hold 失败数均为 0；WNS/WHS 必须逐时钟域报告。
- 资源门：LUT、FF、BRAM、DSP 均有绝对值和相对未剪枝基线的增量；不能把逻辑 issue 计数当作物理资源节省。
- 新鲜度门：报告生成时间不早于冻结 HEAD 中任一被测 RTL、约束、Tcl、runner 或 verifier 的最后修改时间。
- 证据门：每个配置有可重放命令、工具版本、器件、时钟、报告路径和 SHA-256；vector-less 功耗只作为估算并明确置信度。

## 6. 停止条件

- 发现比较对象拓扑、器件、时钟或约束不一致。
- 任一 runner 使用旧 RTL、旧约束或隐式缓存结果。
- 只能得到综合结果而没有实现/时序/DRC 结果。
- 报告无法区分未剪枝基线与剪枝版本。
- 需要修改 NP4B 冻结协议、神经元方程或 Host Bridge 才能完成测量。

## 7. 已批准的冻结决策

九项实际裁定、执行机和批准链见 `NPU_PRUNING_NP6_FREEZE_DECISIONS.md`。仓库所有者已在 PR #5 评论 `5492928792` 逐项确认，当前没有待确认的 NP6 决策。
