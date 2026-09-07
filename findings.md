# 调研与实验发现

## 2026-09-07 UART重分配 V14/V15

- 用户明确裁定`V14→UART_TX`、`V15→UART_RX`。当前B1A工程未占用这两个管脚；板厂HDMI例程将V14/V15作为并行RGB低两位，说明它们属于可用PL I/O，但也表示实板上与HDMI发送器输入共网。
- 新路径保持LVCMOS33。板载CH340物理连接仍在L17/M17，因此B1B必须使用外置3.3 V USB-TTL交叉连接：V14接适配器RX、V15接适配器TX并共地。
- 该改动改变XDC和硬件身份，旧bitstream/XSA不再用于后续B1B；必须在新源码提交上重新运行Vivado实现并生成新清单。

## 2026-09-07 B1B Fastlane V2

- 当前唯一由`git clean -ndX`列出的忽略目录是`boards/hellozynq/b1a_hw/build/`。该目录不能整体清理，因为B1B仍需复用其中的bitstream、XSA、build manifest和签核摘要。
- B1A RTL/XDC/BD/Tcl/IP身份未变，B1B入口无需重新运行Vivado；进入应用实现前只保留产物哈希、XSA可读、JTAG可见和UART设备定位四项低成本检查。
- B1B不等待PHY、UDP、DMA、NPU或ENeuron验证；这些仍由B1C及后续阶段关闭。
- bitstream和XSA SHA-256分别与manifest中的`5d0940eb...e6d6`、`053fc032...81df`一致。XSCT 2024.1可打开XSA，并识别`ps7_cortexa9_0/1`、`ps7_ddr_0`、`ps7_uart_0`和200 MHz FCLK0。
- 五份原始Vivado报告均被`build_manifest.json.reports_sha256`引用，合计不足1 MiB；它们仍属于可复核证据，不作为本轮清理目标。
- Windows仍只枚举蓝牙COM6/COM7，没有板载USB-UART端口。JTAG首次XSDB查询没有显式打印`targets`返回值，因此结果暂记为未裁定，不把空文本误判为无设备。
- 修正输出后XSDB列出APU、两个运行中的Cortex-A9和`xc7z020`，JTAG就绪项通过。当前唯一前置缺口是UART接收通道，不能用蓝牙COM6/COM7替代。
- 系统临时目录中12个早期ENeuron T1/T2调试日志共375084字节已移入Windows回收站；范围限定为明确的`eneuron_t1_*`、`eneuron_fifo_*`和`eneuron-t2-*`日志，可恢复。
- 最短主线路径是把代码合并门与阶段签核门分开：可复现构建和一次实板UART/DDR通过足以证明实现可进入主线；三次完整断电冷启动仍用于关闭B1B，不应被取消。
- 板厂资料明确板载`USB TO UART`使用CH340；Windows已安装`ch341ser.inf` 3.9.2024.9，并保留多个历史CH340 COM设备，但当前全部为`CM_PROB_PHANTOM`。因此无需先安装驱动，当前缺口是连接板正面左上角、拨码开关下方标有`UART`的USB-C口；Digilent `VID_0403:PID_6014`仅是JTAG通道。
- XSCT 2024.1的`hsi::open_hw_design`会把XSA内嵌bit展开到XSA同目录并覆盖同名磁盘文件，因此不能直接在正式build目录打开XSA。初始预检时standalone bit为冻结哈希`5d0940eb...e6d6`；检查后磁盘bit变为XSA内嵌版本`bebb577b...b941`，XSA自身仍为`053fc032...81df`。B1B下载前必须恢复冻结standalone bit，后续XSA检查改在独立临时目录副本上执行。
- 配置区核对证明XSA内嵌bit与独立重建bit从同步字后的4,045,516字节完全一致，payload SHA-256均为`b546109d...cfeb5`；两者只差160字节头中的生成时间。以manifest目标SHA穷举原构建时间字段得到`02:47:53`，恢复文件完整SHA精确命中`5d0940eb...e6d6`，正式bit身份已恢复。

## 2026-09-07 B1B 工具链与设备就绪

- 当前权威基线为 `main@065a68ce1fc87836ad3d0062883a226ba54e61d9`，B1A bitstream/XSA与正式报告仍保留在本地忽略目录，可直接进入软件bring-up。
- 本机存在 `G:\Xilinx\Vitis\2024.1`，但 `xsct/xsdb/vitis/bootgen` 未加入当前PowerShell PATH；下一步从安装目录定位受支持入口。
- Windows当前只枚举COM6/COM7两个蓝牙串口，没有发现明显的板载USB-UART设备。该事实不阻止先验证XSA/工具链，但阻止关闭UART实板门。


## 2026-09-07 B1A-HW 快速收敛

- GMII-to-RGMII v4.1 自动生成的 clocks XDC 已为 4 条 `TIMING-54` 创建 AMD IP 内部 waiver，并说明该接口的时钟间 false path 可安全忽略；不再将这 4 条已豁免项作为 B1A 阻断。
- 当前 6 条 `TIMING-18` 中，5 条是顶层 `RGMII_0_td[3:0]` / `RGMII_0_tx_ctl` 缺少 output delay，1 条是 MDIO 双向口缺少 input delay。RGMII TX 是上板链路正确性的直接阻断；低速 MDIO 项单独裁定。
- `REQP-1577` 为 GMII-to-RGMII IP 内部 MMCM 输出采用不同 buffer 类型的 DRC warning；在 setup/hold、route 和 DRC error/critical warning 均通过时暂不扩展处理，除非实板链路暴露相关问题。
- routed checkpoint 快速探针能找到 1 个 TX generated clock 和 5 个顶层 TX 端口，但按 IP 原 XDC 的 add/overwrite 组合补约束后，`TIMING-18` 仍为 6；下一步验证四条 rise/fall、min/max 约束全部显式保留的组合。
- 第二种约束组合验证通过：首条 max 后，其余 min、fall max、fall min 均使用 `-add_delay`，`TIMING-18` 从 6 降为 1；5 条 RGMII TX 缺失全部消失，仅剩 MDIO 输入项。该组合应落入板级 XDC。
- `report_compile_order -constraints` 已确认实现期顺序：IP clocks XDC 为第3项，板级 `hello_zynq_b1a.xdc` 为第4项，两者均为LATE但板级文件明确后读；generated TX clock在板级约束执行前可用。
- Vivado XDC不支持普通 `if`；同时RX `create_clock` 必须早于IP clocks XDC，而TX delay必须晚于它。最终结构拆成普通主XDC与独立LATE TX XDC，避免互相冲突。
- 拆分后的实现期顺序已确认：主XDC为NORMAL索引3、IP clocks XDC为LATE索引4、TX XDC为LATE索引5，满足RX早于IP、TX晚于IP的双向顺序要求。
- 干净提交 `18fd65c8465f047fbfb0fe63c81a39412a9ea6e5` 的Vivado 2024.1完整构建通过：setup/hold失败端点0/0、route error 0、DRC error/critical 0/0、RGMII TX缺失output delay 0。只保留1条MDIO input delay方法学warning和1条GMII-to-RGMII内部 `REQP-1577` DRC warning。
- 方法学报告仍列出4条 `TIMING-54`，但同一IP生成XDC包含AMD创建的对应waiver；按已确认的IP约束语义记录，不作为B1A-HW阻断。
- 最终资源为136 LUT、257 FF、0 BRAM、0 DSP、4 BUFGCTRL、1 MMCM；本地B1A build目录约26.9 MB。仓库忽略项中可安全清理的当前产物包括B1A build、`.Xil`、Python缓存、根Vivado日志和`clockInfo.txt`；B0 build包含历史实板流程产物，本轮不扩大清理范围。

- 2026-09-06：额度边界确认。GitHub Actions 当前因账户额度耗尽不可作为本阶段验收依赖；后续不主动触发或等待 hosted runner。GitHub 仓库、分支和 PR 仅用于版本归档与人工审查；未运行的 Actions 统一记录为 `NOT_RUN_BILLING_BLOCKED`，不得当作代码失败或通过。
- 2026-09-06：本机复现证据闭环。`python -X utf8 -m unittest -v test_reproducibility test_ci_fast_v1` 返回 12/12 通过；`python -X utf8 tools/repro/verify_repository.py --t1` 返回 `REPRO_G0_MANIFEST_PASS` 与 `REPRO_G1_T1_PROTOCOL_SLICE_PASS`。
- 2026-09-06：T1 协议切片修复已在工作树核对：非法 `SAMPLE_FENCE` 只产生错误响应；mask staging 未闭合时拒绝 fence；fence 响应回显真实 active epoch；四条 FIFO 的远端 `rst_busy` 经两级同步后汇合；Host 状态和错误标志使用 CDC 二级同步。该证据仍不等于 T1-01～T1-12 全量、T2、T3 或板级完成。
- 2026-09-06：扩展 T1 同频切片通过。新增响应背压 5 拍稳定性检查；样本首 beat 已绑定 epoch=1 后，在剩余 beat 期间发布 epoch=2，当前结果仍回显 1，下一样本结果回显 2；复位重入后 ready/valid 与旧 payload 均未泄漏。Icarus `compile=0 sim=0`，输出 `T1_PROTOCOL_SKELETON_PASS`。这仍只覆盖部分 T1 项目，不替代 T1-01～T1-12 全量、T2 或 T3。
- 2026-09-06：T1-02 首轮断言曾因只等待 3 个 NPU 时钟而误报 `STATE_CLEAR` 未生效；日志确认核心已接受 `op=8`。将 testbench 改为带 100 拍上限的状态等待后通过，并验证 `FREEZE_SET` 进入/退出及冻结期间配置拒绝。该修正是观察时序校准，不改变 RTL。
- 2026-09-06：T1-12 FIFO 边界切片通过。新增 `tb_npu_zynq7020_t1_fifo_boundary.sv`，对 128/128/64/96 bit 四种 payload 分别验证空读 underflow、depth=16+FWFT 外部容量 17、满写 overflow、读写指针回绕、FWFT 长背压稳定性和有序排空。既有 `test_host_bridge_xpm_wrapper` 也恢复为 5/5 通过；此前失败来自把外部可见容量误设为 16，不是 XPM 模型缺陷。
- 2026-09-07：T1-06 独立 fence 验收通过。新增 `tb_npu_zynq7020_t1_fence_accept.sv`：模型有效且 mask staging 未闭合时，`SAMPLE_FENCE` 只返回 `0xE` 且样本窗口保持关闭；完整发布 next epoch 后，fence 返回 `0xD`，逐字段核对 opcode、fence ID、active epoch=0 和保留位，并确认只打开一个样本窗口。Icarus 编译退出码 0，输出 `T1_FENCE_ACCEPT_PASS`。这不等于 T1 全量，也不覆盖 TLAST/T2/T3。
- 2026-09-07：T1-09 已按批准的 A2 形成独立边界裁定：当前 T1 wrapper 没有 TLAST 端口，因此记为 `NA_FOR_T1_WRAPPER`，不伪造 TLAST 仿真通过；未来外层 AXI-Stream shim/packetizer 仍需单独测试早到、晚到和缺失 TLAST。
- 2026-09-07：T2 首个可变时钟切片通过。参数化 testbench 在 `(NPU_HALF,PHASE)=(7,2),(9,1),(4,3)` 三组非整数关系下均完成跨域错误响应背压、模型/mask/fence 顺序、8/10 beat sideband、单窗口和复位重入，统一入口输出 `REPRO_G2_T2_VARIABLE_CLOCKS_PASS`。曾有一次 600 Host 周期结果等待误报，根因是慢 NPU 的观察窗口不足，改为 5000 后通过。
- 2026-09-06：为恢复免费 Git 推送，管理员已将仓库 Actions 权限设置为 `enabled=false`。三个本地提交已推送到现有 PR #68，远端 head 为 `3227162d8f8e321f4e6b479923db34403b84f87c`；API 返回 PR `OPEN / MERGEABLE` 且无 checks。空 checks 列表只表示 Actions 暂停，不能作为通过证据。

## 2026-09-07 GitHub 可复现性审计

- `git archive HEAD` 的隔离快照可完成 CI-Fast、NPU Oracle 和 artifact layout 共 57 项测试，说明当前已提交基线的一部分能脱离原工作树重放。
- T1 wrapper、testbench 和测试计划仍在本地 WIP；wrapper 当前存在未声明 `core_cmd_ready` 及前向隐式 wire 问题，不能编译，所以 GitHub 尚不足以复现 T1。
- 当前没有统一 Python 依赖锁；数据 fixture 生成器直接依赖 scikit-learn。复现入口必须区分“消费已提交 fixture”和“从源重新生成 fixture”。
- `run_vivado_npu_single_clock_ooc.ps1` 把 Vivado 固定到个人 `G:` 盘，破坏跨机器入口；应改为参数/环境变量定位，同时严格核对 Vivado 2024.1。
- 单时钟 OOC manifest 已正确绑定 RTL、runner、Tcl、报告、器件、100 MHz 和 4 DSP，是 G2 的基础；重新运行应比较机器判据，不应要求含路径/时间戳的全部报告逐字节相同。
- `artifacts/README.md` 的单时钟 OOC 描述仍停在历史 setup 失败，与当前 V2 manifest 的 `VIVADO_OOC_PASS` 冲突，实施可复现性门时必须修正。
- GitHub 官方当前说明：完整 commit SHA 是 action 不可变引用方式；当前工作流使用可移动的大版本标签，应在 R8 获批后改为 SHA 固定并保留标签注释。
- AMD 当前 UG894 继续支持用 batch Tcl、命令参数和 `report_* -file` 固化可重放流程；现有非工程模式 Tcl 方向正确，主要缺口是入口路径、统一验证器和干净快照门。

## 2026-09-05 P15-T0 静态合同审计

- 四条逻辑流的职责已经清楚：128 位命令、128 位响应、样本输入和结果输出；AXI-Stream 位于异步 FIFO 外侧，T1 不接 AXI-Lite、DMA、Ethernet 或 PS7。
- 样本的完整 FIFO 载荷是 `data[31:0] + sample_id[31:0]`，实际为 64 位；结果的完整 FIFO 载荷是 `data[31:0] + sample_id[31:0] + mask_epoch[31:0]`，实际为 96 位。32 位只表示 AXI `TDATA`，不能代表 FIFO 宽度。
- 只读审计发现七项 T1 阻断：命令字段布局冲突、V1/V2 framing 冲突、命令与样本跨 FIFO 顺序未定义、reset-busy/ready 跨域汇合未冻结、TLAST/TUSER 错误语义不完整、FIFO 参数和资源归因不足、目标器件与旧 Host Bridge OOC 不一致。
- 当前骨架/端口表采用 `[127:124]` 4-bit opcode；Oracle V3 采用 `[7:0]` 8-bit opcode。现有随机 TB 也使用高 nibble+epoch，且只做样本后再改 mask 的串行测试，不能证明四 FIFO 并发下的顺序合同。
- 当前仍是 `P15_T0_REVIEW_REQUIRED / NO_RTL_AUTHORIZATION`；审计不授权创建顶层 RTL。

## 2026-09-05 P15-T0 附录二次复核

- 复核发现原 A2 的严格 TLAST/整帧丢弃承诺无法与无预缓冲的逐 beat 流式 wrapper 同时成立；建议改为 T1 只采用 V2 8/10 beat 计数，TLAST 仅作外层提示，严格包检查交给更外层 packetizer。
- A3 需要冻结 wrapper-only `SAMPLE_FENCE` 的完整编码、成功响应类别、fence ID、sample FIFO 预填和 `sample_ready` 窗口；建议使用 opcode `0xA`、`fence_id=cmd_payload[31:0]`、响应类别 `0xD`，fence 前不允许样本预填，成功后只开放一个 8-beat 窗口。
- ready/valid 合同必须区分“禁止新握手”和“撤销已呈现事务”：busy 变化不能在非复位期间撤销已呈现 valid/payload；复位才是取消边界。
- `mask_epoch` 不能逐 bit CDC；建议只通过 result FIFO/fence 响应的原子 payload 传递，Host 状态只同步单 bit 摘要。
- A1/A5 还需把保留位/未知 opcode 错误优先级以及 XPM `FIFO_READ_LATENCY=0`、`CDC_SYNC_STAGES=2`、`SIM_ASSERT_CHK=1` 写成唯一参数。
- 以上结论已写入 Nexus 二次复核摘要；A1-A7 仍为提案，当前不授权 T1 RTL。

## 2026-09-05 P15-T0 fence 条件再校正

- 发现若把核心 `runtime_idle=1` 作为 `SAMPLE_FENCE` 必要条件，已发布但尚未在下一样本首 beat 激活的 mask 可能使摘要暂时为 0，导致首次样本死锁。
- 已将建议条件改为核心 `sample_ready=1`、无 `result_valid/rsp_valid`、wrapper 无开放样本窗口，并由 wrapper 追踪模型/mask staging 是否闭合；该条件不依赖不可见的 `mask_state` 内部编码。
- 测试合同已加入“已发布 mask 等待首 beat”向量，防止把 `runtime_idle=0` 错当成 fence 不可接受。

## NPU 局部剪枝 NP4B 实施授权（2026-08-29）

- 八项决定已批准，后续不再为两输入输出兼容、核心 opcode 扩展、共享 gate 或 Host Bridge 集成保留分支。
- 实施采用纵向 TDD：先证明 committed snapshot 公开接口，再接 ENeuron 原子观察；先证明 Pulse FEEDBACK exactly-once，再组合 commit→clear；最后才接网络屏障。
- 每个可独立签核阶段及时更新规划、发现和进度文档并提交，避免把多个未验证层堆入同一提交。
- 公共 gate 的响应是单槽并可背压，网络提交屏障必须为每个 gate 保存 done 位；只等待“当前拍全部 rsp_valid”会漏掉先完成者。
- 网络原子性需要两个屏障：先汇合 10 个 gate commit 响应，再汇合 10 个核心 `STATE_CLEAR` 响应；外部 mask epoch 只能在第二个屏障后公开。
- 既有 `pulse_mini_network_4x2x2.sv` 逐核串行调度且输出只有两输入，不能直接扩参数得到批准的 `4→8→2`；NP4B3 应把公共 commit/clear 屏障与模型专用 TICK/训练调度分开。
- Pulse 旧形式 harness 把 `past_valid` 仅在非复位分支置位，同时在该分支第一次执行 `assume(rst)`，会让复位释放轨迹不可达；只有“无反例”而没有成功命令 witness 的旧日志不能继续使用。
- 修复后的 reach 使用 falsify 证明成功路径可达；日志中的 `model found: FAIL!` 在这些专门的 reach 查询中是预期 witness，不是设计失败，verifier 必须按查询类型计数。
- `4→8→2` 的一拍路由不需要先运行隐藏层、再运行输出层；可以同拍启动 10 个核心，只要输出输入连接的是旧 `pending_hidden`，并在全部响应完成后才替换 pending。这既保留固定一逻辑 tick 延迟，也避免组合穿透。
- episode 尾部 flush 必须是独立命令语义：只让输出层消费最后一个 pending，隐藏层 response ready 保持 0，完成后清 pending。
- ENeuron 的 committed snapshot 可以零状态成本导出：纯组合展开正式 snapshot 数组即可，snapshot 无效时保留旧数据并由 valid/commit ID 决定事务意义。
- 单核和网络的 commit→clear 所有权需要参数化而不是复制 wrapper：默认单核自行 clear；网络实例关闭自动 clear，由全局 barrier 在十个 gate 全部成功后统一广播 clear。

## NPU 局部剪枝 NP4B 接入审计（2026-08-29）

- ENeuron 四输入 SNAPSHOT 在接受后经过四拍扫描和一拍 commit 才原子发布；只读端口必须连接正式 `eligibility_snapshot[]`，不能连接扫描工作副本。
- 非零 MOD 在最终 commit 沿清核心 `snapshot_valid`，tile 再晚一拍完成；因此 evidence 必须在合法 MOD 接受边界读取，不能等 MOD done 后补读。
- ENeuron 零 MOD 不清核心 snapshot，但 tile 会消费 tile 级 pending snapshot；NP4B 必须以 tile pending commit ID 为事务真值，不顺手改变现有核心语义。
- Pulse-Mini-L/L2 都在合法 FEEDBACK 接受沿清 captured direction；wrapper 的时序逻辑可在同一沿看到旧值，core response 周期再读取已经来不及。
- Pulse 的成功非零 FEEDBACK response 必须等 OBSERVE 完成后再向上游公开，避免权重已更新而 utility 尚未更新；response 背压期间必须禁止重复观察。
- `cmd_ready` 只说明核心没有未消费 response，不能代替网络 episode/路由安全边界；commit 需要独立 `prune_safe_boundary` 或等价调度状态。
- 提交新 mask 后必须先清动态学习历史再开放 TICK，否则新结构会继承旧结构的 trace/evidence；`STATE_CLEAR` 不能同时清 utility/mask，也不能替代 CONFIG 的 `PRUNE_CLEAR`。
- 现有 `4→2→2` 网络的输出核只有两个输入。两层严格 `2:4` 必须使用新的 `4→8→2` 测试拓扑，不能用计数或命名掩盖扇入不满足。
- NP4B 的逻辑 `issue_mask` 和发射计数仍不是 BRAM 真跳读、共享 lane 周期或功耗证据；这些结论继续留给 NP6/NP7。

## NPU 局部剪枝 NP4A/NP5 公共控制器（2026-08-29）

- S2-only 生产控制器不需要权重输入；NP5 原“负权重绝对值”覆盖属于已淘汰的 S0/S3 路径，保留它会无谓增加 abs 和比较逻辑，因此从 RTL 门中删除。
- 四拍顺序扫描足以在不暴露中间密度的前提下得到确定性 top-2；同分只使用较小输入编号，不需要额外权重破同分状态。
- 60000 条三模型协同事务零差异，说明固定 gain 差异可以完全留在无状态二位饱和适配器，公共 utility/mask 控制器无需复制三套。
- 两个负向变体分别证明原子发布和确定性 tie-break 都是可观测合同，不是注释性要求。
- 既有 Pulse 形式 harness 的复位假设会形成不可满足轨迹；新 harness 使用首拍 reset、后续 release，并额外要求成功 commit 可达，避免把空证明写成 PASS。
- 当前 ENeuron 核没有正式 snapshot evidence 端口，Pulse 会在 FEEDBACK 时清证据，现有 tile 输出又只有两输入；这三点使“独立控制器通过”不能直接升级为“现有网络已集成”。

## NPU 局部剪枝 NP4 V1 接口冻结（2026-08-29）

- 六项决定已由用户批准，后续 RTL 不再保留 detector gate、渐进剪枝或直接权重恢复的可选分支。
- 同一个严格 `2:4` 控制器服务隐藏层和输出层；模型差异只留在固定 gain=`1/2/1` 的证据适配边界，不复制三套排名逻辑。
- 一次原子提交意味着活动 mask 只能从稠密 `1111` 一次切换到合法双位 mask；第二次提交必须拒绝，直到显式 `PRUNE_CLEAR`。
- `issue_mask` 的位置是硬件收益声明的关键：只有在读取请求和计算发射前完成相交，才能计作真实结构跳过；隐藏和输出节省必须分账。
- 本次批准只解决设计授权，不构成 RTL、协同仿真、形式、资源、时序或功耗证据。

## NPU 局部剪枝 B2.1 输出门控（2026-08-28）

- 三模型 output-2:4、detector-3:4、detector-2:4 均保持 BAcc/coverage 100%，全网读取/发射分别为 120/120/80，全部跨过 132 的 45% 系统门。
- output-2:4 的节省严格分解为隐藏结构 80、输出结构 40；没有把输入零活动或 detector channel gate 重复计入。
- 两连接输出无法以原权重 2 跨过阈值 6；每输出两次正常训练后，ENeuron/L/L2 保留权重分别达到 7/4/6，零直接权重或阈值写入。
- detector-2:4 虽减少 66.67%，但需要新增跨层通道 enable 和路由状态；output-2:4 复用同一控制器并已减少 50%，按 KISS 选择后者。
- learned 与随机 mask 都为 100%，因为四个 detector 是人为等价冗余；只能声明冗余消除，不能声明输出 utility 优于随机。
- NP2、NP3、B2.1 软件门均已通过，允许开始 NP4 接口审核；RTL、时序、周期和功耗仍完全未证明。

## NPU 局部剪枝 NP3 闭环（2026-08-28）

- 三模型一次 `2:4` 与软件渐进 `3:4→2:4` 在同一父 checkpoint、相同两次微调预算下都保持 BAcc/coverage 100%，最终 mask 相同；渐进没有收益，应删除中间状态机。
- 错误符号实际作用于 ENeuron modulator 和 Pulse FEEDBACK 后，三模型 BAcc/coverage 均降到 0%，证明正常微调依赖正确第三因子而非账本装饰。
- 三模型所有分支均为零 Host mask 写入、每 detector 一次真实 commit；最终被剪权重与局部历史不更新，mask 在微调期间不变。
- 同分支 INFER 探针直接复用活动核心，权重、学习历史、utility、mask 和 mask-valid 指纹全部冻结，不依赖每样本重新复制来制造通过。
- 错误符号分支的 80 次读取来自任务彻底失败，不能算有效系统收益；正常分支仍为 160，B2.1 仍是 NP4 前唯一未闭合的软件硬门。

## NPU 局部剪枝 NP2 量化扫描（2026-08-28）

- Pulse-Mini-L 的失败原因不是一位 presence 天生不能累计，而是等级 1 与 `old-1+level` 的固定衰减正好抵消；固定映射 `0→0, 1→2` 后 BAcc/coverage 从 0% 恢复到 100%。
- 三模型最小合格 gain 为 ENeuron/L/L2=`1/2/1`；更大 gain 没有精度收益，并开始产生 1.07%..3.21% 的真实 utility clip 或 83.33% 的窗口稳定性下降。
- 入选配置的边界同分率、输入编号破同分率、clip event rate 和最终占满率均为 0%；最后三个 stable 前缀及误导证据前后 mask 保持率均为 100%。
- 三模型入选 mask 都是前四 detector `0x5`、后四 `0xa`，全网络读取仍为 160，只减少 33.33%；量化修正没有解决输出层瓶颈。
- L 的软件算法路线重新开放，但这不等于 RTL 零成本或系统收益通过；三模型仍需 NP3 和 B2.1。

## NPU 局部剪枝 B2（2026-08-28）

- B1 过于简单的根因是输出只需要一个 detector 响应；B2 将输出门槛提高为 3/4 detector，随机掩码 median 才降到可辨识的 75%/25%。
- 权重全部饱和后 S0 只能按输入编号，median BAcc 为 50%；最后一次误导证据使 S1 为 0%，而长期累计 S2 只有 ENeuron/L2 能恢复到 100%。
- 在 B2 原始 gain 1 下，Pulse-Mini-L 的等级 1 每次被统一衰减抵消，因而不能保留重复证据；NP2 已证明映射到等级 2 可恢复累计，不能再把失败归因于一位 presence 的原理限制。
- S3 在 10 seed 上相对 S2 没有精度增益；后续不应为 S3 增加权重破同分 RTL。
- ENeuron/L2 隐藏读取减少 50%，但输出层仍稠密，导致全网络只减少 33.33%。要达到 45% 系统门，下一步应剪输出 detector/通道，而不是先优化四选二控制器。
- L 的 66.67% 读取减少来自 detector 不发放和输出层无工作，伴随 BAcc 0%；性能失败产生的“节省”必须判为无效。
- B2 是人为构造的评分压力任务，只能证明局部证据表达力；不能替代图像识别、真实模型分布或 RTL 物理收益。

## NPU 局部剪枝 B1（2026-08-28）

- ENeuron、Pulse-Mini-L、Pulse-Mini-L2 的 S0-S3 都保留隐藏输入 0/1，留出集均为 20/20；共同随机掩码 `1001/1100` 均降到 10/20。这证明 B1 能识别“保留任务通道”和“随机删除”的差异。
- S0、S1、S2、S3 在 B1 的 mask、立即精度、微调后精度完全相同；B1 不具备资格迹评分相对幅度评分的辨识力，不能用于选择 S3 RTL。
- Pulse-Mini-L2 在当前 P8 序列中也只产生一级方向证据，没有使用到其二级证据容量；这解释了 L2 与 L 在 B1 完全一致，但不构成 L2 永远无收益的结论。
- `2:4` 的静态稀疏率是 50%，不等于真实工作量必降 50%。保留通道恰好高频活动且输出层未剪时，全网络发射计数只减少 18.21%–19.78%。
- 不应期本身造成的零读取必须与结构剪枝分开；若在核心判断 refractory 前无条件累计 gate.issue，会虚报读取和结构节省。
- 一拍隐藏路由需要 episode 尾部只排空输出层，不能再推进隐藏层；漏掉 flush 会把最后 tick 的合法响应误判为 abstain。
- B1 立即剪枝后已经保持 20/20，说明该小任务不需要稀疏微调恢复；B2 仍需比较一次剪枝与渐进剪枝，不能外推。

