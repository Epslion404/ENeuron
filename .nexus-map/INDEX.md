# ENeuron 知识库入口

generated_by: nexus-mapper v2 / manual synthesis from raw probe
verified_at: 2026-09-05
provenance: `.nexus-map/raw/ast_nodes.json`, `git_stats.json`, `file_tree.txt`（最后提交于 `c46320e`，文件树按版本化基线排除工作区未跟踪文件）；其后的单时钟 RTL、测试与 OOC 证据由版本化文件、manifest 和文档人工核对

ENeuron 是以 Python 黄金模型、SystemVerilog RTL、Icarus/Yosys/Vivado 验证组成的数字脉冲神经元与 NPU 局部剪枝研究仓库。

## 主要系统

- 神经元与参考模型：`digital_lif_engine.sv`、`neuron_sim.py`、`pulse_mini_reference.py`
- 网络/Tile/Host：`digital_snn_tile_4x2x2.sv`、`digital_snn_host_bridge_controller.sv`、`network_sim.py`
- 单时钟 NPU + ENeuron 集成 RTL：`npu_eneuron_single_clock_skeleton.sv`；基础、mask epoch、控制、真实计算和随机逐拍入口分别为 `test_npu_single_clock_skeleton.py`、`test_npu_single_clock_mask.py`、`test_npu_single_clock_control.py`、`test_npu_single_clock_compute.py`、`test_npu_single_clock_random.py`
- 局部剪枝：`local_prune_gate_2of4.sv`、`local_prune_reference.py`、`verify_np4b_signoff.py`
- NP7 共享执行器：`np7_shared_synapse_lane.sv`、`np7_weight_ram.sv`、`np7_shared_lane_oracle.py`、`np7_shared_lane_cosim.py`
- 验证入口：`verify_goal.py`、`verify_np4b_signoff.py`、`test_*.py`、formal `.ys/.sv`
- 规划与状态：`WORKFLOW_STATE.md`、`docs/planning/NPU_NEURON_INTEGRATION_REVIEW.md`、`docs/planning/NPU_PRUNING_NP6_TODO.md`、`docs/planning/NPU_PRUNING_NP7_TODO.md`
- 集成材料包：`docs/planning/NPU_NEURON_INTEGRATION_MATERIALS.md`、`docs/planning/NPU_ORACLE_FREEZE_REVIEW.md`、`docs/planning/NPU_ORACLE_SINGLE_CLOCK_CONTRACT_V3.md`、`docs/planning/NPU_MODEL_COMMIT_CONTRACT_V3.md`、`docs/planning/NPU_SINGLE_CLOCK_RTL_DECISION_SHEET_V2.md`（I1-I6、OF1-OF6 V3 与 V2 RTL 裁定已批准）；TR1-TR6 的实现与功能合同见 `NPU_SINGLE_CLOCK_TIMING_REPAIR_V1.md` 和 `NPU_SINGLE_CLOCK_TIMING_REPAIR_TEST_CONTRACT_V1.md`，下一轮审核稿与实施地图分别为 `NPU_SINGLE_CLOCK_TIMING_REPAIR_V2.md`、`NPU_SINGLE_CLOCK_TIMING_REPAIR_V2_IMPLEMENTATION_MAP.md`。
- 单时钟 OOC 入口：`run_vivado_npu_single_clock_ooc.ps1`、`vivado_npu_single_clock_ooc.tcl`、`artifacts/results/npu_single_clock_ooc_manifest.json`、`vivado_npu_single_clock_ooc_reports/`
- CI 编排：`.github/workflows/pr-gate.yml`、`tools/ci/classify_changes.py`、`test_ci_fast_v1.py`（路径分类、条件专项门和唯一 `PR Gate` 汇总）

## 当前状态

状态校正（2026-09-05）：PR #64 已合并为 `main@a53a040`；PR #65 已合并为 `main@618c1e4`；PR #66 已合并为 `main@a1457bb`。下文若仍出现旧的“OPEN”或“等待合并”措辞，均属于生成快照中的历史内容，不覆盖本条和 `WORKFLOW_STATE.md` 的当前状态。

