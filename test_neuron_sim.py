import unittest

from neuron_sim import CounterIFNeuron, ThreeFactorNeuron, make_trial


class NeuronSimulationTests(unittest.TestCase):
    def test_inference_freezes_weights(self) -> None:
        neuron = ThreeFactorNeuron(4)
        before = list(neuron.weights)
        neuron.inference(make_trial(1), label=1)
        self.assertEqual(before, neuron.weights)

    def test_three_factor_separates_equal_count_patterns(self) -> None:
        neuron = ThreeFactorNeuron(4)
        for _ in range(30):
            neuron.run_trial(make_trial(1), label=1, modulator=1, train=True)
            neuron.run_trial(make_trial(0), label=0, modulator=-1, train=True)
        positive = neuron.inference(make_trial(1), label=1)
        negative = neuron.inference(make_trial(0), label=0)
        self.assertGreater(positive.spike_count, negative.spike_count)
        self.assertGreater(neuron.weights[0], neuron.weights[2])

    def test_counter_has_refractory_gap(self) -> None:
        neuron = CounterIFNeuron(1)
        events = ((0,), (0,), (0,), (0,))
        result = neuron.inference(events)
        self.assertEqual(result.spike_ticks, (2,))

    def test_weights_do_not_wrap(self) -> None:
        neuron = ThreeFactorNeuron(1)
        neuron.weights[0] = neuron.weight_max
        neuron.eligibility[0] = 1000
        neuron.apply_modulator(1)
        self.assertEqual(neuron.weights[0], neuron.weight_max)

    def test_delayed_modulator_commits_existing_eligibility(self) -> None:
        neuron = ThreeFactorNeuron(4)
        before = list(neuron.weights)
        neuron.run_trial(make_trial(1), label=1, train=False, learn_enable=True)
        self.assertNotEqual(neuron.eligibility, [0, 0, 0, 0])
        neuron.apply_modulator(1)
        self.assertNotEqual(before, neuron.weights)

    def test_zero_modulator_does_not_change_weights(self) -> None:
        neuron = ThreeFactorNeuron(4)
        before = list(neuron.weights)
        neuron.run_trial(make_trial(1), label=1, train=False, learn_enable=True)
        neuron.apply_modulator(0)
        self.assertEqual(before, neuron.weights)

    def test_event_order_within_step_does_not_change_result(self) -> None:
        left = ThreeFactorNeuron(4)
        right = ThreeFactorNeuron(4)
        left.step((0, 1), tick=0)
        right.step((1, 0), tick=0)
        self.assertEqual(left.current, right.current)
        self.assertEqual(left.v, right.v)
        self.assertEqual(left.eligibility, right.eligibility)

    def test_leaky_state_returns_to_zero_without_input(self) -> None:
        neuron = ThreeFactorNeuron(1)
        neuron.current = 100
        neuron.v = 100
        for tick in range(32):
            neuron.step((), tick=tick)
        self.assertEqual(neuron.current, 0)
        self.assertEqual(neuron.v, 0)


if __name__ == "__main__":
    unittest.main()