## NPU 局部剪枝 NP1（2026-08-28）

- 公共控制器必须接收由各神经元适配器归一化后的 `evidence_levels=0..3`；直接在控制器内右移原始证据会把 Pulse-Mini-L 的 `0/1` 和 L2 的 `0/1/2` 消成零。
- S2 比较键冻结为 `utility, input_index`，S3 才加入 `abs(weight)`；若 S2 也用权重破同分，两种方法会退化为同一算法。
- V1 的“不恢复”要求 `mask_valid=1` 后拒绝第二次剪枝，直到 CONFIG 执行 `PRUNE_CLEAR`；否则更高 commit ID 可让已剪连接自动长回。
- `groups_skipped` 不能把 `activity_mask=0` 计为结构收益。NP1 因而分开记录 `inactive_groups` 与非零活动被结构完全挡住的 `groups_skipped`，并直接累计 `reads_saved_by_structure`。
- 每次本地证据观察增加严格递增的 observation ID，避免同一 CAPTURE/snapshot 被 S2/S3 重复累计；非法命令只改变拒绝日志和计数，不改变权重工作量、分数、掩码或提交状态。
- 固定 B0 摘要中，16 种 activity mask 在结构掩码 `1010` 下产生 32 次稠密请求、16 次真实读取和 16 次结构节省；这是黄金模型的发射计数证据，不是现有并行 RTL 已获得周期或功耗收益的声明。

## Pulse-Mini L1 泄放升级（2026-08-19）

- 当前默认 Pulse-Mini 没有膜电位泄漏，导致长时间稀疏输入仍能累加；这是保持架构简洁时最直接、最有价值的能力缺口。
- L1 只增加一个共享小计数器，不引入乘法器、第二套资格迹线、片上损失函数或新的网络协议。
- 语义冻结为：每接受一个逻辑 `TICK` 计时；到期先将 soma 向零移动一个单位，再加入本 tick 有符号输入并饱和，最后判阈值；不应期暂停计时。
- `LEAK_PERIOD=0` 是无泄放基线。扫描 `{0,1,2,4,8,12}` 后，周期 8 是当前预注册硬门下的最小通过候选；这不是对所有任务和权重范围的全局最优证明。
- 该升级最多称为 `Pulse-Mini-L` 的时间过滤增强，不能称为 ENeuron 等价物；它仍然只有方向型学习状态，没有多位 eligibility、独立电流状态或自适应阈值。
- 三方正式比较已把 `Pulse-Mini(leak_period=0)` 与 `Pulse-Mini-L(leak_period=8)` 分开报告；共同单元任务、噪声任务和固定 `4->2->2` 网络上两者结果相同，主要可观察差异出现在稀疏事件积分。
- 六个权重 `+1` 的正事件在 gap 12 时，无泄放 Pulse-Mini 仍发放 1 次，Pulse-Mini-L 为 0；这证明计时器确实增加了时间选择性，但不代表周期 8 对所有输入密度和权重幅度都最优。
- RTL 旁证当前覆盖默认 `LEAK_PERIOD=8`；无泄放基线的对比结论来自 Python 黄金模型消融，不能写成两个参数版本都做过独立 RTL bit-exact 签核。

## 当前项目

- 项目目录初始为空，没有可复用的模拟器或测试框架。
- 采用标准库 Python，避免把 NumPy/PyTorch 依赖带入硬件原型验证。

## 设计假设

- 输入采用离散时间步的二值事件。
- 突触权重采用有符号定点整数；脉冲到达时直接条件累加权重。
- 三因子候选通过有符号调制信号兑现资格迹线，覆盖无监督/奖励/局部监督接口。
- 复杂度先用状态位数和每事件操作数做代理，后续 RTL 综合再测 LUT/BRAM/Fmax。

## 安全边界

- 模拟结果只证明行为和相对取舍，不等价于 FPGA/ASIC 的综合面积、功耗或时序结果。
- 任务调制信号是外部提供的局部训练信号；单个神经元不会自行产生完整的多层信用分配。

## 实验结果

- `counter_if`：10 种训练顺序的区分成功率 0%，正负模式都产生 2 个脉冲，权重不变。
- `pair_stdp_lif`：10 种训练顺序的区分成功率 0%，四个权重都饱和到 7，说明无任务调制时会把两类活动一起增强。
- `three_factor_lif`：10 种训练顺序的区分成功率 100%，最终权重稳定为 `[7, 7, -7, -7]`，正样本平均 6 个脉冲，负样本平均 0 个脉冲。
- 推荐模型状态位代理为 169 位，基线为 84 位，二因子模型为 108 位；推荐模型每输入事件约 16 个抽象操作，二因子约 9 个。
- 100 组包含丢脉冲或额外同类脉冲的扰动测试中，推荐模型正样本非零响应率和负样本零响应率均为 100%。

## 推荐取舍

- 目标是任务导向自训练、延迟奖励或局部误差：保留每突触 eligibility。
- 目标只是无监督相关性学习或聚类：可以移除 eligibility，使用二因子 STDP，减少状态和更新操作。
- 推理阶段必须关闭 `learn_enable`，并验证权重在整个推理过程中不变。

## 网络级实验

- `DigitalSNN2Layer` 使用 4 个输入轴、2 个隐藏神经元、2 个输出神经元；隐藏到输出固定 1 tick 路由延迟，并在 episode 结束时 flush pending spike。
- Host 在 episode 结束时捕获每个神经元的 eligibility 快照，用 `commit_id` 延迟提交调制；重复或未知 commit 会被拒绝。
- 20 个训练种子下，可寻址目标调制的干净任务成功率为 100%，100 个扰动样本的平均准确率为 100%。
- 全局 reward 配合逐 tick WTA 时，20 个种子干净准确率均值仍只有 22.5%；WTA 限制同 tick 竞争，但不能自动解决隐藏层信用分配。
- 两阶段 Host 训练在 20 个种子下达到 100%：先用目标调制训练并冻结隐藏特征，再用 epsilon 探索和 reward 只训练输出动作层。
- 该结果证明 Host 训练闭环可用，但不证明全局奖励、多层信用分配或通用任务已经解决。

## Goal 证明审计（2026-08-11）

- 当前 `task_plan.md` 仍将“RTL 与 Python 黄金模型逐周期 bit-exact”列为未完成项，因此现阶段不能声称设计已经完全符合 goal。
- 已有证据覆盖算法行为、训练/推理模式隔离、网络闭环和周期传输模型；尚未覆盖真实 HDL 编译仿真、形式性质、综合、时序、资源、功耗与板级运行。
- “作为 AI 自训练与推理的硬件基石”应被定义为可组合、可训练、可冻结推理且接口确定的最小单元；它不等于已经证明可解决任意任务、具备通用信用分配或达到实用规模。
- 2026-08-11 实际回归：`python -m unittest -v` 共运行 27 项，25 项通过、1 项失败、1 项错误；`rtl_smoke.py` 因 `rtl_reference.py` 的负移位异常退出，延迟 modulator 测试也未产生预期权重更新。`python -m compileall -q .` 通过。
- `rtl_reference.py` 与 `digital_lif_core.sv` 目前并非 bit-exact：至少存在 eligibility 衰减公式、同周期多次非阻塞写覆盖、不应期输入门控、post trace 更新和阈值稳态机制差异。
- YosysHQ SBY 文档把 `bmc/prove/live/cover` 分成不同验证模式；形式工具只证明已编码性质及其假设范围。EQY 用于两个电路设计间的形式等价，不能证明高层 AI 目标本身。
- Verilator 官方文档支持 lint、断言和覆盖率插桩；AMD 官方文档要求在完整布局布线后使用 Timing Summary 做时序签核，并指出准确功耗需要真实切换活动而非默认活动率。
- 三因子学习的一手研究支持“eligibility trace + 第三因子”作为延迟信用分配机制，但这只支撑学习规则选择，不推出当前定点参数、RTL 实现或任意任务性能正确。

## V1 语义冻结发现（2026-08-11）

- `docs/design/recommended_design.md` 的单时间步顺序先执行输入积分，后写“不应期屏蔽输入”，无法唯一确定不应期内 `I` 是否吸收事件；RTL 前必须改成唯一 next-state 方程。
- 当前规格没有定义 pre/post 同 tick 时 eligibility 的合并方式，也没有定义 `tick_valid`、`mod_valid`、`weight_we` 同周期的优先级。
- V1 应避免对同一寄存器在一个 `always_ff` 周期中多次非阻塞赋值；先在组合逻辑中累计唯一 next value，再在时钟边沿提交。
- 高层 `ThreeFactorNeuron` 当前实际使用趋零衰减、更新后的 `pre_trace` 参与 eligibility、`post_trace` 累加以及自适应阈值；`digital_lif_core.sv` 当前分别使用算术右移、旧 `pre_trace`、post trace 直接覆盖且没有阈值寄存器，不能直接声称与算法模型等价。
- 本机存在 `winget` 和 `choco`，可以尝试安装真实 HDL 工具；在安装并运行编译器前，任何“RTL 已实现”的结论都只能保持未验证。
- 已通过真实 Icarus Verilog 12.0 编译并运行 `digital_lif_core.sv`；`rtl_cosim.py` 在 5 个 seed、每个 128 个随机 tick（另含 mod-only、CSR 写、INFER 冲突周期）下逐字段比较 131 个状态，全部通过。
- Yosys 0.56 `hierarchy -check; proc; opt; check; stat` 通过，报告 0 个结构错误；同时报告 6 类宽度/内存展开警告，当前仍需作为实现质量问题记录。
- Verilator 5.040 可解析 RTL，但默认 lint 仍有 29 个 `WIDTHEXPAND/WIDTHTRUNC` 警告；`--Wno-fatal` 才能返回成功，尚不能称为零警告 lint 签核。
- 当前 Python/静态/RTL 回归总计 30 项通过；这证明单核行为闭环，不证明网络 RTL、FIFO、snapshot/commit 或目标器件 PPA。

## 网络协议缺口（2026-08-11）

- `TileCycleTransport` 尚未实现 `TICK_BEGIN(event_count)` 的数量校验；少发、多发或错 tick 事件不能作为原子事务被拒绝。
- `EPISODE_END` 路由 flush 在输出 FIFO 溢出时可能先消费部分 pending spike，再抛出异常，缺少 all-or-nothing 语义。
- 多个 eligibility snapshot 的提交顺序会影响饱和权重结果；必须冻结为单调 `commit_id`，或实现与顺序无关的基准权重/累加器。
- `DigitalSNN2Layer.apply_host_modulator` 当前缺少 TRAIN/IDLE、episode、地址和提交顺序门控；网络级推理冻结还没有对 traces、eligibility、threshold 做完整断言。

## 多周期引擎初审（2026-08-12）

- 最新 `digital_lif_engine.sv` 已由 Icarus Verilog 以 `-g2012` 编译通过；这只证明语法与展开成立，不证明事务语义等价。
- 当前 `mod_valid=1, modulator=0` 会进入 `S_MOD_SCAN` 并在末地址清除 `snapshot_valid`；Python 黄金模型把零调制定义为 no-op 并保留 snapshot，二者确定不等价。
- `ADDR_BITS` 默认固定为 2；当 `N_INPUTS > 4` 且调用者忘记同步修改时，`scan_index` 会回绕而无法到达末地址。参数必须自动推导或增加 elaboration 检查。
- `TICK_SCAN` 使用 32 位 `current_acc_work` 跨地址累计，扫描结束后才执行一次 `sat_state`；这一点与黄金模型“先求和、后饱和”一致，仍需随机反例验证。
- 首轮 Yosys 检查发现 `address_as_int` 同时由 `always_comb` 和 `always_ff` 驱动，形成真实多驱动；必须删除共享临时变量后再接受结构检查结果。

## 多周期引擎签核（2026-08-12）

- 多周期核通过 20 个 seed × 1000 个混合事务，共 20000 个事务；另有 10 个 seed × 256 个事务直接断言 busy 期间架构状态不变和事务延迟合同。
- 最终 FSM 把每个突触拆为读取/衰减与更新两拍，并把电流饱和、膜电位相加、发放判断分拍；定宽 8/12/16 位趋零衰减消除了通用 32 位函数产生的无意义长进位链。
- Vivado 2024.1、`xc7a35tcpg236-1`、100 MHz OOC post-route：`WNS=+0.469 ns`、`TNS=0`、setup/hold 失败端点均为 0。
- 最终资源：813 LUT、544 FF、0 BRAM、0 DSP；相对单周期参考核 2338 LUT / 214 FF / WNS=-22.793 ns，LUT 明显下降，寄存器因流水和事务工作区增加。
- DRC 没有 error/critical warning，但有一个 OOC 环境的 `CFGBVS-1` warning；运行器日志首行的 Tcl store 权限 critical warning 来自本机启动环境，不是设计 DRC。功耗 0.080 W、Medium confidence，仍只是 vector-less OOC 估算。

## 4->2->2 Tile 初次物理实现（2026-08-12）

- 20 seeds × 500 个 Tile 混合事务，共 10000 个事务与独立 Python oracle 一致；完整回归 41 项通过。
- Vivado 2024.1 初次 OOC route 成功，内部最差 setup/hold 均为寄存器到寄存器路径，分别为 +0.231 ns / +0.128 ns；资源 3157 LUT / 1972 FF / 0 BRAM / 0 DSP。
- 初次报告缺少 `HD.CLK_SRC`，AMD UG905 对 OOC 实现建议同时使用 `create_clock` 和 `HD.CLK_SRC` 改善时钟延迟、偏斜与 CPR 估计；最终签核应以后续补约束重跑结果为准。
- Tile 顶层数据端口没有板级 input/output delay 或 partition-pin 位置，因此当前 OOC 只签核内部寄存器路径，不签核未来 Host/总线接口的端口时序。

## V3 决策批准后的实施发现（2026-08-13）

- 用户已批准 V3 六项冻结决策，后续实现不得用 Teacher、Hybrid、reward、Python 或 RTL 结果相互代偿。
- 最新独立 Tile 原始报告为 `3152 LUT / 1972 FF / 0 BRAM / 0 DSP`，100 MHz OOC 的 WNS/WHS 为 `+0.213/+0.026 ns`，TNS/THS 和 setup/hold failing endpoints 均为 0。
- 独立 Tile 的 OOC 白名单告警当前是 DRC `CFGBVS-1 x1` 与 methodology `TIMING-18 x180`；它们反映未指定板级配置电压和端口 delay，不能被描述为板级签核。
- T0 资源预算与当前测量值分离：预算冻结为 `LUT <= 3200`、`FF <= 2000`、`BRAM36/BRAM18/DSP = 0`；摘要仍记录精确实测值。
- G4 数据泄漏检查必须使用排除 split、seed、sample index、skeleton id 和 label 的 `input_hash`；manifest 完整性另用包含 label 的 `example_hash`。
- Temporal 正式数据冻结为跨 model seed 共享；`generate_temporal_split` 不再接收模型 seed，统计单位为同一数据集上的 paired model-seed。
- `input` schema 精确限定为 `episode_ticks/events`，`input_hash` 只重建这两个语义字段；额外 `label_hint/nonce` 不能泄漏标签或掩盖跨 split 重复。
- Temporal validator 现在接收冻结 `master_seed/B`，在结构检查后重放生成器并逐 split 做 canonical exact comparison，认证 seed、sample/skeleton ID、phase、顺序和 provenance。
- manifest 升级为 `g4_temporal_dataset_v2`，同时记录 `input_hashes/input_sha256` 与 `example_hashes/example_sha256`，源码固定绑定实际 `g4_benchmark.py`；development manifest 共 1312 个唯一输入/完整样本。
- 最终一键审计已闭环：159 项回归、两套有限 formal、额外 10000 个 Tile 事务、独立 Tile、真实 XPM 与完整系统 Vivado 报告均通过；XPM 和系统 CDC 的固定 marker 均使用各自严格解析器，不放宽通用 `KEY=VALUE` 合同。
- 该 PASS 只恢复并加强既有 G1/G2/G3a 工程签核，同时证明 Temporal development 数据合同可复现；它不等于三任务 P0a/P0b、训练能力、P5 RTL 任务 cohort、P6 扩展性或完整 G4 通过。

## T3 P0-P4 实施审计（2026-08-13）

- 现有 `HostTrainingController.reward_modulator(label, result)` 同时读取真实标签并按 hidden/output 活动生成 neuron-specific 调制，不能作为 V3 P3 的纯全局 reward 证据。
- T3 主实现应独立于历史 `network_sim.py` 训练 helper：复用数字神经元/网络动力学和 commit 接口，但把数据、训练权限、strict decoder、负对照、统计与结果 manifest 放在新的 G4 模块中。
- 当前 RTL 主结论限定 no-WTA；所有正式 P1/P2/P3 实验必须显式构造 `hidden_wta=False, output_wta=False`，历史 WTA sweep 只能保留为旧探索证据。

## 4->2->2 Tile 最终签核（2026-08-12）

- 补 `HD.CLK_SRC` 后的最终 OOC：100 MHz WNS +0.148 ns、TNS 0、WHS +0.057 ns、THS 0；3861 个内部端点零失败，route error 0。
- 最终资源为 3156 LUT / 1972 FF / 0 BRAM / 0 DSP；功耗 0.104 W、Medium confidence、无活动文件，只能作为 vector-less 估算。
- 固定黄金测试确认一 tick 跨层路由、非零 eligibility、合法 MOD 后真实权重改变、过期 commit 拒绝、零调制和 INFER 冻结；完整回归为 42 项通过。
- 当前 Tile 直接接收每 tick 的 4-bit spike mask。`TICK_BEGIN/INPUT_EVENT/FIFO` 和带 `episode_id/tick/neuron_id` 的输出标签仍是外层传输协议，不是当前 Tile 已实现端口。

## Tile 协议修复与有限形式验证（2026-08-13）

- 组合派发曾按“合法命令”跳过非法高优先级请求，而时序仲裁按“命令存在”拒绝该事务，导致返回错误的同时仍可能写权重或启动 TICK；定向 Icarus 回归已复现并锁定该反例。
- 修复后，SNAPSHOT、WEIGHT、MOD 的存在先确定优先级，合法性只决定是否产生子核请求；非法高优先级命令不会放行任何低优先级请求。
- Yosys 0.56 的 `async2sync` 会自动 lower SystemVerilog `$check`；私有 Tile 信号不能从顶层 harness 用层次名可靠引用，断言必须放在 Tile 的 `FORMAL` 条件块或显式导出。
- 真实四核 Tile 在仅约束首拍复位、后续释放的敌对输入下完成 24 拍 BMC：约 451 万变量、1252 万子句，无反例；覆盖最长 17 周期训练 TICK，但不是无限时域归纳或全状态形式等价。
- 2026-08-13 Vivado 2024.1 OOC 重跑结果：setup `+0.053 ns`、hold `+0.026 ns`、route error 0，3144 LUT / 1971 FF；功耗 0.103 W 为无活动文件的 Medium-confidence 估算。

## Host Bridge V1 第二轮反例审查（2026-08-13）

- 原响应布局只保留 6-bit opcode，不能完整关联 8-bit 命令；已改为命令/响应同构 128-bit 布局，响应有效性仅由外部 `valid` 表示。
- TRAIN `EP_END` 若先 flush、后检查 commit，会在重复或过期 commit 上形成不可回滚的部分提交；必须在 flush 前同时检查 snapshot 槽、commit 严格递增、episode/tick 状态和 Tile ready。
- `bridge_rst` 会复位真实 Tile 核心并把权重恢复为初值，不是仅清 transport；保留权重的恢复路径必须使用有序、不可抢占的 `ABORT`。
- 当前设计没有 completed transaction cache；`txn_id` 只能用于关联，不能提供重传去重或幂等 exactly-once。
- tick 计数需要 17-bit 内部尾态：允许 `16'hffff` 成功提交，随后只允许 `EP_END/ABORT`，防止 16-bit 静默回绕。
- Python `flush_route()` 无条件推进输出层一次；即使 `pending_hidden=0`，RTL 也不得优化掉该 output-only tick。
- Tile 权重读口是组合口，Bridge 必须使用 setup/capture 两拍锁存地址和数据。
- 本机 Vivado 2024.1 的 `xpm_fifo_async` 支持冻结的 depth/width/FWFT/CDC 参数；真正风险在 reset-busy 门控和“只有实际 FIFO 接受边沿后才释放事务”。
- 现有 RTL 测试仍未覆盖真实双时钟 CDC、响应背压和随机 producer/consumer；这些已列入 Bridge 验收门槛，不能沿用单时钟 Tile cosim 代替。
- Bridge 若要在 flush 前验证 commit 严格递增，不能猜测或复制 Tile 元数据；Tile 需导出只读 `last_commit_valid_state/last_commit_id_state`。
- `STATUS_READ` 必须独立于 `tile.ready` 和 episode active 状态，否则 fatal 或异常 busy 时无法诊断；需要 Tile 的命令在 LAUNCH 状态等待 ready，本地命令直接完成。
- delayed MOD 只快照 eligibility，不快照权重基准；pending snapshot 期间若允许 `WEIGHT_WRITE`，最终更新会依赖 Host 插入的模型写操作，因此 V1 冻结为“可读、不可写”。
- 一个 flit 可能同时违反多个规则；若不冻结错误优先级，Python oracle 与 RTL 即使都无副作用也可能返回不同 status。审核稿已增加确定性首错顺序。

## Host Bridge V1 第三轮终审（2026-08-13）

- TRAIN `EP_END` 的 flush spike 必须在 flush done 边沿锁存到事务私有 `ep_end_flush_spikes`，否则后续 SNAPSHOT 会覆盖 Tile 的单周期输出。
- STATUS 必须分成 session 页和 snapshot/commit 页；page 1 在 snapshot/last commit 无效时对应 ID 强制返回 0，避免 RTL 与 oracle 对寄存器残留产生分歧。
- `EP_START` 与 `EP_END` 一样使用完整预检和响应接受边沿提交；Host 可见 architectural session/input-tick staging 只在 `response_accept` 更新，事务 working state 可在执行中更新。
- 错误优先级不能把依赖 session 模式的动态字段检查放进共同前缀。共同 `BAD_FIELD` 只检查静态布局；INFER `EP_END` commit 必须为 0 放在 `BAD_STATE/EPISODE_ID` 之后。
- `fatal_error/fatal_opcode/fatal_phase` 是首次内部故障 sticky 状态；普通协议错误不修改，后续 fatal 不覆盖，只有 hard reset 清除。phase 覆盖 EP_START clear、TICK、EP_END flush/snapshot、MOD、WEIGHT、ABORT clear 和 controller internal。
- 四个 2-bit modulator 只允许 `11=-1/00=0/01=+1`；`10=-2` 在启动 Tile 前返回 `BAD_FIELD`，以匹配当前符号调制软件模型。
- 本机 Vivado 2024.1 的 `xpm_fifo_async` 源码确认支持 depth 16、128-bit、FWFT、`CDC_SYNC_STAGES=2`、`wr_rst_busy/rd_rst_busy`；FWFT 配置明确补充 `FIFO_READ_LATENCY=0`。官方实例模板同时明确 `rst` 必须同步于写时钟，因此 Bridge 改为 Host/Tile 两域分别全同步采样 `bridge_rst`，不把异步置位复位直接接入 XPM。
- XPM 后续 reset 不能在上一次 write-side `wr_rst_busy` 退出前重入。V1 选择外部合同而非片内排队器：只有 command/response 两个 FIFO 的 write-side busy 都为 0 后才允许再次断言 `bridge_rst`；不满足该条件的物理接口必须在板级适配器中延迟 reset 请求。
- 实现拆为七类依赖任务：Tile 原语、Python oracle、Bridge controller、XPM wrapper、双时钟协同仿真、formal/CDC、Vivado OOC。旧 Tile post-route 报告不能作为增加 ROUTE_FLUSH/Bridge 后的签核证据。
- T2 bit-exact 审查进一步冻结：错误响应 `arg0/arg1` 清零；H0/H1 地址 0..3、O0/O1 地址 0..1；epoch 为 32-bit modulo 且仅合法 MOD（包括全零调制）增加；WEIGHT_WRITE 不增加；INTERNAL_FATAL 不提交正常 architectural next-state。

## Host Bridge T3/T5 实现发现（2026-08-13）

- T3 真实集成协同仿真必须同时比较三层真值：128-bit response、11 个 Host architectural/fatal 字段、79 个 Tile/四核内部与 commit 字段；仅比较响应不足以证明错误无副作用或 response_accept 提交边界。
- controller 的 Host architectural 状态允许在 Tile 执行期间保持旧值，只有响应接受边沿提交；Tile 状态可在响应前完成更新，因此 PRE 检查应使用“旧 Host 架构 + 新 Tile 真值”，POST 检查使用“新 Host 架构 + 同一 Tile 真值”。
- 20 seeds x 1000 混合命令会充分覆盖所有成功 opcode，但任意 128-bit 位型主要命中 BAD_OPCODE/BAD_FIELD；动态首错链仍需独立定向流硬性覆盖所有非保留、非故障注入状态码。
- T5 双时钟 scoreboard 以 `host_cmd_valid && host_cmd_ready` 作为 outstanding ledger 登记点，以 `host_rsp_valid && host_rsp_ready` 作为按序 oracle 提交/比对点；不能用 producer 发起时刻或 Tile 域 FIFO 读边沿替代 Host 可见事务边界。
- hard reset 是破坏性边界：T5 在 reset 断言后丢弃全部 outstanding ledger、重建 Python oracle，并验证 FIFO/session/commit/epoch 清空及权重恢复 INIT_WEIGHT；不得期待 reset 前命令或响应在 reset 后恢复。
- T5 的随机流必须独立覆盖 command FIFO empty/full、response FIFO empty/full、两侧同时 push/pop、16 深度指针回绕和长时间 response backpressure；仅用低占用随机 ready 不能证明满队列门控。

## Host Bridge T4/T7 最终签核（2026-08-13）

- Icarus FWFT 模型必须区分“外部消费当前预取字”和“RAM 字搬入预取槽”。首次预取也要推进内部 Gray 读指针，否则第 17 个可见字无法释放 RAM 槽并导致 transport 死锁。
- Vivado 2024.1 官方 XPM xsim 实测本配置 `FIFO_WRITE_DEPTH=16 + READ_MODE=fwft` 的 command/response 外部可见容量均为 17；两条 FIFO 的填满、排空、64 字回绕、长背压和 hard reset 全部通过。
- XPM wrapper 综合为 4 个 RAMB36，仿真专用 reset 重入断言没有进入综合网表；wrapper CDC 只有 4 条 XPM 内部 reset synchronizer `CDC-3 Info`。
- 完整系统 post-route 使用 Host 50 MHz、Tile 100 MHz：Host WNS/WHS `+14.306/+0.105 ns`，Tile WNS/WHS `+0.081/+0.058 ns`，两域 TNS/THS 和 setup/hold violations 均为 0。
- 系统资源为 `3682 LUT / 2486 FF / 4 RAMB36 / 0 DSP`；route errors、DRC Error/Critical Warning 均为 0。功耗 `0.112 W` 为无活动文件的 Medium-confidence vector-less 估算。
- 系统 CDC 共 8 条，全部在官方 XPM 内部：4 条 Gray pointer `CDC-6 Warning` 和 4 条 reset sync `CDC-3 Info`；XPM 外 Critical/Unsafe/Warning 为 0。
- OOC 仍没有真实顶层 input/output delay、partition pin、配置电压和板级复位源。Vivado `report_cdc` 明确跳过无 input delay 的顶层端口，因此 `bridge_rst` 的物理异步来源必须留到板级适配/XDC 签核。

## G4 能力边界前置审计（2026-08-13）