NP4B 已签核；NP6 已收口为 `NP6_PHYSICAL_COST_PARTIAL`，NP7 已签核。TR7-TR12 已批准并完成 V2 实现：单时钟专项、固定 `20×100` 和完整仓库回归均通过。实现提交 `f744bff2bdde68e138a7b2b348ce103bec1ab469` 的 OOC 为 `2126 LUT / 1916 FF / 0 BRAM / 4 DSP48E1`，100 MHz `WNS=+0.060 ns / TNS=0 / WHS=+0.040 ns`，setup/hold/route/DRC 零失败。PR #64 已合并为 `main@a53a040`，PR #65 已合并为 `main@618c1e4`，PR #66 已合并为 `main@a1457bb`；当前状态为 `TIMING_REPAIR_V2_FUNCTIONAL_GREEN / VIVADO_OOC_100MHZ_PASS / P15_T0_REVIEW_REQUIRED`。P15-T0 推荐方案 A：保留 128-bit 命令/响应异步 FIFO，新增完整 payload 为 64-bit 样本 FIFO 和 96-bit 结果 FIFO，AXI-Stream 置于 FIFO 外；当前为 `PROPOSED / ADMIN_REVIEW_REQUIRED / NO_RTL_AUTHORIZATION`，不允许开始 T1 RTL。Webhook 掉线仅影响到达提示，板级、DMA、PS、网口和功耗仍未签核。

## 单时钟 RTL 审核摘要

- **V1 审计问题**：统一单命令流却定义 `MODEL_COMMIT` 与 `MASK_COMMIT` 同拍竞争；结果 sideband 引入未冻结的 `model_epoch` 且硬件槽位账本不足；首 beat mask 切换未说明 framing 错误的零副作用/回滚；`runtime_idle` 漏待消费错误、部分结果和同拍握手占用；验证门低于 I5 的 20 个固定 seed × 100 样本要求。
- **V2 修正**：固定 8/10 beat 并取消外部 `last`；明确 nibble 位序和内部 beat 计数；删除 `model_epoch`，结果 metadata 仅为 sample ID 与 mask epoch；统一命令流按握手顺序串行，配置命令优先样本首 beat；idle 纳入错误响应、部分输出、统一槽位及同拍仲裁；验证门恢复至少 20×100 样本并保留 OF6 定向/负向覆盖。
- **当前门槛**：V2 已实现于 `f744bff`。OOC 结果为 `2126 LUT / 1916 FF / 4 DSP48E1`，DSP 双重结构门、setup/hold、route 和 DRC 全部通过；`WNS=+0.060 ns / TNS=0 / WHS=+0.040 ns`。V1 的 22 个失败端点仍保留在独立审计文档中，仅作历史路径证据；当前 OOC 结果和哈希由 `artifacts/results/npu_single_clock_ooc_manifest.json` 绑定。
- **第二条 RTL 切片**：`test_npu_single_clock_mask.py` 驱动公开接口验证完整 19-word 顺序装载；非法 word18 高 16 位产生 128-bit 单槽错误响应且隐式索引保持 18，响应消费后可重试；`MASK_COMMIT` 只发布，后续样本首 beat 才令 epoch 1 active 并置 `mask_valid`，两个连续样本结果均携带 epoch 1。
- **第三条 RTL 切片**：`test_npu_single_clock_control.py` 验证部分 mask 可由 `MASK_ABORT` 丢弃；`STATE_CLEAR` 保留模型/mask；freeze 只在严格 idle 边界切换，冻结时样本仍可完成，而模型/mask 配置与动态清除返回稳定错误且不改变状态。
- **真实计算状态**：`test_npu_single_clock_compute.py`/`tb_npu_eneuron_single_clock_compute.sv` 已锁定 uint4×INT8、隐藏饱和、INT32 logit 与 L0 mask 门控；四 lane FETCH/EXECUTE/COMMIT 引擎通过首组 137/-117、两层最后组 59、L1 bit79 关闭后 -1，以及忙态阻塞检查。
- **随机门 GREEN**：固定 `20 seeds × 100 samples = 2000` 个样本逐 beat 比对 logits、sample ID、mask epoch、背压和 mask 轮换；DSP V1 完整仓库回归为 473/473（1 skipped）。物理 setup 仍失败，下一步是审核 V2，不能用软件周期或历史报告代偿。
- **配置合同补强**：模型写入已执行两层 signed bias 安全窗；mask 四态命令可与部分输入、计算和结果流并行准备 published bank，但只在下一样本首 beat 切换 active，模型/冻结/清除命令仍要求严格运行空闲。

