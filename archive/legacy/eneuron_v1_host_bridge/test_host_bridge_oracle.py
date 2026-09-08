"""Host Bridge V1 128-bit codec 与逐命令 oracle 回归。"""

from __future__ import annotations

import unittest
import random

from host_bridge_oracle import (
    FatalPhase,
    Flit,
    HostBridgeOracle,
    Opcode,
    ReferenceTileBackend,
    Status,
    decode_modulators,
    encode_modulators,
)


def command(
    opcode: int | Opcode,
    *,
    flags: int = 0,
    txn_id: int = 1,
    episode_id: int = 0,
    tick_id: int = 0,
    arg0: int = 0,
    arg1: int = 0,
) -> Flit:
    return Flit(int(opcode), flags, txn_id, episode_id, tick_id, arg0, arg1)


class FlitCodecTests(unittest.TestCase):
    def test_fixed_vector_round_trip(self) -> None:
        flit = Flit(0xA5, 0x5A, 0x1234, 0x5678, 0x9ABC, 0xDEF01234, 0x56789ABC)
        self.assertEqual(flit.pack(), 0xA55A123456789ABCDEF0123456789ABC)
        self.assertEqual(Flit.unpack(flit.pack()), flit)
        self.assertEqual(flit.to_bytes(), bytes.fromhex("a55a123456789abcdef0123456789abc"))
        self.assertEqual(Flit.from_bytes(flit.to_bytes()), flit)

    def test_codec_rejects_out_of_range_fields(self) -> None:
        with self.assertRaises(ValueError):
            Flit(0x100, 0, 0, 0, 0, 0, 0)
        with self.assertRaises(ValueError):
            Flit.unpack(1 << 128)
        with self.assertRaises(ValueError):
            Flit.from_bytes(b"short")

    def test_signed_modulator_codec(self) -> None:
        encoded = encode_modulators((-1, 0, 1, -1))
        self.assertEqual(encoded, 0b11_01_00_11)
        self.assertEqual(decode_modulators(encoded), (-1, 0, 1, -1))
        with self.assertRaises(ValueError):
            decode_modulators(0b10)

    def test_random_128_bit_round_trip(self) -> None:
        rng = random.Random(0xE11)
        for _ in range(1000):
            value = rng.getrandbits(128)
            self.assertEqual(Flit.unpack(value).pack(), value)


class RecordingTileBackend(ReferenceTileBackend):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.fail_next: dict[str, FatalPhase] = {}

    def _record(self, name: str, *args: object) -> None:
        self.calls.append((name, args))
        phase = self.fail_next.pop(name, None)
        if phase is not None:
            raise RuntimeError(f"injected tile failure at {phase.name}")

    def state_clear(self) -> None:
        self._record("clear")
        super().state_clear()

    def tick(self, input_mask: int, learn_enable: bool) -> tuple[int, int]:
        self._record("tick", input_mask, learn_enable)
        return super().tick(input_mask, learn_enable)

    def route_flush(self, learn_enable: bool) -> int:
        self._record("flush", learn_enable)
        return super().route_flush(learn_enable)

    def snapshot(self, commit_id: int, episode_id: int) -> None:
        self._record("snapshot", commit_id, episode_id)
        super().snapshot(commit_id, episode_id)

    def mod_commit(self, commit_id: int, modulators: tuple[int, int, int, int]) -> None:
        self._record("mod", commit_id, modulators)
        super().mod_commit(commit_id, modulators)

    def weight_write(self, neuron: int, weight: int, value: int) -> None:
        self._record("weight_write", neuron, weight, value)
        super().weight_write(neuron, weight, value)

    def weight_read(self, neuron: int, weight: int) -> int:
        self._record("weight_read", neuron, weight)
        return super().weight_read(neuron, weight)


class HostBridgeOracleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tile = RecordingTileBackend()
        self.bridge = HostBridgeOracle(self.tile)
        self.txn_id = 1

    def execute(self, opcode: int | Opcode, **fields: int) -> Flit:
        fields.setdefault("txn_id", self.txn_id)
        self.txn_id += 1
        return self.bridge.execute(command(opcode, **fields))

    def assert_status(self, response: Flit, expected: Status) -> None:
        self.assertEqual(response.flags, int(expected))

    def start(self, episode_id: int = 7, train: bool = False) -> Flit:
        return self.execute(Opcode.EP_START, flags=int(train), episode_id=episode_id)

    def begin_tick(self, episode_id: int, tick_id: int, count: int) -> Flit:
        return self.execute(
            Opcode.TICK_BEGIN,
            episode_id=episode_id,
            tick_id=tick_id,
            arg0=count,
        )

    def input_event(self, episode_id: int, tick_id: int, synapse: int) -> Flit:
        return self.execute(
            Opcode.INPUT_EVENT,
            episode_id=episode_id,
            tick_id=tick_id,
            arg0=synapse,
        )

    def commit_tick(self, episode_id: int, tick_id: int) -> Flit:
        return self.execute(Opcode.TICK_COMMIT, episode_id=episode_id, tick_id=tick_id)

    def test_all_opcode_success_paths(self) -> None:
        self.assert_status(self.start(episode_id=7, train=True), Status.OK)
        self.assert_status(self.begin_tick(7, 0, 2), Status.OK)
        self.assert_status(self.input_event(7, 0, 0), Status.OK)
        self.assert_status(self.input_event(7, 0, 1), Status.OK)
        tick_response = self.commit_tick(7, 0)
        self.assert_status(tick_response, Status.OK)
        self.assertEqual(tick_response.arg0 & ~0xF, 0)

        end_response = self.execute(Opcode.EP_END, episode_id=7, arg0=10)
        self.assert_status(end_response, Status.OK)
        self.assertEqual(self.tile.calls[-2][0], "flush")
        self.assertEqual(self.tile.calls[-1], ("snapshot", (10, 7)))
        self.assertEqual(end_response.arg0 & 0x3, 0)
        self.assertEqual(end_response.arg1, self.tile.weight_epoch)

        status1 = self.execute(Opcode.STATUS_READ, arg0=1)
        self.assert_status(status1, Status.OK)
        self.assertEqual(status1.episode_id, 7)
        self.assertEqual(status1.tick_id, 10)
        self.assertEqual(status1.arg0 & 0xFFFF, 10)
        self.assertEqual((status1.arg0 >> 16) & 1, 1)
        self.assertEqual((status1.arg0 >> 17) & 1, 1)

        read = self.execute(Opcode.WEIGHT_READ, arg0=0)
        self.assert_status(read, Status.OK)
        self.assertEqual(read.arg0, 2)
        write = self.execute(Opcode.WEIGHT_WRITE, arg0=(5 << 4))
        self.assert_status(write, Status.SNAPSHOT_BUSY)

        mod = self.execute(
            Opcode.MOD_COMMIT,
            episode_id=7,
            arg0=10,
            arg1=encode_modulators((1, -1, 1, -1)),
        )
        self.assert_status(mod, Status.OK)
        self.assertEqual(mod.arg0, 10)
        self.assertEqual(mod.arg1, 1)

        write = self.execute(Opcode.WEIGHT_WRITE, arg0=(5 << 4))
        self.assert_status(write, Status.OK)
        read = self.execute(Opcode.WEIGHT_READ, arg0=0)
        self.assertEqual(read.arg0, 5)

        self.assert_status(self.start(episode_id=8), Status.OK)
        abort = self.execute(Opcode.ABORT, episode_id=8)
        self.assert_status(abort, Status.OK)
        self.assertFalse(self.bridge.episode_active)

    def test_static_field_validation_precedes_dynamic_chain(self) -> None:
        response = self.execute(
            Opcode.TICK_BEGIN,
            flags=1,
            episode_id=99,
            tick_id=33,
            arg0=7,
        )
        self.assert_status(response, Status.BAD_FIELD)
        self.assertEqual(self.tile.calls, [])

        response = self.execute(0xFE, flags=0xFF, arg0=0xFFFFFFFF)
        self.assert_status(response, Status.BAD_OPCODE)

    def test_each_opcode_rejects_static_reserved_bits_without_tile_calls(self) -> None:
        cases = (
            command(Opcode.EP_START, flags=2),
            command(Opcode.TICK_BEGIN, arg0=8),
            command(Opcode.INPUT_EVENT, arg0=8),
            command(Opcode.TICK_COMMIT, arg1=1),
            command(Opcode.EP_END, arg0=1 << 16),
            command(Opcode.MOD_COMMIT, arg1=1 << 8),
            command(Opcode.WEIGHT_WRITE, arg0=1 << 12),
            command(Opcode.WEIGHT_READ, arg0=1 << 4),
            command(Opcode.ABORT, tick_id=1),
            command(Opcode.STATUS_READ, arg0=2),
        )
        for request in cases:
            with self.subTest(opcode=request.opcode):
                calls_before = list(self.tile.calls)
                response = self.bridge.execute(request)
                self.assert_status(response, Status.BAD_FIELD)
                self.assertEqual(self.tile.calls, calls_before)

    def test_each_modulator_lane_rejects_reserved_encoding(self) -> None:
        for lane in range(4):
            with self.subTest(lane=lane):
                response = self.execute(Opcode.MOD_COMMIT, arg1=0b10 << (lane * 2))
                self.assert_status(response, Status.BAD_FIELD)
                self.assertEqual(self.tile.calls, [])

    def test_error_response_echoes_header_and_clears_payload(self) -> None:
        request = command(
            Opcode.TICK_BEGIN,
            txn_id=0x1234,
            episode_id=0x5678,
            tick_id=0x9ABC,
            arg0=4,
        )
        response = self.bridge.execute(request)
        self.assert_status(response, Status.BAD_STATE)
        self.assertEqual(response.opcode, request.opcode)
        self.assertEqual(response.txn_id, request.txn_id)
        self.assertEqual(response.episode_id, request.episode_id)
        self.assertEqual(response.tick_id, request.tick_id)
        self.assertEqual(response.arg0, 0)
        self.assertEqual(response.arg1, 0)

    def test_first_error_chains_and_error_side_effects(self) -> None:
        cases = [
            (command(Opcode.TICK_BEGIN, episode_id=1, arg0=5), Status.BAD_STATE),
            (command(Opcode.INPUT_EVENT, episode_id=1, arg0=7), Status.BAD_STATE),
            (command(Opcode.TICK_COMMIT, episode_id=1), Status.BAD_STATE),
            (command(Opcode.EP_END, episode_id=1), Status.BAD_STATE),
            (command(Opcode.MOD_COMMIT, episode_id=1), Status.COMMIT_ID),
            (command(Opcode.WEIGHT_READ, arg0=0xF), Status.ADDRESS),
            (command(Opcode.WEIGHT_WRITE, arg0=0xF), Status.ADDRESS),
            (command(Opcode.ABORT, episode_id=1), Status.BAD_STATE),
            (command(Opcode.STATUS_READ, arg0=2), Status.BAD_FIELD),
        ]
        for request, expected in cases:
            with self.subTest(opcode=request.opcode):
                before = self.bridge.architectural_state()
                calls_before = list(self.tile.calls)
                response = self.bridge.execute(request)
                self.assert_status(response, expected)
                self.assertEqual(self.bridge.architectural_state(), before)
                self.assertEqual(self.tile.calls, calls_before)

        self.assert_status(self.start(episode_id=3), Status.OK)
        self.assert_status(self.begin_tick(3, 0, 1), Status.OK)
        before = self.bridge.architectural_state()
        duplicate_first = self.input_event(3, 0, 0)
        self.assert_status(duplicate_first, Status.OK)
        before_duplicate = self.bridge.architectural_state()
        duplicate = self.input_event(3, 0, 0)
        self.assert_status(duplicate, Status.DUP_EVENT)
        self.assertEqual(self.bridge.architectural_state(), before_duplicate)
        mismatch = self.commit_tick(3, 0)
        self.assert_status(mismatch, Status.OK)
        self.assertNotEqual(self.bridge.architectural_state(), before)

    def test_tick_dynamic_error_priority_and_zero_event_commit(self) -> None:
        self.assert_status(self.start(episode_id=0x20), Status.OK)

        response = self.execute(
            Opcode.TICK_BEGIN,
            episode_id=0x21,
            tick_id=9,
            arg0=5,
        )
        self.assert_status(response, Status.EPISODE_ID)

        self.bridge.next_tick_ext = 0x10000
        response = self.execute(
            Opcode.TICK_BEGIN,
            episode_id=0x20,
            tick_id=9,
            arg0=5,
        )
        self.assert_status(response, Status.COUNTER_WRAP)

        self.bridge.next_tick_ext = 0
        response = self.execute(
            Opcode.TICK_BEGIN,
            episode_id=0x20,
            tick_id=9,
            arg0=5,
        )
        self.assert_status(response, Status.TICK_ID)
        response = self.execute(Opcode.TICK_BEGIN, episode_id=0x20, arg0=5)
        self.assert_status(response, Status.EVENT_COUNT)

        self.assert_status(self.begin_tick(0x20, 0, 0), Status.OK)
        extra = self.input_event(0x20, 0, 0)
        self.assert_status(extra, Status.EVENT_COUNT)
        tick = self.commit_tick(0x20, 0)
        self.assert_status(tick, Status.OK)
        self.assertEqual(self.tile.calls[-1], ("tick", (0, False)))

    def test_input_event_and_tick_commit_first_error_priority(self) -> None:
        self.assert_status(self.start(episode_id=0x30), Status.OK)
        self.assert_status(self.begin_tick(0x30, 0, 2), Status.OK)

        wrong_episode = self.execute(
            Opcode.INPUT_EVENT,
            episode_id=0x31,
            tick_id=4,
            arg0=7,
        )
        self.assert_status(wrong_episode, Status.EPISODE_ID)
        wrong_tick = self.execute(
            Opcode.INPUT_EVENT,
            episode_id=0x30,
            tick_id=4,
            arg0=7,
        )
        self.assert_status(wrong_tick, Status.TICK_ID)
        bad_synapse = self.input_event(0x30, 0, 4)
        self.assert_status(bad_synapse, Status.SYNAPSE_RANGE)

        self.assert_status(self.input_event(0x30, 0, 1), Status.OK)
        wrong_episode = self.execute(
            Opcode.TICK_COMMIT,
            episode_id=0x31,
            tick_id=4,
        )
        self.assert_status(wrong_episode, Status.EPISODE_ID)
        wrong_tick = self.execute(
            Opcode.TICK_COMMIT,
            episode_id=0x30,
            tick_id=4,
        )
        self.assert_status(wrong_tick, Status.TICK_ID)
        before = self.bridge.architectural_state()
        short = self.commit_tick(0x30, 0)
        self.assert_status(short, Status.EVENT_COUNT)
        self.assertEqual(self.bridge.architectural_state(), before)

        self.assert_status(self.input_event(0x30, 0, 2), Status.OK)
        self.assert_status(self.commit_tick(0x30, 0), Status.OK)

    def test_episode_start_mod_and_weight_first_error_priority(self) -> None:
        self.tile.snapshot_valid = True
        self.tile.last_commit_valid = True
        self.tile.last_commit_id = 0xFFFF
        response = self.start(episode_id=1, train=True)
        self.assert_status(response, Status.SNAPSHOT_BUSY)
        self.tile.snapshot_valid = False
        response = self.start(episode_id=1, train=True)
        self.assert_status(response, Status.COUNTER_WRAP)

        self.tile.last_commit_valid = False
        self.assert_status(self.start(episode_id=1), Status.OK)
        response = self.execute(Opcode.MOD_COMMIT, episode_id=9, arg0=9)
        self.assert_status(response, Status.BAD_STATE)
        response = self.execute(Opcode.WEIGHT_WRITE, arg0=0xF)
        self.assert_status(response, Status.BAD_STATE)
        self.assert_status(self.execute(Opcode.ABORT, episode_id=1), Status.OK)

        response = self.execute(Opcode.MOD_COMMIT, episode_id=9, arg0=9)
        self.assert_status(response, Status.COMMIT_ID)
        self.tile.snapshot_valid = True
        self.tile.pending_episode_id = 7
        self.tile.pending_commit_id = 8
        response = self.execute(Opcode.MOD_COMMIT, episode_id=9, arg0=9)
        self.assert_status(response, Status.EPISODE_ID)
        response = self.execute(Opcode.MOD_COMMIT, episode_id=7, arg0=9)
        self.assert_status(response, Status.COMMIT_ID)

        response = self.execute(Opcode.WEIGHT_WRITE, arg0=0xF)
        self.assert_status(response, Status.SNAPSHOT_BUSY)
        self.tile.snapshot_valid = False
        response = self.execute(Opcode.WEIGHT_WRITE, arg0=0xF)
        self.assert_status(response, Status.ADDRESS)

    def test_tick_ffff_commits_then_exhausts_new_ticks(self) -> None:
        self.assert_status(self.start(episode_id=2), Status.OK)
        self.bridge.next_tick_ext = 0xFFFF
        self.assert_status(self.begin_tick(2, 0xFFFF, 0), Status.OK)
        self.assert_status(self.commit_tick(2, 0xFFFF), Status.OK)
        self.assertEqual(self.bridge.next_tick_ext, 0x10000)
        response = self.begin_tick(2, 0, 0)
        self.assert_status(response, Status.COUNTER_WRAP)
        self.assert_status(self.execute(Opcode.EP_END, episode_id=2), Status.OK)

    def test_train_and_infer_drive_tile_learning_per_transaction(self) -> None:
        self.assert_status(self.start(episode_id=1, train=False), Status.OK)
        self.assert_status(self.begin_tick(1, 0, 0), Status.OK)
        self.assert_status(self.commit_tick(1, 0), Status.OK)
        self.assertEqual(self.tile.calls[-1], ("tick", (0, False)))
        self.assert_status(self.execute(Opcode.EP_END, episode_id=1), Status.OK)
        self.assertEqual(self.tile.calls[-1], ("flush", (False,)))

        self.assert_status(self.start(episode_id=2, train=True), Status.OK)
        self.assert_status(self.begin_tick(2, 0, 0), Status.OK)
        self.assert_status(self.commit_tick(2, 0), Status.OK)
        self.assertEqual(self.tile.calls[-1], ("tick", (0, True)))
        self.assert_status(self.execute(Opcode.EP_END, episode_id=2, arg0=1), Status.OK)
        self.assertEqual(self.tile.calls[-2], ("flush", (True,)))
        self.assertEqual(self.tile.calls[-1], ("snapshot", (1, 2)))

    def test_repeated_txn_id_is_not_deduplicated(self) -> None:
        request = command(Opcode.WEIGHT_WRITE, txn_id=0x4444, arg0=(3 << 4))
        first = self.bridge.execute(request)
        second = self.bridge.execute(request)
        self.assert_status(first, Status.OK)
        self.assert_status(second, Status.OK)
        writes = [call for call in self.tile.calls if call[0] == "weight_write"]
        self.assertEqual(len(writes), 2)

    def test_weight_read_sign_extends_negative_eight_bit_value(self) -> None:
        write = self.execute(Opcode.WEIGHT_WRITE, arg0=(0xF9 << 4))
        self.assert_status(write, Status.OK)
        read = self.execute(Opcode.WEIGHT_READ)
        self.assert_status(read, Status.OK)
        self.assertEqual(read.arg0, 0xFFFFFFF9)

    def test_working_state_is_released_after_response_accept(self) -> None:
        response = self.start(episode_id=1)
        self.assert_status(response, Status.OK)
        self.assertEqual(self.bridge.working_state(), (0, 0, 0))

    def test_state_aware_random_command_streams_are_total_and_atomic(self) -> None:
        for seed in range(10):
            rng = random.Random(seed)
            tile = RecordingTileBackend()
            bridge = HostBridgeOracle(tile)
            txn_id = 0

            for _ in range(1000):
                if rng.random() < 0.35:
                    request = Flit(
                        opcode=rng.randrange(256),
                        flags=rng.randrange(256),
                        txn_id=txn_id,
                        episode_id=rng.randrange(1 << 16),
                        tick_id=rng.randrange(1 << 16),
                        arg0=rng.randrange(1 << 32),
                        arg1=rng.randrange(1 << 32),
                    )
                else:
                    request = self._make_state_aware_request(bridge, rng, txn_id)
                txn_id = (txn_id + 1) & 0xFFFF

                bridge_before = bridge.architectural_state()
                tile_before = tile.observable_state()
                response = bridge.execute(request)

                self.assertEqual(Flit.unpack(response.pack()), response)
                self.assertEqual(response.opcode, request.opcode)
                self.assertEqual(response.txn_id, request.txn_id)
                if response.flags != Status.OK:
                    self.assertEqual(bridge.architectural_state(), bridge_before)
                    self.assertEqual(tile.observable_state(), tile_before)

    @staticmethod
    def _make_state_aware_request(
        bridge: HostBridgeOracle,
        rng: random.Random,
        txn_id: int,
    ) -> Flit:
        tile = bridge.tile
        if not bridge.episode_active:
            choices = [Opcode.STATUS_READ, Opcode.EP_START, Opcode.WEIGHT_READ]
            if not tile.snapshot_valid:
                choices.append(Opcode.WEIGHT_WRITE)
            else:
                choices.append(Opcode.MOD_COMMIT)
            opcode = rng.choice(choices)
            if opcode == Opcode.STATUS_READ:
                return command(opcode, txn_id=txn_id, arg0=rng.randrange(2))
            if opcode == Opcode.EP_START:
                train = rng.choice((False, True))
                return command(
                    opcode,
                    txn_id=txn_id,
                    flags=int(train),
                    episode_id=rng.randrange(1 << 16),
                )
            if opcode == Opcode.MOD_COMMIT:
                return command(
                    opcode,
                    txn_id=txn_id,
                    episode_id=tile.pending_episode_id,
                    arg0=tile.pending_commit_id,
                    arg1=encode_modulators(
                        tuple(rng.choice((-1, 0, 1)) for _ in range(4))
                    ),
                )
            neuron = rng.randrange(4)
            weight = rng.randrange(4 if neuron < 2 else 2)
            arg0 = neuron | (weight << 2)
            if opcode == Opcode.WEIGHT_WRITE:
                arg0 |= rng.randrange(256) << 4
            return command(opcode, txn_id=txn_id, arg0=arg0)

        episode_id = bridge.active_episode_id
        if bridge.tick_open:
            choices = [Opcode.STATUS_READ, Opcode.ABORT, Opcode.TICK_COMMIT]
            if bridge.seen_event_count < bridge.expected_event_count:
                choices.extend((Opcode.INPUT_EVENT, Opcode.INPUT_EVENT))
            opcode = rng.choice(choices)
            if opcode == Opcode.STATUS_READ:
                return command(opcode, txn_id=txn_id)
            if opcode == Opcode.ABORT:
                return command(opcode, txn_id=txn_id, episode_id=episode_id)
            if opcode == Opcode.TICK_COMMIT:
                return command(
                    opcode,
                    txn_id=txn_id,
                    episode_id=episode_id,
                    tick_id=bridge.next_tick_ext & 0xFFFF,
                )
            unused = [index for index in range(4) if not bridge.seen_mask & (1 << index)]
            return command(
                opcode,
                txn_id=txn_id,
                episode_id=episode_id,
                tick_id=bridge.next_tick_ext & 0xFFFF,
                arg0=rng.choice(unused),
            )

        opcode = rng.choice(
            (Opcode.STATUS_READ, Opcode.TICK_BEGIN, Opcode.TICK_BEGIN, Opcode.EP_END, Opcode.ABORT)
        )
        if opcode == Opcode.STATUS_READ:
            return command(opcode, txn_id=txn_id, arg0=rng.randrange(2))
        if opcode == Opcode.TICK_BEGIN:
            return command(
                opcode,
                txn_id=txn_id,
                episode_id=episode_id,
                tick_id=bridge.next_tick_ext & 0xFFFF,
                arg0=rng.randrange(5),
            )
        if opcode == Opcode.ABORT:
            return command(opcode, txn_id=txn_id, episode_id=episode_id)
        commit_id = 0
        if bridge.episode_train:
            commit_id = tile.last_commit_id + 1 if tile.last_commit_valid else 0
        return command(
            opcode,
            txn_id=txn_id,
            episode_id=episode_id,
            arg0=commit_id,
        )

    def test_status_pages_report_architectural_and_tile_truth(self) -> None:
        self.assert_status(self.start(episode_id=0x1234, train=True), Status.OK)
        self.assert_status(self.begin_tick(0x1234, 0, 3), Status.OK)
        self.assert_status(self.input_event(0x1234, 0, 1), Status.OK)
        self.assert_status(self.input_event(0x1234, 0, 3), Status.OK)

        page0 = self.execute(Opcode.STATUS_READ)
        self.assertEqual(page0.episode_id, 0x1234)
        self.assertEqual(page0.tick_id, 0)
        self.assertEqual(page0.arg0 & 0x7, 0b111)
        self.assertEqual((page0.arg0 >> 8) & 0x7, 3)
        self.assertEqual((page0.arg0 >> 11) & 0x7, 2)
        self.assertEqual((page0.arg0 >> 14) & 0xF, 0b1010)
        self.assertEqual(page0.arg1, 0)

        self.assert_status(self.input_event(0x1234, 0, 0), Status.OK)
        self.assert_status(self.commit_tick(0x1234, 0), Status.OK)
        self.assert_status(self.execute(Opcode.EP_END, episode_id=0x1234, arg0=9), Status.OK)
        page1 = self.execute(Opcode.STATUS_READ, arg0=1)
        self.assertEqual(page1.episode_id, 0x1234)
        self.assertEqual(page1.tick_id, 9)
        self.assertEqual(page1.arg0, 9 | (1 << 16) | (1 << 17))
        self.assertEqual(page1.arg1, 0)

    def test_infer_ep_end_does_not_apply_train_commit_checks(self) -> None:
        self.tile.last_commit_valid = True
        self.tile.last_commit_id = 0xFFFF
        self.assert_status(self.start(episode_id=4, train=False), Status.OK)
        response = self.execute(Opcode.EP_END, episode_id=4)
        self.assert_status(response, Status.OK)
        self.assertEqual([name for name, _ in self.tile.calls[-2:]], ["clear", "flush"])

    def test_train_ep_end_prechecks_before_flush(self) -> None:
        self.assert_status(self.start(episode_id=4, train=True), Status.OK)
        self.tile.snapshot_valid = True
        calls_before = list(self.tile.calls)
        response = self.execute(Opcode.EP_END, episode_id=4, arg0=1)
        self.assert_status(response, Status.SNAPSHOT_BUSY)
        self.assertEqual(self.tile.calls, calls_before)

        self.tile.snapshot_valid = False
        self.tile.last_commit_valid = True
        self.tile.last_commit_id = 9
        response = self.execute(Opcode.EP_END, episode_id=4, arg0=9)
        self.assert_status(response, Status.COMMIT_ID)
        self.assertEqual(self.tile.calls, calls_before)

        self.tile.last_commit_id = 0xFFFF
        response = self.execute(Opcode.EP_END, episode_id=4, arg0=0xFFFF)
        self.assert_status(response, Status.COUNTER_WRAP)
        self.assertEqual(self.tile.calls, calls_before)

    def test_abort_preserves_weights_snapshot_and_commit_metadata(self) -> None:
        self.assert_status(self.start(episode_id=5, train=True), Status.OK)
        self.assert_status(self.execute(Opcode.EP_END, episode_id=5, arg0=3), Status.OK)
        self.assert_status(self.start(episode_id=6, train=False), Status.OK)
        before = self.tile.persistent_state()
        self.assert_status(self.execute(Opcode.ABORT, episode_id=6), Status.OK)
        self.assertEqual(self.tile.persistent_state(), before)
        self.assertEqual(self.tile.pending_hidden, 0)

    def test_abort_is_legal_with_an_open_tick_and_clears_staging(self) -> None:
        self.assert_status(self.start(episode_id=15), Status.OK)
        self.assert_status(self.begin_tick(15, 0, 2), Status.OK)
        self.assert_status(self.input_event(15, 0, 3), Status.OK)
        self.assertTrue(self.bridge.tick_open)
        response = self.execute(Opcode.ABORT, episode_id=15)
        self.assert_status(response, Status.OK)
        self.assertFalse(self.bridge.episode_active)
        self.assertFalse(self.bridge.tick_open)
        self.assertEqual(self.bridge.expected_event_count, 0)
        self.assertEqual(self.bridge.seen_event_count, 0)
        self.assertEqual(self.bridge.seen_mask, 0)

    def test_zero_modulator_consumes_snapshot_and_increments_epoch(self) -> None:
        self.assert_status(self.start(episode_id=16, train=True), Status.OK)
        self.assert_status(self.execute(Opcode.EP_END, episode_id=16, arg0=2), Status.OK)
        weights_before = tuple(tuple(neuron.weights) for neuron in self.tile.neurons)
        response = self.execute(
            Opcode.MOD_COMMIT,
            episode_id=16,
            arg0=2,
            arg1=encode_modulators((0, 0, 0, 0)),
        )
        self.assert_status(response, Status.OK)
        self.assertFalse(self.tile.snapshot_valid)
        self.assertEqual(self.tile.weight_epoch, 1)
        self.assertEqual(
            tuple(tuple(neuron.weights) for neuron in self.tile.neurons),
            weights_before,
        )

    def test_weight_epoch_wraps_modulo_32_bits(self) -> None:
        self.tile.oracle.weight_epoch = 0xFFFFFFFF
        self.tile.snapshot_valid = True
        self.tile.pending_episode_id = 1
        self.tile.pending_commit_id = 1
        response = self.execute(
            Opcode.MOD_COMMIT,
            episode_id=1,
            arg0=1,
            arg1=encode_modulators((0, 0, 0, 0)),
        )
        self.assert_status(response, Status.OK)
        self.assertEqual(response.arg1, 0)
        self.assertEqual(self.tile.weight_epoch, 0)

    def test_hard_reset_clears_everything_and_restores_initial_weights(self) -> None:
        self.assert_status(self.execute(Opcode.WEIGHT_WRITE, arg0=(7 << 4)), Status.OK)
        self.assert_status(self.start(episode_id=9, train=True), Status.OK)
        self.assert_status(self.execute(Opcode.EP_END, episode_id=9, arg0=4), Status.OK)
        self.bridge.hard_reset()
        self.assertEqual(self.bridge.architectural_state(), HostBridgeOracle().architectural_state())
        self.assertEqual(self.tile.weight_epoch, 0)
        self.assertFalse(self.tile.snapshot_valid)
        self.assertFalse(self.tile.last_commit_valid)
        self.assertTrue(all(weight == 2 for neuron in self.tile.neurons for weight in neuron.weights))

    def test_fatal_is_first_failure_sticky_and_status_remains_available(self) -> None:
        self.tile.fail_next["clear"] = FatalPhase.EP_START_CLEAR_WAIT
        response = self.start(episode_id=1)
        self.assert_status(response, Status.INTERNAL_FATAL)
        self.assertTrue(self.bridge.fatal_error)
        self.assertEqual(self.bridge.fatal_opcode, Opcode.EP_START)
        self.assertEqual(self.bridge.fatal_phase, FatalPhase.EP_START_CLEAR_WAIT)

        blocked = self.execute(Opcode.WEIGHT_READ)
        self.assert_status(blocked, Status.INTERNAL_FATAL)
        self.assertEqual(self.bridge.fatal_opcode, Opcode.EP_START)
        self.assertEqual(self.bridge.fatal_phase, FatalPhase.EP_START_CLEAR_WAIT)

        page0 = self.execute(Opcode.STATUS_READ)
        self.assert_status(page0, Status.OK)
        self.assertEqual((page0.arg0 >> 4) & 1, 1)
        self.assertEqual(page0.arg1 & 0xFF, Opcode.EP_START)
        self.assertEqual((page0.arg1 >> 8) & 0xFF, FatalPhase.EP_START_CLEAR_WAIT)

        self.bridge.hard_reset()
        page0 = self.execute(Opcode.STATUS_READ)
        self.assertEqual((page0.arg0 >> 4) & 1, 0)
        self.assertEqual(page0.arg1, 0)

    def test_each_tile_failure_maps_to_the_frozen_fatal_phase(self) -> None:
        scenarios = (
            ("clear", FatalPhase.EP_START_CLEAR_WAIT, command(Opcode.EP_START, episode_id=1)),
            ("tick", FatalPhase.TICK_WAIT, command(Opcode.TICK_COMMIT, episode_id=1)),
            ("flush", FatalPhase.EP_END_FLUSH_WAIT, command(Opcode.EP_END, episode_id=1)),
            ("snapshot", FatalPhase.EP_END_SNAPSHOT_WAIT, command(Opcode.EP_END, episode_id=1, arg0=1)),
            ("mod", FatalPhase.MOD_WAIT, command(Opcode.MOD_COMMIT, episode_id=1, arg0=1)),
            ("weight_write", FatalPhase.WEIGHT_WAIT, command(Opcode.WEIGHT_WRITE)),
            ("weight_read", FatalPhase.WEIGHT_WAIT, command(Opcode.WEIGHT_READ)),
            ("clear", FatalPhase.ABORT_CLEAR_WAIT, command(Opcode.ABORT, episode_id=1)),
        )

        for operation, phase, request in scenarios:
            with self.subTest(phase=phase):
                tile = RecordingTileBackend()
                bridge = HostBridgeOracle(tile)
                if phase == FatalPhase.TICK_WAIT:
                    bridge.execute(command(Opcode.EP_START, episode_id=1))
                    bridge.execute(command(Opcode.TICK_BEGIN, episode_id=1))
                elif phase in (FatalPhase.EP_END_FLUSH_WAIT, FatalPhase.ABORT_CLEAR_WAIT):
                    bridge.execute(command(Opcode.EP_START, episode_id=1))
                elif phase == FatalPhase.EP_END_SNAPSHOT_WAIT:
                    bridge.execute(command(Opcode.EP_START, flags=1, episode_id=1))
                elif phase == FatalPhase.MOD_WAIT:
                    tile.snapshot_valid = True
                    tile.pending_episode_id = 1
                    tile.pending_commit_id = 1
                tile.fail_next[operation] = phase
                state_before = bridge.architectural_state()
                response = bridge.execute(request)
                self.assert_status(response, Status.INTERNAL_FATAL)
                self.assertEqual(bridge.fatal_phase, phase)
                expected_state = (*state_before[:-3], True, int(request.opcode), int(phase))
                self.assertEqual(bridge.architectural_state(), expected_state)

    def test_controller_internal_fatal_is_sticky(self) -> None:
        self.bridge.record_controller_fault(0xE1)
        self.assertTrue(self.bridge.fatal_error)
        self.assertEqual(self.bridge.fatal_opcode, 0xE1)
        self.assertEqual(self.bridge.fatal_phase, FatalPhase.CONTROLLER_INTERNAL)
        self.bridge.record_controller_fault(Opcode.EP_END)
        self.assertEqual(self.bridge.fatal_opcode, 0xE1)
        self.assertEqual(self.bridge.fatal_phase, FatalPhase.CONTROLLER_INTERNAL)
        response = self.execute(0xFE)
        self.assert_status(response, Status.INTERNAL_FATAL)

    def test_fatal_prefix_precedes_bad_opcode_but_not_status_static_check(self) -> None:
        self.bridge.record_controller_fault(Opcode.EP_END)
        response = self.execute(0xFE, flags=0xFF)
        self.assert_status(response, Status.INTERNAL_FATAL)
        malformed_status = self.execute(Opcode.STATUS_READ, arg0=2)
        self.assert_status(malformed_status, Status.BAD_FIELD)
        valid_status = self.execute(Opcode.STATUS_READ)
        self.assert_status(valid_status, Status.OK)

    def test_ep_end_flush_result_survives_snapshot_subtransaction(self) -> None:
        self.assert_status(self.start(episode_id=12, train=True), Status.OK)
        self.tile.pending_hidden = 0b11
        original_snapshot = self.tile.snapshot

        def corrupt_output_after_snapshot(commit_id: int, episode_id: int) -> None:
            original_snapshot(commit_id, episode_id)
            self.tile.last_output_spikes = 0

        self.tile.snapshot = corrupt_output_after_snapshot  # type: ignore[method-assign]
        response = self.execute(Opcode.EP_END, episode_id=12, arg0=1)
        self.assert_status(response, Status.OK)
        self.assertEqual((response.arg0 >> 2) & 0x3, self.bridge.last_ep_end_flush_spikes)


if __name__ == "__main__":
    unittest.main()