- `make_dataset()` 只有两个固定训练模板；`clean_accuracy` 复用训练样本，`make_noisy_dataset()` 也只从相同模板做至多一次删除和一次同类插入，当前没有真正的 train/validation/test 隔离。
- `run_network_sweep.py` 的 teacher 模式没有传入 `init_seed`，20 个 seed 只改变训练顺序和扰动集；不能据此声称完成 20 个独立模型初始化。
- `artifacts/results/network_sweep_results.json` 早于当前 `network_sim.py`，且 `verify_goal.py` 不执行网络 sweep 或检查结果新鲜度，因此其中 teacher/hybrid 100%、reward-only 22.5% 只能作为历史结果，不能作为当前一键验收证据。
- 当前网络和 Host 协议硬编码二分类 4->2->2；`teacher_modulator()` 直接按标签向隐藏层和输出层发放 neuron-specific signed modulator，而 reward-only 只用全局正确/错误信号按活动路径门控，两者验证的是不同信用信息条件。
- G4 前置验证必须至少包含独立任务族、严格 split 哈希隔离、独立初始化/训练顺序/数据 seed、推理前后全部学习状态逐字段冻结检查，以及 majority、未训练网络和 label-shuffle 负对照。
- 主会话使用无落盘脚本独立复跑三任务探测，Python 3.14.2；`network_sim.py` SHA-256 为 `9AF92DC0C8FA5447EF5986E35392AB240999F7B2BDDA192CEC30B26CADD3F798`，`neuron_sim.py` 为 `1B31C6A84A77B4B47669D02EB2A7FC46C6BDD70051799DCF059E75D51002E3A2`。
- 10 seeds 探测结果：Spatial teacher/hybrid 均为 2560/2560，reward 为 384/2560；Temporal 三模式均为 0/2560；XOR teacher/reward 为 0/2560，hybrid 为 8/2560。
- Temporal/XOR 的输出几乎全部是 `prediction=-1`，所以零准确率首先混合了输出活动不足，不能直接当作时间表征或 XOR 容量失败。正式方案必须先有 label-blind activity calibration 和 decision coverage 门槛。
- 当前 `_predict()` 在非零平局时返回 class 0，会形成类别偏置；G4 验收应在外部 evaluator 使用 strict spike-count，平局统一 abstain 并计错，不必改核心神经元状态方程。
- 当前 Tile 没有 WTA 仲裁，而历史 reward/hybrid sweep 在 Python 中启用了 WTA；no-WTA 才能作为当前 RTL 主结论，WTA 结果只能作为新增 RTL 的候选上限。
- e-prop 原文支持“局部 eligibility trace x top-down learning signal”的结构，并明确 neuron-specific feedback 与 global learning-signal baseline 不等价；这与当前 teacher 和 reward-only 的信息条件差异一致，但不证明本项目的定点规则已经实现 e-prop。
- GEM 原文定义任务测试矩阵及 ACC/BWT/FWT；本项目可以借用这些持续学习评价指标，但不能因此声称已实现 GEM 算法。

## G4 V2 反例审查与活动校准（2026-08-13）

- 48 tick、固定全 2 权重、关闭学习时，`B=1` 的三任务 hidden/output 均无活动；`B=2` 时三任务 hidden/output active rate 均为 100%。同一全 2 初态下，高层模型与四个 `RtlReferenceNeuron` 在 300 个样本上的 hidden/output spike count 完全一致。
- 随机初始化 `1..3` 的 20 seeds 中，`B=2/3/4` 都存在 seed 15 完全无输出，XOR 还有 seeds 3/8 仅 75% 活动。burst 只可作为固定初态编码正对照，不能保证随机初态或训练后网络不死亡，也不能靠继续放大 `B` 掩盖失败。
- 旧 Temporal `ABABABAB/BABABABA` 的首事件直接泄漏标签。V2 改为 `AABABBAB/ABBAABAB`，两类首尾相同、A/B 各 4 次，并要求 first-only、last-only、直方图和时间骨架 nuisance-only 基线接近 50%。
- 所有任务必须先生成 label-blind 时间骨架，再构造类别 counterfactual；抖动、拒绝采样、首尾 tick、间隔分布和总事件数均不得携带标签。Calibration 独立成 split 并进入 manifest/hash 隔离。
- label shuffle 的低 overall accuracy 可由全 abstain 伪造。V2 增加 prediction 固定的 evaluation-label permutation 零分布，并要求 training-label shuffle 同时报 activity、coverage 和 conditional accuracy。
- 二分类下 `(action, reward)` 可精确恢复 label。P3 主结论因此只允许向四核广播同一标量调制；预先冻结且不依赖 action/label/task/sample 的 neuron-specific feedback 单列为 feedback-alignment 候选。
- `hybrid_no_wta` 在当前全局 `learn_enable` 下只能冻结隐藏权重，不能冻结隐藏 trace、eligibility 和自适应阈值。冻结全部隐藏学习状态需要分层 `learn_enable`，并重做 bit-exact、formal 和 Vivado 签核。
- P4 带 task context 时只能称 task-aware/task-incremental continual learning。每个 model seed 内的 6 个任务排列是重复测量，统计与 bootstrap 单位必须是 seed，并要求至少 8/10 seeds 按排列聚合后通过。
- P5 必须用 `RtlReferenceNeuron + HostBridgeOracle`，不能直接用语义不同的 `network_sim.py`。每个 RTL seed 先 hard reset、12 写、12 读回并检查元数据；训练遵守单槽 snapshot，commit ID 在 16-bit 不回绕范围严格单调。
- P5 spike count 只在 `host_rsp_valid && host_rsp_ready` 握手时累计，并分别读取 `TICK_COMMIT.arg0[3:2]` 与 `EP_END.arg0[3:2]`。Host 黑盒只验响应、计数、权重和元数据；eligibility/trace/threshold/membrane 等只作为 testbench 白盒证据。
- 最新独立 Tile 原始报告为 3152 LUT / 1972 FF、WNS +0.213 ns、WHS +0.026 ns；README/`docs/verification/goal_audit.md` 仍是旧数字，且 `verify_goal.py` 尚未独立审计 Tile 报告。V2 将其冻结为正式实现的 T0。

## G4 V3 反证审计（2026-08-13）

- V2 Temporal `AABABBAB/ABBAABAB` 可由第 2 或第 5 个 symbol 100% 分类；前四位 A 计数为 3/2，后四位为 1/2，多个固定位置 bigram 也直接泄漏。任意两条不同固定字符串都至少有一个绝对位置不同，不能继续靠替换固定模板解决。
- V3 使用循环 motif `AABABABB/AABBABAB`，均匀 phase 0..7，输出旋转后的 8-symbol cycle 再重复开头 2 symbols。独立枚举验证：两类各 8 条序列且集合不相交；每个绝对位置 unigram、每个固定位置 bigram、前后 5-symbol 计数，以及全局 1/2/3-gram histogram 的类条件分布完全相同；4-gram 分布不同。
- 10-symbol、`B=4` 至少占 40 tick；48-tick episode 无法容纳 9 个可拉伸间隔。V3 统一改为 64 tick，旧 48-tick burst 结果降级为探索证据，正式 calibration、activity 和高层/RTL-reference spike count 必须重跑。
- P4 若允许 Host 保存旧样本、旧标签或无限片外状态，可以靠联合重训代做持续学习。V3 主结论冻结为 task-aware、no-replay，并增加相同 context/数据/预算的 joint-training upper bound。
- P5 若训练器同时生成命令、期望值和解码，会形成同源软件自证。V3 隔离语义训练器、raw golden-vector 生成器和独立 scoreboard，并加入固定手算向量。
- 当前大规模双时钟 Icarus cosim 使用接口等价 FIFO；真实 AMD XPM 只有独立 xsim 证据。V3 将 P5a 定义为接口等价 FIFO 的完整 cohort，P5b 定义为真实 XPM 的代表性短 cohort，两者同时通过才称完整真实 Host Bridge 仿真闭环。
- 固定 4->2->2 的 P0-P5 不能证明可扩展性。V3 增加 P6：共享流水线和同步 RAM 的 4->2->2、16->16->2、64->32->2 三参数点，独立验收 cycle reference、Vivado OOC、资源增长、吞吐和状态容量。
- reward 日志不能证明实现未读取 label/action。V3 将主 API 收窄为 `reward_to_modulation(reward) -> (m,m,m,m)`，增加 AST/依赖检查和“相同 reward、改变 label/action/prediction，输出逐位不变”的边界测试。
- Host Bridge V1 的 `INPUT_EVENT` 固定 synapse 0..3，权重地址固定四核，`MOD_COMMIT` 固定四路调制，不能驱动 P6 的 16/64 输入网络。P6 必须先冻结可寻址流式协议 V2，并与 V1 分开完成 oracle、cosim、formal/CDC 和 Vivado 证据。
- P4/P5/P6 必须按训练模式绑定结论：Teacher 通过不能代偿 Hybrid 或纯全局 reward。V3 增加声明矩阵，要求 `verify_g4.py` 对每项输出 PASS/FAIL/NOT-RUN；只有全部通过才允许 `G4_FULL_PASS`。
- V3 Temporal 64-tick 活动探针覆盖 2 labels x 8 phases x 8 skeletons，共 128 样本：`B=1` hidden/output 全静默；`B=2/3/4` 两类 hidden/output active 均为 100%；所有 burst 的高层模型与四个 `RtlReferenceNeuron` spike count 均 128/128 一致。固定全 2 权重时两输出始终同计数，因此 strict decoder 全 abstain，进一步说明活动正对照不等于分类能力。
- Temporal 容量预判先确认 225 种有效 A/B 隐藏权重产生 137 种唯一脉冲签名；随后检查 6929 个唯一隐藏签名组合，并对每组枚举全部 225x225 输出读出器，32 样本最好为 25/32、coverage 32/32。独立 `DigitalSNN2Layer` 重放同样为 25/32。该结果只说明容量风险，不证明不存在更好权重，也不是正式验收。

## G4 T3 执行规格前置审计（2026-08-13）

- 完整 `DigitalSNN2Layer.inference()` 调用前后全部学习字段当前不相等：episode reset 会清 trace/eligibility 并恢复 threshold。该事实不应直接触发无必要的方程/RTL修改；正式 P0a 应审计 EP_START 白名单复位、推理区间逐字段冻结，以及整笔调用的持久训练状态不变。
- 历史 reward/hybrid helper 分别读取 label/result 或按 action 定向输出调制，不能复用为 `reward_global_no_wta`；正式模型适配器只接收 `sample["input"]`。
- 正式计分和动作选择必须从 output spike count 调用 `strict_decode()`；禁止使用非零平局偏向 class 0 的 `NetworkEpisode.prediction`。
- Temporal 只有 8 个有效离散权重；既有 Train 最优 78.125% 是固定 2-hidden 的容量硬风险。正式 direct-weight 将对 Temporal 做结构化覆盖，对 Spatial/XOR 各做 100000 个唯一候选。
- 本机测得 64-tick inference 约 0.622 ms/episode、训练提交约 0.894 ms/episode、朴素 direct search 约 49 candidates/s。T3 的 final P1-P3 预计 30-45 分钟，全部 P4 模式预计 1.5-2 小时。
- `docs/design/g4_t3_execution_spec.md` 已将 P0a 拆分、permutation 数值门、P4 聚合/context/no-replay、负对照配对、direct-search、统计边界、Spatial/XOR、训练预算和 joint budget 写成 12 项待审核合同。
- D1 独立反证确认 inference 的正确合同不是“整次调用全部学习字段不变”，而是 EP_START 白名单基线转换、其后的推理区间逐字段冻结、整笔调用持久训练状态不变；适配器还需显式拒绝在未 capture/未 commit 的信用状态进入 INFER。
- D2 独立反证确认共享数据的 20 model seeds 必须共用同一 evaluation-label permutation；若 permutation seed 含 model seed，会错误压低零分布方差。正式零分布改为每 `(task, split, permutation_index)` 一份公共平衡置换。
- D4 独立反证确认 context 在 tick 0..15，但一拍路由会把 context 来源活动延伸到 tick 16；正式分类只统计 tick 17..79 和 EP_END flush，并同时审计 context hash 与原 payload hash。
- D5 本机 Python 3.14.2 实测 `-I` 仍包含全局 `site-packages`，`-I -S` 才排除；no-replay worker 因此冻结为绝对 `sys.executable -I -S -u`、临时 cwd、环境 allowlist、model-only bundle 和模式专用 IPC。audit hook 只作为 trusted-worker fail-closed 断言。
- `python -I -S network_sim.py` 的只读探针进一步确认安全路径不会加入脚本目录，旧模块因无法导入同目录 `neuron_sim.py` 而退出；正式 model-only worker 必须是自包含单入口或通过固定标准库 bootstrap 显式加载已验哈希 bundle，不能借 `PYTHONPATH/site-packages` 绕开隔离。
- D6 不能按 `(epoch, sample_position)` 临时派生探索随机量；broker 必须预生成不可变 `RandomPlan`，主实验与 training-label-shuffle 记录相同计划哈希和初态 digest。
- D7/D10 独立审计要求冻结有序双隐藏签名、搜索 batch/top-64/邻域/去重算法，以及 Spatial/XOR 的 bit 位序、first_start、canonical offset、sample 顺序和 ID；否则 100000 候选和数据 split 都不可复算。
- D8 的 P3 evaluation-permutation comparator 冻结为逐 seed 的 10000 次公共置换指标均值；main-eval/main-shuffle 与 overall/conditional 共四组 paired-bootstrap 下界都必须严格大于 10pp。
- D11 checkpoint 必须在 clone 上只读评估，tie-break 使用最终 12 权重中位于 +/-7 的数量，不能使用会被 Validation inference 污染的累计 saturation counter。context admission checkpoint 与跑满预算的 P4 single endpoint 是两个独立产物。
- D12 预算按成功接受并完成的训练 episode 对应 MOD_COMMIT 计数，即使 delta 为 0 或权重饱和也计入；每个排列/single/joint 独立 reset，commit ID 从 0 开始，最大单 run 为 18432 次且不得回绕。
- direct search 的 49 candidates/s 测量只覆盖 Train 32；按 Train+Validation 160 样本线性外推，Spatial/XOR 每任务 100000 候选约 170 分钟，两任务约 5.7 小时。Temporal 约 3.51 亿次输出读出检查仍需先做 chunk/vectorized benchmark。
- D5 最终反证发现“bundle 加载前安装 audit hook”与“无条件拒绝 compile/exec/import”不可同时执行：本机 Python 3.14.2 探针确认 `compile(bytes, path, "exec")` 和 `exec(code)` 会分别触发 `compile`、`exec` 审计事件。规格已收敛为固定 bootstrap、一次性 `LOADING_VERIFIED_BUNDLE`、路径/源码哈希/code-object 三重绑定，并在外层 `exec` 放行前切换到 `SEALED`；运行期继续拒绝全部动态加载。
- D5 修订后经 Host/no-replay 独立终审放行，规格 SHA-256 为 `D88EBE4A64C34DAE42E5C16888E2F786F4C560D6BE0B90EBFF1F48749009DE0C`，未发现剩余 P0/P1。实现时还必须给 bundle 使用受限 `__builtins__`、移除 `__import__`，并静态检查 AST/字节码无 import；原因是已缓存模块的再次 `__import__` 不保证产生新的 import 审计事件。

## 原始 Goal 对齐复核（2026-08-13）

- 当前 `digital_lif_engine.sv` 的权重、pre trace、eligibility 和 snapshot 都是每核寄存器数组；`digital_snn_tile_4x2x2.sv` 固定实例化 2 个 4-input 隐藏核和 2 个 2-input 输出核。它证明了神经元方程与固定小网络可综合，但没有证明资源可随突触数主要进入 RAM，也没有证明可复制到实用规模。
- 本地学习路径确实存在：episode 内生成 eligibility，`SNAPSHOT` 锁存，`MOD_COMMIT` 在核内执行 `weight += modulator * eligibility >> LEARNING_SHIFT`。因此 Host 不需要计算逐突触 delta。
- 但 Host Bridge 同时暴露无权限分层的 `WEIGHT_WRITE`，idle 且无 pending snapshot 时可直接改任意权重。现有训练日志若只观察最终权重，不能单独证明权重来自可塑路径；正式训练闭环必须审计命令轨迹并要求训练区间没有 `WEIGHT_WRITE`，或在正式运行角色中硬件/协议禁用该命令。
- 历史 Python Hybrid 在 feature/reward 阶段之间直接赋值随机输出权重；这只能视为初始化/阶段重载，不能作为纯片上可塑训练证据。正式路径必须通过受审计 `WEIGHT_WRITE` 初始化后封闭该权限，再以 `MOD_COMMIT` 完成全部学习。
- 因而原始 Goal 当前最准确状态是：神经元最小学习机制已建立，固定网络数字前端已建立；“训练真实性的任务级 RTL 闭环”“共享 RAM 可扩展网络”和“板级实际闭环”仍未完成。T3 只需保留足以排除标签泄漏、Host 代算权重和无效任务的最小门槛。
- 对上述结论再次按最初问题反审计：共享 RAM 大规模化和板级实际闭环是更强工程目标，不应作为“最小数字神经元基石”成立的必要条件；可信 Host 场景也不要求新增 `RUN_SEAL`。核心唯一未闭合项收敛为：在同一真实 Host Bridge + Tile RTL run 中，以命令账本证明初始化后无直接写权重，并完成训练、局部 MOD 更新、权重读回、冻结推理和未训练输入验证。

## 原始 Goal C1 冻结合同（2026-08-14）

- 硬复位初态四核权重全部为 2；固定两轮训练，每轮顺序为 label 0、label 1，commit ID 为 0..3。
- Teacher 调制按 H0/H1/O0/O1 排列：label 0 为 `(+1,-1,+1,-1)`，label 1 为 `(-1,+1,-1,+1)`；训练区间不发送 `WEIGHT_WRITE`。
- 严格解码规定输出计数平局（包括 0,0）为 abstain；训练前 clean 为 `(-1,-1)`，两轮后 clean 为 `(0,1)`。
- 两轮后冻结权重为 H0=`(-6,-7,7,7)`、H1=`(7,7,-6,-7)`、O0=`(7,-7)`、O1=`(-7,7)`，`weight_epoch=4`。
- `make_noisy_dataset(seed=3,count=100)`、全部 86 个唯一扰动形态和 seed 0..99 各 20 样本均为 100% accuracy/coverage；正式 M3 RTL run 使用同一 seed 的 20 个扰动样本缩短仿真。
- 一轮训练后仍为严格 abstain，因此 2 epochs/4 commits 是该冻结初态和任务下的最小可靠合同，不是任意任务的泛化结论。

## 原始 Goal M3 实际 RTL 证据（2026-08-14）

- 同一真实双时钟 Host Bridge + Tile 实例连续接受 957 条命令；训练起点为响应索引 64，命令 SHA-256 为 `191d7c588411515f4386685b6dfcd8ce7e3894a21f87ff3a54a40de2f9989c09`。
- 响应账本 SHA-256 为 `cb63bcc596843607cdb7c774a91a8ffd38d9b21ee304cd266ecd33e2974a5256`，hash chain 尾值为 `cf4b268a199675d71462f1b6ec55a76f38691f4e6dbd90d9cf8d1b72e1509a74`。
- 四次 `MOD_COMMIT` 后各紧跟 12 次 `WEIGHT_READ`；48 个逐突触更新全部符合 `delta=(mod*eligibility_snapshot) >>> 3` 和 `sat(weight+delta,-7,+7)`，并覆盖正负算术右移与双向饱和。
- 训练区间 `WEIGHT_WRITE` 出现数和成功数均为 0；最终 `weight_epoch=4`。训练前 clean 为全 abstain，训练后 clean `(0,1)`，20 个冻结扰动样本 20/20 正确，推理后最终权重未改变。

## ENeuron 1.0 发布审计（2026-08-19）

- 当前目录和父目录都没有 `.git`，因此 1.0 需要在本目录新建 `main` 仓库，而不是接续未知历史。
- Git 全局身份已配置为 `Nept Epslion <11226778+Nept-Epslion@user.noreply.gitee.com>`。
- 当前 M1-M4 的最强闭环证据是 169 项回归、Tile/Controller 有限 BMC、10000 个 Tile 压力事务、957 条真实双时钟 M3 命令、48 次逐突触本地更新核对和冻结推理 20/20。
- XC7Z020 单核现有实测为：4 输入 `818 LUT / 544 FF`，2 输入 `718 LUT / 380 FF`，均为 `0 BRAM / 0 DSP`；它们是当前完整三因子核的上界参照，不是原始极简计数器方案的实测结果。
- `verify_goal.py` 默认审计既有 Tile、XPM 和系统 Vivado 产物，并检查报告时间不早于源码。若整个报告目录被忽略，干净克隆无法复验默认路径。
- 1.0 应保留验证器读取的文本报告、机器摘要、Tile 实现 DCP、Tile Vivado 日志和真实 XPM `simulate.log`；其余综合 DCP、Vivado 工程缓存、波形、VVP、Python 缓存和大体量 formal 日志可忽略。
- Pulse-Mini 的规划必须与 1.0 分开：1.0 是已验证的完整三因子硬件基线，Pulse-Mini 是重新审视原始计数/分频构想后的低成本候选，不能用估算资源冒充综合实测。
- 发布交叉审查发现 `docs/design/rtl_contract.md` 仍保留早期 Tile 数值 `3144/1971/+0.053 ns`；已按冻结摘要统一为 `3152/1972/+0.213 ns`。
- Git 检出不保留原始 mtime，而 `verify_goal.py` 会检查报告晚于源码；因此全新检出的权威复验入口是 `python verify_goal.py --rerun-vivado`，默认命令只适用于已保存同一工作区时间关系的审计。

## Pulse-Mini 方案结论（2026-08-19）

- 原始四输入方案的 84 位状态代理成立，但上限复位、单向增强、无抑制、分频方向不明、内部 RST 和无延迟反馈使它不能直接完成任务导向训练。
- Pulse-Mini 初稿曾保留 3 位模 8 脉冲进度和 2 位三态方向；该方案已在语义反审查中废止，最终推荐为 4 位有符号连接、4 位最近输入窗口、正/负两个 presence flag，以及共享 8 位有符号胞体、4 位最近输出和 4 位同步不应期。
- `train_post` 只进入学习时间检测器，不直接拉高 `spike_out`；它允许可信 Host 提供神经元级教师事件，同时逐树突变化仍由本地输入历史决定。
- 单槽 CAPTURE/FEEDBACK 只对单生产者、严格有序链路承诺 exactly-once；不增加 core commit ID、多槽 RAM 或 FIFO，跨 CDC/重试由 wrapper 加序号。
- 算法与 pending 状态约 69 位；综合目标为 `140~240 LUT / 100~140 FF / 0 BRAM / 0 DSP`，这是待 RTL/Vivado 验证的预算，不是实测。
- 以 XC7Z020 的 53200 LUT 为边界，按约 45% 资源预留后，固定四输入核的工程量级约 121~209 个；首版阵列目标为 128 核，只有 routed 通过后才能改称实测容量。

## Pulse-Mini 语义反审查修订（2026-08-19）

- 独立审查确认：跨样本保存 3 位分频进度会与 `STATE_CLEAR` 冲突。清除它会让短样本中的弱连接不可观察；保留它又会让结果依赖前一个样本。因此推荐 Pulse-Mini 删除跨样本分频进度，输入脉冲直接条件加入当前有符号连接；原始分频仅在 P1 做忠实成本基线。
- 独立审查确认：一个饱和三态不能同时保证“冲突抵消”和“顺序无关”。已改为每条树突两个 presence flag；CAPTURE 时仅正证据为 `+1`、仅负证据为 `-1`、两者同现为 `0`。
- 连接更新已冻结为数值规则 `weight_next=saturate(weight + feedback_sign * captured_direction,-7,+7)`；4 位编码 `1000` 的 `-8` 非法并返回错误。
- 已冻结窗口只随成功接受的逻辑 TICK 推进、同 tick `natural_spike OR train_post` 只算一个 post 事件、阈值使用本 tick 贡献后的胞体、presence flag 只在 P0 明确顺序表后写 RTL。
- 分立 valid/ready 端口改为统一 `cmd_valid/cmd_ready` + `rsp_valid/rsp_ready`；非法请求必须握手返回错误，`WEIGHT_READ` 必须返回符号扩展数据。无 core commit ID 时，exactly-once 只承诺单生产者严格有序链路，跨 CDC/重试由 wrapper 加序号。
- `STATE_CLEAR` 仅在 idle 且无 pending 时接受，清动态与学习证据但保留连接；INFER 的冻结只约束 TICK，不把显式样本边界清除误判为学习写入。
- Pulse-Mini 目标预算更新为 `140~240 LUT / 100~140 FF / 0 BRAM / 0 DSP`，算法与 pending 状态约 69 位；XC7Z020 容量表改按约 45% 资源预留计算。
- 目标声明收窄为“可作为固定小网络构件”；新增 P8 固定 `4->2->2` 训练/冻结推理闭环，未通过前不宣称已经完成网络级基石。

## Pulse-Mini P2 黄金模型（2026-08-19）

- 新增 `pulse_mini_reference.py`：固定四输入、权重 `-7..+7`、八位有符号饱和胞体、阈值 6、不应期 1 tick、窗口 3；实现 `MODE_SET/STATE_CLEAR/TICK/CAPTURE/FEEDBACK/WEIGHT_WRITE/WEIGHT_READ` 和单槽严格有序 `cmd/rsp` valid-ready 事务。
- 参考模型以每条树突正/负 presence flag 记录先后证据；`CAPTURE` 映射为 `+1/0/-1`，`FEEDBACK` 按一步数值更新并在 `-7..+7` 饱和，非法四位权重 `1000 (-8)` 和反馈编码 `10` 显式拒绝。
- `INFER` 的 `TICK` 不改变权重、年龄、presence 或 pending 学习字段；`train_post` 只参与学习事件，不伪造自然 `spike`。`STATE_CLEAR` 保留连接，仅在无 pending 时清动态与证据。
- 新增 `test_pulse_mini_reference.py`，14 项回归覆盖全部 16 输入掩码、所有输入排列、正负零连接、正负胞体饱和、窗口端点和冲突证据、反馈饱和/零消费/exactly-once、pending 背压、非法模式与权重编码、CONFIG 写入、推理冻结、结构化日志。`python -m unittest -v test_pulse_mini_reference.py`：14/14 通过。

## Pulse-Mini P3-P8 证据（2026-08-19）

- `pulse_mini_core.sv` 与 `pulse_mini_reference.py` 逐事务一致；`python pulse_mini_cosim.py` 输出 `PULSE_MINI_COSIM_PASS seeds=20 transactions=20000`。
- `& .\run_formal_pulse_mini.ps1` 使用 Yosys 0.56 SAT depth=20 输出 `PULSE_MINI_FORMAL_PASS depth=20`，无 model found。
- `pulse_mini_negative_control.py` 输出 `PULSE_MINI_NEGATIVE_CONTROL_PASS duplicate_feedback_counterexample=1`；真实模型的第二次反馈返回 `NO_PENDING`，错误实现的反例会把权重从 1 错误推进到 2。
- P5 训练 runner 输出：训练前 10/20，训练后 20/20，no-feedback 10/20，反向反馈 0/20，label-shuffled 10/20，训练期 `train_weight_write_count=0`，最终权重 `[6,-6,0,0]`。这只是神经元级 `train_post` 监督任务。
- Pulse-Mini 单核 Vivado 2024.1 `xc7z020clg400-1` routed 摘要：182 LUT / 76 FF / 0 BRAM / 0 DSP，WNS +0.463 ns，TNS 0，WHS +0.205 ns，THS 0；`python verify_pulse_mini.py` 通过。vector-less power 只作估算。
- 阵列报告必须使用 `keep_hierarchy/dont_touch`，否则广播相同输入会被综合器等价合并成一个核。保留实例后真实结果为 32 核 5867/2432/+0.151 ns，64 核 11699/4864/-0.131 ns，128 核 23342/9728/-0.466 ns。故 P7 只能报告资源与失败边界，不能声称 128 核 100 MHz 通过。
- Python P8 固定 4->2->2 网络通过：训练前双类输出均为 0，训练后正类输出位 1、负类输出位 2，各 10 个扰动样本全对；`route_delay_observed=1`、`weights_frozen=True`、`direct_weight_write_count=0`、无反馈输出 `[0,0]`。结论限定为固定小网络训练/推理原型。
## P1 原始方案实测证据（2026-08-19）