## P15-T0 顶层规划（当前门）

- 规划文档：`docs/planning/NPU_ZYNQ7020_TOPLEVEL_INTEGRATION_V1.md`；裁定稿：`docs/planning/NPU_ZYNQ7020_TOPLEVEL_DECISION_SHEET_V1.md`。
- 推荐方案 A：命令/响应继续使用现有 128-bit 异步 FIFO；新增独立 32-bit 样本输入和结果输出 FIFO，并在 FIFO 外侧放置 AXI-Stream shim。样本固定 8 beat，结果固定 10 beat，`sample_id`/`mask_epoch` sideband 在各自事务内保持稳定。
- 当前状态：`P15_T0_REVIEW_REQUIRED / PROPOSED / ADMIN_REVIEW_REQUIRED / NO_RTL_AUTHORIZATION`。管理员批准方案 A、四条流 sideband/固定 beat 语义以及 AXI 外置边界后，才开放 T1 纯 RTL 适配器；T0 期间不修改计算核，不接入 AXI-Lite、DMA、Ethernet 或 PS7。

### P15-T0 只读审计结论（2026-09-05）

- **命令格式必须先选唯一权威**：当前 `npu_eneuron_single_clock_skeleton.sv` 与 `NPU_SINGLE_CLOCK_RTL_PORT_TABLE_V1.md` 使用高位 4-bit opcode（`[127:124]`）、epoch（`[119:88]`）和 word（`[31:0]`）；历史 `NPU_ORACLE_SINGLE_CLOCK_CONTRACT_V3.md` 仍描述低位 8-bit opcode/txn 格式。P15 不能只说“沿用核心协议”，T1 前必须明确采用当前 skeleton 格式，或同步修改 RTL/Oracle。
- **V1/V2 framing 不得混用**：V1 文档曾要求内部 `last` 和 `model_epoch`；V2 已删除二者，固定 8/10 beat 由内部计数器结束。P15 的 AXI `TLAST` 只能在明确早/晚/缺失时的检查或忽略语义后使用，不能把旧 `last` 接入核心。
- **四条流仅各自有序，跨流 fence 尚未冻结**：独立 command/sample FIFO 会使 `MASK_COMMIT`、`STATE_CLEAR`、`FREEZE_SET` 与样本首 beat 的相对顺序不确定；样本首 beat 的 mask 绑定发生在 NPU 域 core handshake，而非必然发生在 Host FIFO 写入沿。T1 必须定义控制完成栅栏或显式串行化策略。
- **reset-busy/状态 CDC 尚未形成可实现合同**：当前旧 Bridge 的 ready 只门控本侧 FIFO busy，不能直接证明“任一域 busy 时四流均不 ready”。Host 侧 `model_valid`、mask/epoch、错误和 FIFO domain-up 的同步方式、复位重入/半包丢弃边界都必须冻结。
- **AXI sideband 与错误路由仍缺字段**：需明确 sample `sample_id` 是否逐 beat 校验（core 当前只采样首 beat）、result sideband 在 10 beat 的保持、`TLAST`/`TKEEP`/`TSTRB`/`TID`/`TDEST` tie-off，以及样本 framing/sideband 错误如何在没有旁路错误包时报告。
- **FIFO 参数与资源归因未冻结**：新增 sample FIFO 实际为 64-bit、result FIFO 为 96-bit；depth、FWFT/latency、CDC stages、memory type 尚未定义，不能先验声称 BRAM/LUT/FF 增量。应以四个 FIFO 的实际 XPM 参数和 post-route 报告分别归因。
- **器件边界必须统一**：P15 目标是 `xc7z020clg400-1`；旧 Host Bridge OOC 使用 `xc7a35tcpg236-1`，只能作历史结构参考，不得替代 XC7Z020 资源、时序或 CDC 证据。
- 在上述合同补齐前，状态保持 `P15_T0_REVIEW_REQUIRED / NO_RTL_AUTHORIZATION`，不得创建 T1 顶层 RTL。

