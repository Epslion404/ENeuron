import unittest

from cycle_transport import BackpressureError, InputEvent, SpikeEvent, TileCycleTransport
from network_sim import DigitalSNN2Layer, HostTrainingController, make_dataset


class CycleTransportTests(unittest.TestCase):
    def test_same_tick_event_order_is_atomic(self) -> None:
        left = TileCycleTransport(DigitalSNN2Layer(), input_fifo_depth=4, output_fifo_depth=8)
        right = TileCycleTransport(DigitalSNN2Layer(), input_fifo_depth=4, output_fifo_depth=8)
        left.begin_episode(1, 0, train=False)
        right.begin_episode(1, 0, train=False)
        left.begin_tick(0, 2)
        right.begin_tick(0, 2)
        left.push_input(InputEvent(1, 0, 0))
        left.push_input(InputEvent(1, 0, 1))
        right.push_input(InputEvent(1, 0, 1))
        right.push_input(InputEvent(1, 0, 0))
        self.assertEqual(left.tick_commit(), right.tick_commit())

    def test_input_backpressure_is_visible(self) -> None:
        transport = TileCycleTransport(DigitalSNN2Layer(), input_fifo_depth=2, output_fifo_depth=8)
        transport.begin_episode(1, 0, train=False)
        transport.begin_tick(0, 2)
        self.assertTrue(transport.push_input(InputEvent(1, 0, 0)))
        self.assertTrue(transport.push_input(InputEvent(1, 0, 1)))
        self.assertFalse(transport.push_input(InputEvent(1, 0, 2)))
        self.assertEqual(transport.rejected_input_events, 1)

    def test_commit_snapshot_survives_next_episode(self) -> None:
        network = DigitalSNN2Layer()
        transport = TileCycleTransport(network)
        host = HostTrainingController()
        events, label = make_dataset()[0]
        transport.begin_episode(10, label, train=True)
        for tick, active in enumerate(events):
            transport.begin_tick(tick, len(active))
            for synapse_id in active:
                self.assertTrue(transport.push_input(InputEvent(10, tick, synapse_id)))
            transport.tick_commit()
        transport.end_episode()
        transport.pop_output()
        transport.capture_commit(10)

        transport.begin_episode(11, label, train=True)
        transport.end_episode()
        hidden_modulator, output_modulator = host.teacher_modulator(label)
        transport.commit_modulator(10, hidden_modulator, output_modulator)
        self.assertNotIn(10, network.pending_commits)

    def test_output_spikes_are_timestamped(self) -> None:
        transport = TileCycleTransport(DigitalSNN2Layer(), output_fifo_depth=8)
        transport.begin_episode(1, 0, train=False)
        transport.begin_tick(0, 2)
        transport.push_input(InputEvent(1, 0, 0))
        transport.push_input(InputEvent(1, 0, 1))
        transport.tick_commit()
        transport.end_episode()
        spikes = transport.pop_output()
        self.assertTrue(all(event.episode_id == 1 for event in spikes))
        self.assertTrue(all(event.tick >= 0 for event in spikes))

    def test_event_count_mismatch_does_not_advance_tick(self) -> None:
        transport = TileCycleTransport(DigitalSNN2Layer())
        transport.begin_episode(1, 0, train=False)
        transport.begin_tick(0, 2)
        transport.push_input(InputEvent(1, 0, 0))
        with self.assertRaises(RuntimeError):
            transport.tick_commit()
        self.assertEqual(transport.next_tick, 0)
        self.assertEqual(len(transport.input_fifo), 1)

    def test_duplicate_synapse_is_rejected(self) -> None:
        transport = TileCycleTransport(DigitalSNN2Layer())
        transport.begin_episode(1, 0, train=False)
        transport.begin_tick(0, 2)
        transport.push_input(InputEvent(1, 0, 0))
        with self.assertRaises(ValueError):
            transport.push_input(InputEvent(1, 0, 0))
        self.assertEqual(transport.duplicate_input_events, 1)

    def test_route_flush_overflow_is_atomic(self) -> None:
        network = DigitalSNN2Layer()
        transport = TileCycleTransport(network, output_fifo_depth=1)
        transport.begin_episode(1, 0, train=False)
        network.pending_hidden = (0, 1)
        transport.output_fifo.append(SpikeEvent(1, 99, 0))
        before_pending = transport.network.pending_hidden
        with self.assertRaises(BackpressureError):
            transport.end_episode()
        self.assertEqual(transport.network.pending_hidden, before_pending)
        self.assertEqual(tuple(transport.output_fifo), (SpikeEvent(1, 99, 0),))
        self.assertEqual(transport.episode_id, 1)


if __name__ == "__main__":
    unittest.main()
