# B3-MVP 2026-09-12 实板证据

同一 `xc7z020clg484-2` / 200 MHz bitstream（RTL 身份 `be84596`）上关闭 B3-04、B3-11 板级 epoch 读回、B3-13/B3-14。

## 物理门

- WNS=+0.045 ns，TNS=0，WHS=+0.036 ns，THS=0
- setup/hold failing endpoints=0，route errors=0，DRC hard errors=0
- DSP48E1=4
- bit SHA-256=`0ecbe76274c39418f2a60a88358d3ff6f09f5a2ed73a44a3a419c34eb91d3a11`
- XSA SHA-256=`135d979d61c629922ee5419e51dd97ef045d9bab79930432816d09f109291d1a`
- UART：CH340 `VID_1A86:PID_7523`，COM15

## B3-11 epoch

`overlap_1_20260912T150551Z` MASK_COMMIT 后、下一样本前：

- `B2_NPU_ACTIVE_MASK_EPOCH=0`
- `B2_NPU_PENDING_MASK_EPOCH=1`
- sample 仍为 0/0

样本后 `post_pass_probe.log`：`active=1 pending=0`，logits=`165,-18,14,0,0,0,0,0,0,153`。第二次 overlap `20260912T150654Z` 同样 `epoch_hold_active=0 / pending=1`。计算中 overlap 仍只由 Icarus 证明。

## B3-13/14 局部周期

两轮一致：

| mode | logits | execute/skip | last_compute_cycles | decision_source |
| --- | --- | --- | --- | --- |
| dense | 165,-18,...,153 | 592/0 | 2494 | none_full_open_or_dense |
| full-open | 165,-18,...,153 | 592/0 | 2494 | host_full_open_mask |
| static mixed | 74,-18,...,114 | 296/296 | 1606 | host_replay_static_mixed |
| live-ENeuron | 165,-18,...,153 | 296/296 | 1606 | live_eneuron_s2 |

组级动态剪枝相对 dense 少 888 个 NPU compute cycles。不是网口加速，也不是测得功耗。
