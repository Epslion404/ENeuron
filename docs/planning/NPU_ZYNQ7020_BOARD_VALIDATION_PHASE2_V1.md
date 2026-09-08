# XC7Z020 实板验证阶段 2 规划 V1

状态：`ACTIVE / FASTLANE_V1 / B0_COMPLETE / B1A_HW_DEFINITION_COMPLETE / B1B_PENDING / B1_DECISION_PENDING`

日期：2026-09-07

## 目标和证据原则

在 HelloZynq `xc7z020clg484-2` 上依次打通 PL、PS/DDR/网口、DMA、NPU + ENeuron 和端到端 A/B。纯仿真和 OOC 继续用于开发与定位，但不能单独关闭阶段 2 任务。

每次正式实板运行必须绑定 Git commit、Vivado版本、完整 part、RTL/XDC/脚本哈希、bitstream SHA-256、JTAG设备、输入、机器输出和现场观测。不同 bitstream 或源码的证据不得拼成同一次通过。

板厂参考仓库固定为 `master@73d529d8f159ca372b7d9855eddc80880ecd9d05`，本地克隆已获授权保留。PR #69 已合并为 `main@102dee2a004283ce4144aaf6ee0a2cee3ebd2887`，B0 已关闭。

B1A来源审计及可重建硬件定义均已完成。原始硬件定义在提交`18fd65c`通过；管理员随后将UART重分配为`V14=TX`、`V15=RX`，当前有效硬件身份绑定提交`f0dbc84`。Vivado 2024.1已重新生成bitstream/XSA，setup/hold/route/DRC硬门和RGMII TX顶层output delay门通过。B1A完成只表示硬件定义进入主线候选；UART、DDR读写、PHY、链路和UDP仍须B1B/B1C实板验证，`B1-GATE`保持未通过。

## Fastlane V1：更快进入主线

- 最终硬门不变，但允许安全、可复现、默认不影响现有路径的阶段切片先通过小 PR 进入主线；合并切片不等于对应 B1～B4 阶段通过。
- B1 拆为三段：B1A 板级事实与可重建硬件定义，B1B PS7/UART/DDR，B1C PHY/UDP。每段独立提交、验证和合并，避免整阶段互相等待。
- 只运行受改动影响的最小验证集。文档/JSON只跑解析、状态一致性和 `git diff --check`；软件修改不重建未变化的 PL；RTL/XDC/BD/Tcl 身份未变化时复用已有 bitstream/XSA哈希，不重复跑 Vivado。
- 同一失败不重复全量验证。先固定首错并运行最小复现，修复后重跑受影响切片；只在阶段最终门或共享合同变化时扩大回归。
- 实板操作按一次连接会话批量执行：身份确认、下载、UART、DDR、MDIO和UDP依赖顺序不变，但不在每个中间文档提交后重新上电或重新下载。
- 报告、Nexus和历史摘要在每段合并前同步一次；运行中的细节写入机器日志，不为每个观察点单独创建状态提交。
- GitHub Actions关闭期间不等待空checks或webhook；本机定向验证通过、PR为CLEAN/MERGEABLE且证据边界正确即可合并。Actions恢复后再按变更分类运行对应门。

## B0：PL 配置、50 MHz 时钟和 LED

冻结设计为 M19 50 MHz→26-bit自由计数器→P20，不实例化 PS7、DDR、Ethernet、ILA 或 NPU。

详细逐项 TODO 见 `docs/planning/TODO.md` 的 P16。本文件冻结阶段边界与通过原则。

通过条件：

- 完整实现目标为 `xc7z020clg484-2`，setup/hold、route和 DRC Error/Critical Warning 全部通过。
- bitstream 与干净 commit、源文件哈希一一绑定。
- 当前正式候选 bitstream至少在上电和断电重启后各完成一次 JTAG program，并且每次 `DONE_INTERNAL=1`、`DONE_PIN=1`、`ISC_DONE=1`。
- 用户现场观察至少 10 个完整 LED周期，节奏约 1.34 秒/周期。
- 断电重启后重新连接、下载同一 bitstream 并再次观察通过。

当前源码提交为 `f3b8174...`，正式 bitstream为 `df16ed6c...8971`。完整断电前后两次program、三项DONE、错误位和两次10周期现场测量全部通过，B0状态为 `B0_COMPLETE`。

## B1：PS7、DDR、UART 和 PHY

- 从固定板厂提交提取可重建的 PS7/DDR/EMIO配置，消除绝对路径依赖。板载网口实际为 PS GEM经 EMIO输出 GMII、PL侧 `GMII TO RGMII` 后连接 PHY，不能按纯 MIO网口处理。
- 来源审计与软件栈裁定并行。先按实际 `MT41K256M16` 重新冻结 DDR 参数，增加 H17 物理 PHY reset，并解决 PHY地址和RGMII时序，再生成仓库内独立硬件定义。
- B0 通过后裁定首轮使用 bare-metal + lwIP 或 Linux；推荐先用 bare-metal + lwIP 减少变量。
- 依次验证 UART启动、DDR读写、PHY reset/MDIO ID、链路协商、网线重插和最小 UDP 收发。
- B1 只证明板级基础设施，不声明 NPU 已接入。

## B2：AXI DMA 和流协议

- 冻结 DMA模式、缓存策略、对齐、帧长、中断/轮询和超时合同。
- 先做真实 DMA回环，再接现有 128-bit命令/响应、8-beat样本、10-beat结果接口。
- 覆盖背压、TLAST错误、长度错误、缓冲区回绕、丢失、重复、乱序和恢复。
- 用硬件周期计数器和 Host日志同时记录，B2 通过前不报告剪枝性能。

## B3：传统 NPU + ENeuron 固定向量

- 在同一 bitstream 上加载冻结模型与样本，分别运行 dense、全开、全关和 mixed mask。
- 保存全部结果 beat、sample ID、mask epoch、错误响应、硬件周期、执行组和跳过组。
- 逐样本对照冻结期望，验证 pending mask 只在 fence/样本边界原子生效。
- 板上失败必须保留原始输入输出，不能用仿真 PASS 覆盖。

## B4：网口端到端 A/B

- 冻结带 sequence/sample ID、model ID、mask epoch和错误码的应用协议。
- 在同一 bitstream、模型、输入、频率和软件下比较 dense/bypass 与 gated。
- 实测吞吐、p50/p95/p99延迟、丢包、结果一致性、硬件周期、有效组和跳过组。
- 功耗只有在外部仪器、测点和采样方法冻结后才报告；Vivado估算不能代替实测。
- 首次完整 A/B 跑通后才重新审查资源裁剪候选。