- `pulse_original_core.sv` 的冻结映射为 `period=max(1,255-learn_count)`：学习值越大，分频周期越短；输入事件在该通道达到周期时产生树突脉冲并清零进度。
- 定向模型通过 4/4：学习计数器从 `255` 再学习一次回绕为 `0`；强连接周期 2 拍、弱连接周期 7 拍；胞体达到阈值后输出一拍脉冲并进入同步睡眠；接口没有负反馈或抑制路径。
- Vivado 2024.1 `xc7z020clg400-1` routed 报告：`183 LUT / 85 FF / 0 BRAM / 0 DSP`，vector-less 功耗 `0.105 W`（报告未绑定活动文件）。100 MHz 核心时序为 `WNS=-1.605 ns, TNS=-30.454 ns, WHS=+0.150 ns, THS=0`，因此 P1 仅作为成本/缺陷基线，100 MHz 时序门未通过。
- Vivado 日志无综合错误、无 DRC Error/Critical Warning，route status 的失败/未布线网络为 0；OOC 输入/输出封装延迟被 false-path 排除，摘要明确标注 `REGISTER_TO_REGISTER_ONLY`。

## Pulse-Mini P4/P8 收口（2026-08-19）

- `pulse_mini_signoff_summary.json` 为 `pulse_mini_signoff_v1` 机器摘要，绑定 `pulse_mini_core.sv`、Python 黄金模型、20,000 条固定协同事务的黄金摘要、形式脚本、负向控制、P5 任务和网络 RTL 文件 SHA-256。
- P4 正向证据闭环为 20 seeds × 1000 transactions bit-exact、Yosys 0.56 depth 20 无反例、重复反馈负向控制反例；摘要状态为 `PASS`。
- P8 RTL 网络协同仿真共 272 条命令。输出层训练教师事件固定在第 6 个 tick；第 1 个 tick 会让后续隐藏重复脉冲进入负证据窗口，导致方向抵消，这不是路由丢失。
- P8 RTL 通过后，固定 `4 -> 2 -> 2` 网络可以称为训练/冻结推理原型；仍不能外推为通用 AI、纯全局 reward 学习或任意规模网络。

## Pulse-Mini TODO 收口（2026-08-19）

- P0 十项行为合同已由实现证据冻结并标记批准，`docs/planning/TODO.md` 不再保留未完成 checkbox。
- P7 广播阵列协议测量：32、64、128 核的单条 TICK/FEEDBACK 响应均为 1 个逻辑周期；由于一槽响应不能同拍替换，持续接受率为 0.5 命令/周期。32/64/128 核分别可在一次广播 TICK 中观察到 32/64/128 个输出脉冲，说明输出拥塞边界是 N 位向量和 Host 消费带宽，而不是核内发放缺失。
- P7 共享 lane 对比使用 `pulse_mini_lane_model.py` 的可复现周期模型：128 核使用 1/2/4/8/128 条 lane 时，每个全阵列 tick 分别需要 128/64/32/16/1 个 lane 周期。该模型没有被写成 LUT、FF 或 routed 容量证据。
- P7 资源硬门审计由 `verify_pulse_mini_p7.py` 收口：简单广播阵列的最大 100 MHz routed 并行规模为 32 核；64 核 `WNS=-0.131 ns`，128 核 `WNS=-0.466 ns`，故 `capacity_claim=NOT_PROVEN` 保持不变。

## 两版本纯仿真比较（2026-08-19）

- 在零初始权重、12个相同训练样本和同一20样本留出集上，两版均由10/20提升到20/20，且第一次正负训练重复后已经达到满分。
- 满分不代表学习过程等价：ENeuron第一次正结果把权重从0更新到2，Pulse-Mini只更新到1；重复8次同方向事件时，ENeuron eligibility为189，而Pulse-Mini仍只有方向1。
- 当前默认参数下，两版实际可改变权重的输入到结果窗口都是0..2 tick。ENeuron内部eligibility可延续到gap 9，但当前定点右移后更新为0。
- 相同权重`+1`时，六个事件可令无泄漏Pulse-Mini达到阈值；ENeuron因电流/膜泄漏不发放。各自训练一次后，ENeuron只在事件间隔0/1 tick发放，Pulse-Mini在扫描到12 tick时仍发放。
- 同一连接形成正负presence冲突时，Pulse-Mini按合同CAPTURE为0；ENeuron在对应自然spike序列后仍保留eligibility 60。前者确定但丢强度，后者保留净信用但更依赖参数缩放。
- 四类共同噪声扫描中，两版均对未训练通道噪声完全不敏感；在当前饱和对称权重下，对dropout和对立通道噪声的曲线也几乎一致，因此这组任务不能证明谁在一般噪声下更强。
- 共同固定网络上，ENeuron 20 seeds训练后均为100%，Pulse-Mini为20/20。原生协议再次复现ENeuron纯全局reward 22.5%均值，Pulse-Mini仍没有可替代的纯全局reward证据。

## Pulse-Mini-L2 训练协议与多任务评估（2026-08-19）

- 用户批准进入 L2 实现阶段。L2 采用每条连接 2 位正证据计数器 + 2 位负证据计数器；每种证据每个成功 TICK 最多计一次；CAPTURE 保存正减负的有符号步长，范围 -2..+2；FEEDBACK 仍使用原有 0/+1/-1 编码并一次消费 pending 槽。
- 训练协议冻结为“每个样本 STATE_CLEAR；每个输入段为输入 tick -> teacher-post tick -> 三个空 tick；CAPTURE -> 定向 FEEDBACK”。该安排避免长序列只在末尾发 post 导致窗口外证据丢失，也避免相邻 teacher-post 把同一事件同时记成正负证据。
- 多类输出采用 one-hot：三类使用 3 个输出单元，四类使用 4 个输出单元；没有用 2-bit binary code 代替类别。多标签任务使用 4 个独立输出位，不使用 WTA。
- `local_teacher` 定义为按标签给目标输出 +1、非目标输出 -1 的 neuron-specific supervised credit；`global_scalar_reward` 定义为所有输出收到同一个环境标量的负对照，两个结果不合并。
- 新增 `pulse_mini_protocol_experiments.py`，固定 8 个 seed，比较三类通道、四类组合、三类时间顺序和四位多标签任务。三类通道 local teacher：L/L2 均 100%；四类组合：L 覆盖 0%，L2 覆盖约 66.9%，覆盖样本准确率 100%；时间顺序任务两者均 0%；多标签 exact-match：L 30.2%，L2 33.3%，bit-level accuracy：L 73.7%，L2 75.4%。全局标量奖励在这些固定任务上均 0% 覆盖，说明没有信用分配不能替代局部教师。
- 新增 `pulse_mini_l2_reference.py`、`pulse_mini_l2_core.sv`、L2 事务回归、L2 Icarus/Python 20 seeds x 1000（20000 条）协同仿真和 depth-20 Yosys SAT 证明；均通过。
- Pulse-Mini-L2 Vivado 2024.1 XC7Z020 routed 最终实测为 `366 LUT / 91 FF / 0 BRAM / 0 DSP`，WNS `-4.690 ns`、WHS `+0.152 ns`。相对 L1 的 `182/76/+0.463 ns`，L2 增加 `184 LUT / 15 FF`；LUT 约增加 101.1%，FF 约增加 19.7%，且 100 MHz setup 失败。这是真实硬件边界，不能继续沿用 L1 的时序通过声明。
- L2 的主要价值是让重复局部证据产生幅度 `-2..+2` 的一次反馈，已在四类组合任务把 L1 的 0% 覆盖提高到约 66.9%，覆盖样本准确率 100%；它没有增加顺序记忆，也没有使全局标量奖励获得信用分配能力。
- L2 时序失败主要出现在权重到胞体/发放和证据幅度更新共享的整数组合路径；后续若追求 100 MHz，应拆分窄位宽 TICK 与 CAPTURE/FEEDBACK 数据路径，而不是删除证据强度功能。

## ENeuron 图像识别 D0（2026-08-19）

- 用户批准把真实图像实验从已有 `4→8→10` 协议探针提升为独立的 `8×8` 十分类任务；首轮网络冻结为 `64→16→4→10`，每个单元保持 4 条树突，共 30 个单元、120 条逻辑连接。该决策不覆盖原有 Pulse-Mini P9 探针。
- D0 使用一次性生成的 8×8 fixture，运行时只依赖标准库；数据按原始 sample ID 做 train/validation/test 分层，manifest 绑定 fixture SHA-256，禁止运行时联网或隐式换数据。
- 首选 rank-order latency 编码：灰度量化到 0..15，选亮度最高的 16 个像素，在 16 tick 内各发一个脉冲，同亮度按像素索引升序。固定事件数避免总脉冲量成为标签泄漏通道。
- 新增 `digit8x8.py` 和 6 项 D0 合同测试；确定性、恒定事件数、tie-break、patch mask 往返、标签/全局随机独立和 split 防泄漏均通过。
- D0 只冻结输入和编码，不证明数字识别能力。D1 必须先完成无学习基线、软件可分性上限和严格十分类解码，再进入 ENeuron 训练。

## ENeuron 图像识别 D1（2026-08-19）

- D1 最近质心软件上限使用每像素发放 tick 特征，在测试集取得 balanced accuracy 79.80%、accuracy 80.00%、macro-F1 79.46%、coverage 100%。
- 只看总事件数、首事件 tick、末事件 tick 均没有有效覆盖；标签打乱后 balanced accuracy 8.69%，接近十分类机会水平。
- 该结果支持继续做 ENeuron 训练，但不能把软件最近质心结果写成神经元学习结果。下一步先做固定特征、只训练十个输出神经元，再进入分层局部教师。

## Pulse-Mini 规划复核

- 原始计数/分频核实测 `183 LUT / 85 FF / WNS -1.605 ns`；它可作为成本反例，但不能作为 100 MHz 主线。
- Pulse-Mini-L 实测 `182 LUT / 76 FF / WNS +0.463 ns`，是当前四输入复制主线；L2 实测 `366 LUT / 91 FF / WNS -4.690 ns`，暂不扩阵。
- 简单广播阵列 32 核通过 `WNS +0.151 ns`，64/128 核分别为 `-0.131/-0.466 ns`；扩展瓶颈首先是扇出、布线、输出和 Host 带宽，而非器件 LUT/FF 数学容量。
- 面向数字识别，若输入已编码成 4 个事件特征，首个十分类目标应为 `4 -> 8 -> 10`，共 18 个神经元和 112 条相邻层连接；784 输入必须走事件编码、BRAM 和共享 lane。
- 本轮只修改规划文件，未修改已签核 RTL；208 项回归全部通过。

## 2026-08-26 当前项目报告证据复核

- 报告生成前 HEAD 为 `be062e0`，当时工作树干净，正式标签为 `v1.0`；D2 报告与 provenance 修正在标签之后。
- 项目主结论应分层：ENeuron 1.0 已闭合原始 Goal M1-M4；Pulse-Mini-L 是当前最省资源且 100 MHz routed 通过的四输入候选；Pulse-Mini-L2 增强证据强度但 100 MHz setup 失败；D2 数字识别协议通过而性能失败。
- 当前项目报告只使用仓库内源码、机器摘要和 Vivado 2024.1 产物，不补造新的器件或板级声明。
- XC7Z020 完整 ENeuron 四输入核实测为 `818 LUT / 544 FF / WNS +0.431 ns`，二输入核为 `718 LUT / 380 FF / WNS +0.418 ns`；均为 100 MHz OOC、0 BRAM、0 DSP。
- XC7Z020 Pulse 路线实测：原始计数/分频 `183/85/-1.605 ns`，Pulse-Mini-L `182/76/+0.463 ns`，L2 `366/91/-4.690 ns`；只有 L 在 100 MHz setup 门下通过。
- Pulse-Mini-L 简单广播阵列 routed：32 核 `5867/2432/+0.151 ns` 通过；64 核 `11699/4864/-0.131 ns`、128 核 `23342/9728/-0.466 ns` 未通过 100 MHz。
- 数字识别 D1 软件最近质心达到测试 BAcc 79.80%、coverage 100%；D2 十种子局部教师实验测试 BAcc 均值 4.74%、coverage 均值 52.18%、0/10 seed 过门，状态为 `D2_FAIL_GENERALIZATION`。

## 2026-08-26 FPGA 图像识别性能评估

- 8×8 D2 为 30 个四输入单元、120 条连接、18 个逻辑 tick。按单核 `2*N_INPUTS+4` 推理合同，全并行核心理论延迟约 216 个 100 MHz 周期，即 2.16 us/图；30 核整体尚未 routed。
- 30 核按四输入完整 ENeuron 单核线性估算为 24540 LUT / 16320 FF，约占 XC7Z020 的 46.1% LUT / 15.3% FF，未计路由、Host 和控制。
- 优化持久态按每突触 40 bit、每神经元约 53 bit 估算，8×8 D2 只需约 6390 bit；当前直接复制成本高主要来自每核控制与工作副本，而非信息本身。
- 代表性 `784->128->10` 稠密网络有 101632 条连接。完整训练态约 4.07 Mbit，理论最低约 111 个 RAMB36；若消除独立 snapshot bank，可降到约 78 个 RAMB36；仅推理 8 bit 权重约 23 个 RAMB36。
- 若 28×28 采用 `K=T=64` 稀疏编码，每图约 66 个逻辑 tick，每图约 6.71 M 次突触访问。当前每突触约两周期语义下，8 lane 理论无额外 post 扫描约 16.8 ms/图，16 lane 约 8.4 ms/图；工程目标可分别定为 30 fps 和 60 fps。
- 当前 8×8 失败的首要瓶颈不是算力：D1 已证明输入有信息，但 D2 四路特征与一正九负调制使权重趋同。应先做 winner-only 负调制和 4/16/64 路特征消融，再做 RTL 扩展。

## 2026-08-28 NPU 局部自动剪枝与动态门控调研

- 现代加速器只有在稀疏模式与执行硬件共同设计时才会真正加速。NVIDIA TensorRT 当前要求矩阵乘/卷积权重按输入通道满足每连续 4 项至少 2 个零的 `2:4` 结构；即使层满足稀疏资格，也可能因实际策略更慢而退回稠密执行。
- AMD Vitis AI UG1414 明确指出，细粒度稀疏需要专用跳零与压缩硬件，并支持连续 M 个权重内裁掉 N 个的 N:M 模式。典型 M 为 4/8/16，常用 50% 稀疏；官方流程仍要求稀疏模型生成、微调和导出。
- AMD 的迭代剪枝建议从已训练稠密基线开始，小步剪枝后微调；一次删除过多参数可能导致精度无法恢复。因此本项目第一版不应从随机初始化直接永久删除，也不应每 tick 改变拓扑。
- Structured RigL 的公开研究结论支持结构化动态稀疏：非结构化稀疏难以在真实硬件获得加速，固定扇入的 N:M 结构更适合硬件。但其剪除/生长算法不能直接视为本项目资格迹门控已经有效，必须单独做对照。
- 对本项目最自然的硬件粒度是当前四输入树突组。首轮应比较 `dense`、固定 `2:4`、本地动态 `2:4` 三种模式；先证明同一任务精度和有效 MAC/突触访问下降，再进入 RTL。
- 资格迹有符号且可能正负抵消，不能单独充当重要性。候选评分应至少比较 `|weight|`、局部活动/贡献的无符号累计、以及二者的低成本组合。

## 2026-08-29 NP4B2 Pulse wrapper 事实

- Pulse-L/L2 无需修改核心 opcode：外部 bridge 可以在 FEEDBACK 接受沿保存旧证据，等待核心成功后串行执行一次 gate OBSERVE，再向 Host 公开原响应。
- 单核部署需要 commit 成功后自动 `STATE_CLEAR`；网络部署必须关闭自动 clear，由十参与者公共屏障在全体 commit 完成后统一清理。一个参数化 bridge 已覆盖两种合同。
- 结构 mask 必须在 TICK 进入核心前应用；核心处于不应期时属于动态跳过，应单独计数，不能记入结构剪枝收益。
- 未提交 mask 时，L/L2 wrapper 已与裸核心逐事务 bit-exact；这证明旁路没有改变原运行语义，但不证明网络级或物理加速。

## 2026-08-29 NP4B3 ENeuron 网络事实

- 真正的输出层 `2:4` 需要两个四输入输出神经元分别消费四个隐藏事件；原 `4→2→2` 的二输入输出核不能通过包装变成严格 `2:4`。
- 固定一拍路由由独立 scheduler 保证：本拍输出只读旧 pending，本拍隐藏结果在 all-done 后成为下一拍 pending；route flush 只推进输出并清 pending。
- 十 gate 原子提交不能只汇合 gate 响应；成功公开前还必须等待十个核心的 `STATE_CLEAR`，否则新 mask 与旧学习历史会同时对外可见。
- 分层计数必须由实例身份驱动。ENeuron 顶层现已证明 8 个 hidden 和 2 个 output 的 dense/issued/saved 互不串账；这仍是逻辑事件账本，不是 BRAM 跳读、周期缩短或功耗证据。

## 2026-08-29 Pulse 网络恢复审计

- `pulse_mini_pruned_network_4x8x2.sv` 当前只是端口骨架，所有 ready/valid 和状态均为常量；薄顶层能够编译只证明接口形状，不证明网络执行。
- 当前首个有效 RED 是广播 `MODE_SET` 的 `HOST_READY_TIMEOUT`。根因不是核心模式限制，而是共享网络没有实例化十个 wrapper，也没有目标 ready 汇合和 sticky response barrier。
- Pulse 网络最小纵向实现顺序冻结为：十 wrapper 与 Host MODE_SET tracer → TICK/flush scheduler → CAPTURE/FEEDBACK → commit/clear barrier → 分层账本与背压。

## 2026-08-29 NP4B3 Pulse 网络事实

- Pulse-L 与 L2 可以复用完全相同的网络控制面；差异只在 wrapper 类型，Host、路由、commit 和账本协议无需复制。
- 网络 barrier 的原子预检要求每个 wrapper 的 prune `ready` 在 idle 时独立于 `valid`。这是 ready/valid 接口合同修正，不改变 gate 或神经元状态机。
- Host 错误汇总必须逐 lane 判断完整 3-bit status 是否非零，不能只拼 status bit0；同时广播标志和目标必须在接受沿锁存，避免上游随后改变字段影响未完成事务。
- 当前通过的是逻辑网络行为和访问账本，不是物理周期缩短、存储跳读或功耗证据。

## 2026-08-29 ENeuron NP4B4 可观测性补齐

- 网络长事务不能用层次路径核对十 gate epoch，因此 wrapper/顶层需要纯只读导出 observation/commit valid 与 ID；该补丁只连接既有 gate 状态，不改变方程或事务延迟。
- 既有 `host_weight_rdata` 原先只保存事务完成值，空闲改变地址不会读取权重。复用同一端口增加 H_IDLE 组合寻址读，可在 INFER 前后无副作用比较权重；H_WAIT/H_RSP 仍保持锁存值和背压稳定。
- 长事务黄金模型独立使用 `RtlReferenceNeuron` 复现十核、固定一拍路由、gate utility/mask/epoch 与分层账本；当前只完成模型和 64 事务 tracer 测试入口，协同驱动模块仍待落盘。

## 2026-08-29 NP4B4 ENeuron 长事务事实

- 正式规模为 20 个独立 seed、每个 1000 个事务，三模型不得合并报告；ENeuron 本轮已独立完成 20,000。
- INFER 冻结必须区分正常 TICK/flush 与显式 `STATE_CLEAR`：后者允许清动态 membrane/threshold，但不得改变权重、gate utility/mask/ID 或 committed 学习协议。
- 零 MOD 会消费 wrapper pending commit 元数据，但按既有核心合同保留 committed snapshot valid；非零 MOD 才消费核心 snapshot。黄金模型必须复现该差异。
- 被剪 lane 的 committed snapshot 在后续显式 SNAPSHOT 中可从旧非零值发布为 0，因为 `STATE_CLEAR` 保留旧 committed 容器且 live eligibility 已被清零；验收要求只允许 nonzero→0，禁止 0→非零，并同时要求权重与 utility 零变化。

## 2026-08-29 NP4B5 负向控制事实

- 正向测试全部通过不足以证明验收器敏感；四类已知错误必须各自构造反例，并由同一合同检查器明确拒绝。
- “只掩 TICK”错误的关键不是当拍数值输出，而是被剪 lane 的权重或学习历史仍变化；验收器必须同时检查两者。
- 网络原子性检查必须把部分 mask 可见与中途 TICK 接受结合起来；只检查最终十 mask 全有效会漏掉部分 epoch。
- 严格 `2:4` 是每个输出神经元四输入保留两路，不能用总计四条二输入连接替代结构分组。

## 2026-08-29 Pulse 长事务可观测性事实

- 仅从 soma/spike 与读计数间接推断 issue mask 不足以满足逐周期前置门控签核；40-bit issue mask 必须作为只读 audit 状态公开。
- Pulse 动态学习状态还包括 leak timer、post age 与 captured direction；缺失这些字段会让 INFER 冻结和被剪 evidence 检查不完整。
- L/L2 的 captured direction 位宽不同，可在网络审计边界统一为每 lane 3-bit signed；这是表示归一化，不改变核心存储或学习规则。

## 2026-08-29 NP4B TODO 复核

- ENeuron 随机网络协同仿真的最小 tracer 已实际通过；长矩阵仍需以正式 20 seeds × 1000 结果签核，不能只凭测试文件存在判定完成。
- Pulse-Mini-L/L2 的 `4→8→2` 公共接口编译、Host 字段锁存以及路由/训练/commit-clear/账本定向合同当前 3/3 通过；这比旧记录中的“常量端口骨架”更进一步，但仍不等于两模型各 20×1000 长事务通过。
- NP4B 后续主链应收敛为：ENeuron 长矩阵收口 → Pulse L/L2 独立长事务 → 网络级负向/形式性质 → 全仓回归与机器摘要 → 用户审批 NP6。NP6 前不运行 Vivado。

## 2026-08-29 NP4B 收口规划事实

- Pulse-L/L2 随机协同仿真目前只是基础设施初版；在 64 事务 tracer 实际通过前，直接启动 20000 条矩阵只会放大首个差异的定位成本。
- Pulse-L wrapper 已具备非空 depth=32 exactly-once 形式证据，但共享 bridge 并不能自动证明 L2 的证据编码和成功路径，因此 L2 仍需自己的 witness。
- 十核完整神经元直接展开为一个大 SAT 问题不是当前最简路线；公共 barrier 用小状态抽象证明，再用真实顶层结构/编译和随机协同仿真绑定，能覆盖控制原子性且避免状态空间无效膨胀。
- NP4B 最终机器摘要必须分别保留三模型统计；任何合并总事务数都不能替代单模型通过结论。

## 2026-08-29 NP4B4 Pulse 长事务事实

- 64 事务 tracer 会在十进制事务号达到 10 时捕获解析进制错误；事务编号与状态字段必须分别按十进制和十六进制解析，不能整行统一转换。
- route flush 必须显式清训练输入。若沿用上一笔 TICK 的 `output_train_post`，INFER 输出核会正确拒绝该 TICK；因此 testbench 必须检查 flush 状态，不能只等 valid。
- Pulse-L 与 L2 各 20,000 条都逐事务一致，并分别记录 commit、exact-two、被剪 lane、INFER、issue-mask、背压和分层账本；这比只比较最终 spike 或只报告合计事务数更强。
- Pulse-L 与 L2 的逻辑读取统计不同，因为两种本地证据强度导致后续膜状态、脉冲和活动掩码轨迹不同；这不是硬件吞吐或物理功耗差异证据。

## 2026-08-29 NP4B5 Pulse wrapper 形式事实

- 只证明 OBSERVE 计数增加一次，仍不足以直接签核“成功响应前 utility 已更新”；harness 必须同时观察 utility，并在运行响应背压期间证明它稳定。
- L/L2 的共享 bridge 允许复用同一性质结构，但核心证据位宽和成功轨迹不同，因此必须保留两个独立 reach witness，不能用 L 的 witness 替代 L2。
- reach 脚本中的 `-falsify` 找到模型表示目标成功路径确实可达；它与不变量脚本的“无模型即成功”语义相反，verifier 必须分别检查两个标志，避免把空证明当通过。

## 2026-08-29 NP4B 续跑审计事实

- 当前 Pulse-L/L2 形式源码、脚本、正式日志和 witness 尚未入库；“本地证明通过”与“仓库证据闭环”是两个不同状态，必须先形成独立提交。
- ENeuron 当前公开端口能证明事务级原子结果，但不能单独证明内部核心 MOD 与 gate OBSERVE 同拍握手；强合同需要验证专用 bind/内部断言，且不得把该验证可见性变成运行时接口依赖。
- `local_prune_commit_barrier.sv` 保存 gate 返回的 mask，但本身不检查 popcount。因此 `barrier success→十个 exact-two` 是组合结论，必须同时绑定公共 gate 的 `ST_OK commit→exact-two` 证明。
- barrier 抽象只能直接证明 `runtime_blocked`，不能独立证明三个真实顶层的 TICK/flush/Host ready 已关闭；该绑定必须由真实顶层结构检查和定向/随机协同仿真完成。
- 现有 Pulse 摘要 verifier 主要检查存在性和正数门槛，尚未绑定固定 seed、精确统计、源码/runner SHA-256 或证据新鲜度；它不能替代最终 NP4B fail-closed 总 verifier。
- ENeuron 当前缺少独立落盘的 20,000 事务结果文件；最终 D1 必须在源码冻结后为三模型重新生成三个独立正式结果。

## 2026-08-29 P0 形式证据固化事实

- 两套 proof/reach 可安全并行运行，因为它们使用独立顶层、日志和 witness 文件；最终证据仍必须分别验证，不能把并行执行视为合并证明。
- `.gitignore` 默认排除 `.log`/`.vcd`，因此正式 proof 日志和成功 witness 必须按精确文件名强制加入；修改全局忽略规则会把大量历史中间产物带入仓库，不符合 KISS。
- 旧 `*_cex.vcd` 和 `*.tmp.log` 只记录失败/中间尝试，不属于正式证据集合；最终 SHA-256 清单必须拒绝这些文件冒充签核 witness。
- 原始 Yosys 日志含工具横幅行尾空格，普通 `git diff --check` 会对日志报噪声；修改日志会破坏原始证据。正确边界是对人工维护文件执行空白检查，对工具产物执行哈希和标记校验。

## 2026-08-29 P1/P2/P3 启动审计事实

- ENeuron 真实顶层已在 `FORMAL` 块中直接断言 `barrier_runtime_blocked` 时三类 ready 全低；Pulse 公共顶层的组合逻辑也显式包含该阻塞条件，但仍需同强度验证绑定，不能只凭源码目视签核。
- 既有 `formal_local_prune_gate.sv` 已证明 `mask_valid→exact-two`、commit 原子发布、INFER 拒绝冻结和 response 背压；P2 总 verifier 应引用并哈希这组证据，而不是在 barrier 环境中重新声称独立证明 gate 算法。
- 现有前三类 NP4B5 负向控制确实只运行 Python 自包含模型；它们适合说明合同含义，但不足以证明当前 RTL 验收链能捕获真实接线/时序 mutation，因此 P3 的 RTL 变体补强是必要硬门。

## 2026-08-29 P2/P3 收口事实

- barrier 的 exact-two 是组合结论：gate verifier 证明真实 gate 的 proof/reach/witness，barrier verifier 再证明十参与者原子汇合；只检查 gate `.ys` 文件含 proof 命令不构成证据绑定。
- gate reach 现在显式约束第 8 拍 `mask_valid=1`、`mask_commits=1`、mask=`0011` 并输出 VCD，避免“存在某个模型”却没有可审计 exact-two witness。
- P2 首版 cex 暴露的是 harness 错误地要求十路 clear 同拍返回；真实设计允许错拍 response 并用 sticky seen 汇合。修正验证模型后 DUT 无需修改。
- P3 的 mutation 基于当前真实 RTL 源文本，能捕获指定的 evidence 时序、学习输入门控、runtime barrier 和输出路由错误；它们仍不是每个错误版本的动态 Icarus 仿真，因此最终正确性继续由正式 RTL cosim/formal 共同承担。

## 2026-08-29 P1 ENeuron 形式事实

- 当前公开端口只能证明事务级结果；内部同拍接受通过 `FORMAL` 条件断言直接比较 `core_mod_valid&&core_ready` 与 gate OBSERVE handshake，验证逻辑不进入普通综合接口。
- 非空 witness 的成功粘滞位在 MOD 完成后的下一拍置位，因此 VCD 最后一拍可以出现新的任意输入甚至 reset；真正成功证据位于前一拍的 `done=1`、`protocol_error=0`、utility 已更新、pending 已清。不能只读取最终一拍解释轨迹。
- P1 完整展开 `digital_lif_engine`、gate 和 wrapper，depth=32 SAT 明显重于小状态 barrier；仍保持真实公开 TICK→SNAPSHOT→MOD 路径，没有用内部状态假设换取快速通过。

