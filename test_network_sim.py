import unittest

from network_sim import DigitalSNN2Layer, HostTrainingController, make_dataset, make_noisy_dataset


class NetworkSimulationTests(unittest.TestCase):
    def test_host_training_separates_two_classes(self) -> None:
        network = DigitalSNN2Layer()
        host = HostTrainingController()
        history = host.train(network, make_dataset(), epochs=30, seed=7)
        self.assertGreaterEqual(history[-1], 0.5)
        self.assertEqual(host.evaluate(network, make_dataset()), 1.0)

    def test_host_training_specializes_hidden_and_output_weights(self) -> None:
        network = DigitalSNN2Layer()
        host = HostTrainingController()
        host.train(network, make_dataset(), epochs=30, seed=7)
        self.assertGreater(network.hidden[0].weights[2], network.hidden[0].weights[0])
        self.assertGreater(network.hidden[1].weights[0], network.hidden[1].weights[2])
        self.assertGreater(network.output[0].weights[0], network.output[0].weights[1])
        self.assertGreater(network.output[1].weights[1], network.output[1].weights[0])

    def test_inference_freezes_all_network_weights(self) -> None:
        network = DigitalSNN2Layer()
        host = HostTrainingController()
        host.train(network, make_dataset(), epochs=10, seed=7)
        before = [list(neuron.weights) for neuron in network.neurons]
        host.evaluate(network, make_noisy_dataset(seed=11, count=20))
        after = [list(neuron.weights) for neuron in network.neurons]
        self.assertEqual(before, after)

    def test_inference_freezes_all_learning_state(self) -> None:
        network = DigitalSNN2Layer()
        network.begin_episode(label=0, train=False)
        for neuron in network.neurons:
            neuron.pre_trace = [17 for _ in neuron.pre_trace]
            neuron.post_trace = 23
            neuron.eligibility = [31 for _ in neuron.eligibility]
            neuron.threshold = neuron.base_threshold + 2
        before = [
            (tuple(neuron.pre_trace), neuron.post_trace, tuple(neuron.eligibility), neuron.threshold)
            for neuron in network.neurons
        ]
        network.step_tick((0, 1), tick=0)
        network.flush_route(1)
        network.end_episode()
        after = [
            (tuple(neuron.pre_trace), neuron.post_trace, tuple(neuron.eligibility), neuron.threshold)
            for neuron in network.neurons
        ]
        self.assertEqual(before, after)

    def test_noisy_dataset_remains_separable(self) -> None:
        network = DigitalSNN2Layer()
        host = HostTrainingController()
        host.train(network, make_dataset(), epochs=30, seed=7)
        accuracy = host.evaluate(network, make_noisy_dataset(seed=3, count=100))
        self.assertGreaterEqual(accuracy, 0.9)

    def test_complexity_counts_two_layers(self) -> None:
        complexity = DigitalSNN2Layer().complexity()
        self.assertEqual(complexity["neuron_count"], 4)
        self.assertEqual(complexity["synapse_count"], 12)
        self.assertGreater(complexity["state_bits_proxy"], 0)

    def test_reward_protocol_is_addressable(self) -> None:
        network = DigitalSNN2Layer()
        result = network.inference(make_dataset()[0][0], label=1)
        hidden, output = HostTrainingController.reward_modulator(label=1, result=result)
        self.assertEqual(len(hidden), 2)
        self.assertEqual(len(output), 2)

    def test_wta_allows_at_most_one_spike_per_layer_and_tick(self) -> None:
        network = DigitalSNN2Layer(hidden_wta=True, output_wta=True)
        network.begin_episode(label=0, train=False)
        for neuron in network.neurons:
            neuron.threshold = 1
        hidden, output = network.step_tick((0, 1), tick=0)
        self.assertLessEqual(sum(hidden), 1)
        self.assertLessEqual(sum(output), 1)

    def test_hybrid_host_training_supports_reward_readout(self) -> None:
        network = DigitalSNN2Layer(hidden_wta=True, output_wta=True, init_seed=5)
        host = HostTrainingController()
        host.train_hybrid(network, make_dataset(), feature_epochs=30, reward_epochs=100, seed=5)
        self.assertEqual(host.evaluate(network, make_dataset()), 1.0)

    def test_cycle_interface_has_one_tick_route_latency(self) -> None:
        network = DigitalSNN2Layer()
        network.begin_episode(label=0, train=False)
        network.hidden[0].threshold = 1
        network.hidden[1].threshold = 1
        network.output[0].threshold = 1
        network.output[1].threshold = 1
        hidden_now, output_now = network.step_tick((0,), tick=0)
        self.assertEqual(output_now, (0, 0))
        self.assertEqual(hidden_now, (1, 1))
        _, output_next = network.step_tick((), tick=1)
        self.assertNotEqual(output_next, (0, 0))

    def test_delayed_commit_is_independent_of_host_latency(self) -> None:
        immediate = DigitalSNN2Layer()
        delayed = DigitalSNN2Layer()
        host = HostTrainingController()
        for commit_id, (events, label) in enumerate(make_dataset()):
            for network in (immediate, delayed):
                network.run_episode(events, label=label, train=True)
                network.capture_commit(commit_id)
            hidden_modulator, output_modulator = host.teacher_modulator(label)
            immediate.apply_host_modulator(hidden_modulator, output_modulator, commit_id=commit_id)
            # 在等待主机期间先运行下一 episode，快照应保证结果仍然一致。
            delayed.apply_host_modulator(hidden_modulator, output_modulator, commit_id=commit_id)
        self.assertEqual(
            [list(neuron.weights) for neuron in immediate.neurons],
            [list(neuron.weights) for neuron in delayed.neurons],
        )

    def test_commit_order_is_explicit_and_snapshot_has_metadata(self) -> None:
        network = DigitalSNN2Layer(max_pending_commits=2)
        host = HostTrainingController()
        dataset = make_dataset()
        for commit_id, (events, label) in enumerate(dataset, start=10):
            network.run_episode(events, label=label, train=True)
            commit = network.capture_commit(commit_id)
            self.assertEqual(commit.commit_id, commit_id)
            self.assertEqual(commit.episode_id, commit_id - 10)
            self.assertEqual(commit.weight_epoch, 0)

        before = [list(neuron.weights) for neuron in network.neurons]
        hidden, output = host.teacher_modulator(dataset[1][1])
        with self.assertRaises(ValueError):
            network.apply_host_modulator(hidden, output, commit_id=11)
        self.assertEqual(before, [list(neuron.weights) for neuron in network.neurons])

        hidden, output = host.teacher_modulator(dataset[0][1])
        network.apply_host_modulator(hidden, output, commit_id=10)
        hidden, output = host.teacher_modulator(dataset[1][1])
        network.apply_host_modulator(hidden, output, commit_id=11)
        self.assertEqual(network.weight_epoch, 2)

    def test_pending_commit_capacity_is_bounded(self) -> None:
        network = DigitalSNN2Layer(max_pending_commits=1)
        dataset = make_dataset()
        network.run_episode(*dataset[0], train=True)
        network.capture_commit(0)
        network.run_episode(*dataset[1], train=True)
        with self.assertRaises(RuntimeError):
            network.capture_commit(1)


if __name__ == "__main__":
    unittest.main()
