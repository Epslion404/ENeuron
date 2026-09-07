# P16 项目阶段 2：实板验证路线

verified_at: 2026-09-07

authoritative_sources: `docs/planning/TODO.md`、`task_plan.md`、`findings.md`、`progress.md`

## 目标与当前入口

P16 的目标是在 HelloZynq `xc7z020clg484-2` 上依次打通 PL、PS/DDR/网口、DMA、`64→32→10` 传统 NPU、ENeuron 局部门控和网口端到端 A/B。阶段门只由同一身份链上的实板证据关闭；仿真和 OOC 可用于定位，但不能代替 bitstream、JTAG、UART、Host/网口日志与现场观察。

当前执行点仍在 P16-B0。当前源码 `f3b8174e8ca30d427e9de3eea2d36feb6a5e6a06`、bitstream `df16ed6ccd9124f2dc4391d96e868ebd7846aebf3df335099b742cc7cd318971` 的第一次正式 program 已通过。用户已确认 `PL_LED1/P20` 稳定闪烁，10 个完整周期实测 `13.42 s`，通过理论 `13.4217728 s` 与冻结窗口 `12.6–14.2 s`。run-1 机器与现场证据已闭环。

用户随后确认板卡完全断电。`2026-09-07T15:02:49Z` 的正式只读探针精确匹配 target `localhost:3121/xilinx_tcf/Digilent/210251A08870` 1 个，但 `target_opened=0`、`accessible_device_count=0`，Vivado transcript 明确报告 `No devices detected`。证据位于 `artifacts/logs/hellozynq_b0/20260907T150221Z_df16ed6c_power_off/`，结果 SHA-256 为 `fe594c87...3776e`，transcript SHA-256 为 `3a953999...1f634`，完整断电确认 PASS。

因此状态为 `B0_RUN1_FIELD_PASS / COMPLETE_POWER_OFF_PASS / RUN2_PENDING`；`B0-GATE` 未通过，下一步是重新上电并执行同一 bitstream 的第二次正式 program、`PL_LED1/P20` 观察和 run-2 归档，B1 不得启动。

run-1 机器归档由 `boards/hellozynq/b0_smoke/archive_b0_program_run.ps1` 生成。归档 manifest 绑定当前 bitstream `df16ed6c...8971`、program log SHA-256 `0152fe32...a49e`。`field_observation.json` 已更新为稳定闪烁、10周期 `13.42 s` 与 `status=PASS`，当前 SHA-256 为 `d93bcc25...ab083`。run-1已形成机器与现场闭环。

## B1–B4 串行门

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

PR #69 尚未合并。固定 base 为 `main@7857d32561cbd5f86d02b1a21ee0edfb3ae895f1`；run-1证据提交为 `ffc6f1134e5218cce63aa7c988313fbdbc4d352b`，推送后观测状态为 `OPEN / CLEAN / MERGEABLE`。较早的 `8db816d...` 继续作为历史审计快照。Actions 已关闭，空 `statusCheckRollup` 只表示未运行，不是通过证据。run-2 和 B0-GATE 完成前保持暂不合并。