## 2026-08-29 NP4B 最终收口规划事实

- P1 执行期间证明了“技术证明通过”与“证据已进入仓库”必须分开记录；随后已由提交 `c811bcf` 完成仓库闭环。
- P4 必须在 P1 独立提交后冻结源码与 seed，再重跑三模型。先跑长矩阵、后修改源码会使结果与最终 RTL 失去绑定。
- 三模型 seed 固定为 ENeuron `101..120`、Pulse-L `201..220`、Pulse-L2 `301..320`；每个模型必须独立报告 20,000 条，合计数不能代替单模型门槛。
- 最终摘要必须 fail-closed：精确文件键集合、SHA-256、新鲜 runner 退出码、工具版本、witness 字节数和实际 unittest 数量缺一即失败。
- NP4B 的逻辑访问计数只能证明门控语义。物理 BRAM 跳读、真实周期缩短、功耗和 XC7Z020 时序仍属于 NP6/NP7，当前 TODO 不授权 Vivado。

## 2026-08-29 持久工作流事实

- `WORKFLOW_STATE.md` 是当前状态指针，活动 TODO 是详细合同；状态文件不复制完整设计任务，避免形成第二份真值。
- `workflow_resume.ps1` 只做 fail-closed 只读恢复：检查持久文件和必要字段，输出 HEAD、工作树、活动 TODO 未完成数及最近记录，不执行验证、提交或 Vivado。
- Windows 会话不能假设 `iverilog` 位于 `PATH`；当前可复现绝对路径为 `C:\msys64\ucrt64\bin\iverilog.exe`，后续签核应记录该工具路径和版本。

## 2026-08-29 NP4B 最终签核事实

- 三种神经元在同一严格 `4→8→2`、十个四输入 gate 网络上分别完成 20 个固定 seed × 1000 条事务，逐事务零差异；合计 60,000 条不能替代三个独立 20,000 门槛，但三者均已分别通过。
- 五套新鲜形式证据覆盖 ENeuron/Pulse-L/Pulse-L2 wrapper、公共 gate 和 N=10 barrier；每套同时具备不变量无反例与非空成功 witness。
- 最终 discovery 纳入 P5 verifier 测试后为 359/359；总摘要绑定 87 个文件，并拒绝缺失、多余、陈旧哈希和 cex/tmp 证据。
- NP4B 证明的是结构门控和功能集成：不能把 hidden/output 逻辑读取节省写成共享 BRAM 真跳读、墙钟加速、功耗下降或 XC7Z020 时序通过。
- 下一阶段唯一合法状态是 `NP6_REVIEW_REQUIRED`；用户未批准前不调用 Vivado。

## 2026-08-29 GitHub 推送准备事实

- 初始状态为 `main`、HEAD=`4b7f146`、工作树干净且无 remote；现已按用户指定配置 `origin=git@github.com:Epslion404/ENeuron.git`。
- 当前 `.gitignore` 已正确忽略 Python 缓存、Icarus/VCD、通用日志/DCP、`.Xil` 和现有 Vivado 工程工作目录；本地共有 88 条被忽略路径。
- 12 份被通用规则命中但仍已跟踪的 `.log`/`.vcd` 均属于 NP4B 正式 proof/reach 证据，必须保留在版本库中。
- 当前 392 个已跟踪文件合计约 12.8 MB；完整历史最大 blob 为 1,908,947 bytes，没有超过 10 MiB 或 GitHub 100 MiB 单文件限制的对象。
- 当前版本与全部 61 个提交的历史扫描均未命中高置信度 token、私钥、带密码 URL、通用凭证赋值或敏感文件名。
- 本机当前会话找不到 `gh`，但这不阻塞 Git SSH：用户说明 GitHub/Gitee 共用 `~/.ssh/id_ed25519_gitee` 后，显式测试成功认证为 `Epslion404`。
- `git ls-remote git@github.com:Epslion404/ENeuron.git HEAD refs/heads/main` 使用共用 key 后退出码为 0 且无 refs，证明目标仓库存在并且目前为空。
- 现有 `Host github` 别名已指向该共用 key；为保持用户指定的 `github.com` remote 不变，仓库只需设置局部 `core.sshCommand`，无需修改全局 SSH 配置。

## 2026-08-30 PR #1 第二轮复审初始事实

- PR HEAD 已从首轮审查的 `4277395` 更新为 `169003684b260aaabf98fb3b6e70866cb0c24bed`，新增两个提交；PR 仍为 OPEN、MERGEABLE，且没有 CI checks。
- 原先不兼容的 `neuron_gate_core.sv`、8 位 score/cooldown/自动 regrow 实现及生成物已撤出差异；当前 7 个文件主要围绕既有 `local_prune_gate_2of4.sv` 的 Vivado runner、测试、报告与动态恢复设计提案。
- 协作者报告的是干净检出 `7266e2b` 上的 Vivado Simulator 2024.2.0，共 51 次仿真、6447 条事务；他明确承认未在 Vivado 2024.1 上运行。
- 本机已有项目指定 Vivado 2024.1，可对 PR 当前 SHA 独立复现；是否满足验收仍取决于 runner/对拍真实性和 2024.1 实跑结果。

## 2026-08-30 PR #1 第二轮复审结果

- 在 PR HEAD `169003684b260aaabf98fb3b6e70866cb0c24bed` 上使用 `G:/Xilinx/Vivado/2024.1` 完整运行真实 XSim：51 次 `xvlog`、51 次 `xelab`、51 次 `xsim` 和 1 次版本探针均退出 0。
- Vivado 2024.1 复现覆盖 45 个正常用例、5 个失败敏感变异、6447 条事务和 154728 个字段比较；最终输出 `VIVADO_LOCAL_PRUNE_GATE_PASS`，五个源码 SHA-256 与 PR 当前文件一致。
- 相关 Icarus/签核回归 24 项中 23 项通过、1 项失败：`test_verify_local_prune_rtl.test_source_hashes_are_current` 在新鲜 Windows worktree 失败。
- 第一层根因是仓库未固定文本 EOL，而系统 Git `core.autocrlf=true`；旧摘要记录的是 LF git blob 哈希，验证器却哈希 CRLF 工作树字节，因此干净 Windows 检出会让所有文本源误报陈旧。
- 第二层且直接由 PR 引入的根因是 `local_prune_gate_cosim.py` 已修改，但 `local_prune_rtl_results.json` 仍保留旧哈希 `b4d424...`；当前 PR git blob 哈希为 `c313220...`，即使消除 EOL 差异仍会真实失败。
- `reviewer_counterexample` 用例先测试 CONFIG mask `1100`，随后 `PRUNE_CLEAR`，再用 `(3,0,0,0)` 和零 utility 分别提交；它没有让 `1100` 与下降分数同时参与同一选择，也不存在已撤出架构的 cooldown，因此报告中的“原反例已固化”表述不精确。

## 2026-08-30 PR #1 第三轮复审初始事实

- 协作者新增 `ee4b9ff`（代码）和 `fd5aa96`（证据）两次提交；PR 最新 HEAD 为 `fd5aa9622bcb8b3c5e1bedbfc0639199a23026a9`。
- 新增 `.gitattributes`、`eneuron.local_prune_rtl.v2` 摘要和 canonical LF 哈希逻辑；`local_prune_gate_cosim.py` 仍是被修改的关键输入。
- 协作者明确报告本机没有 `iverilog/vvp/yosys`，因此 cosim/formal 块未在本轮本机重跑，并将其标记为继承或未复验；该口径需要检查摘要和验证器是否真正 fail-closed。

## 2026-08-30 PR #1 第三轮复审结果

- 最新 HEAD `fd5aa9622bcb8b3c5e1bedbfc0639199a23026a9` 的 28 项针对性回归通过；设置 `VIVADO_ROOT=G:/Xilinx/Vivado/2024.1` 后真实 XSim 集成测试也通过。
- 本机独立运行 `python verify_local_prune_rtl.py`：三模型 60,000 条 Icarus cosim、32 拍 Yosys 形式验证均退出 0。
- 本机独立运行最新 HEAD 的完整 Vivado 2024.1 runner：45 个正常用例、5 个 mutants、6447 条事务、154728 个字段，154 次工具调用全为退出码 0。
- 最新 HEAD 的全仓 `python -m unittest discover -v` 为 `Ran 381 tests in 906.922s`，失败 2 项，均为 `test_verify_np4b_signoff` 的 formal ENeuron witness 字节数不一致（24069/22922）。
- 根因与 PR 新增 `.gitattributes` 直接相关：`*.vcd text eol=lf` 改变已跟踪 VCD 工作树字节，而 `verify_np4b_signoff.py` 仍按原始 `stat().st_size` 和原始 SHA-256 校验 `np4b_signoff_summary.json`，造成完整签核链失效。
- 另发现 `verify_local_prune_rtl.py` 的正常 `build_summary(run_checks=True)` 路径不输出 `tool_availability`，执行正式重验证后会删除该 v2 字段；现有测试未覆盖此回归。
- 已向 PR 提交新的中文 `CHANGES_REQUESTED`，要求固定正式证据字节或统一 NP4B canonical 策略、刷新总摘要、补充完整 discover 复跑，并保持 v2 元数据字段完整。

## 2026-08-30 PR #1 审查口径调整

- 用户批准不同 Vivado 版本结果互认；2024.1 与 2024.2 不再构成阻断条件。
- 审查反馈已精简为两个硬问题：NP4B VCD 原始哈希/长度回归，以及正常 `verify_local_prune_rtl.py` 丢失 `tool_availability`。

## 2026-08-31 PR #1 第四轮精简复审中间事实

- 最新 HEAD `46fc59edae7ec0ae4ae56afed4de2d9a8e1d2049` 的 35 项关键回归通过，包含本机 Vivado 2024.1 真实 XSim 短回归；上一轮的 canonical witness 和 v2 元数据定向测试均通过。
- 正式执行 `python verify_local_prune_rtl.py` 完成三模型 60,000 条 cosim 与 32 拍形式验证，生成的 `local_prune_rtl_results.json` 保留 `tool_availability`、`source_hash_policy`、`provenance`、`toolchain_provenance` 和 `verified_on`。
- 同一次正式重验证会改写 `formal_local_prune_gate.log`、`formal_local_prune_gate_reach.log`、`formal_local_prune_gate_success.vcd`；紧接着运行 `python verify_np4b_signoff.py` 因 `formal_local_prune_gate.log` canonical SHA-256 不一致失败。
- `_toolchain_provenance()` 声称重验证后会恢复这些产物为提交字节，但当前实现没有兑现；需以干净 worktree 完整回归进一步确认提交态是否仍通过。

## 2026-08-31 PR #1 第四轮精简复审结论

- 干净 HEAD `46fc59e` 完整 `python -m unittest discover -v` 为 `Ran 385 tests in 453.104s / OK`，本机 Vivado 2024.1 XSim 集成通过；提交态本身完整回归为绿。
- 上一轮的 canonical witness 绑定与 v2 元数据保留均已闭合；Vivado 2024.1/2024.2 版本差异未作为阻断。
- 唯一阻断是正式重验证链不闭合：`verify_np4b_signoff.py` PASS → `verify_local_prune_rtl.py` PASS → `verify_np4b_signoff.py` FAIL，且报告的 `binding_refresh` 基线仍停在 `073969d`，机器摘要已为 `6f03609`。
- 已向 PR 最新 HEAD 提交 review `5065226301`，状态 `CHANGES_REQUESTED`；GitHub 回读确认正文完整、PR 仍为 open，未合并、未关闭、未修改协作者分支。

## 2026-08-31 PR #1 第五轮复审结论

- 最新 HEAD `4fec2aa6dd364cbb8ebba83fe852efd0f7db3ecc` 已实现 formal 证据 `finally` 恢复和 NP4B 摘要重绑定；三步顺序 `verify_np4b_signoff.py → verify_local_prune_rtl.py → verify_np4b_signoff.py` 在本机全部退出 0。
- 无 Vivado 环境的干净提交态完整回归：`Ran 386 tests in 445.206s / OK (skipped=1)`；本机 Vivado 2024.1 的短 XSim 单测单独重跑通过，输出 `VIVADO_LOCAL_PRUNE_GATE_PASS`。
- 启用 Vivado 的全量 discover 首轮曾出现一次 `xsim exited 3221225477`，但同一短测试随后独立重跑通过；不构成 RTL 或签核阻断。
- 协作者最新评论中的全量表把 `386 tests / 0 failures / 2 errors / exit 1` 同时称为“全绿”，数字和语义矛盾；这是报告口径问题，需在评论中更正为实际可复现结果，不影响代码批准。

## 2026-08-31 PR #1 第五轮回复复核

- 协作者追加评论 `5477928602`，明确无代码与签核链改动，PR HEAD 仍为 `4fec2aa`。
- 已将两组环境结果拆开：权威复审为 `386/386 OK (skipped=1, exit=0)`；其本机 discover 的 2 个 XPM 编译 errors 与 `origin/main` 同样存在，单列为环境对照；四态矩阵保持 32/态、全绿。
- 文字更正与本机复验结果一致，没有新增阻断；PR 继续保持 `APPROVED`。

## 2026-08-31 PR #1 合并后仿真结果解读

- `origin/main` 已合并为 `92b70f9`。Vivado/XSim 报告（原始证据生成于 2026-08-31）覆盖 3 个模型、45 个用例、6,447 条事务、154,728 个可见字段和 5 个故意变异，全部通过。
- 三模型 4→8→2 局部剪枝协同证据各 20,000 条事务，总计 60,000 条；无 Python/RTL 差异、无 strict 2:4 违规、INFER 学习状态冻结、被剪权重/utility/evidence 无变化。
- Pulse-Mini-L 逻辑工作量减少 53,440 / 168,509 = 31.71%；Pulse-Mini-L2 减少 47,874 / 153,416 = 31.21%。这些是模型计数的 issue/read 工作节省，不是实测 FPGA 墙钟加速。
- ENeuron 报告记录 277 次 pruned snapshot 由非零变为零，但 pruned weight/utility 仍为 0 次变化；这说明冻结门控成立，不等于已证明物理读端口跳过。
- 当前摘要明确未证明：BRAM 真跳读、墙钟 speedup、功耗降低、XC7Z020 时序/资源；下一步若要声明硬件收益，必须进入 Vivado 综合/实现和板级吞吐测量。

## 2026-08-31 PR #2 复审与最小修复事实

- PR #2 标题为 `test(vivado): run the short xsim regression on all three gain models`，分支 `feature/vivado-full-models-20260831`，初始 HEAD 为 `d9902ade4ecb4fda8a50060c60d3d14787410ab4`。
- 差异范围很小：`test_local_prune_gate_vivado.py` 将短 XSim 测试模型从 `eneuron,pulse_mini_l2` 扩展为 `eneuron,pulse_mini_l,pulse_mini_l2`，并刷新 `docs/reports/SIMULATION_REPORT.md` 与 `TEST_MATRIX.json`。
- 本机隔离 worktree 使用 `G:/Xilinx/Vivado/2024.1` 执行 `python -m unittest test_local_prune_gate_rtl test_verify_local_prune_rtl test_local_prune_gate_vivado`，结果为 32 tests / 0 failures / 0 errors / exit 0；真实 XSim 输出 `VIVADO_LOCAL_PRUNE_GATE_PASS version=Vivado Simulator v2024.1 models=3 seeds=1 transactions_compared=723 cases=24 mutants=0`。
- 初审发现 `docs/reports/SIMULATION_REPORT.md` 复现命令仍写 `pull/1/head:pr-1`，与 PR #2 不匹配；已在 PR 分支推送最小修复提交 `f975cd7 docs: fix PR2 reproduction command`，改为 `pull/2/head:pr-2`。
- 直连 GitHub `gh`/REST/curl 三种 HTTPS API 提交 review/comment 均在 `api.github.com` TLS/连接层被重置；Git SSH push 正常。本机发现 `127.0.0.1:7897` 代理可用于 GitHub REST GET/POST。
- 已通过代理和 `gh api --method POST repos/Epslion404/ENeuron/issues/2/comments` 成功向 PR 页面提交中文评论 `5479989535`。
- PR 描述仍存在口径瑕疵：把 `386 tests / 0 failures / 2 errors / exit 1` 与“386/386 OK”并列。该问题属于 PR 描述文字，不影响已推送的仓库文件和本机测试结论，但合并前最好由 PR 作者更正。
- PR 后续 HEAD 更新到 `699acae92e5412b9e1fb83d0a855116607d545d1`：新增 `858d79e` 将 PR #2 复现命令修复落到 `make_local_prune_report.py`，新增 `699acae` 重新渲染 `docs/reports/SIMULATION_REPORT.md`。最新生成器和报告均已固定为 `pull/2/head:pr-2`。
- 本机轻量复核最新 HEAD：`python -m compileall -q make_local_prune_report.py test_local_prune_gate_vivado.py` 通过；重新运行 `make_local_prune_report.py` 可渲染出 PR #2 复现命令；`git diff --check` 通过。
- 已通过代理 PATCH PR body，将“你的机器预期 386/386 OK”改为“复核机器以实际输出为准”，消除 `errors=2 / exit=1` 与全绿并列的误导。
- 代理下 `gh pr review 2 --approve` 返回退出码 0；随后 GraphQL/REST 回读 reviews 多次 EOF，因此只记录“approve 命令成功提交”，不记录“已回读确认”。
## 2026-08-31 根目录 Markdown 归档审计

- 根目录归档前共有 35 个已跟踪 Markdown 文件，当时尚无 `docs/` 目录。
- 根目录已有未提交内容仅为 `docs/reports/STAGE_REPORT_2026-08-31.md` 与 `progress.md`；本次必须保留并纳入归档审计，不能回退。
- `README.md` 是项目入口；`task_plan.md`、`findings.md`、`progress.md` 是默认持久规划文件，按 skill 合同必须留在项目根目录。
- `WORKFLOW.md`、`WORKFLOW_STATE.md` 与根目录 `workflow_resume.ps1` 共同构成恢复入口，保留在根目录可避免破坏操作路径和恢复语义。
- 其余 Markdown 可按设计、规划、报告、验证四类迁入 `docs/`，但最终映射必须先审计源码、脚本、摘要和 Markdown 中的固定路径引用。
- 本任务只做文档移动与引用修复，不重跑算法、RTL、形式验证或 Vivado；历史验证结论及边界保持不变。
- 非 Markdown 固定路径依赖集中在 7 组：Goal 文档解析、局部剪枝合同哈希、阶段报告生成器、Pulse-L2 协议报告生成器、仿真比较报告默认输出、持久工作流活动 TODO，以及少量报告正文生成文本。
- `docs/design/LOCAL_PRUNE_RTL_CONTRACT.md` 不只是说明文件：它的文件名和内容哈希被 `local_prune_rtl_results.json` 与 `verify_local_prune_rtl.py` 绑定。迁移它会级联改变正式签核摘要；应先审计 NP4B 总摘要生成链，再决定迁移或作为机器绑定例外保留。
- `docs/verification/goal_audit.md` 与 `docs/design/recommended_design.md` 被 `verify_goal.py`/测试按文件名解析；可迁移，但必须同步代码与测试中的仓库相对路径。
- `docs/reports/SIMULATION_REPORT.md`、`docs/reports/SIMULATION_COMPARISON_REPORT.md`、`docs/reports/PULSE_MINI_L2_PROTOCOL_REPORT.md` 是工具默认输出目标；迁移时必须同步生成器默认路径，避免下一次生成重新污染根目录。
- `docs/planning/NPU_PRUNING_NP4B_TODO.md` 是 `workflow_resume.ps1` 的活动合同路径；迁移时必须同步恢复脚本、工作流状态与说明文档，并执行恢复检查。
- 首轮机械替换的唯一键包含关系是 `TODO.md` 同时为两个 NPU TODO 文件名的后缀；按“长键后替换短键”执行会产生重复目录。根因是替换操作非幂等，不是原文或 Git 移动损坏。
- 最终迁移采用完整归档方案：29 个 Markdown 进入 `docs/`，根目录只保留 README、两个持久工作流文件和三个规划记忆文件；`docs/README.md` 提供四类可点击索引。
- 所有显式 `docs/design|planning|reports|verification/*.md` 引用均指向现存文件；Markdown 链接检查为零断链。
- T0 Goal 测试的临时目录夹具原先只支持根文件，迁移后需创建嵌套父目录；两项测试先稳定 RED，再以两处最小 `mkdir(parents=True, exist_ok=True)` 修复并 GREEN。
- `workflow_resume.ps1` 与 HEAD 都是无 BOM UTF-8；Windows PowerShell 5.1 在中文注释紧邻 `$repoRoot` 赋值时可把赋值吞入错误解析路径，表现为下一行读取未定义变量。把这一条非功能注释改为 ASCII 是最小跨版本修复。
- 单行 ASCII 修复后解析继续在后续中文字符串处失败，排除了“仅首条注释异常”的假设；根因是 Windows PowerShell 5.1 对整份无 BOM UTF-8 中文脚本的解码。UTF-8 BOM 是保留中文日志且兼容该解释器的文件级修复。
- `--refresh-signature` 只诚实记录签名迁移，不能冒充行为/形式证据已重跑；当本机 Icarus/VVP/Yosys 齐全时，现有测试要求正式重验证。文档合同路径进入签名集合后，应运行官方非 Vivado 重验证而不是放宽测试。
- 正式非 Vivado 重验证后，41 项 Goal/局部剪枝/NP4B 定向测试全部通过，独立 NP4B verifier 继续输出 `NP4B_SIGNOFF_VERIFY_PASS`；迁移没有改变原有功能边界。
- 报告生成器能向归档路径写入，但精确重渲染依赖评审工作区的 `vivado_regression_console.log` 和对应 Git 分支状态。当前主工作区缺少这些输入，生成结果会明确降级；不能用它覆盖包含原始真实控制台证据的正式报告。
- 最终结构为根目录 6 个 Markdown，`docs/design=9`、`docs/planning=3`、`docs/reports=15`、`docs/verification=2`，另有 `docs/README.md`；37 个 Markdown 的显式相对链接检查为零断链。
- NP4B 总摘要不直接绑定 `docs/design/LOCAL_PRUNE_RTL_CONTRACT.md`，但绑定了 `local_prune_rtl_results.json`；迁移合同会先改变该结果文件，再通过总摘要形成二级哈希级联。
- `verify_local_prune_rtl.py` 已有“正式重验证后刷新 NP4B 总摘要”的机制，说明级联可以由项目既有入口处理；真实刷新函数/脚本名仍需定位。
## 2026-09-01 根目录非 Markdown 文件归档调研

- 当前 `main` 与 `origin/main` 一致；调研开始后只有 `task_plan.md`、`progress.md` 两个规划文件有本轮未提交修改。
- 根目录有 287 个已跟踪文件：151 个 Python、41 个 SystemVerilog、28 个 JSON、19 个 PowerShell、15 个 Yosys 脚本、10 个 Tcl、7 个正式日志、5 个正式 VCD、2 个 TXT，以及入口/配置文件。
- 根目录另有大量被 `.gitignore` 排除的本地生成物：`*.vvp`、失败 `*_cex.vcd`、`*.tmp.log`、`clockInfo.txt`、缓存和 Vivado 工作目录。这些不属于“归档”，更适合清理或保持忽略。
- 已跟踪的 Vivado 证据分布在 12 个根目录报告目录中；其中 DCP、日志、报告和 XSim transcript 被 `verify_goal.py` 或 `.gitignore` 例外明确绑定，不能按普通缓存移动。
- 直接把 151 个 Python 文件拆进 `src/`/`tests/` 会改变模块导入、`unittest discover`、脚本相对路径和 subprocess 工作目录，属于架构重排，不符合本次“干净一点”的 KISS 范围。
- 最值得优先评估的 V1 是：清理未跟踪生成物，并将已跟踪的机器结果/正式证据与 Vivado 报告统一到少数 `artifacts/` 子目录；RTL/Python/测试代码暂留根目录，避免一次性包结构改造。
- 根目录当前有 47 个明确被忽略的单文件生成物：VVP、Host/Formal 失败或覆盖波形、临时日志和 `clockInfo.txt`。它们都不是已跟踪正式证据；清理不会改变 Git 历史，但同一工具按旧默认路径运行时会重新生成。
- 28 个已跟踪 JSON、2 个 TXT 的外部引用通常为 2–13 处；多数由生成器/测试/报告固定文件名读取，机械迁移必须同步 runner、verifier、报告和 JSON 内嵌路径。
- 12 个根目录 Vivado/仿真证据目录中，11 个含已跟踪文件。多个目录被 `.gitignore` 例外、`verify_goal.py`、验证脚本和报告绑定；整体迁入 `artifacts/vivado/` 可行，但需要统一调整 Tcl/PowerShell 输出目录和验证器常量。
- 7 个已跟踪正式 `.log` 与 5 个正式 `.vcd` 是 NP4B 哈希/字节数签名的一部分，且 runner 会按根路径重写。V1 若同时移动它们，会把单纯整理扩大为形式证据流水线重构；建议暂留根目录。
- 因此更小的 V1 候选是：清理 47 个 ignored 根生成物；迁移 JSON/TXT 到 `artifacts/data|results|signoff`；迁移 Vivado 报告目录到 `artifacts/vivado`；正式形式日志/VCD、源码和测试暂留根目录。
- 30 个 JSON/TXT 可以完整分为：`artifacts/data` 4 个输入/manifest（约 505 KiB）、`artifacts/results` 15 个实验结果（约 1.38 MiB）、`artifacts/signoff` 11 个签核摘要（约 51 KiB），没有遗漏根目录已跟踪 JSON/TXT。
- Vivado 目录迁移需修改约 9 个 PowerShell runner、9 个 Tcl 输出目录、`verify_goal.py`、Pulse verifier、Goal 测试、`.gitignore` 例外和 4 份报告/设计文档。目录整体移动可保持目录内相对结构，但仍是独立的大验证切片。
- 将机器数据与 Vivado 目录放进同一提交会扩大审查面。更符合 KISS 的顺序是：V1A 清理 ignored 生成物；V1B 迁移 30 个 data/results/signoff；V1C 单独迁移 Vivado 证据目录。每一切片分别验证并提交。
- 并行反证进一步确认：15 个历史/实验结果 JSON 不进入当前 NP4B/local-prune/Pulse/T0/M3 签核哈希集合；另外 4 个 data/manifest 与 11 个 signoff JSON/TXT 仍是合同或证据入口，不应在 V1 迁移。
- 54 个 Python 文件以脚本目录作为 `ROOT`，31 处 subprocess 以根目录为 cwd；14 个 PowerShell、10 个 Tcl、15 个 Yosys 脚本也依赖扁平根布局。源码/测试/工具全量归档必须作为单独架构迁移，而非本轮清噪。
- 最终推荐 V1 收缩为：迁移 15 个结果 JSON 到 `artifacts/results/`；可选清理 47 个 ignored 根文件及纯缓存目录；其它文件和证据目录全部不动。

### V1 执行冻结事实

