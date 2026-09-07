# P16 项目阶段 2：实板验证路线

verified_at: 2026-09-07

authoritative_sources: `docs/planning/TODO.md`、`task_plan.md`、`findings.md`、`progress.md`

## 目标与当前入口

P16 的目标是在 HelloZynq `xc7z020clg484-2` 上依次打通 PL、PS/DDR/网口、DMA、`64→32→10` 传统 NPU、ENeuron 局部门控和网口端到端 A/B。阶段门只由同一身份链上的实板证据关闭；仿真和 OOC 可用于定位，但不能代替 bitstream、JTAG、UART、Host/网口日志与现场观察。

P16-B0 已完成。当前源码 `f3b8174e8ca30d427e9de3eea2d36feb6a5e6a06`、bitstream `df16ed6ccd9124f2dc4391d96e868ebd7846aebf3df335099b742cc7cd318971` 在同一target/device上完成两次正式program和现场观察；10个完整周期分别实测 `13.42 s`、`13.4 s`，均通过理论 `13.4217728 s` 与冻结窗口 `12.6–14.2 s`。

用户随后确认板卡完全断电。`2026-09-07T15:02:49Z` 的正式只读探针精确匹配 target `localhost:3121/xilinx_tcf/Digilent/210251A08870` 1 个，但 `target_opened=0`、`accessible_device_count=0`，Vivado transcript 明确报告 `No devices detected`。证据位于 `artifacts/logs/hellozynq_b0/20260907T150221Z_df16ed6c_power_off/`，结果 SHA-256 为 `fe594c87...3776e`，transcript SHA-256 为 `3a953999...1f634`，完整断电确认 PASS。

重新上电后只读探针确认同一Digilent target上的唯一 `xc7z020_1` 恢复且下载前未配置；run-2于 `2026-09-07T15:26:56Z` 下载同一bitstream，三项DONE=`1/1/1`、错误位为0，现场10周期 `13.4 s`。PR #69已合并为 `main@102dee2...`，Fastlane V1已进入 `main@308bdec...`。当前状态为 `B0_COMPLETE / B1A_SOURCE_AUDIT_COMPLETE / B1_DECISION_PENDING / FASTLANE_V1`。

B1A来源审计固定在板厂 `73d529d8...`，确认GEM0/MDIO/UART0经EMIO、FCLK0=200 MHz和PL引脚，同时发现四项未决事实：板上 `MT41K256M16` 与参考PS7配置 `MT41J256M16 RE-125` 不一致、H17物理PHY复位未引出、物理PHY地址未确认、RGMII板级input/output delay未冻结。详见 `docs/planning/HELLOZYNQ_B1A_SOURCE_AUDIT_V1.md` 和 `.nexus-map/concepts/board_phase2_b1a.json`；当前不得声明B1A或B1通过。

run-1 机器归档由 `boards/hellozynq/b0_smoke/archive_b0_program_run.ps1` 生成。归档 manifest 绑定当前 bitstream `df16ed6c...8971`、program log SHA-256 `0152fe32...a49e`。`field_observation.json` 已更新为稳定闪烁、10周期 `13.42 s` 与 `status=PASS`，当前 SHA-256 为 `d93bcc25...ab083`。run-1已形成机器与现场闭环。

run-2归档位于 `artifacts/logs/hellozynq_b0/20260907T152656Z_df16ed6c_run2_machine/`，program log与现场观察SHA-256分别为 `1d4fada3...3613b`、`73c81d86...a25f8`，`observation_status=PASS`。双运行和完整断电证据已进入最终B0摘要。

## B1–B4 串行门

最终阶段门仍按B1→B2→B3→B4串行；实现进入主线采用Fastlane V1。B1拆为B1A板级事实/可重建硬件定义、B1B PS7/UART/DDR、B1C PHY/UDP，每段定向验证后即可合并，但只有B1C最终摘要满足全部条件才标记B1-GATE通过。相同RTL/XDC/BD/Tcl/IP身份不重复跑Vivado，软件和文档修改只跑受影响门。

- **B1：PS7、DDR、UART、PHY、最小 UDP。** 入口只接受主线上的 `B0-GATE=PASS`。先冻结 PS7/DDR/引脚和启动合同，再以 UART 冷启动、DDR 零错误、PHY/千兆链路、三档 UDP 和拔插恢复关闭本门；B1 不表示 NPU 已接入。
- **B2：AXI DMA 与固定帧协议。** 入口只接受 `B1-GATE=PASS`。先以 AXI DMA simple mode + polling、PL loopback 和明确的 DDR/cache 所有权打通真实双向搬运，再实现 packetizer/depacketizer、TLAST/错误/复位和四流 fence 计数；通过前不报告剪枝加速。
- **B3：传统 NPU + ENeuron 固定向量。** 入口只接受 `B2-GATE=PASS`。保持 `64→32→10`、634 model words、8-beat sample、10-beat result 和四 DSP 合同，依次验证 dense、full-open、Host 静态 `2:4`、live-ENeuron，并覆盖 epoch 原子性、背压与复位恢复。
- **B4：网口端到端 A/B。** 入口只接受 `B3-GATE=PASS`。固定同一 bitstream、ELF、模型、样本、时钟和网络条件，对四种模式执行可重复 A/B；正确性先于性能，端到端结果必须拆分网口、软件、DMA、排队和 NPU 计算开销。没有合格外部测量链时写 `POWER_NOT_MEASURED`。

只有 B4 的同一完整证据包证明“网口输入 → PS/DDR → DMA → 传统 NPU + ENeuron → 网口输出”并完成正确性和可重复 A/B，阶段 2 才能标记完成。

## 静态 mask 与 live-ENeuron 的事实边界

- `Host static 2:4 mask`：Host 重放预先冻结的合法 mask，用于隔离验证 NPU 门控执行器、位序、epoch 和跳过计数。它不是神经元自动决策。
- `live-ENeuron`：实板运行中由 ENeuron 证据形成组内候选和严格 `2:4` mask，经 pending bank 与 fence 原子提交，并能绑定决策证据、gain、epoch 和生效样本。只有该路径通过，才可声称“神经元参与局部自动剪枝”。
- B3、B4 的正确性、周期、执行/跳过组和性能统计必须将两种模式分开，不得合并或互相代证。

## 发布状态

PR #69最终HEAD `02514b5...` 已于 `2026-09-07T16:17:15Z` 合并，merge commit为 `102dee2...`。Actions已关闭，空 `statusCheckRollup`只表示未运行；B0合并依据是本机定向验证、Vivado/JTAG/现场证据及PR CLEAN/MERGEABLE。B1从该main提交启动。
