# XC7Z020 传统 NPU + ENeuron 顶层集成规划 V1

状态：`PLANNING / OOC_CORE_SIGNED_OFF / TOPLEVEL_RTL_NOT_STARTED`

日期：2026-09-05

## 1. 目标

把已经通过单时钟 OOC 的传统 INT8 NPU + ENeuron 核接入 XC7Z020 的可复现实验顶层，使外部数据流可以提交模型、发送固定 8-beat 样本并接收固定 10-beat 结果。第一版只证明数据通路、跨时钟和背压合同，不把网口吞吐或板级功耗写成已实现能力。

当前核心基线为 `main@a53a040`，OOC 父提交为 `f744bff2bdde68e138a7b2b348ce103bec1ab469`。核心资源为 `2126 LUT / 1916 FF / 0 BRAM / 4 DSP48E1`，Vivado 2024.1、`xc7z020clg400-1`、100 MHz post-route `WNS=+0.060 ns / TNS=0 / WHS=+0.040 ns`，零 setup/hold/route/DRC 失败。

## 2. 现有可复用边界

- 计算核：`npu_eneuron_single_clock_skeleton.sv`，单时钟、128-bit 命令/响应、固定 8-beat 输入和 10-beat 输出。
- 双时钟桥：`digital_snn_host_bridge.sv`，Host 域与 Tile/计算域之间使用两个 XPM 异步 FIFO；当前 FIFO 深度为 16，数据宽度为 128 bit。
- 已有系统参考：`digital_snn_host_bridge_system.sv`，可作为跨时钟复位、命令/响应和 Tile 连接的参考，但它面向 4→2→2 脉冲 Tile，不应直接冒充 INT8 NPU 顶层。
- 片外职责：模型装载、样本分帧、标签/奖励、训练调度、网口协议和 DMA 描述符均留在 PS/Host 或更外层。

## 3. V1 顶层边界

### 3.1 推荐的最小端口层

先定义与核心协议一一对应的流适配器，不在第一刀引入完整 AXI4-Lite 寄存器地图：

- `host_clk`、`npu_clk`、同步复位请求；
- 128-bit 命令输入流与 128-bit 响应输出流；
- 32-bit 样本输入流（`sample_data`、`sample_id`）与 32-bit 结果输出流（logit、sample ID、mask epoch）；
- `irq/status` 只作为结果或错误可用提示，不承担数据传输；
- 可观察的 FIFO reset-busy、计算忙/空闲、模型有效、冻结和错误状态。

AXI4-Stream、AXI DMA 和 Ethernet 适配放在该端口层之外或第二个薄封装中，避免把厂商协议耦合写入已经签核的核心。

### 3.2 时钟与复位

- `host_clk` 和 `npu_clk` 可以不同频率；所有跨域数据只经过现有异步 FIFO。
- 每个时钟域使用本域同步释放复位；在两个域都退出 reset-busy 前，命令和样本 ready 必须保持为 0。
- 不允许从组合逻辑跨时钟传播核心状态、mask epoch 或结果 payload。
- 复位期间丢弃部分样本、部分命令和未消费结果；复位后模型必须重新提交，active mask 回到协议规定的默认状态。

### 3.3 数据与顺序

- 模型装载完成后才允许样本流握手；命令流遵循核心既有 opcode 和错误响应合同。
- 一个样本固定 8 个 32-bit beat；一个结果固定 10 个 32-bit beat。适配器不得自行插入或删除 beat。
- 结果 payload 在 `valid=1 && ready=0` 期间保持稳定；命令和样本源在 `ready=0` 期间保持 valid/payload 稳定。
- active mask 只在样本首 beat 绑定；DMA/网口分包不能改变这一边界。

## 4. 分阶段实施

### T0：合同冻结（当前步骤）

- [x] 记录核心 OOC 结果、提交身份和未覆盖的板级边界。
- [x] 明确 Host Bridge 可复用部分与 4→2→2 Tile 专用部分。
- [x] 冻结最小流适配器、时钟、复位、背压和 beat 顺序。
- [ ] 评审并批准 V1 顶层端口命名和 AXI 外部适配位置。

### T1：纯 RTL 顶层适配器

- [ ] 新建薄封装，只连接核心与两个异步 FIFO，不修改核心计算方程或 mask 语义。
- [ ] 建立模型装载、样本输入、结果输出、错误背压和 reset-reentry testbench。
- [ ] 与单时钟参考模型逐 beat 对照；至少覆盖全开、全关、mixed mask、结果背压和复位丢弃。

### T2：双时钟协同仿真

- [ ] 使用可变 `host_clk/npu_clk` 比例和相位，验证 FIFO 不乱序、不重复、不丢 beat。
- [ ] 统计命令/样本/结果吞吐、FIFO 峰值占用和端到端延迟；所有数字绑定具体时钟和测试向量。
- [ ] 增加负向 mutation：复位重入、ready 抖动、结果槽满、模型未提交和 mask 中途更新。

### T3：XC7Z020 OOC/顶层物理门

- [ ] 先对“核心 + 适配器 + FIFO”做 OOC，分别记录 LUT/FF/BRAM/DSP、WNS/TNS/WHS/THS、route/DRC。
- [ ] 再建立含 PS7/AXI 适配的顶层；PS7、DMA、Ethernet 的资源和时序单独归因。
- [ ] 只有真实 XDC、板卡时钟、I/O delay 和 bitstream 级实现通过后，才报告板级时钟和吞吐。

### T4：网口数据流与训练闭环

- [ ] 选定具体开发板和 Ethernet/PS 软件栈，定义包头、样本 ID、模型版本和错误恢复。
- [ ] 以旁路 NPU 和 ENeuron 门控 NPU 做同输入 A/B，对比有效 MAC、周期、准确率、丢包和功耗。
- [ ] 持续学习、奖励信用分配和在线更新另立训练合同，不由本 V1 顶层门代偿。

## 5. 首个可验收门

V1 顶层适配器只有同时满足以下条件才算通过：

1. 纯 RTL 双时钟协同仿真逐 beat 与核心黄金模型一致。
2. reset、ready/valid、FIFO 满/空、结果背压和 mask 生效边界无丢失、重复或乱序。
3. 核心计算资源与 OOC 基线差异可解释；适配器新增 BRAM、LUT、FF 和时序单独列出。
4. 不把 AXI、DMA、网口或 PS 软件的存在写成已完成；这些必须由后续 T3/T4 证据证明。

## 6. 当前不做的事

- 不修改 `npu_eneuron_single_clock_skeleton.sv` 的数值路径。
- 不把 `digital_snn_host_bridge_system.sv` 直接改造成 NPU 顶层。
- 不在没有端口合同和双时钟 testbench 前接入 Ethernet 或 DMA。
- 不用 OOC 核心时序结果推导板级吞吐、功耗或网口性能。