- 15 个目标文件全部为已跟踪根文件，缺失为 0；在 NP4B、local-prune、Pulse、M3、T0 六类当前签核摘要中的文件名命中均为 0。
- 当前工作树除本轮 `task_plan.md`、`findings.md`、`progress.md` 外无其它修改。
- ignored 根单文件白名单稳定为 47 项；它们均由 `git status --ignored` 标记 `!!`，不在 `git ls-files` 中。
- 两个结果文件的短名称存在后缀包含关系；实施时必须使用精确完整路径，避免重复替换。
- 隐式读取点包括 `test_local_prune_reference.py` 对 B0 摘要的固定读取；`run_local_prune_b21.py` 同时加载 `artifacts/results/local_prune_np2_results.json` 和 `artifacts/results/local_prune_np3_results.json` 并绑定其哈希。二者都必须随迁移更新。
- 结果路径引用主要分为四类：CLI 默认输出、脚本内固定写出、测试固定读取、文档/历史记录。V1 不改变显式 `--output` 自定义能力，只改变默认路径。
- `digit8x8_d2.py` 直接入口和 `run_digit8x8_d2.py` 多种子入口都能写 D2 结果，二者必须统一到归档目录。
- `run_local_prune_b21.py` 的 `prerequisite_sha256` 键将随路径变为 `artifacts/results/...`；这是机器结果对真实前置文件位置的诚实记录，需要重新生成 B2.1 结果才能保持内容自洽，不能只手改旧 JSON。
- V1 实施后完整 `unittest discover` 为 387/387 通过，真实 Vivado 用例因未设置 `VIVADO_ROOT` 跳过 1 项；NP4B 独立 verifier、compileall 和持久工作流 Check 均通过。
- `verify_goal.py` 的软件与 M3 阶段通过，但报告审计拒绝现有 Tile Vivado 证据：`digital_lif_engine.sv` 与 `digital_snn_tile_4x2x2.sv` 最后变更于 2026-08-29，`vivado_tile_reports/` 仍是 2026-08-19 的报告。该陈旧关系早于 V1 且与结果路径迁移无关，但按冻结验收合同仍是提交阻断项。
- 不得通过修改时间戳、放宽 verifier 或把旧报告解释成当前 RTL 证据来绕过该门；V1 又明确禁止调用 Vivado，因此需要用户决定是否把 Vivado 重建作为独立获批动作，或明确调整本次归档验收范围。
- 用户选择严格重建后，Vivado 2024.1 三关均真实通过：Tile OOC 为 3152 LUT/1972 FF、100 MHz WNS +0.213 ns；XPM 双向 FIFO 容量/排空/回绕仿真与综合通过；完整 System 在 Host 50 MHz / Tile 100 MHz 下分别获得 WNS +14.306/+0.081 ns，CDC 分类无 external unsafe/critical 或 XPM unknown/critical。
- `verify_goal.py` 已在 Vivado 证据重建后完整退出 0，并输出 `GOAL_AUDIT_PASS`。除 387 项软件回归外，Tile 协议形式证明成功，Host Bridge 控制器 20 拍安全证明及 6 类可达性见证成功，Tile 20 seeds × 500 事务和 System 957 条命令协同仿真成功。
- 严格闭环仍不等价于“所有未来行为均已证明”：当前没有证明无限时域/全状态等价、任意 RAM 容量、完整板级 bitstream、真实活动功耗或通用 AI 自训练。Vivado 的 0.103 W/0.112 W 仅为 vector-less OOC 估算，置信度 Medium。

## 2026-09-01 PR #5 回复复核

- GitHub 仓库中不存在编号 #4 的 PR 或 Issue；全部 PR 为 #1、#2、#3、#5。用户所述“PR4 新回复”按唯一匹配的新活动解释为 PR #5。
- PR #5 最新 HEAD 仍为 `a7e8b09a050df5f2d39e5070e9f42ee12004fa62`，没有新代码提交；新增的是协作者评论 `5492861157`。
- 协作者承认此前批准记录仅为仓库外指令自述，并请求仓库所有者确认九项决策。用户本轮已经直接确认九项全部同意，因此原审查第 3 项授权溯源问题可以关闭。
- 验证器非 fail-closed、ENeuron 配对微架构不一致、孤立诊断文件三项尚无代码修复，PR 仍不具备批准条件。
- 仓库所有者确认评论已提交并回读成功：`https://github.com/Epslion404/ENeuron/pull/5#issuecomment-5492928792`；PR 状态保持 `CHANGES_REQUESTED`。
- PR #5 HEAD `61988e2` 的只读 verifier 正向退出 0，manifest SHA 前后不变，工作树干净；mutation suite 10/10 通过。
- `verify_np6_physical_cost.py` 对冻结来源只调用 `git log` 取提交时间，再比较 checkout 后的 `signoff_summary.txt` mtime；它没有把 manifest 所绑定的 RTL/runner 字节与 `git show <frozen_git_head>:<path>` 比较。后续提交若同步修改源码和 manifest，旧报告仍可能被接受，冻结来源合同尚非 fail-closed。
- 阶段报告仍声明冻结 HEAD `67a70f3`，但 manifest 与七份摘要绑定 `7023b15`；冻结决策文档和报告仍写“确认前/授权待确认”并只引用协作者评论 `5492861157`，没有引用仓库所有者确认 `5492928792`。
- PR #5 HEAD `550ec26` 已要求 manifest binding、`git show 7023b15:<path>` 和当前磁盘文件三者哈希完全一致，并移除 mtime 新鲜度判定。
- 本机复验：compileall 通过；只读 verifier 正向 PASS；manifest 不变、工作树干净；mutation suite 12/12 PASS，T8/T9 均拒绝冻结后源码/runner 与 manifest 联合篡改；测试后 HEAD 仍为 `550ec26`。
- 阶段报告已统一为冻结 HEAD `7023b15`，批准链已引用仓库所有者评论 `5492928792` 并删除待确认状态。当前没有新的合并阻断；结论仍只允许记为 `NP6_PHYSICAL_COST_PARTIAL`。

## 2026-09-01 NP6 合并后状态恢复

- PR #5 已于 2026-09-01 合并，merge commit `241b1d0`；本地旧工作流仍写 NP6 未批准，属于状态漂移而非新的工程阻断。
- NP6 实际结论是 `PARTIAL`：7 个配置均完成实现且 route/DRC error 为 0，只有 gate 和 ENeuron 剪枝封装通过 100 MHz。
- NP7 的最小可信边界应先证明独立共享突触执行路径，再接三模型网络；否则完整网络中的学习、泄放和路由会掩盖 RAM 请求与 lane 周期的因果关系。
- 稀疏记录采用两个权重和两个位置索引即可唯一表达合法 `2:4`，无需再保存可漂移的四位结构掩码。
- NP7 必须在 Vivado 前先以负向实现证明计数器能拒绝“全读后门控”和“MAC 后清零”，否则读取/操作下降声明不可审计。
- Nexus 首轮增量探测因 `--max-nodes 500` 丢弃 1182 个节点；提高到 2500 后得到 1682 节点、2310 条边，`truncated=false`、`parse_errors=0`，消除了结构覆盖降级。
- 干净提交态首次 mutation 复验的 T0 失败不是 verifier 污染：`shutil.copytree` 复制 4 个 `-text` VCD 后，临时 Git 工作树出现二进制字节差异。将测试夹具改为 `git clone --no-hardlinks` 后，T0 和 T1–T9 全部通过，最终 `MUTATION_SUITE PASS checks=12`。

## 2026-09-01 PR #6 初始事实

- 唯一开放 PR 为 #6：`NP7 共享 BRAM 与共享 lane：NP7.1–NP7.6 完成，G3 未达标 ⇒ NP7.7 停在功能阶段（NP7_FUNCTIONAL_HOLD）`。
- 最新远端 HEAD 为 `398dc1aedc401ede04b9ec8a6b79e4c740cb2d1d`，base 为 `main`。
- PR 没有 NP7 Vivado runner、XSim transcript、综合报告或物理成本验证器；正文明确写明 G3 失败后未运行 NP7.7。
- 本机 Vivado 2024.1 `xvlog` 能分析四个 NP7 RTL 模块，但拒绝 `tb_np7_exec_unit.sv`：第 153 行使用 `run_phase`，第 168 行才声明，报 `VRFC 10-3380`。`tb_np7_negative.sv` 在第 152/167 行存在同类问题；当前仓库工装不能完成 Vivado 行为仿真。
- `cfg_illegal_index` 仅作组合提示，dense/sparse 顶层仍把未经门控的 `cfg_valid` 传给 RAM；`np7_weight_ram.sv` 在 `cfg_open=1` 时无条件写入，违反“非法 CONFIG 写入时拒绝”的冻结合同。
- sparse 的 `checked_lat` 没有 reset 赋值，也没有在接受新事务时清零；依赖它的一次性运行期结构复查不可靠。现有 testbench 在非法写入沿之前主动退出，形式工装又假设合法记录，均未覆盖该缺陷。
- 周期模型 11 项单测通过；三模型集成独立复跑问题数为 0；软件验证器得到 `rejects=0 blocking_gates=G3 overall=FAIL`，证明证据完整但 G3 硬门确实失败。
- 突变套件在 Windows 默认中文代码页下直接运行会错误解析子进程输出，多项显示 `ESCAPED`，最终触发 `UnicodeEncodeError`；设置 `PYTHONUTF8=1` 后 13/13 PASS。测试脚本需要自行固定子进程 UTF-8，而不是依赖调用环境。
- `docs/planning/NPU_PRUNING_NP7_FREEZE_DECISIONS.md` 的决策 2 与 3 被 `|| 3 |` 拼在同一表格行，文档结构损坏。
- 已向 PR #6 提交中文 `CHANGES_REQUESTED`，review id 为 `PRR_kwDOUIH1ms8AAAABLtyLuA`；要求修复上述问题，并在所有者确认八项冻结决定及 G3 A/B/C/D 路径后再复审。

## PR #6 两类裁定代价

- 八项冻结决定是授权/语义基线，不是无成本形式手续。原样批准只关闭授权链；若修改某项，其所有下游证据必须按依赖范围重开。
- A 与“原样批准八项”冲突：A 把决策 7 的 G3 从 25% 改为 20%。当前最差 L4/L8 为 21%，只有 1 个百分点余量；工程改动小，但有事后降低目标的可信度成本。
- B 与“原样批准八项”冲突：B 改决策 5 的零路径周期合同。V1 将零路径 2 拍降为 1 拍，L1 反事实从 22.33% 提升到 33.75%；预计各 lane 为约 30–34%，需要 oracle、dense/sparse RTL、形式、账本、验证器和全部证据重跑。
- B 中单独 V2 虽降低绝对周期，却把相对降幅降到 17.65%；V1+V2 的绝对周期最好但相对降幅 30.65%，低于 V1 的 33.75%。若当前目标是 G3，相比 V1 不值得先引入 V2 复杂度。
- C 是唯一能原样批准八项的路径：保留 G3≥25% 并承认 NP7 功能阶段失败。关闭 PR 可零新增工程量；若要合并功能基线，仍必须修复当前 Vivado testbench、CONFIG 拒绝和编码阻断。
- D 会改写冻结 B2.1 性能口径，实质涉及决策 6/7。随机流量下 L4/L8 仅 25.3%，余量 0.3 个百分点；物理背压或流量变化很容易抹掉，且不能回答真实 B2.1 任务是否加速。
- 决策 8 若原样批准，NP7.7 必须使用 Vivado 2024.1；本机已有 2024.1，但协作者当前只有 2024.2，因此执行责任需要转移或另行批准版本例外。

## NP7 各路径的实际系统效果

- 当前 V0 在冻结任务上的每 tick 周期约为：L1 dense 34.333、sparse 26.667；L2 为 33.667/26.333；L4/L8 为 33.333/26.333。若严格按 100 MHz 串行调度映射，相当于每 tick 约节省 70–77 ns，但这不是整机实测。
- sparse 从 L1 增到 L2 只把每 tick 从 26.667 降到 26.333，约 1.25%；L4/L8 不再改善。固定握手开销占 70.9%，且 2:4 每组最多只有两个保留权重，因此高 lane 数在本任务上基本闲置。
- G1 72.22% 与 G2 50% 表示读流量和有效加法显著下降，可能降低共享存储压力与动态翻转；但当前 32x20 RAM 很小，是否映射为 BRAM、LUTRAM，以及是否减少物理块数仍必须由 Vivado 证明。
- A 只改变“通过/失败”标签，不改变任何一拍实际运行行为。D 只改变考题分布，同样不会让冻结 B2.1 部署更快。
- B-V1 会真实减少零活动事务的控制周期，同时必须保证神经元泄放、阈值和时间仍推进。按 L1 账本，sparse 可从 1600 降到 1060 周期；V1+V2 的 sparse 绝对周期可到 860，但协议复杂度和时序风险更高。
- G3 是局部共享执行单元指标。若该单元只占整机时间 30%/50%/80%，当前约 22.3% 的局部周期下降对应的理论整机吞吐提升约 7%/13%/22%；Ethernet、DMA、PS 调度和神经元状态更新会进一步限制实际收益。

## DP-NP7-001 管理员裁定

- 仓库管理员选择 B-V1+V2：A/C/D 不采用，V1-only 不作为本轮最终交付。
- 决定 1/2/3/4/6/7 批准；决定 5 被单槽弹性流水合同取代；决定 8 保留软件门全绿后进入 Vivado，并允许 2024.1/2024.2 精确版本绑定。
- V1：零路径在下游 ready 时同拍 accept/result；背压时必须保存稳定结果，且神经元状态仍推进。
- V2：非零最后一批可在同一边沿完成旧结果并接受下一事务；任意时刻最多一个未退出结果，背压或 lane stall 时不得提前推进。
- 旧周期恒等式作废；新账本必须逐拍记录 accept/result、同拍重叠、零路径单拍、结果背压、启动和排空。
- 当前 NP7.1–NP7.6 证据因周期合同变化全部失效；需修复原 review 五项阻断后全量重跑，G3 保持 25%。
- 知识库文件为 `docs/planning/NPU_PRUNING_NP7_DECISION_B_V1_V2.md`，并已加入 `docs/README.md` 与 NP7 TODO。
- 管理员评论已提交到 PR #6：issue comment `5498372499`；回读作者为 `Epslion404`，PR 仍为 `CHANGES_REQUESTED`。

## 2026-09-03 PR #17 合并后状态审计

- 远端 `main` 当前为 `0ca6a50d4b4724b75387188bb3321f27a69caa59`，PR #17 已合并，当前无开放 PR。
- PR #16 的 run `33753869517` 与 PR #17 的 run `33755848063` 均为四道 CI 全成功；仓库外接收器收到对应 SHA 的 `workflow_run completed/success`，PR #17 另收到 `pull_request closed`。
- PR #17 只收口文档、持久工作流和 Nexus 状态，没有传统 NPU + ENeuron 集成业务 RTL，也没有启动新的 Vivado。
- Nexus 已在 PR #17 中刷新到 PR #16 基线；合并后需要再更新验证头和主分支合并点到 `0ca6a50d`，否则知识库会落后一代。
- `workflow_resume.ps1 -Mode Check` 返回 PASS，活动 TODO 未完成项为 0；这不等价于集成审核 I1-I6 已批准。
- `docs/planning/NPU_NEURON_INTEGRATION_REVIEW.md` 仍为 `REVIEW_REQUIRED`，当前只能进行静态审计、文档与 Nexus 维护。
- 用户未跟踪文件 `np75_tmp_sparse_protocol.ys` 仍保持原样，不纳入提交或 Nexus 文件树。

## 2026-09-03 集成审核门审计结论

- 持久工作流恢复检查、主线同步、开放 PR 检查、最近 CI 和仓库外 Webhook 健康检查均通过；这说明项目管理闭环可继续运行。
- 这些检查不等价于传统 NPU + ENeuron 集成完成。当前缺口仍是 I1-I6 管理员裁定、Python bit-exact 旁路/门控 oracle、集成 RTL、协同仿真、形式验证和集成级 Vivado 证据。
- 在审核门批准前继续实现业务 RTL 或运行 Vivado，会绕过已冻结的阶段边界；本轮仅更新可复核状态快照。

## 2026-09-03 PR #21 合并后的事实

- 静态审计 PR #21 已在 run `33765822606` 四门成功、Webhook 收到同 SHA 成功终态后合并为 `588e7d5`；状态与 Nexus 的主线锚点需要跟随该合并点更新。
- 合并只改变文档/Nexus 和工作流记录，不扩展传统 NPU + ENeuron 的能力声明；I1-I6 仍是唯一实质人工门。

## 2026-09-03 I1-I6 批准结论

- I1-I6 已批准，项目可以进入传统 NPU + ENeuron 集成的第一实质阶段。
- 先实现 Python bit-exact 旁路/门控 oracle，再做 RTL；这能把数值语义、门控语义和边界提交合同固定下来，避免把 RTL 调试与模型定义混在一起。
- I1-I6 的批准不等于集成性能或 Vivado 结果已证明；所有吞吐、资源、功耗和准确率结论仍需后续证据。

## 2026-09-03 Python oracle 首条边界发现

- 首条旁路测试最初使用 `0..63` 像素，隐藏层累加超过 127，实际触发批准的隐藏层 ReLU/饱和规则；失败断言是测试向量预期错误，不是实现错误。
- 已将 tracer 向量改为全 1，继续验证未饱和的 bit-exact 路径；后续必须单独覆盖饱和路径。

## 2026-09-03 Python oracle 边界证据

- 全开门控与 bypass 的完整结果对象逐字段相等，说明门控只影响执行/读取计数，不改变开放路径的数值语义。
- 极值输入与权重测试确认隐藏层中间值先经过 ReLU 和 `0..127` 饱和，再作为输出层输入；不能用未饱和累加值直接计算 logits。
- 当所有输出 logits 相等时，参考模型保持 `prediction=None` 并置 `abstain=True`，避免把平局伪装成分类成功。

## 2026-09-03 CI-Fast V1 关键发现

- 原 workflow 对所有 PR 无条件启动四个 job；最近完整 run 用时约 13.7–16.9 分钟，文档或单个 Python 测试改动也承担 NP7/Windows 成本。
- PR #24 在 Python、NP7 两条检查仍为 `in_progress` 时已合并为 `3b53a7e`，证明现有分支保护没有把这些检查作为有效强制门。
- 新 workflow 保留单一稳定 `PR Gate` 名称，避免直接使用 workflow `paths` 过滤导致 required check 永久 Pending；专项 job 在 job 层条件跳过。
- 分类逻辑采用未知文件触发全仓回归的保守规则；workflow 手动运行强制所有专项门，避免手工验证被误裁剪。
- `msys2/setup-msys2@v2` 在 `update: false` 下仍可能把 UCRT64 树放在 action 临时位置；仅检查固定路径会造成假失败。正确优化是减少触发次数，同时保留路径探测与固定路径联接/复制，不牺牲 Windows 专项证据。
- PR #25 的真实 GitHub 结果证明路径分类和固定汇总门可运行；workflow 变更会故意触发全量门，普通文档变更需单独 PR 验证轻量路径。
- 当前私有仓库套餐不允许 branch protection/ruleset API，不能把 `PR Gate` 注册为真正 required check；任何“已设置保护分支”的文档表述都必须改为“待升级套餐或组织策略”。

## 2026-09-03 NPU oracle 协议发现

- 门控提交必须拆成 pending 与 active 两份；运行中的样本只读 active 快照，pending 不能组合穿透。
- 单槽结果背压不仅保持结果稳定，还必须阻止下一样本启动，否则会覆盖尚未被下游接受的 logits。
- `STATE_CLEAR` 可以增加动态清除计数，但不得回退已提交 mask epoch；`infer_freeze` 同时拒绝 mask 更新和动态清除。
- 样本输入校验必须先于所有状态提交；否则非法图片会把 runtime 卡在 busy，或错误消费 pending epoch。
- 结果完成接口不能接受外部 `InferenceResult` 参数，否则调用者可把非当前样本结果注入输出槽；内部 `_inflight` 是更接近硬件事务所有权的最小表达。

## 2026-09-03 NPU oracle 冻结审计发现

- 14 项通过只证明当前函数级合同的已覆盖部分，不能替代逐位数值、地址映射和逐拍接口冻结。
- INT32 必须定义 bias 合法域和溢出行为；当前 Python 无限精度会产生硬件 32-bit 累加器无法直接复现的 logits。
- V1 若声明固定 `64→32→10/group=4`，就应在构造边界拒绝其他配置；不能让非整除参数以运行期 `IndexError` 失败。
- mask 位序必须由单 bit 和跨层混合手算向量证明。全开、全关和整版 epoch 切换无法发现输出通道或组地址互换。
- frozen dataclass 不会递归冻结其中的 list；背压结果要真正稳定，logits 需要不可变容器。
- pending、freeze、clear 和 hard reset 是同一状态机的组合边界，必须在 RTL 前统一冻结，不能分别用几个函数测试拼出结论。

## 2026-09-03 OF1-OF6 反审计发现

- 对固定维度而言，配置期限制 bias 可以保证所有合法计算无 INT32 溢出，且不增加 MAC/DSP 反馈路径；比正常回绕更符合分类语义，比逐拍饱和更容易保持时序和加法顺序无关性。
- 外部灰度裁剪和核心 uint4 合法域必须分层；否则 Python 的钳位逻辑会被误解为片上 NPU 必需硬件。
- 固定长度配置应优先使用隐式顺序计数，而不是显式地址加完整性 bitmap：模型 634 word 用 10-bit counter，mask 19 word 用 5-bit counter。
- mask 至少包含 loading/complete/published 三阶段；published 后只允许由后续样本首 beat 原子消费，不能继续覆盖。
- hard reset 对 BRAM 的正确合同是“内容不可用、model_valid 清零”，不是“物理清零所有存储位”。

## 2026-09-03 CI action 运行时发现

- GitHub 已开始对 checkout v4 的 Node.js 20 运行时给出弃用 annotation；保持旧主版本虽然暂时能被强制放到 Node 24 执行，但会持续产生维护风险。
- 官方当前稳定主版本为 checkout/setup-python v7，最低 runner 为 `v2.327.1`；GitHub 托管 runner 的实际兼容性仍必须由本仓库 workflow 全量 run 证明。
- action 版本是 CI 证据生成环境的一部分；升级必须触发全仓、Windows、NP7 功能与物理完整性门，不能沿用升级前 run 代偿。
# 2026-09-03 PR #18 状态核对

- PR #18 的四道门均已成功：Python/语法、XPM CDC、NP7 功能与证据、NP7 物理证据；同一 HEAD `59bef59a` 的 `workflow_run completed/success` 已由仓库外 Webhook 记录。
- `mergeStateStatus=CLEAN` 且 `mergeable=MERGEABLE` 后完成合并；当前主线为 `1877140c`。这只证明状态文档收口，不扩展 NP7 或集成能力声明。
- `NPU_NEURON_INTEGRATION_REVIEW.md` 仍为 `REVIEW_REQUIRED`，I1-I6 未批准前不能实现传统 NPU + ENeuron 集成 RTL 或运行新的 Vivado。

- PR #19 的 CI 四门均成功并已合并为 `63028d4`；Webhook delivery API 显示本次终态事件曾因 EOF 失败，服务恢复后 `/healthz` 内外均为 200。不能把“服务恢复”倒推成该历史 delivery 已补投，当前仍以 GitHub run/PR API 作为终态证据。
- 本切片提交时误留在本地 `main`，但只产生了未推送的本地提交；通过从该提交创建专用分支恢复 PR 流程，没有强制推送或覆盖远端 `main`。

## 2026-09-03 OF1-OF6 V3 二次反审计

- V2 的 634-word 只给出段长度，没有冻结段内线性映射；必须固定层、输出、组和 byte 的对应关系，否则转置装载也可能被误判为合规。
- “非法 beat 拒绝”不能通过数据相关 `ready=0` 实现，否则 Host 持有非法 `valid` 会死锁；V3 改为握手并返回错误、RAM/计数器零副作用、同索引可重试。
- 双 mask bank 必须有 empty/loading/complete/published 四态命令矩阵；published 由下一样本首 beat 交换指针采用，不能复制 592 bit。
- freeze 只允许在完全 idle、无结果且 staging empty 时切换；frozen 下拒绝全部模型/mask 写和 `STATE_CLEAR`，但允许正常样本输入/输出。
- V1 不做数据相关零跳过：open group 即使激活全零也固定计一次读取和四次 MAC，避免 Python 与 RTL 性能账本分叉。
- Python 核心输入和权重不允许借 `int()` 隐式转换；`bool`、浮点、字符串和越界值必须 fail-closed。`prediction/abstain` 只是 Host 派生诊断，不属于 RTL bit-exact 端口。

## 2026-09-04 OF1a RED 证据

- 旧 `quantize_input()` 通过 `int()` 接受浮点、字符串和 `bool`，并把越界整数裁剪到 `0..15`，与批准的核心 uint4 合同冲突。
- `None` 会泄漏 Python `TypeError`，说明错误类型和错误消息也未冻结。
- runtime 只有在 `model.infer()` 成功后才提交 pending epoch，因此无需重写事务逻辑；只要完整图片在乘加前统一验证，非法像素即可保持 active epoch、running 和结果槽不变。

## 2026-09-04 OF1a GREEN 结论

- 最小修正只用 `validate_uint4_input()` 替换隐式转换入口，不改变推理循环、mask 账本或 runtime 状态机。
- 使用 `type(value) is int` 明确排除 Python 中属于 `int` 子类的 `bool`；合法域仅为 `0..15`，所有非法值统一抛出包含 `uint4` 的 `ValueError`。
- 64 个像素先完整验证、后进入 mask 和乘加，因此末像素非法也不会产生部分 MAC、读取计数或 epoch 提交。

## 2026-09-04 OF1b RED 证据

- 当前权重路径使用 `int()` 后钳位，因而错误接受越界整数、浮点、字符串和 `bool`；`None` 泄漏 `TypeError`。
- bias 只调用 `int()`，既无严格类型域也无两层安全窗口；所有四个边界外一单位的值均被接受。
- `NpuConfig` 没有 V1 固定参数检查，`64.0` 也可进入模型；`InferenceResult.logits` 仍为可变 list。
- 当前 `load_weights()` 依次写四个成员。严格校验若直接嵌入这些赋值，后半段失败会形成混合模型；必须先在局部完成四块数据的验证和复制，最后统一提交。

## 2026-09-04 OF1b GREEN 结论

- V1 参数在 `NpuConfig.__post_init__()` 一次拒绝所有非精确 `64/32/10/group4` 的数值或类型，避免未验证拓扑进入 oracle。
- 四块模型参数先复制到局部容器并完成严格整数与闭区间验证，最后以一次成员解包提交；首次失败保持 unloaded，reload 失败保持旧模型完整。
- 第一层 bias 安全窗为 `[-2147360768, 2147361727]`，第二层为 `[-2146963456, 2146967519]`；合法第二层边界配合最坏权重贡献恰好产生 `-2147483648` 与 `2147483647`。
- logits 在结果构造时转换为 tuple；冻结 dataclass 阻止字段替换，tuple 阻止元素改写，runtime 背压期间继续持有同一结果对象。

## 2026-09-04 OF3 mask 位序与工作量账本

- 当前实现的两层扁平索引已分别等价于 `h*16+g` 和 `o*8+g`，每个开启 bit 只覆盖对应行内连续四个权重。
- 内部单 bit 手算向量只开启 `mask0[87]` 与 `mask1[25]`，得到唯一非零 logit 90、2 次组读取和 8 次 MAC；把 L0 改为相邻 `mask0[88]` 后结果归零，证明测试能发现 group 偏移。
- 首尾 mixed 向量同时开启 `mask0[0]/mask0[511]` 与 `mask1[0]/mask1[79]`，得到首尾输出 12/40 和 4/16 读取/MAC，锁定两层边界与高端通道。
- 输入和隐藏激活全零时，5 个 open group 仍固定计 5 次读取与 20 次 MAC；只有关闭 mask 才允许跳过，V1 不引入数据相关零跳过。

## 2026-09-04 OF4a 634-word RED

- 当前仓库没有模型 word 镜像解码或完整镜像载入 API，只有直接四数组 `load_weights()`；因此 634-word 段表仍仅存在于文档。
- 最小切片限定为纯镜像边界：完整 634 word、每 word 严格 uint32、权重 byte0 对应最低 8 bit、bias 按 32-bit 二补码解释。
- 原子性继续复用 OF1b：先在局部解码全部数据，再调用已签核的原子 `load_weights()`；不在 OF4a 引入 ready/valid、响应槽、顺序计数器或 `MODEL_COMMIT` 状态机。

## 2026-09-04 OF4a 634-word GREEN

- 解码器先把调用方序列快照为 tuple，再要求长度恰为 634，并统一验证每项必须是真正的 `0..0xffffffff` 整数；首、中、尾位置均覆盖非法类型和值域。
- 权重段按低字节优先解为 signed INT8，bias 段按二补码解为 signed INT32；全量映射测试逐项检查 512/32/80/10 四段，安全 bias 边界由 OF1b 与 OF4a 原子拒绝矩阵共同验证。
- `load_model_words()` 只在完整解码后调用已签核的原子 `load_weights()`；两层 bias 首尾的安全窗外值均拒绝，最晚 word633 失败仍保留旧模型或 unloaded 状态。
- 该 API 允许函数级 oracle 重复原子 reload，仅用于冻结完整镜像语义；RTL 的一次装载锁定、逐 beat 接受和 `MODEL_COMMIT` 仍属于后续协议切片。
- 首版只检查四段首尾，不能排除内部 word 交换/重复；最终测试改为逐项核对全部 512 个第一层权重 word、32 个第一层 bias、80 个第二层权重 word和10个第二层 bias，并验证解码后修改源列表不影响快照。