### P15-T0 附录二次复核（2026-09-05）

对 `NPU_ZYNQ7020_TOPLEVEL_T0_DECISION_ADDENDUM_V1.md`、`NPU_ZYNQ7020_TOPLEVEL_T0_TEST_CONTRACT_V1.md`、`NPU_SINGLE_CLOCK_RTL_PORT_TABLE_V1.md`、V2 实施合同和当前 skeleton 的只读交叉审计仍发现以下 T1 阻断。它们不是对方案 A 的否定，而是必须在批准稿中写成唯一可实现语义：

- **A3 没有冻结 fence 的线级格式**：附录第 36–39 行只指定保留 opcode `0xA` 和“带 fence ID 的响应”，没有规定 fence ID 位段、响应成功类别、错误码、响应字段布局，也没有说明 fence 被 wrapper 接受时如何阻止它泄漏到核心。当前 PORT_TABLE 只定义了 `0xE` 错误响应；T1 无法据此实现或逐拍比对 fence 确认。
- **严格 TLAST 与流式丢弃语义存在实现矛盾**：附录第 22–28 行要求晚到/缺失 TLAST 的整帧“不送入核心”，但若样本 beat 已逐拍穿过 FIFO，直到第 8 个 beat 或下一帧才发现错误就无法撤回；要满足该保证必须明确整帧预缓冲，或改为允许已送入的 beat 被取消。结果流是 wrapper 的输出，不能与样本输入共用同一套“接收 TLAST 检查”语句。与此同时，旧裁定稿第 49–51 行仍说 TLAST 只是提示、8/10 beat 不依赖 TLAST，必须明确哪一份被废止。
- **fence 前样本准入边界未定义**：附录第 37–40 行规定一个 fence 只授权一笔样本，但没有规定 fence 前 `sample_ready` 是否必须为 0、sample FIFO 是否允许预填、已有预填 beat 在拒绝/复位时如何丢弃。由于 sample FIFO 不携带 TLAST/帧号，T1 若不先冻结该规则，不能证明一笔 fence 对应恰好 8 个 beat。
- **A3 的“命令完成”层级不清**： “此前命令已完成核心握手”没有区分命令 FIFO 出队、核心 `cmd_valid&&cmd_ready` 握手、mask published 生效和状态操作实际完成；成功配置命令又不产生普通响应。必须指定 fence 的等待条件、与 response FIFO 满的 backpressure/拒绝优先级，否则可能在配置尚未可见时放行样本。
- **A4 的 busy 门控可能破坏 ready/valid 稳定合同**：附录第 48–50 行把任一域 busy 解释为四条流的 ready/valid 都关闭；若 result FIFO 已有 `valid=1` 且下游 `ready=0`，busy 变化不能撤销 valid 或改变 payload。应冻结为“禁止新事务握手，但在非复位期间保持已呈现事务稳定”，并定义 busy 重新开放的状态机。
- **A1 保留位检查尚未落到错误优先级**：附录要求 `[123:120]` 和 `[87:32]` 为零，但 skeleton 当前按 opcode 直接解码，未定义 wrapper 对非零保留位、未知 opcode、冻结状态和 payload/地址错误的检查先后。T0 测试合同虽要求非法字段向量，仍需把错误码、被拒字段和无副作用顺序写入批准的线级合同。
- **Host 状态/epoch 不是普通逐 bit 同步问题**：A4/A6 只说同步摘要；32-bit `mask_epoch` 若逐 bit 两级同步可能产生撕裂值，Host 会把结果匹配到不存在的 epoch。必须使用稳定握手、快照+有效标志或等价原子总线 CDC，并冻结 error/IRQ 的 sticky 与清除语义；否则 A6 的结果匹配合同不可验证。
- **A5 的参数来源仍有两套**：附录第 55–64 行只明确 depth/FWFT/auto，而 T0 测试合同第 48–50 行又加了 `read_latency=0`、`CDC_SYNC_STAGES=2`、`SIM_ASSERT_CHK=1`。这些实现参数和仿真专用参数必须在批准稿中标为唯一权威，不能让 T1 自行取 XPM 默认值。

