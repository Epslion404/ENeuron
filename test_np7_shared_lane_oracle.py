"""NP7.1：共享 lane 周期 oracle 的穷举回归。

覆盖 16 种活动掩码、6 种合法 2:4 结构、三类非法索引，以及 1/2/4/8 lane
的精确请求、操作、周期与突触和账本。
"""

from __future__ import annotations

import random
import unittest

from np7_shared_lane_oracle import (
    ACC_MAX,
    ConfigError,
    FORMAT_DENSE,
    FORMAT_SPARSE,
    GROUP_WIDTH,
    LANE_COUNTS,
    SharedLaneUnit,
    decode_dense_group,
    decode_sparse_group,
    encode_dense_group,
    encode_sparse_group,
    exhaustive_structures,
    illegal_index_samples,
    mask_from_indices,
    sat_add,
    tree_sum,
)

# B-V1+V2（PR #6 评论 5498372499）：零路径只有 1 拍，accept 与 result 同一边沿。
ZERO_CYCLES = 1


def build(fmt: str, lane_count: int, weights, indices) -> SharedLaneUnit:
    unit = SharedLaneUnit(fmt, lane_count)
    for group in range(unit.group_count):
        if fmt == FORMAT_DENSE:
            unit.config_write(group, weights)
        else:
            unit.config_write(group,
                          [weights[indices[0]], weights[indices[1]]], indices)
    unit.config_finish()
    return unit


def expected_cycles(fmt: str, lane_count: int, ops: int) -> int:
    """B-V1+V2 单笔（冷启动）事务的闭式周期：1(ACCEPT) + READ + 1(LAT) + batches。

    旧合同的独立 DONE 拍已作废；冷启动时 accept 无法折叠，仍占 1 拍。
    """
    if ops == 0:
        return ZERO_CYCLES
    batches = (ops + lane_count - 1) // lane_count
    base = 4 if fmt == FORMAT_DENSE else 3
    return base + batches


class RecordFormatTests(unittest.TestCase):
    def test_dense_round_trip_and_reserved_bits(self) -> None:
        for weights in ([0, 0, 0, 0], [127, -128, 7, -7], [-128, 127, -1, 1]):
            words = encode_dense_group(weights)
            self.assertEqual(len(words), 2)
            unit = SharedLaneUnit(FORMAT_DENSE, 1)
            unit.config_write(0, weights)
            unit.ram[31] = None
            self.assertEqual(unit._decode_group(0)[0],
                             {i: weights[i] for i in range(4)})
        self.assertRaises(ConfigError, encode_dense_group, [1] * 3)
        self.assertRaises(ConfigError, encode_dense_group, [128, 0, 0, 0])
        self.assertRaises(ConfigError, decode_dense_group, [1 << 16, 0])

    def test_six_legal_structures_enumerated(self) -> None:
        structures = exhaustive_structures()
        self.assertEqual(len(structures), 6)
        masks = set()
        for indices in structures:
            word = encode_sparse_group([5, -5], indices)[0]
            pair, decoded, mask = decode_sparse_group([word])
            self.assertEqual(pair, (5, -5))
            self.assertEqual(decoded, indices)
            self.assertEqual(mask, mask_from_indices(indices))
            self.assertEqual(bin(mask).count("1"), 2)
            masks.add(mask)
        self.assertEqual(len(masks), 6)

    def test_illegal_indices_rejected_at_config(self) -> None:
        for indices in illegal_index_samples():
            self.assertRaises(ConfigError, encode_sparse_group, [1, 2], indices)
        unit = SharedLaneUnit(FORMAT_SPARSE, 1)
        for indices in illegal_index_samples():
            with self.assertRaises(ConfigError):
                unit.config_write(0, [1, 2], indices)
        self.assertEqual(unit.configured_groups, set())

    def test_stored_illegal_indices_rejected_on_decode(self) -> None:
        for word in (0x00000, (0 << 16) | (0 << 18), (2 << 16) | (1 << 18),
                     (3 << 16) | (3 << 18)):
            self.assertRaises(ConfigError, decode_sparse_group, [word])

    def test_ram_is_read_only_after_config(self) -> None:
        unit = build(FORMAT_SPARSE, 2, [4, -4, 0, 0], (0, 3))
        self.assertRaises(RuntimeError, unit.config_write, 1, [1, 2], (0, 1))