## 2026-09-04 OF4b1 19-word RED

- mask 完整镜像固定为 19 个 uint32 word：前 16 个承载 mask0 的 512 bit，后三个低 80 bit 承载 mask1；所有 bit 均按 word 内 LSB-first 展开。
- word18 仅低 16 bit 合法，高 16 bit 是保留位；任何置位必须整体拒绝，不能静默忽略。
- 本切片只建立无状态 `decode_mask_words()`，不与现有 `_PendingMasks` 或 `stage_masks()` 合并，避免提前选择四态命令、错误响应和 epoch 时序。

## 2026-09-04 OF4b1 19-word GREEN

- `decode_mask_words()` 已实现严格 19-word `uint32` 快照校验；所有输入先复制为 tuple，拒绝 `bool`、浮点、字符串、`None`、负数和超过 `0xffffffff` 的值。
- canonical packing 已逐 bit 验证：word0.bit0 到 word15.bit31 映射 `mask0[0..511]`；word16.bit0 到 word18.bit15 映射 `mask1[0..79]`。word18 高 16 位是保留位，非零立即拒绝。
- 返回的两层 mask 均为独立 tuple；修改源列表或尝试修改解码结果都不会改变已发布快照。
- 验证：OF4b1 定向 `2/2`，完整 oracle `27/27`，CI-Fast `8/8`，`compileall` 和 `git diff --check` 通过；独立审计 PASS。
- 明确边界：本切片不实现 active/staging、epoch、四态命令、错误响应、valid/ready、RTL 或 Vivado；这些内容归入 OF4b2 及之后阶段。

## 2026-09-04 OF4b2 RED

- 新增 `MaskCommand`、`MaskCommandKind`、`MaskConfigPort`、`MaskStepResult` 的公开行为测试草案；当前基线缺少这些接口，3 条测试均以明确缺失失败。
- 测试冻结三条最小行为：`empty → loading → complete → published`；非法命令必须先握手再产生单个错误响应，响应背压期间稳定且不接受下一笔；第 19 个 word 的保留位错误排空后必须在原隐式索引重试。
- 本切片不预设内部寄存器、状态编码或 RTL 结构；响应和状态字段通过不可变步骤结果对外观察。

## 2026-09-04 OF4b2a 实现中

- Python 端口采用单错误响应槽：无待响应时 `cmd_ready=1`；非法命令仍被接受并产生一个错误码；响应未被 `response_ready` 接受前，后续命令不握手。
- staging 状态为 `empty/loading/complete/published`；19 个合法 word 后进入 `complete`，`MASK_COMMIT` 只发布下一 epoch，`accept_sample_boundary()` 才交换到 active。
- 非法 word、非法 epoch、非法状态和冻结状态均零副作用；保留位失败不会推进隐式 word index，排空响应后可同索引重试。
- 当前 6 条行为测试通过，但尚未覆盖完整命令矩阵、同周期响应/新命令仲裁、与 `NpuEpochRuntime` 的正式组合；这些保留为后续 OF4b2b/OF4b3。
- 独立审计发现 `MASK_BEGIN(epoch=active_epoch)` 会造成不可提交 staging；已补回归并修正为 BEGIN/COMMIT 均要求 `active_epoch+1 mod 2^32`，当前 7 条 OF4b2 测试通过。
- 端口本身仍不判断样本运行、输入部分 beat 或结果槽；冻结切换的全局 idle 条件必须由上层 runtime/集成层负责。
- OF4b2 终审 PASS：BEGIN/COMMIT 均要求 next epoch，`active_epoch=0xffffffff` 可正确回绕到 0；错误响应消费拍保持稳定且不接受新命令。当前切片 GREEN，但完整状态矩阵和 runtime 组合仍待 OF4b2b。

## 2026-09-04 OF4b2b GREEN

- 完整状态矩阵覆盖 `empty/loading/complete/published` 的所有非法命令组合；每项均验证一次握手、错误响应背压稳定、错误消费拍不接新命令、状态/索引/epoch 零副作用及恢复。现有 OF4b2 已使该组直接回归绿，不把它改写为虚假的 RED。
- `NpuEpochRuntime.bind_mask_port()` 只增加组合层所有权与冻结判定：运行中、结果槽占用、runtime pending 或 mask staging 非空时拒绝切换；完全 idle 时把 freeze 同步到端口。
- frozen 仍允许 `begin_sample → complete_sample → accept_result`，但配置、动态清除和端口 `MASK_BEGIN` 均被拒绝；runtime 组合测试 5/5，完整 oracle 41/41。
- 后续必须把相同全局 idle/freeze 合同映射到单时钟 RTL；本切片没有运行 Vivado，也没有声明硬件吞吐或资源收益。
- 2026-09-04 单时钟 RTL 设计审核前静态审计发现：Python oracle 与设计稿在 634-word/19-word 镜像、数值域、结果背压、版本切换、复位和冻结边界上已对齐；但样本/结果 beat 字段、统一配置流拓扑、双 commit 同拍行为、`mask_valid` 默认全开语义、未提交模型的 `sample_ready` 行为和 runtime idle 硬件组合仍需明确。详见 `docs/planning/NPU_SINGLE_CLOCK_RTL_DESIGN_AUDIT_V1.md`，共 8 项待补规格，未创建 RTL、未运行 Vivado。

## 2026-09-04 RTL 裁定 V1 审计与 V2 修正

- 独立审计确认 V1 不能直接批准：结果 metadata 引入 oracle 未定义的 `model_epoch`，320-bit 结果槽账本不完整；统一命令流下不存在 `MODEL_COMMIT` 与 `MASK_COMMIT` 同拍竞争；样本 framing、首拍 mask 切换后的错误回滚、`model_valid=0` 的逐拍 ready 行为以及 `runtime_idle` 的错误/部分输出/FIFO 条件均未闭合。
- V2 将样本固定为 8 个 `32-bit` beat、结果固定为 10 个 `32-bit` signed beat，beat 序号由 DUT 内部计数，取消外部 `last`；像素采用 `pixel[8*k+j] = beat_data[4*j +: 4]`，结果只锁存 `sample_id` 与 `mask_epoch`，删除 `model_epoch`。
- V2 将配置固定为一条 128-bit 命令流和一条 128-bit 响应流；配置命令与样本首拍同拍时配置优先，统一命令流按握手顺序串行化两个 commit，不再定义不存在的 commit 碰撞优先级。
- V2 明确复位后全开 mask 且 `mask_valid=0` 仍允许推理；样本首拍原子锁存 mask/epoch；`model_valid=0` 时 `sample_ready=0`；`runtime_idle` 必须计入 partial input、running、partial output、result/error slot 和命令/响应槽占用。
- 验证门改为至少 20 个固定 seed × 每个 100 个样本（不少于 2000 个），并覆盖背压、reset、freeze/clear、epoch 回绕、错误同索引重试、全开/全关/mixed mask、负权重和负向 mutation。V2 provisional JSON 明确 `admin_review_required`、`rtl_allowed=false`、`vivado_allowed=false`。

## 2026-09-04 单时钟 RTL 骨架与 mask epoch 切片

- 第一条垂直切片冻结模型无效拒收、634-word 顺序装载/提交、配置优先样本首 beat、固定 8-beat 输入、单槽错误响应和固定 10-beat 结果背压；当前结果仍为零占位，不能称为 NPU 数值实现。
- 第二条切片加入 19-word mask staging、next-epoch 检查、published 等待和样本首 beat 激活。复位默认全开但 `mask_valid=0`；首次用户版本激活后置 1，结果槽锁存该样本 epoch，后续样本继续使用 active epoch。
- word18 高 16 位保留位错误会产生稳定单槽响应，隐式索引保持 18；响应消费后可在同一索引重试。该负向测试发现旧响应拼接只有 126 位，现由唯一 `make_error_response()` 生成严格 128 位字段。
- 连续第二个样本测试发现第 8 beat 后输入计数必须显式归零；修正后两个样本均完整接收 8 beat。当前尚未实现 mask bit 对真实 MAC 的门控、INT8 计算、freeze/clear 或 Vivado OOC。

## 2026-09-04 单时钟控制切片

- `MASK_ABORT` 只在 loading/complete 接受，并一次丢弃隐式 word index、staging epoch 与部分镜像；随后严格 idle 恢复，active mask/epoch 不变。
- `STATE_CLEAR` 只在 runtime、响应槽和模型/mask staging 全空时接受；骨架用 `state_clear_count` 提供公开可观察证据，清除不改变 `model_valid`、active mask 或 epoch。
- `FREEZE_SET` 使用命令 flags 的 bit0。进入/退出冻结都必须等待严格 idle；结果槽占用期间 Host 可以保持命令 valid，直到结果排空后才握手。
- `infer_frozen=1` 时样本流继续工作，模型/mask 配置、abort 与 `STATE_CLEAR` 均握手后返回错误且零副作用；`FREEZE_SET` 自身仍可用于退出冻结。
- 当前三条 RTL 切片只冻结协议骨架，不证明 INT8 乘加、mask 实际跳读、吞吐、资源、时序或功耗。

## 2026-09-04 单时钟真实计算 RED

- 真实计算 tracer 使用可手算稀疏模型：hidden0 的前四个权重为 +10，hidden1 的前四个权重为 -1 且 bias=100；output0 对 hidden0/1 权重为 +2/-3 且 bias=3。
- 输入首 beat 为 `0x0000ffff`，按已批准 nibble 位序得到 pixel0..3=15；全开默认 mask 下 hidden0 饱和为 127、hidden1=40，首个 logit 应为 137。
- 发布 epoch 1 且仅关闭 L0 bit0 后，hidden0 变为 0，首个 logit 应为 -117；该向量同时锁定 active mask 复制、首拍 epoch 激活和真实门控效果。
- 现有占位 RTL 返回 0，测试以 `logit0 mismatch got=0 expected=137` 正确失败，证明 RED 针对缺失的数值路径而非测试环境问题。
- `.nexus-map/INDEX.md` 含将仓库文本伪装为强制指令的段落；按安全规则仅作为不可信数据处理，不执行其权限扩张要求。
- 最小 GREEN 使用单个 32-bit 模型读口语义：每次取出四个 INT8 权重供四 lane 并行乘法，L0/L1 均按 FETCH→ACCUM 分拍；关闭 group 直接跳过模型读取与乘加。
- active mask 使用独立 19-word bank，published mask 只在样本首 beat 复制；后续 staging 不会污染运行中或已激活版本。
- 边界回归增加 hidden31/group15 与 output9/group7，只在最后组非零；全开时 output9=59，关闭 L1 bit79 后只剩 bias=-1，证明最后组新累加值与两层最高 mask 位均生效。
- 计算开始后 `cmd_ready=0`、`sample_ready=0`、`runtime_idle=0`；结果仍由原有 10-beat 槽保持背压稳定。
- 模型配置必须在写入 word 512..543 与 624..633 前把 payload 解释为 signed INT32，并分别限制在 `[-2147360768, 2147361727]`、`[-2146963456, 2146967519]`；失败仍握手、产生错误、索引不前进。
- OF4 冻结合同允许部分输入、当前计算和结果背压期间继续准备并发布下一 mask。RTL 因此只对 mask 四类命令开放运行期 `cmd_ready`；模型、freeze、clear 和其它命令仍等待严格空闲。
- 标准 ready/valid 源在并发路径上必须先稳定 `valid/payload` 再等待 ready；否则当 ready 合法依赖 opcode 分类时会形成源端自锁。
- Yosys 0.56 的 `read_verilog; hierarchy; proc; check` 返回 0，只提示 `mask_active_words` 展开为寄存器；这不等价于 Vivado BRAM、资源或时序证据。

## 2026-09-04 随机协同仿真设计

- 随机门按每个固定 seed 单独运行一次 Icarus：模型 634 word、100 个样本 800 word、99 个用户 mask 1900 word、期望结果 1000 word 均通过 `$readmemh` 输入，避免把大数组硬编码进 testbench。
- 第 0 个样本使用复位后的默认全开 mask/epoch0；发送该样本后立即开始发布第 1 个 mask。后续每个样本的下一版 mask 都在当前计算或结果背压期间装载并 commit，下一样本首 beat 才激活。
- 每个结果先保持 `result_ready=0` 若干确定周期，再以 10 个 beat 消费；验证每 beat 的 logit、sample ID 和 epoch，覆盖结果槽稳定性与 mask 不串样本。
- mask 模式按样本轮换全关、全开和随机 mixed；模型权重包含正负 INT8，bias 使用安全范围内的正负小值，参考计算与 RTL 使用同一固定 seed 数据。
- 19-word mask 容器是 608 bit，但合同有效域为 512+80=592 bit；随机生成器必须对最后 word 的高 16 bit 进行零填充，不能把保留位当作可用 mask。

## 2026-09-04 PR #54 合并门审计

- GitHub API 当前确认 PR #54 为 `OPEN / MERGEABLE / CLEAN`；`Classify changes`、`Fast Python and diff check`、`Full repository regression` 和 `PR Gate` 均成功，三个不相关重门按路径跳过。
- 这些 CI 结果只覆盖提交 HEAD `084f849`，不能覆盖工作树中尚未跟踪的 `tb_npu_eneuron_single_clock_random.sv` 与 `test_npu_single_clock_random.py`。
- 随机门已确认是 testbench 首 beat ready/valid 观察竞态：DUT 内部 `logit_values` 与 Python 期望一致；在拉高 `result_ready` 后直接按下降沿采样会重复首 beat，改变等待拍数又可能跳过首 beat。
- 两样本同步消费者已扩展为稳定的下降沿观察/上升沿握手循环，完整固定 `20×100`（共 2000 样本）已通过；随机 testbench 已进入 PR HEAD `8ee7fe8`，当前等待 GitHub CI 重验。

## 2026-09-04 PR #54 合并后事实

- GitHub 已将包含随机 testbench 的 PR #54 合并为 `2a33f12`；此前“等待同一 HEAD CI”的描述只适用于合并前历史快照。
- 当前软件/RTL 仿真闭环为：四项单时钟定向门通过、固定 `20×100=2000` 样本逐 beat 通过、完整回归 `469/469（1 skipped）` 通过。
- 当时物理证据仍为空：该条记录属于 OOC 执行前的历史快照，不能覆盖下方 2026-09-04 的实际结果。
- 随后已固定器件 `xc7z020clg400-1`、100 MHz 约束和 Vivado 2024.1 runner，并完成综合、实现、setup/hold、DRC 与报告哈希绑定；网口、DMA、PS、板级功耗和端到端吞吐仍后置。
## 2026-09-04 传统 NPU + ENeuron 单时钟 Vivado OOC 结果

- 当前 OOC 运行绑定 `HEAD=39e41d4`；该提交相对 `origin/main@2a33f12` 只包含文档/Nexus 收口，`npu_eneuron_single_clock_skeleton.sv` 未改变。工具为 Vivado 2024.1，器件为 `xc7z020clg400-1`，OOC 时钟为 100 MHz（10 ns）。
- 综合、opt、place、route、时序和 DRC 均完成，Vivado 退出码为 0；`ROUTE_ERRORS=0`、`DRC_ERRORS=0`。DRC 仍有 OOC 环境 warning：`RTSTAT-10`（无可布线负载）和 `ZPS7-1`（PS7 未实例化），它们不是 RTL DRC error，也不等价于板级签核。
- 资源为 `2672 LUT / 1879 FF / 0 BRAM36 / 0 BRAM18 / 0 DSP`。`input_pixels_reg` 被实现为寄存器，未推断为 BRAM；这只是当前骨架的实现结果，不代表未来大模型存储方案。
- setup 未通过：`WNS=-5.087 ns`、`TNS=-421.539 ns`、244 个失败端点；hold 通过：`WHS=+0.098 ns`、`THS=0`、0 个失败端点。故当前物理状态必须写为 `VIVADO_OOC_SETUP_FAIL / TIMING_REPAIR_REQUIRED`，不能称作 XC7Z020 100 MHz 收敛。
- `WNS` 说明最差路径至少还需消除约 5.087 ns 的组合/布线延迟。按 `10 ns + 5.087 ns` 粗略折算约 66.3 MHz，仅作定位参考，不替代完整频率扫描，也不能作为板级吞吐预测。
- 最差路径审计已经完成；下述 V1 方案取代本条历史“待分析”入口。

## 2026-09-04 单时钟 RTL 关键路径分类与 V1 方案

- 最差 setup 路径从 `compute_group_index_reg[1]_rep` 到 `hidden_values` 分布式存储写入端，数据路径 14.775 ns：逻辑 6.884 ns、布线 7.891 ns、23 级逻辑。前 20 条最差路径属于同一端点族，不是互不相关的小违例。
- 当前 `FETCH→ACCUM` 虽已把模型读取分开，但 `ACCUM` 一拍仍包含输入动态索引、四个窄乘法、组内求和、32 位累加、最后一组 ReLU/127 饱和和隐藏值写回，形成结构性长链。
- KISS 修复是增加共用 signed 32-bit `lane_sum_latched`，把启用组改为 `FETCH→EXECUTE→COMMIT`；关闭组继续直接跳过，保持结构化剪枝的周期收益。
- 第一轮不强制 DSP。先验证 LUT-only V1 是否收敛；只有同条件 OOC 仍失败才单独审核 DSP 或进一步流水化 V2，避免一次改变时序、资源映射和调度三件事。
- 全开时新增约 592 cycles/sample，粗略从 1268 增至 1860；100 MHz 计算上限约 53.8k samples/s。该数字是周期估算，不是板级、DMA 或网口实测。
- 现有 compute/control/mask/skeleton watchdog 分别为 9000/6000/5000/5000 cycles，随机门为 3,000,000 cycles；V1 预计不会直接超过，但实施仍需让功能检查只依赖握手和结果有效，不写死旧延迟。
- 独立反审计发现原 TR3 与关闭组流程矛盾：关闭组应在 `FETCH` 直接推进，不能要求所有组都等到 `COMMIT`。现已将稳定合同限定为启用组，并明确关闭的最后一组在 `FETCH` 用当前累加器写回。
- 分拍后末组仍保留 INT32 加法、饱和和写回组合链，V1 不能预先保证 100 MHz。若 OOC 仍失败，必须按新最差路径选择：写回链优先独立 `WRITEBACK`，乘法链才评估 DSP。
- 计算周期可统一表示为：当前实现 `676+E`，V1 为 `676+2E`，其中 `E` 是启用的四权重组数。全开、关闭两组、全关分别为 V1 的 1860、1856、676 拍。
- 最小验证不需要新增 RTL debug 端口：扩展 compute testbench 层次观察内部 FSM 即可。三样本分别核对 592/590/0 次 `EXECUTE/COMMIT`，其中全关样本还证明 bias 不受 mask 影响。
- 五个现有 testbench 都通过握手或 `result_valid` 等待计算完成；`repeat(10)` 是结果 beat 数而非计算延迟。现有 watchdog 对 V1 仍有裕量，但实施后必须记录真实周期，不允许用盲目增大 watchdog 掩盖停顿。
- 只靠全关和随机门仍缺少“L0 最后一组关闭、此前累加非零”的小型定向证据；测试合同新增 epoch 3，只关闭 L0 bit15，使 hidden0 在 group0 累加 600 后从关闭的最后组 `FETCH` 直接饱和写回。该样本启用 591 组，V1 延迟应为 1858 拍。
- 当前 Icarus 实测/推导显示 V1 无需调整 watchdog：最小裕量是 skeleton 的约 1802.5 拍；compute 加入两条新样本后仍要求至少保留 1200 拍规划裕量。

## 2026-09-04 TR1-TR6 批准与强制 DSP 修订

- 管理员批准 TR1-TR6，并要求强制使用 DSP；按上下文将输入 `DPS` 解释为 XC7Z020 的 DSP48E1。
- AMD Vivado UG901/UG912 说明 `USE_DSP="yes"` 可以覆盖默认选择并将算术结构强制映射到 DSP；7 Series UG479 的 DSP48E1 signed 25×18 乘法器足以覆盖当前 L0 的 5×8 和 L1 的 8×8 signed 乘法。
- 最小架构固定为四条共享 signed 8×8 乘法 lane：L0 uint4、L1 uint7 都零扩展为 signed 8-bit，四个权重按 signed INT8 输入；只对乘积信号施加属性，避免把累加器也强制映射到 DSP。
- 物理签核新增精确硬门 `DSP=4`。源代码出现属性但 Vivado 报告不是 4 个 DSP 时必须失败。

## 2026-09-04 Vivado DSP 推断探针

- Vivado 2024.1、`xc7z020clg400-1` 实测：无属性窄乘法映射为 LUT；属性直接放在内部或输出乘积信号可得到 1 DSP；函数局部乘积上的属性会被忽略。
- 四个内部 signed 乘积信号分别施加 `use_dsp="yes"` 时稳定得到恰好 4 DSP；只给最终 `lane_sum` 施加属性只得到 2 DSP 并保留大量 LUT，不满足合同。
- 最小实现应删除当前函数局部乘法结构，建立四组共享 `signed [7:0] activation/weight` 和四个带属性的 `signed [15:0] product`；L0/L1 不得各复制一套组合乘法表达式。
- 探针证据保存在仓库外 `C:\Users\Epsilon\AppData\Local\Temp\eneuron_dsp_probe_20260905`，未污染仓库。四个 DSP 占 XC7Z020 共 220 个 DSP48E1 的约 1.82%。
- TDD RED 可分辨：不启用合同宏时，扩展后的 C1-C4 仍在旧 RTL 上 bit-exact 通过；启用合同宏时因缺少新寄存器/状态失败；独立源码门因没有四个显式乘积属性失败。由此可排除 testbench 重构破坏既有功能这一混淆因素。
- 仅验证 592/590/0/591 的总次数仍可能被“重复执行一个零权重组并遗漏另一个零权重组”蒙混。最终合同改为逐组 bitmap：592 个 tuple 的 FETCH 必须恰好一次，EXECUTE/COMMIT bitmap 必须逐 bit 等于 active mask；EXECUTE 锁存的模型字还必须等于当前 tuple 的真实模型地址。
- 关闭组的证明也改为直接时序检查：普通关闭组下一拍仍在同层 FETCH 且 group+1，关闭末组直接进入下一 bias/跨层/结果槽，过程中 `model_word_latched` 不得改变。因此全关 C3 不再是只靠“0 次执行 + 676 拍”的间接结论。

## 2026-09-04 DSP V1 OOC 结果与新路径

- OOC 精确绑定实现提交 `50550733e4af4779f3d6933738fa043ecb919970`。资源为 `2192 LUT / 1904 FF / 0 BRAM / 4 DSP48E1`；相比旧实现减少 480 LUT、增加 25 FF，并把四个乘法器真实映射到 DSP。
- 双重 DSP 结构门通过：utilization `DSP=4`，实现网表 `DSP48E1_COUNT=4`；四个 cell 分别是 `lane_product_0..3`。
- hold `WHS=+0.090 ns`、route error=0、DRC error=0；setup 仍失败，`WNS=-0.673 ns`、`TNS=-6.462 ns`、22 个失败端点。相较旧版 `WNS=-5.087 ns`、244 个端点已有显著改善，但仍不能声明 100 MHz 收敛。
- 新最差路径从 `compute_group_index_reg[1]_rep__1` 到 `lane_sum_latched_reg[30]`，数据路径 10.651 ns，其中逻辑 5.978 ns、布线 4.673 ns、11 级逻辑；实际经过 3 个激活选择 LUT、1 个 DSP48E1、求和 LUT 和 5 个 CARRY4。
- 当前 `timing_impl.rpt` 只展开前 20 条 setup 路径：14 条属于动态激活选择/DSP/求和到 `lane_sum_latched`，6 条属于 `compute_group_index` 到 `logit_values` 写使能；剩余 2 个失败端点没有展开，不能声称全部 22 个端点已分类。只增加 WRITEBACK 会漏掉已知首要 DSP 输入路径；只锁存激活值又可能留下已知写使能失败。
- KISS 首选 V2 是在 FETCH 锁存四个激活操作数，并让 L0/L1 最终值统一在独立 WRITEBACK 状态写数组。预估增加约 65 FF、少量 LUT 和每样本 42 拍；强制 DSP=4 和所有外部/数值合同不变。

## 2026-09-04 DSP V1 全部失败端点补证

- 从保留的 routed checkpoint 重新执行 `report_timing_summary -delay_type min_max -max_paths 50`；扩展报告 SHA-256 为 `BE8F1BF268553E9BDAEB31FF7DB348D6F4573011DF6CBDB699D840A71D91F04D`，摘要仍为 `WNS=-0.673 ns / TNS=-6.462 ns / 22` 个 setup 失败端点。
- 全部 22 个端点完成分类：14 个从 `compute_group_index_reg[1]_rep__1` 经动态激活选择、DSP48E1 和求和链到 `lane_sum_latched`；8 个从 `compute_group_index_reg[3]` 到 `logit_values` 分布式存储写使能。
- 旧文档中的“前 20 条为 14+6、剩余2个未分类”是原冻结报告的可见边界，现已由扩展报告补齐为 `14+8=22`；TR7/TR8 与 TR9 分别覆盖两个端点族，V2 方案边界无需改变。
- 完整证据身份和逐端点清单见 `docs/verification/NPU_SINGLE_CLOCK_TIMING_ENDPOINT_AUDIT_V1.md`。该审计不修改 RTL、约束、实现或原始 manifest，物理状态仍是 `VIVADO_OOC_SETUP_FAIL`。

## 2026-09-04 PR #60 合并事实

- PR #60 将全部 22 个失败端点补证和 Nexus 同步合入主线，merge commit 为 `4fc4c71e4c579d9b7181cd09950daf5b521854d4`。
- 权威 Actions run `33911646530` 绑定 HEAD `c0f1beaff63ffa516c8fea2de749819a9f534b4e` 并成功；Webhook 同 SHA 终态也为 success，但签名未验证，只作交叉通知。
- 当前没有开放的实现授权：TR7-TR12 仍需管理员批准。该合并只增强失败路径证据，不改变 `DSP_GATE_PASS / VIVADO_OOC_SETUP_FAIL`。

## 2026-09-04 V2 KISS 实施审计

- V2 不需要新增原计划的 signed 32-bit `writeback_value_latched`。现有 `mac_accumulator` 在物理末组启用时由 COMMIT 更新，末组关闭时保持原值，随后都可由统一 WRITEBACK 读取。
- 从 DSP V1 routed checkpoint 定向检查全部 32 个 `mac_accumulator[*]/D` 端点，最差 setup slack 为 `+5.272 ns`、data path delay 为 `4.381 ns`、3 级逻辑；报告 SHA-256 为 `E0725B14C16150406347101814C6CA067359DBF102BFCCB68947256275833D36`。这是候选结构依据，不是修改后 OOC 通过证据。
- V2 预计新增状态由约 64 bit 收敛为四个 signed 8-bit 激活锁存器，共约 32 bit；两个 WRITEBACK 状态仍装入现有 4-bit FSM。准确 LUT/FF 与时序必须等待获批后的 Vivado 实测。
- 每个样本仍固定增加 42 个 WRITEBACK 周期，C1/C2/C3/C4 预计为 `1902/1898/718/1900`。compute testbench 的 9000 拍 watchdog 预计只剩 1122.5 拍余量，批准后应定向调到 9500；精确周期断言不放宽。
- `COMPUTE_COMPLETE` 必须延后到最终 `L1_WRITEBACK && unit==9`，但可直接读取当前稳定 active-mask 的末位保留 `path=COMMIT` / `path=MASK_BYPASS`，无需新增硬件来源状态。
- 当前仍为 `REVIEW_REQUIRED / RTL_CHANGES_BLOCKED`；本轮只冻结实施地图和测试边界，不修改 RTL、测试周期或 OOC 证据。
## 2026-09-05 TR7-TR12 批准后的事实

- TR7：FETCH 锁存四个 signed 8-bit 激活值；EXECUTE 不再从输入/隐藏数组动态选数。
- TR8：四个乘法 lane 的操作数在 EXECUTE 期间来自稳定锁存器，保持当前 signed INT8/INT32 语义。
- TR9：L0/L1 最终数组写入统一后移到 WRITEBACK；复用现有 signed 32-bit `mac_accumulator`，不新增第二个 32-bit 写回寄存器。
- TR10：每个样本新增 32 个隐藏单元和 10 个输出单元的 WRITEBACK，共 42 拍；C1/C2/C3/C4 为 1902/1898/718/1900 拍。
- TR11：综合和实现网表继续要求恰好 4 个 DSP48E1；禁止乘法退回 LUT，也禁止以 DSP 实现求和/写回。
- TR12：先在旧 RTL 上取得独立 V2 合同 RED，再做最小 RTL 修改和功能回归；只有功能门通过后才允许 Vivado OOC。方案 A setup 仍失败时保留报告并重新审核方案 B。

