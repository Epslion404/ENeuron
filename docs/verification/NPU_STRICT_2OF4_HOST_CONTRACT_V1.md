# NPU 严格连接级 2:4 Host 合同

日期：2026-09-12

## 范围

本合同只定义严格连接级 `2:4` 候选在 Host 侧的编码、解码和合法性检查。它不修改当前 `xc7z020clg484-2` 板端协议、RTL、bitstream 或 mask 命令格式，也不构成实板门通过证据。

## 当前板端边界

- 当前 packet-NPU 使用 `19` 个 32-bit mask word，共 `592` 个组。
- 每个现有 mask bit 控制一个四权重组，粒度是 `group_4way`。
- 因此现有 19-word 格式不能表达每组四条连接中具体保留哪两条。
- 严格 lane-level `2:4` 需要每组一个 4-bit mask；`592 × 4 = 2368` bit，即 `74` 个 32-bit word。

## 编码规则

- 组顺序保持现有 `L0: 512` 组、`L1: 80` 组，共 `592` 组。
- 每组使用一个 4-bit lane mask，按 LSB-first 连续打包到 74 个 32-bit word。
- 合法值必须恰好有两位为 1，即：`0011`、`0101`、`0110`、`1001`、`1010`、`1100`。
- 非法 mask、错误组数、错误 word 数和超出 unsigned 32-bit 范围的 word 必须拒绝。

## 已完成验证

`strict_2of4_mask.py` 提供 `encode_lane_masks`、`decode_lane_masks`、`validate_lane_mask` 和 `active_lane_count`；`test_strict_2of4_mask.py` 已覆盖六种合法值 round-trip、长度检查、非法值拒绝和跨 word 边界的非法组检查，当前结果为 `3 passed`。

## 未完成事项

仍需新增协议版本或新 opcode，并同步 RTL、Vivado、软件 runner、周期计数和实板证据，才能关闭 `B3-08b`。在此之前，任何使用现有 19-word packet 的结果都只能标记为 `group_4way`，不能称为严格连接级 `2:4`。
