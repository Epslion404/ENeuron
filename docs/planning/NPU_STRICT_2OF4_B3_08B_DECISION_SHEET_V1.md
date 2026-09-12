# B3-08b 严格连接级 2:4 实施裁定 V1

日期：2026-09-13
状态：`PROPOSED / DEFERRED_STRUCTURAL / NOT_DAILY_MAINLINE / RTL_NOT_AUTHORIZED`

日常主线已改为 `B3-SPEED-GATE`/`B3-POWER-GATE`。本合同只冻结 B3-08b 若恢复实施时的语义。它不关闭任何实板门，也不再作为加速硬门。

## 已由源码冻结的事实

- 板端仍是 19-word `group_4way`：`MASK_WORD_COUNT=19`，`mask_staging[0:18]`，`mask_word_index[4:0]`。
- 一位关掉整个四权重组。FETCH 按 `scan[0]` 整组 skip；EXECUTE 四 DSP 同拍。
- 外层 packet 没有 mask type；mask 是一条条 `COMMAND` 帧里的 opcode `0x4/0x5/0x6`。
- Host 编码已存在：`strict_2of4_mask.py`，74 word，合法 nibble `0011/0101/0110/1001/1010/1100`。
- 19-word 路径必须保留，否则 B3-MVP 证据全部失效。

## 裁定

1. **opcode**：保留 `0x4/0x5/0x6/0x7` 为 19-word `group_4way`。新增 `0xB LANE_MASK_BEGIN`；`DATA/COMMIT/ABORT` 复用 `0x5/0x6/0x7`，由 BEGIN 选择 19 或 74 的完成条件。不要改 B2 `VERSION=1`（ingress 会直接拒）。
2. **执行**：74-word 合法 2:4 仍按组 FETCH 32-bit 权重 word。禁用 lane 的 activation/weight 置 0，四 DSP 仍同拍。`execute_group_count` 继续表示「读了该组 word」。预期 `execute=592, skip=0`，`last_compute_cycles ≈ dense 2494`。周期下降不是 08b 硬门。
3. **计数**：不把 `skip_group_count` 改成 lane 数。若需要 1184/1184，另加 lane 计数器，且不得挤占状态块 `0x00–0x4C`。
4. **非法 nibble**：Host 发送前 `decode_lane_masks` 拒绝；core 在 DATA 或 COMMIT 硬拒，不 published。Packet 层不解释 nibble。
5. **验收顺序**：Python oracle 数值 → Icarus 装载/执行切片 → 单独授权后再 Vivado 200 MHz → COM15 Host 静态重放。live 严格 2:4 是 B3-10。
6. **B3-05**：能力/身份寄存器放 `0x64+`，可与 08b 同一次 bitstream，但不挡 oracle 切片。

## 明确禁止

- 用 19-word 或 `0x33333333` 勾 B3-08b。
- 把 888 cycle 组级差值写成连接级 2:4 加速或功耗。
- 未过 `WNS>=0/TNS=0` 的 bit 上板。
- 勾 B3-01/05/08b/STRICT，或任何 B2-GATE / B4 项。