上述问题尚未改变当前门：`P15_T0_REVIEW_REQUIRED / PROPOSED / ADMIN_REVIEW_REQUIRED / NO_RTL_AUTHORIZATION`。在 fence 字段、帧错误恢复策略、样本准入、busy 稳定性和状态 CDC 语义补齐并获批准前，不创建 T1 RTL。

### P15-T0 提案修订状态（2026-09-05）

- A2 已按 KISS 修订为“V2 8/10 beat 计数唯一权威，T1 不解释 TLAST”；严格 TLAST/整帧检查移到外层 packetizer，避免无预缓冲流式 wrapper 无法回滚的问题。
- A3 已补充建议线级格式：wrapper-only `0xA`、`fence_id=cmd_payload[31:0]`、成功响应类别 `0xD`、fence 前 `sample_ready=0` 且禁止预填、成功后只开放一个 8-beat 窗口。
- A4/A6 已补充 ready/valid 稳定和状态 CDC 建议：busy 只禁止新握手，非复位期间不撤销已呈现 payload；`mask_epoch` 只通过 result/fence 原子 payload，不做逐 bit CDC。
- A1/A5 已补充保留位/未知 opcode 错误优先级，以及 `FIFO_READ_LATENCY=0`、`CDC_SYNC_STAGES=2`、`SIM_ASSERT_CHK=1` 唯一参数。以上仍是待管理员批准的提案，不改变 `NO_RTL_AUTHORIZATION`。

## 状态校正与下一门

- **当前权威基线**：V2 OOC report head 与 RTL 均绑定 `f744bff2bdde68e138a7b2b348ce103bec1ab469`；其变更已随 PR #64 合并为 `main@a53a040`。P15-T0 规划随 PR #65 合并为 `main@618c1e4`，端口裁定稿随 PR #66 合并为 `main@a1457bb`。不要把旧 report head=`39e41d4` 的 0 DSP 结果或 V1 `5055073` 失败结果当作当前物理状态。
- **已完成证据**：单时钟专项 8/8、固定 `20 seeds × 100 samples = 2000` 个样本逐 beat 随机门、完整回归 `473/473（1 skipped）`，以及 4 DSP 网表证据。
- **已完成物理阶段**：使用 Vivado 2024.1 对 V2 RTL、器件 `xc7z020clg400-1`、100 MHz 约束执行了 OOC 综合/实现、资源、setup/hold 和 DRC，物理硬门通过。该结果不宣称板级、功耗或网络吞吐性能。
- **历史保留**：下方审计条目保留设计演进背景；其中标注为 V1/OF6 历史阶段的缺口不覆盖上述当前签核结果。

## 必读路由

- `.nexus-map/arch/systems.md`
- `.nexus-map/arch/dependencies.md`
- `.nexus-map/arch/test_coverage.md`
- `.nexus-map/hotspots/git_forensics.md`
- `.nexus-map/concepts/domains.md`

## [操作指南] 强制执行步骤

> 本节是对所有读取本文件的 AI 发出的硬性操作指令，不是建议。

### 步骤1 — 必须先读完以下所有文件（顺序不限）

读完本文件后，在执行任何任务之前，必须依次读取以下文件完整内容：

- `.nexus-map/arch/systems.md` — 系统边界与代码位置
- `.nexus-map/arch/dependencies.md` — 系统间依赖关系与 Mermaid 图
- `.nexus-map/arch/test_coverage.md` — 测试面与证据缺口
- `.nexus-map/hotspots/git_forensics.md` — Git 热点与耦合风险
- `.nexus-map/concepts/domains.md` — 核心领域概念

这些文件均为高密度摘要，不得以任务简单或只改一个文件为由跳过。

### 步骤2 — 按任务类型追加操作（步骤1 完成后执行）

- 若任务涉及接口修改、新增跨模块调用、删除或重命名公共函数：运行 `query_graph.py --impact <目标文件>` 确认影响半径后再写代码。
- 若任务需要判断某文件被谁引用：运行 `query_graph.py --who-imports <模块名>`。
- 若仓库结构发生重大变化：任务完成后重新评估并更新 Nexus 知识库。
