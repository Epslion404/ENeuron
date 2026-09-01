# NPU 局部剪枝 NP6 物理成本 TODO

状态：`NP6_REVIEW_REQUIRED`

日期：2026-09-01

## 1. 目标与边界

NP6 只测量 NP4B 已签核剪枝结构在指定 FPGA 上的综合、实现、资源和时序成本。它不改变神经元方程、Host 协议、剪枝 gate 语义或 `4→8→2` 拓扑。

本阶段允许声明：指定 Vivado 版本、器件、约束和源码冻结点下的 LUT/FF/BRAM/DSP、时序裕量、DRC/路由结果，以及相对基线的资源增量。

本阶段禁止声明：真实 BRAM 跳读、共享 lane 周期下降、板级吞吐提升、动态功耗下降、完整 bitstream 可用性或通用 AI 训练能力。BRAM 跳读和共享 lane 属于 NP7；板级测量另行进行。

## 2. 工具与冻结条件

- Vivado：`G:\Xilinx\Vivado\2024.1\bin\unwrapped\win64.o\vivado.exe`
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

- [ ] NP6.0：冻结器件封装、时钟约束、综合/实现策略和比较矩阵。
- [ ] NP6.1：审计现有 runner，确认所有输出目录、约束和顶层与冻结矩阵一一对应。
- [ ] NP6.2：先运行不改 RTL 的静态结构检查和 Tcl dry-run，确认每项都使用当前 HEAD。
- [ ] NP6.3：构建 gate、三种 wrapper、网络和系统的未剪枝/剪枝配对工程。
- [ ] NP6.4：执行 Vivado 综合、实现、时序、DRC、资源和 vector-less 功耗报告。
- [ ] NP6.5：从报告解析资源、WNS/WHS、TNS/THS、DRC、route error，并生成配对增量表。
- [ ] NP6.6：对每项报告、工程输入、Tcl、约束、摘要和 verifier 建立 SHA-256 绑定。
- [ ] NP6.7：运行独立 fail-closed verifier；任一配对缺失、器件/时钟不一致、报告陈旧或解析失败则拒绝签核。
- [ ] NP6.8：更新阶段报告和 `WORKFLOW_STATE.md`，停在 `NP6_PHYSICAL_COST_PASS / NP7_REVIEW_REQUIRED` 或明确失败状态。

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

## 7. 用户需审核的冻结决策

1. 是否批准进入 NP6 并允许调用 Vivado 2024.1。
2. 是否冻结器件为 `xc7z020clg400-1`，还是指定其他 XC7Z020 封装/速度级。
3. 是否接受 100 MHz 为主时钟目标、Host/Tile 采用 50/100 MHz 双时钟约束。
4. 是否接受上述六类配对对象和“不可比对象必须标记”的比较矩阵。
5. 是否接受 vector-less 功耗仅作为附带估算，不作为硬门或性能收益声明。