批准解除的是 RTL 实施阻断，不是物理签核。当前尚未证明 V2 资源、时序、功耗或板级吞吐；这些结论必须等待新的 Vivado 2024.1 OOC 报告。

### V2 RED 证据

`test_npu_single_clock_compute.NpuSingleClockComputeTests.test_timing_repair_v2_contract` 在旧 RTL 上返回失败：首个样本完成时没有任何 L0/L1 WRITEBACK，实际为 `l0=0/32、l1=0/10`。结构测试还确认旧 RTL 没有四个 `lane_activation_latched_*`、两个 WRITEBACK 状态，且隐藏层/输出层各有多个直接写点。该 RED 是实施前门，不代表功能缺陷已经修复。
## 2026-09-05 V2 实施与物理签核

- TR7-TR12 已批准并完成实现；V2 在旧 RTL 上的 RED 先行证据、激活锁存/统一 WRITEBACK RTL、C1-C4 周期合同和逐组白盒门均已闭环。
- 定向专项、固定 `20×100=2000` 样本逐 beat 随机协同仿真和完整回归均通过：`475 tests / OK (skipped=1)`。
- V2 周期为 C1=`1902`、C2=`1898`、C3=`718`、C4=`1900` 拍；compute watchdog 调整到 9500，精确周期门未放宽。
- Vivado 2024.1 OOC 绑定 `f744bff2bdde68e138a7b2b348ce103bec1ab469`：`2126 LUT / 1916 FF / 0 BRAM / 4 DSP48E1`，`WNS=+0.060 ns / TNS=0 / WHS=+0.040 ns / THS=0`，setup/hold/route/DRC 零失败。
- V1 的 `5055073` setup 失败路径已降级为历史审计证据，不再代表当前物理状态；当前 manifest 状态为 `VIVADO_OOC_PASS`。
- PR #64 HEAD 与上述实现提交一致，GitHub Actions run `33946568679` 全绿；Webhook 掉线仅记录为通知通道缺失。
- OOC 结论仍不覆盖板级 I/O、DMA、PS、Ethernet、动态功耗和持续学习；下一阶段必须另行完成顶层与板级签核。
- 2026-09-05：P15-T0 审查结论为“方案 A 最小且可归因”：现有 Host Bridge 不能直接承载 32-bit 样本/结果，因此不把样本塞入 128-bit 配置流；新增 FIFO 的资源与时序必须在 T1/T3 单独测量。AXI、DMA、Ethernet、PS7 暂不进入核心。

## 2026-09-06 P15-T0 状态与 webhook 持久性审计

- 在同一开放 PR 中把 HEAD 和 Actions run 写成“当前值”会产生自指漂移：提交该文档后 HEAD/run 必然改变。正确做法是明确写成“审计快照”，绑定当时 SHA 与 run，实时状态始终从 GitHub API 查询。
- PR #68 快照绑定 HEAD `55ec08eb74f68c46a8a65a016242faa3875c239d` 与 run `33976357259`。GitHub annotation 明确 runner 因账户付款/额度问题未启动，状态是 `NOT_RUN_BILLING_BLOCKED`，不是代码失败，也不是通过证据。
- 仓库外 webhook 成功收到同一 SHA 的 `workflow_run completed/failure`，说明 chmlfrp 到本机的事件路径实际可用；`signature_verified=false`，因此只能触发复核，不能取代 GitHub Checks/API。
- `start_webhook.ps1` 使用 `Start-Process` 启动后台 Python 时，在当前任务宿主下子进程会在调用环境结束后被回收。将 Windows 计划任务的 Action 改为直接运行 Python 后，计划任务保持 `Running`，健康检查稳定返回 HTTP 200。
- 仓库外启动/停止脚本已改为优先控制计划任务；未安装计划任务时才退回旧的直接进程路径。该运维修订不进入 ENeuron 仓库。
- 接收器与隧道是两个独立故障域：本机 `127.0.0.1:2355` 正常不代表 GitHub 能到达公网 `23.147.68.16:22682`。本次 GitHub delivery 的 502 与公网 TCP 失败共同定位到 frpc 隧道未运行。
- chmlfrp 恢复后，本地/公网 `/healthz` 均返回 HTTP 200；GitHub 官方 ping delivery `ee543f6e-aa08-11f1-84fd-d4849c4dec76` 的状态为 `OK / 200`，同一 delivery 出现在接收器 `latest.json`，证明 GitHub→公网隧道→本地接收器全链路恢复。
- 诊断期间曾同时存在 ChmlFrpLauncher 与计划任务两个 frpc 实例。最终保留用户 launcher 管理的单实例并停止额外任务实例，公网 health 仍通过，排除了“依赖重复隧道才可用”的可能。
- 恢复后的第二个真实仓库事件再次闭环：`c2523a9` → run `34043377382`，webhook 收到 requested delivery `2e16b130-aa0a-11f1-86ef-dd7a956d4ed9` 和 completed delivery `3201ce10-aa0a-11f1-8238-2c657afd3f1d`；PR 评论 delivery 为 `4be59cd0-aa0a-11f1-88f2-e2e0e3608dc3`。此前 `6ece08a0…` 属于 `a409512`，已纠正映射。因此公网隧道、接收器和 GitHub hook 均可用，唯一未解除的是 Actions 账户计费阻断。
- 2026-09-07：管理员批准 A1-A7，P15-T0 状态更新为 `T0_APPROVED / T1_RTL_AUTHORIZED`；该批准仅开放 T1，不代表双时钟顶层已完成。
- 2026-09-07：资源审计确认单时钟 NPU 基线为 `2126 LUT / 1916 FF / 0 BRAM / 4 DSP`，其中 `1014 LUT` 报告为 LUTRAM；模型配置存储是首要裁剪候选，但不能把 1014 LUT 全部直接归因给某个数组。
- 2026-09-07：最值得做的候选是 C1 固定模型改 ROM/BRAM、C2 推理专用 ENeuron 删除学习状态和提交路径、C3 固定拓扑特化。C6-C9 会破坏延迟学习、事务原子性、跨流协议或定点语义，不能作为普通省资源改动。
- 2026-09-07：管理员决定将全部资源裁剪延后到第一次完整端到端运行成功之后；在此之前不实施 C1-C9，不修改当前训练/推理基线，不把估算收益写成物理实测。
- 2026-09-07：T2 并发 epoch 切片通过。首个样本 8 beat 已进入 FIFO 后，Host 在 NPU 计算期间发布 epoch=2；当前结果仍逐 beat 回显 epoch=1，随后 fence 仍回显 active=1，下一样本结果回显 epoch=2。三组可变时钟 `(7,2)/(9,1)/(4,3)` 均通过；该证据仍不等于 T2 全矩阵或 T3。
- 2026-09-07：T2 时钟覆盖扩展为六组 `(7,2)/(9,1)/(4,3)/(5,0)/(11,4)/(3,1)`；每组继续覆盖并发 epoch、8/10 beat、背压和复位重入。该结果是扩展确定性切片，不等于随机频率/相位全矩阵。
- 2026-09-07：T2 全矩阵需要拆分两类证据。现有 wrapper 测试负责 fence、epoch、8/10 beat 和背压协议；新的独立 FIFO 矩阵负责四种实际宽度/方向下的满空、回绕、长背压和无丢失/重复/乱序。单独测试 Icarus FIFO 模型不能代替真实 AMD XPM/xsim，该边界必须保留到 T3。
- 2026-09-07：T2 FIFO 矩阵 24/24 通过：8 组 `NPU_HALF/NPU_PHASE` × 3 个固定 seed。四条通道分别比对实际写入和读出序列；测试包含填满、排空、随机读写、读端长背压和中途 reset。本地验证命令是 `python -X utf8 tools/repro/verify_repository.py --t2-fifo-matrix`；结果仍不等于真实 XPM/xsim、T3 或板级。
- 2026-09-07：T2 wrapper 交错/复位切片在4组 `(2,0)/(3,1)/(7,2)/(11,4)` 通过。实际并行验证中，mask 命令和 sample beat 交错接受；模型装载中途、结果背压中、sample 第 4 beat 前的 reset 均能清除半事务，未观察旧响应/结果泄漏。该切片仍使用 Icarus 等价 FIFO 模型，不代替 AMD XPM/xsim 和 T3。
- 2026-09-07：T3 无需新增架构裁定。已批准 A7 明确 `xc7z020clg400-1`、Host/NPU 双 100 MHz 和真实 XPM；`npu_zynq7020_t1_wrapper.sv` 已实例化四个 depth-16、FWFT、`SIM_ASSERT_CHK=1`、`CDC_SYNC_STAGES=2` 的 XPM FIFO，宽度为 128/128/64/96 bit。
- 2026-09-07：现有 `vivado_xpm_wrapper_sim.tcl` 面向旧 `digital_snn_host_bridge` 和 `xc7a35t`，不能作为当前 NPU wrapper 的 T3 证据；现有 `vivado_npu_single_clock_ooc.tcl` 只覆盖单时钟核心。T3 应新增独立 runner，不改写这两份历史证据入口。
- 2026-09-07：T3 真实 AMD XPM/xsim 协同仿真通过；XC7Z020 OOC 通过。顶层准确资源为 `2467 LUT / 2301 FF / 6 RAMB36 / 1 RAMB18 / 4 DSP48E1`，Host/NPU WNS/WHS 分别为 `+3.639/+0.105 ns` 与 `+0.214/+0.042 ns`，setup/hold、route、DRC 和 external CDC 均无失败。Actions 已关闭，正式证据必须在提交后重新绑定新 HEAD。
- 2026-09-07：上述 T3 证据已在实现提交 `c2bc03f` 上重新运行并确认 SHA 一致；随后仅提交 Nexus 与计划文档（`439ac6b`），不改变 RTL。故当前物理结论绑定 `c2bc03f`，文档状态提交绑定 `439ac6b`。
- 2026-09-07：`tb_npu_zynq7020_t1_wrapper.sv` 只对白盒 `dut.core.state_clear_count` 有一处层次引用，真实 XPM 不影响该路径，因此可直接复用；xsim 入口必须排除 `xpm_fifo_async_sim.sv`，由 Vivado 项目的 `XPM_LIBRARIES {XPM_FIFO}` 提供真实 FIFO。

## 2026-09-07 T2 固定种子随机矩阵收口

- 固定种子 `20260907` 生成 24 个唯一 `(NPU_HALF,NPU_PHASE)` 组合，半周期范围为 2-17 ns；统一入口返回 `REPRO_G2_T2_RANDOM_MATRIX_PASS`。
- 固定 5000 Host 周期在慢 NPU 组合下不足。观察预算改为 `2000 + 400 × NPU_HALF`，只改变 testbench 等待上限，不改变 DUT、事务顺序或通过判据。
- 恢复审计确认上一轮只有状态汇报，没有改变权威状态；本轮继续完成 Nexus、复验、提交和推送闭环。

## 2026-09-07 HelloZynq B0 实板

- 板厂固定提交同时证明 M19/P20为 HelloZynq PL时钟/LED引脚，B0 XDC使用 LVCMOS33；目标完整 part固定为 `xc7z020clg484-2`。
- 最小 26-bit计数器实现只使用1 LUT、26 FF和1 BUFG，0 BRAM/0 DSP；50 MHz下 P20完整周期为1.34217728秒。
- 干净提交 `367c813...` 的实现 WNS/WHS为 `+17.918/+0.251 ns`，route error 0，DRC Error/Critical Warning为0。唯一 `ZPS7-1` Warning来自刻意不实例化 PS7的 PL-only范围，不能外推到 B1。
- bitstream SHA-256为 `c16a1f8a035c9f5d70677cf71e433b8b19e040ff336d58c85efc89761e85e3d1`。首次下载前 Vivado报告 DONE=0；两次下载后 CONFIG_STATUS明确给出 DONE_INTERNAL=1、DONE_PIN=1，IR给出 ISC_DONE=1。
- 机器证据证明配置链和 FPGA startup成功，但不能单独证明 M19时钟或 P20 LED工作；必须等待用户现场观察和断电复测。

## 2026-09-07 B0 正式重建与阶段 2 TODO 细化

- 当前 B0 源码提交已由 amend 更新为 `f3b8174e8ca30d427e9de3eea2d36feb6a5e6a06`，主要变化是编程脚本把 `DONE_INTERNAL`、`DONE_PIN`、`ISC_DONE` 三项同时为 1 设为硬失败门。
- Vivado 2024.1 对该提交完成正式重建：`B0_BUILD_PASS`，0 Error、0 Critical Warning；资源与时序保持 `1 LUT / 26 FF / 0 BRAM / 0 DSP`、`WNS=+17.918 ns`、`WHS=+0.251 ns`。
- 新构建 manifest 绑定 `f3b8174...`，bitstream SHA-256 为 `df16ed6ccd9124f2dc4391d96e868ebd7846aebf3df335099b742cc7cd318971`。构建时工作树含未提交文档，因此 manifest 的 `git_worktree_clean=false`；源文件哈希和提交身份仍已记录。
- 已完成的两次 JTAG program 绑定旧 bitstream `c16a1f8...e3d1`；新 bitstream `df16ed6c...8971` 尚未 program。按照阶段 2 的单一证据包原则，不能把旧 program 结果直接写成新 bitstream 的通过证据。
- B0 最终闭环必须对 `df16ed6c...8971` 重新执行 JTAG program、三项 DONE 硬门和现场 LED 观察；断电后再次对同一哈希复测。完成前状态保持 pending。
- 阶段 2 TODO 将按 B0～B4 分解为准备条件、实现任务、实板测试、证据产物和停止条件；B1 首轮软件栈仍建议 `bare-metal + lwIP`，但需在 B0 完全通过后由管理员正式裁定。
- 本轮一次读取误把总 TODO 假定在仓库根目录，`D:\Documents\Code\ENeuron-board-b0\TODO.md` 不存在；已确认权威文件为 `docs/planning/TODO.md`，后续不重复错误路径。
- 固定板厂提交中的 PS Ethernet 参考设计确认：该板没有直接引出 PS GEM 的 MIO 网口，而是由 PS GEM 经 EMIO 输出 GMII，再通过 PL 中的 `GMII TO RGMII` IP 连接板载 PHY；因此 B1 不能只配置 PS MIO，必须保留 PL 侧转换、时钟、复位和 RGMII/MDIO约束。
- 板厂参考设计给出的关键配置包括 UART0、16-bit DDR3、PS `FCLK_CLK0=200 MHz` 供 `GMII TO RGMII` 使用；参考 XDC 中 UART TX/RX 为 L17/M17，MDIO MDC/MDIO 为 G21/H22，RGMII位于 Bank 35相关引脚。上述信息只作为 B1 重建输入，正式配置仍需由仓库脚本生成并在实板逐项验收。
- 板载以太网 PHY 资料位于固定板厂仓库的 RTL8211F 数据手册目录；B1 应先通过 MDIO读取 PHY ID和链路状态，再运行 UDP，避免把协议栈或 IP 配置错误误判为物理链路问题。
- 当前传统 NPU RTL 在 `npu_eneuron_single_clock_skeleton.sv` 中明确冻结为 `64→32→10`，模型为 634 个 32-bit word，样本为 8 beat、结果为 10 beat；B3 固定向量和后续图像流测试应直接复用这一形状，避免在实板 bring-up 阶段同时改变网络规模。
- 一次搜索误用了不存在的 `npu_eneuron_single_clock.sv` 路径；真实文件名为 `npu_eneuron_single_clock_skeleton.sv`。错误未修改仓库，已通过 `rg --files` 纠正，后续不重复该路径。
- 证据身份校正后，`artifacts/README.md` 仍把 B0摘要概括为“干净构建和两次 program”，`concept_model.json` 仍使用 `machine_evidence_pass_field_observation_pending`；两处都需改为“当前构建通过、当前 program pending、历史 program单列”，否则入口摘要会再次误导审查者。

## 2026-09-07 B0 当前产物正式 program 执行

- 执行前复核确认工作树 HEAD 为 `f3b8174e8ca30d427e9de3eea2d36feb6a5e6a06`，本地 bitstream SHA-256 与 manifest 一致，均为 `df16ed6ccd9124f2dc4391d96e868ebd7846aebf3df335099b742cc7cd318971`。
- `run_b0_program.ps1` 在启动 Vivado前强制比对 bitstream和manifest哈希；Tcl只接受单一硬件target和单一XC7Z020器件，并在program后检查 `PROGRAM.FILE` 与请求路径一致。
- 编程成功的硬门是 `DONE_INTERNAL=1`、`DONE_PIN=1`、`ISC_DONE=1` 三项同时成立；脚本还输出 UTC时间、目标、器件、前后配置状态和相关硬件属性，可直接进入正式证据摘要。
- 当前 bitstream `df16ed6c...8971` 的正式 program 已于 `2026-09-07T10:22:56Z` 完成，脚本和Vivado均返回PASS；三项DONE为 `1/1/1`，CRC、IDCODE、security error均为0。
- 原始 `program_run.log` SHA-256为 `0152fe3258cefb16f6e7efd3b12058e5da6cd352c8416f3d12a290e21d6ea49e`。当前剩余证据仅是用户观察P20和断电后对同一bitstream复测。
- 远端刷新后 `origin/main=7857d325...`，当前B0分支相对主线为 `1 ahead / 2 behind`，merge-base仍是批准基线 `e2a1bfa...`。由于正式构建和program证据绑定源码提交 `f3b8174...`，不能用rebase/cherry-pick改写该提交；证据提交后应将 `origin/main` 合入当前分支，保留硬件证据身份。
- Nexus子任务已按当前实板证据更新七个 `.nexus-map` 文件，并正确保留现场观察/断电复测pending。主代理复核发现 `concept_model.json` 的 `current_main_head` 与 `latest_merge` 仍停在PR #68合并前状态，已校正为 `7857d325...`；其余B0 build/program字段与原始日志一致。
- PR #69首次GitHub审计快照为 base `main@7857d325...`、HEAD `8db816d...`、`OPEN / CLEAN / MERGEABLE`、空checks。因为Actions已关闭，空checks只能解释为未运行；Nexus已将该HEAD明确限定为固定快照，后续提交不会使历史描述失真。

## 2026-09-07 阶段 2 TODO 详细化复核

- B0 当前脚本使用固定工作文件名，第二次 program 会覆盖第一次的 `program_result.txt` 与 `program_run.log`；因此正式流程必须在断电前先把 run-1 复制到独立证据目录并计算哈希。未固化原始文件就继续 run-2，会破坏“两次独立运行”的可审查性。
- 板厂资料与当前 XDC 的映射一致：FPGA P20 对应板上 `PL_LED1`。现场任务必须同时写板上丝印和 FPGA引脚，避免观察相邻 `PL_LED2/P21`。
- B3 原清单把合法 mixed mask 与自动剪枝放在同一层，存在把 Host预制 mask误报为 ENeuron自动决策的风险。现拆成 dense、full-open、Host静态 `2:4`、live-ENeuron四级隔离验证。
- B4 的性能比较只有在同一 bitstream、ELF、模型、样本顺序、网络和计时定义下才成立；局部 NPU周期下降不自动等于网口端到端吞吐提升，必须同时保存分段计数。
- 本轮只修改规划与工作记录；没有运行 JTAG、Vivado或实板测试，没有改变 RTL、bitstream、B0机器证据和三个保护文件。
- 当前 `run_b0_program.ps1` 的固定输出已在任何第二次下载之前固化为 run-1；归档目录保存 result、transcript、build manifest和archive manifest。归档脚本拒绝覆盖已有运行目录，并复核 bitstream哈希与两个 PASS marker。
- run-1 归档时仓库存在未提交规划与脚本改动，因此 archive manifest如实记录 `archive_git_head=73859b1`、`archive_worktree_clean=false`；build manifest仍绑定实际生成 bitstream的 `f3b8174...`，两种身份不能混为一个干净构建声明。
- 一次文件搜索在 Windows 上直接向 `rg` 传入 `test_*.py` 路径通配符，返回路径语法错误；未修改仓库，后续改用明确目录和 `-g '*.py'` 过滤，不重复该调用方式。
- `ffc6f11` 推送后，PR #69 的 GitHub权威状态为 `OPEN / CLEAN / MERGEABLE`，head精确为 `ffc6f1134e5218cce63aa7c988313fbdbc4d352b`，`statusCheckRollup=[]`。Actions仍关闭，因此没有远端测试证据；14项定向检查、归档哈希和脚本语法均为本地证据。

## 2026-09-07 B0 首次现场观察周期口径诊断

- 用户确认 LED稳定闪烁，但定性报告“周期短得多”。该证据证明P20附近存在稳定可见活动，但尚不足以证明完整周期符合设计。
- 当前 RTL明确为 `counter[25]`，因此50 MHz下每0.67108864秒改变一次亮灭状态，完整同相周期为1.34217728秒。若用户把相邻亮灭变化称作周期，观感约短一半是预期行为。
- 当前仓库XDC、用户本地引脚速查和两个独立板级示例均使用M19作为50 MHz输入、P20作为LED输出；这降低了映射错误概率，但不能替代对实际板卡丝印和周期的定量观测。
- 在用户给出10秒完整周期数或亮/灭持续时间前，状态保持 `PERIOD_QUANTIFICATION_PENDING`；不提前执行断电run-2，也不直接把定性描述升级为时钟故障。
- 用户进一步澄清所指是完整周期目测约1秒，而非0.671秒翻转间隔。若1.000秒准确，等效输入频率约67.109 MHz，与50 MHz资料不符；但当前只是单周期目测，必须用10周期总时长复核后才能采用该推断。
- 为避免看到测量结果后调整验收线，10周期人工秒表门预先冻结为12.6～14.2秒，理论中心13.4217728秒；窗外先诊断，不直接继续冷启动run-2。
- 首次尝试把多行 PR正文直接作为 `gh pr edit --body` 参数时，PowerShell将正文拆成选项并返回 `unknown shorthand flag`；远端正文未改变。改用管道传给 `--body-file -` 后成功，后续多行正文统一使用标准输入。
- 10个完整周期实测13.42秒，理论13.4217728秒，绝对误差-0.0017728秒、相对误差约-0.0132%，通过预先冻结的12.6～14.2秒门。长窗口结果推翻了“完整周期约1秒”的粗略目测疑点，无需为该疑点启动时钟诊断设计。
- 本轮开始时工作树出现未跟踪的B0时钟诊断RTL/XDC/Tcl/PowerShell文件及相关README修改；它们不是本轮生成，也不再是当前通过门所需。全部保留、不修改、不暂存，避免覆盖未知来源工作。
- 完整断电检查必须区分“调试线缆还在”与“FPGA仍可访问”。本次精确Digilent target仍能枚举，但`open_hw_target`明确报告 `No devices detected`，accessible device count=0；结合用户确认供电指示熄灭，构成比单纯找不到线缆更强的断电证据。
- 新增只读 `probe_b0_power_off.tcl` 与 `run_b0_power_off_probe.ps1`，固定target、拒绝覆盖既有证据目录，并要求线缆target恰好1个、可访问器件0个和PASS marker。正式运行时间为 `2026-09-07T15:02:49Z`，transcript SHA-256为 `3a953999...1f634`。
- 2026-09-07：HelloZynq B0-GATE 已形成完整实板闭环。固定源码 `f3b8174...` 与 bitstream `df16ed6c...8971` 在同一 Digilent target/`xc7z020_1` 上完成 run-1，随后由 JTAG不可访问和 `No devices detected` 证明完整断电；重新上电时器件为未配置状态，再次下载同一文件后 run-2 三项 DONE=`1/1/1`、错误位为0。两次10周期分别为 `13.42 s`、`13.4 s`，均通过预冻结 `12.6～14.2 s` 窗口。该证据只关闭 PL配置、M19时钟和P20路径，不外推到PS/DDR/网口/NPU/ENeuron。
- 2026-09-07：阶段2的主要延迟来自重复收口而非硬件执行：同一身份反复跑Vivado、每个观察点都更新多份状态文件、等待已关闭Actions的空checks都不增加证据强度。Fastlane V1保留最终硬门，但按输入身份缓存物理证据、按变更运行定向门、把B1拆为A/B/C小PR，并在阶段末统一收口，可显著缩短进入主线的时间。
- 2026-09-07：B1A与B1-D1可以解耦。PS7/DDR/UART/GEM/PHY的板级事实和可重建硬件定义对bare-metal与Linux相同，可以先审计；只有BSP、启动代码和lwIP/Linux驱动实现必须等待软件栈裁定。
- 2026-09-07：`D:\Desktop\Note\Zynq7020` 目前可见内容为Obsidian笔记、模块和速查，没有在三层目录内发现Git仓库。板厂固定克隆位置尚需定位，不能用网页记忆或未绑定版本的文件替代固定提交证据。
- 2026-09-07：`D:\Documents\Code\Zynq7020` 不是 `LXB-ZYNQ` 克隆：没有 `.git`，内容为 `1_LED`、`LED_float`、`Advanced_Timer`、`Key_read` 等本地Vivado工程。它可作为用户实验资料，但不能作为板厂固定提交的权威源。
- 2026-09-07：已定位两个板厂克隆：`C:\Users\Epsilon\AppData\Local\Temp\LXB-ZYNQ-codex-20260907` 与 `C:\Users\Epsilon\_tmp\LXB-ZYNQ`。两者remote均为 `https://gitee.com/GLSZ/LXB-ZYNQ.git`，工作树干净且HEAD为 `73d529d8f159ca372b7d9855eddc80880ecd9d05`。B1A采用后者作为稳定只读来源；前者是临时副本，不作为文档路径。
- 2026-09-07：固定提交中 `12_ZYNQ_Code/12_ZYNQ-7000-PS_Code/HelloZynqPS_ETH/` 是B1A最集中参考：含 `design_1.bd`、processing_system7生成配置和以太网工程；`05_HelloZynqPS/04_HelloZynqPS_Linux_ETH/HelloZynqPS_Linux_ETH.md` 解释GEM0经EMIO输出GMII、`GMII TO RGMII`转换、FCLK_CLK0=200 MHz、低有效PS复位需反相，并列出RGMII/MDIO XDC。
- 2026-09-07：初步引脚证据：MDC=G21、MDIO=H22；RGMII RXD[0..3]=A22/A18/A19/B20、RX_CTL=A21、RXC=B19、TXD[0..3]=E21/F21/F22/G20、TX_CTL=G22、TXC=D21，文档将这些PL侧端口设为LVCMOS33并为RXC创建8 ns时钟。仍需从实际XDC/BD复核，不能只依赖教程正文。
- 2026-09-07：已从固定提交的实际源 XDC `project_1.srcs/constrs_1/new/HelloZynq_Linux_ETH.xdc` 复核上述以太网引脚；同时确认 UART0 PL 侧引脚为 TX=L17、RX=M17，均为 LVCMOS33，RGMII RXC 约束为 8 ns。后续只读取源 BD、源 XDC 和导入 wrapper，不再扫描 `.gen/.runs/ip_user_files`。
- 2026-09-07：固定提交的源 BD 直接确认 `processing_system7:5.5`、`gmii_to_rgmii:4.1` 与 `util_vector_logic:2.0` 三个实例；GEM0 的 GMII/MDIO 接入转换器，FCLK_CLK0 接 `clkin`，FCLK_RESET0_N 经逻辑反相后同时接收发复位。源 wrapper 确认 32-bit DDR 数据总线、UART0、MDIO 与完整 RGMII 顶层端口。
- 2026-09-07：六个旧 PR5/PR6 detached 审查工作树均为干净状态，合计约 109 MB；重复临时板厂克隆同样干净，约 1.76 GB。它们不再承担权威输入，稳定板厂克隆 `C:\Users\Epsilon\_tmp\LXB-ZYNQ` 保留。
- 2026-09-07：B1A来源审计发现两个直接阻塞硬件定义的冲突：板卡资料/原理图为 `MT41K256M16`，参考PS7配置为 `MT41J256M16 RE-125`；PS Ethernet参考工程只复位GMII-to-RGMII IP，没有引出H17物理PHY reset。另有物理PHY地址和RGMII板级时序未冻结。当前只能标记 `B1A_SOURCE_AUDIT_COMPLETE`，不得标记B1A或B1通过。
