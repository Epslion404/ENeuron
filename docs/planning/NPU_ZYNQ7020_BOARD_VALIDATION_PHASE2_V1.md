# XC7Z020 实板验证阶段 2 规划 V1

状态：`ACTIVE / BOARD_EVIDENCE_REQUIRED / B0_CURRENT_PROGRAM_PASS / LED_AND_POWER_CYCLE_PENDING`

日期：2026-09-07

## 目标和证据原则

在 HelloZynq `xc7z020clg484-2` 上依次打通 PL、PS/DDR/网口、DMA、NPU + ENeuron 和端到端 A/B。纯仿真和 OOC 继续用于开发与定位，但不能单独关闭阶段 2 任务。

每次正式实板运行必须绑定 Git commit、Vivado版本、完整 part、RTL/XDC/脚本哈希、bitstream SHA-256、JTAG设备、输入、机器输出和现场观测。不同 bitstream 或源码的证据不得拼成同一次通过。

板厂参考仓库固定为 `master@73d529d8f159ca372b7d9855eddc80880ecd9d05`，本地克隆已获授权保留。PR #68 已合并为 `main@7857d32561cbd5f86d02b1a21ee0edfb3ae895f1`；B0 隔离分支从批准的精确 HEAD `e2a1bfa...` 建立。

## B0：PL 配置、50 MHz 时钟和 LED

冻结设计为 M19 50 MHz→26-bit自由计数器→P20，不实例化 PS7、DDR、Ethernet、ILA 或 NPU。

详细逐项 TODO 见 `docs/planning/TODO.md` 的 P16。本文件冻结阶段边界与通过原则。

通过条件：

- 完整实现目标为 `xc7z020clg484-2`，setup/hold、route和 DRC Error/Critical Warning 全部通过。
- bitstream 与干净 commit、源文件哈希一一绑定。
- 当前正式候选 bitstream至少在上电和断电重启后各完成一次 JTAG program，并且每次 `DONE_INTERNAL=1`、`DONE_PIN=1`、`ISC_DONE=1`。
- 用户现场观察至少 10 个完整 LED周期，节奏约 1.34 秒/周期。
- 断电重启后重新连接、下载同一 bitstream 并再次观察通过。

当前源码提交为 `f3b8174...`，正式重建 bitstream为 `df16ed6c...8971`，实现硬门已通过；该当前产物已于 `2026-09-07T10:22:56Z` 正式 program，三项 DONE为 `1/1/1`，CRC/IDCODE/security error为0。现场观察与断电复测仍未完成，因此 B0 不是最终 PASS。

## B1：PS7、DDR、UART 和 PHY

- 从固定板厂提交提取可重建的 PS7/DDR/EMIO配置，消除绝对路径依赖。板载网口实际为 PS GEM经 EMIO输出 GMII、PL侧 `GMII TO RGMII` 后连接 PHY，不能按纯 MIO网口处理。
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