class CycleLedgerTests(unittest.TestCase):
    def test_all_masks_all_structures_all_lanes_exact_ledger(self) -> None:
        weights = [7, -3, 11, -12]
        for lane_count in LANE_COUNTS:
            for indices in exhaustive_structures():
                struct = mask_from_indices(indices)
                dense = build(FORMAT_DENSE, lane_count, list(weights), None)
                pruned = list(weights)
                for position in range(GROUP_WIDTH):
                    if not (struct >> position) & 1:
                        pruned[position] = 0
                dense_group = list(pruned)
                dense = build(FORMAT_DENSE, lane_count, dense_group, None)
                sparse = build(FORMAT_SPARSE, lane_count, pruned, indices)
                for activity in range(1 << GROUP_WIDTH):
                    d = dense.run_group(0, activity)
                    s = sparse.run_group(0, activity)
                    dense_ops = bin(activity).count("1")
                    issue = struct & activity
                    sparse_ops = bin(issue).count("1")
                    self.assertEqual(len(d.ops), dense_ops)
                    self.assertEqual(len(s.ops), sparse_ops)
                    self.assertEqual(d.cycles, expected_cycles(FORMAT_DENSE, lane_count, dense_ops))
                    self.assertEqual(s.cycles, expected_cycles(FORMAT_SPARSE, lane_count, sparse_ops))
                    want_dense = {"group_read_requests": 2 if dense_ops else 0,
                                  "weight_values_fetched": 4 if dense_ops else 0,
                                  "lane_ops_issued": dense_ops}
                    want_sparse = {"group_read_requests": 1 if sparse_ops else 0,
                                   "weight_values_fetched": 2 if sparse_ops else 0,
                                   "lane_ops_issued": sparse_ops}
                    for name, value in want_dense.items():
                        self.assertEqual(getattr(d.ledger, name), value,
                                         (lane_count, indices, activity, name))
                    for name, value in want_sparse.items():
                        self.assertEqual(getattr(s.ledger, name), value)
                    self.assertEqual(s.ledger.completed_groups, 1)
                    self.assertEqual(d.ledger.completed_groups, 1)
                    self.assertEqual(d.ledger.retire_events, 1)
                    self.assertEqual(s.ledger.retire_events, 1)
                    self.assertEqual(d.ledger.accept_events, 1)
                    self.assertEqual(s.ledger.accept_events, 1)
                    self.assertEqual(d.ledger.identity_violations(), [])
                    self.assertEqual(s.ledger.identity_violations(), [])
                    expected_sum = sum(pruned[p] for p in range(GROUP_WIDTH)
                                      if (activity >> p) & 1)
                    self.assertEqual(s.synapse_sum, expected_sum)
                    self.assertEqual(d.synapse_sum, expected_sum)
    def test_zero_fast_path_contract(self) -> None:
        for lane_count in LANE_COUNTS:
            for indices in exhaustive_structures():
                unit = build(FORMAT_SPARSE, lane_count, [9, -9, 0, 0], indices)
                struct = mask_from_indices(indices)
                for activity in range(1 << GROUP_WIDTH):
                    result = unit.run_group(0, activity)
                    if struct & activity:
                        self.assertNotEqual(result.cycles, ZERO_CYCLES)
                        continue
                    self.assertEqual(result.cycles, ZERO_CYCLES)
                    self.assertEqual(result.ledger.group_read_requests, 0)
                    self.assertEqual(result.ledger.weight_values_fetched, 0)
                    self.assertEqual(result.ledger.lane_ops_issued, 0)
                    self.assertEqual(result.ledger.zero_fast_paths, 1)
                    self.assertEqual(result.ledger.completed_groups, 1)
                    self.assertEqual(result.ledger.input_zero_groups,
                                     1 if activity == 0 else 0)
                    self.assertEqual(result.ledger.activity_zero_after_structure,
                                     0 if activity == 0 else 1)
                    self.assertEqual(result.ledger.structural_skips,
                                     0 if activity == 0 else bin(activity).count("1"))
                    self.assertEqual(result.synapse_sum, 0)
                    self.assertEqual([e.cls for e in result.events], ["ZERO"])
                    self.assertEqual(result.zero_path, 1)
                    self.assertEqual(result.ledger.zero_single_cycles, 1)
                    self.assertEqual(result.ledger.identity_violations(), [])
                    self.assertEqual(sum(1 for e in result.events
                                         if e.result_valid and e.accepted), 1)

    def test_backpressure_is_counted_as_stall_only(self) -> None:
        rng = random.Random(20260901)
        for fmt in (FORMAT_DENSE, FORMAT_SPARSE):
            for lane_count in LANE_COUNTS:
                unit = build(fmt, lane_count, [6, -6, 3, -3], (0, 2))
                stall = [rng.randint(0, 1) for _ in range(64)]
                ready = [1 - rng.randint(0, 1) for _ in range(64)]
                result = unit.run_group(0, 0b1011,
                                        lane_stall=lambda c: stall[c] if c < 64 else 0,
                                        result_ready=lambda c: ready[c] if c < 64 else 1)
                led = result.ledger
                self.assertEqual(led.identity_violations(), [])
                self.assertEqual(led.total_cycles,
                                 led.busy_cycles + led.latency_cycles
                                 + led.lane_stall_cycles + led.backpressure_cycles
                                 + led.hold_retire_cycles + led.zero_cycles
                                 + led.accept_cycles + led.idle_cycles)
                self.assertEqual(led.stall_cycles,
                                 led.lane_stall_cycles + led.backpressure_cycles)
                self.assertEqual(led.retire_events, 1)
                self.assertGreaterEqual(led.stall_cycles, 0)
                self.assertEqual(led.completed_groups, 1)
                self.assertEqual(led.lane_ops_issued,
                                 bin((0b1111 if fmt == FORMAT_DENSE
                                      else mask_from_indices((0, 2))) & 0b1011).count("1"))
                for event in result.events:
                    self.assertIn(event.cls, ("RAM", "LANE", "LAT", "LANE_STALL",
                                              "BACKPRESSURE", "HOLD_RETIRE",
                                              "ZERO", "ACCEPT", "IDLE"))
                    busy_cls = event.cls in ("RAM", "LANE")
                    stall_cls = event.cls in ("LANE_STALL", "BACKPRESSURE")
                    # 类别互斥：busy 与 stall 永不重叠；V2 最后一批的锁存边沿
                    # 事件级 busy/stall 可以同时为真，但按优先级归入 LANE。
                    self.assertFalse(busy_cls and stall_cls)
                    if event.busy and event.stall:
                        self.assertEqual(event.cls, "LANE")

    def test_saturation_and_tree_semantics(self) -> None:
        self.assertEqual(sat_add(ACC_MAX, 5), ACC_MAX)
        self.assertEqual(sat_add(-2048, -5), -2048)
        self.assertEqual(tree_sum([1, 2, 3, 4]), 10)
        self.assertEqual(tree_sum([127, -128, 0, 0]), -1)
        unit = build(FORMAT_DENSE, 4, [127, 127, 127, 127], None)
        result = unit.run_group(0, 0b1111, acc_seed=ACC_MAX - 100)
        self.assertEqual(result.synapse_sum, ACC_MAX)
        self.assertEqual(result.ledger.saturation_events, 1)
        plain = sat_add(ACC_MAX - 100, tree_sum([127, 127, 127, 127]))
        self.assertEqual(result.synapse_sum, plain)
    def test_v1_zero_path_under_backpressure_latches_one_result(self) -> None:
        """V1：result_ready=0 时零结果必须锁存并保持，不丢、不重、不被覆盖。"""
        for fmt in (FORMAT_DENSE, FORMAT_SPARSE):
            unit = build(fmt, 4, [9, -9, 3, -3], (0, 2))
            results = unit.run_stream(
                [(0, 0b0000), (0, 0b1111)],
                result_ready=lambda cycle: 0 if cycle < 3 else 1)
            self.assertEqual(len(results), 2)
            zero, full = results
            self.assertEqual(zero.zero_path, 1)
            self.assertEqual(zero.cycles, 4)      # accept + 3 拍锁存保持
            self.assertEqual(zero.synapse_sum, 0)
            self.assertEqual(zero.ledger.accept_cycles, 1)
            self.assertEqual(zero.ledger.backpressure_cycles, 2)
            self.assertEqual(zero.ledger.hold_retire_cycles, 1)
            self.assertEqual(zero.ledger.identity_violations(), [])
            self.assertEqual(unit.ledger.accept_events, 2)
            self.assertEqual(unit.ledger.retire_events, 2)
            self.assertEqual(unit.ledger.zero_fast_paths, 1)
            self.assertEqual(unit.ledger.zero_single_cycles, 0)
            # 锁存期间不得接受下一事务：第二笔只能在退出边沿被接受。
            self.assertEqual(full.accept_cycle, zero.retire_cycle)
            self.assertEqual(full.folded_accept, 1)
            events = unit.stream_events
            self.assertEqual([e.cls for e in events][:4],
                             ["ACCEPT", "BACKPRESSURE", "BACKPRESSURE",
                              "HOLD_RETIRE"])
            self.assertEqual([e.result_valid for e in events][:4],
                             [0, 1, 1, 1])
            self.assertEqual([e.result_zero for e in events][:4], [0, 1, 1, 1])
            self.assertEqual([e.result_sum for e in events][:4], [0, 0, 0, 0])

    def test_v2_gapless_stream_folds_accept_into_retire(self) -> None:
        """V2：连续无气泡流里每笔非零事务都不再消耗独立 accept/DONE 拍。"""
        for fmt in (FORMAT_DENSE, FORMAT_SPARSE):
            for lane_count in LANE_COUNTS:
                unit = build(fmt, lane_count, [1, 2, 3, 4], (0, 2))
                trace = [(0, 0b1111)] * 8
                solo = expected_cycles(fmt, lane_count,
                                       4 if fmt == FORMAT_DENSE else 2)
                results = unit.run_stream(trace)
                self.assertEqual(unit.ledger.completed_groups, 8)
                self.assertEqual(unit.ledger.accept_events, 8)
                self.assertEqual(unit.ledger.retire_events, 8)
                # 只有冷启动那一拍是额外 accept，其余 7 笔全部折叠。
                self.assertEqual(results[0].folded_accept, 0)
                self.assertTrue(all(r.folded_accept for r in results[1:]))
                self.assertEqual(unit.ledger.overlap_cycles, 7)
                want_ops = 4 if fmt == FORMAT_DENSE else 2
                want_batches = (want_ops + lane_count - 1) // lane_count
                want_words = 2 if fmt == FORMAT_DENSE else 1
                self.assertEqual(
                    unit.ledger.total_cycles,
                    1 + 8 * (want_words + 1 + want_batches))
                self.assertLess(unit.ledger.total_cycles, 8 * solo)
                self.assertEqual(unit.ledger.identity_violations(), [])

    def test_v2_lane_stall_blocks_completion_and_accept(self) -> None:
        """lane_stall=1 的拍既不能完成结果，也不能接受下一事务，完成被推后。"""
        trace = [(0, 0b1111), (0, 0b1111)]
        for fmt in (FORMAT_DENSE, FORMAT_SPARSE):
            probe = build(fmt, 4, [1, 2, 3, 4], (0, 2))
            probe.run_stream(trace)
            batch_cycles = [event.cycle for event in probe.stream_events
                            if event.cls == "LANE"]
            self.assertTrue(batch_cycles)
            stalled = {batch_cycles[0], batch_cycles[0] + 1}
            unit = build(fmt, 4, [1, 2, 3, 4], (0, 2))
            results = unit.run_stream(trace,
                                      lane_stall=lambda cycle: 1 if cycle in stalled
                                      else 0)
            events = unit.stream_events
            stall_edges = [event for event in events if event.cls == "LANE_STALL"]
            self.assertEqual(len(stall_edges), 2)
            self.assertTrue(all(not event.result_valid for event in stall_edges))
            self.assertTrue(all(not event.accepted for event in stall_edges))
            self.assertTrue(all(not event.retire for event in stall_edges))
            # 完成被精确推后两拍：既没有提前完成，也没有提前接受。
            self.assertEqual(results[0].retire_cycle, max(stalled) + 1)
            self.assertEqual(results[1].accept_cycle, results[0].retire_cycle)
            self.assertEqual(unit.ledger.retire_events, 2)
            self.assertEqual(unit.ledger.lane_stall_cycles, 2)
            self.assertEqual(unit.ledger.stall_cycles, 2)
            self.assertEqual(unit.ledger.identity_violations(), [])

    def test_one_result_per_accept_over_random_backpressure(self) -> None:
        """任意时刻最多一个未退出结果：每 accept 恰好一个 result，且不覆盖元数据。"""
        rng = random.Random(20260902)
        for fmt in (FORMAT_DENSE, FORMAT_SPARSE):
            for lane_count in LANE_COUNTS:
                unit = build(fmt, lane_count, [5, -5, 2, -2], (0, 2))
                trace = [(rng.randrange(10), rng.randint(0, 15))
                         for _ in range(120)]
                ready = [0 if rng.random() < 0.35 else 1 for _ in range(4096)]
                stall = [1 if rng.random() < 0.2 else 0 for _ in range(4096)]
                results = unit.run_stream(
                    trace, lane_stall=lambda c: stall[c],
                    result_ready=lambda c: ready[c])
                self.assertEqual(len(results), len(trace))
                led = unit.ledger
                self.assertEqual(led.accept_events, len(trace))
                self.assertEqual(led.retire_events, len(trace))
                self.assertEqual(led.completed_groups, len(trace))
                self.assertEqual(led.identity_violations(), [])
                # 退出边沿严格递增，且下一事务不会在它之前被接受（单槽弹性流水）。
                retires = [r.retire_cycle for r in results]
                accepts = [r.accept_cycle for r in results]
                self.assertEqual(retires, sorted(retires))
                self.assertTrue(all(b >= a for a, b in zip(accepts, retires)))
                self.assertTrue(all(n >= m for n, m in zip(accepts[1:], retires[:-1])))
                # 同拍退出+接受时，退出的结果必须属于上一事务（元数据不串）。
                for index in range(1, len(results)):
                    if accepts[index] == retires[index - 1]:
                        edge = unit.stream_events[accepts[index]]
                        self.assertEqual(edge.result_sum,
                                         results[index - 1].synapse_sum)
                        self.assertEqual(edge.result_zero,
                                         results[index - 1].zero_path)
                # 每笔事务在自己退出边沿给出的 result_zero_path 必须与 zero_path 一致
                for result in results:
                    edge = unit.stream_events[result.retire_cycle]
                    self.assertEqual(edge.result_zero, result.zero_path)
                    self.assertEqual(edge.result_sum, result.synapse_sum)

    def test_cold_start_and_tail_drain_are_counted(self) -> None:
        """冷启动 1 拍、尾部排空拍必须单独可观测，不能混进 busy。"""
        unit = build(FORMAT_SPARSE, 4, [1, 2, 3, 4], (0, 2))
        results = unit.run_stream([(0, 0b1111)])
        self.assertEqual(unit.ledger.startup_cycles, 1)
        self.assertEqual(unit.ledger.accept_cycles, 1)
        self.assertEqual(unit.ledger.drain_cycles, 0)
        self.assertEqual(results[0].cycles, 3 + 1)
        stalled = build(FORMAT_SPARSE, 4, [1, 2, 3, 4], (0, 2))
        # 结果一直背压：退出后仍要等 result_ready，排空拍单独可数。
        stalled.run_stream([(0, 0b1111)], result_ready=lambda c: 1 if c >= 9 else 0)
        self.assertGreater(stalled.ledger.backpressure_cycles, 0)
        self.assertEqual(stalled.ledger.retire_events, 1)
        self.assertEqual(stalled.ledger.identity_violations(), [])

    def test_dense_sparse_bit_exact_over_random_streams(self) -> None:
        rng = random.Random(7)
        for lane_count in LANE_COUNTS:
            dense = SharedLaneUnit(FORMAT_DENSE, lane_count)
            sparse = SharedLaneUnit(FORMAT_SPARSE, lane_count)
            structures = []
            for group in range(10):
                indices = rng.choice(exhaustive_structures())
                real = [rng.randint(-128, 127) for _ in range(4)]
                struct = mask_from_indices(indices)
                pruned = [real[p] if (struct >> p) & 1 else 0 for p in range(4)]
                structures.append((indices, real, pruned))
                dense.config_write(group, pruned)
                kept = [pruned[indices[0]], pruned[indices[1]]]
                sparse.config_write(group, kept, indices)
            dense.config_finish()
            sparse.config_finish()
            trace = [(rng.randrange(10), rng.randint(0, 15)) for _ in range(200)]
            for group, activity in trace:
                d = dense.run_group(group, activity)
                s = sparse.run_group(group, activity)
                self.assertEqual(d.synapse_sum, s.synapse_sum)
                indices, _real, pruned = structures[group]
                struct = mask_from_indices(indices)
                want = sum(pruned[p] for p in range(4)
                           if (struct >> p) & 1 and (activity >> p) & 1)
                self.assertEqual(s.synapse_sum, want)
            self.assertLess(sparse.ledger.weight_values_fetched,
                            dense.ledger.weight_values_fetched)
            self.assertEqual(sparse.ledger.completed_groups, 200)
            self.assertEqual(dense.ledger.completed_groups, 200)

    def test_ledger_conservation_across_trace(self) -> None:
        rng = random.Random(11)
        unit = build(FORMAT_SPARSE, 2, [5, -5, 2, -2], (1, 3))
        trace = [(rng.randrange(10), rng.randint(0, 15)) for _ in range(500)]
        results = unit.run_trace(trace)
        led = unit.ledger
        self.assertEqual(len(results), 500)
        self.assertEqual(led.completed_groups, 500)
        self.assertEqual(led.accept_events, 500)
        self.assertEqual(led.retire_events, 500)
        self.assertEqual(led.completed_groups, led.retire_events)
        # V2 的同拍 retire/accept 边沿在逐笔窗口里各计一次，差额必须恰好是 overlap。
        self.assertEqual(sum(r.cycles for r in results),
                         led.total_cycles + led.overlap_cycles)
        self.assertGreater(led.overlap_cycles, 0)
        self.assertEqual(led.structural_skips, sum(r.skip_count for r in results))
        self.assertEqual(led.weight_values_fetched,
                         2 * (500 - led.zero_fast_paths))
        self.assertEqual(led.group_read_requests, 500 - led.zero_fast_paths)
        self.assertEqual(led.zero_fast_paths + (500 - led.zero_fast_paths), 500)
        self.assertEqual(led.busy_cycles + led.stall_cycles + led.accept_cycles
                         + led.latency_cycles + led.hold_retire_cycles
                         + led.zero_cycles + led.idle_cycles, led.total_cycles)
        self.assertEqual(led.identity_violations(), [])
        for result in results:
            self.assertEqual(result.ledger.identity_violations(), [])
        self.assertEqual(led.lane_ops_issued,
                         sum(len(r.ops) for r in results))
        self.assertEqual(led.weight_values_fetched // 2 + led.zero_fast_paths, 500)


if __name__ == "__main__":
    unittest.main(verbosity=2)