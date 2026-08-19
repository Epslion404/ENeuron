import unittest
import random

from neuron_sim import ThreeFactorNeuron
from rtl_reference import RtlReferenceNeuron


class RtlReferenceTests(unittest.TestCase):
    def test_inference_does_not_update_learning_state_or_weights(self) -> None:
        neuron = RtlReferenceNeuron()
        neuron.pre_trace = [9, 7, 5, 3]
        neuron.post_trace = 11
        neuron.eligibility = [64, -64, 31, -31]
        neuron.threshold = 9
        before_weights = tuple(neuron.weights)
        before_trace = tuple(neuron.pre_trace)
        before_post = neuron.post_trace
        before_eligibility = tuple(neuron.eligibility)
        before_threshold = neuron.threshold
        neuron.tick((0, 1), learn_enable=False, tick=0)
        self.assertEqual(tuple(neuron.weights), before_weights)
        self.assertEqual(tuple(neuron.pre_trace), before_trace)
        self.assertEqual(neuron.post_trace, before_post)
        self.assertEqual(tuple(neuron.eligibility), before_eligibility)
        self.assertEqual(neuron.threshold, before_threshold)

    def test_signed_weight_and_state_saturate(self) -> None:
        neuron = RtlReferenceNeuron(init_weight=7)
        neuron.eligibility = [2047] * 4
        neuron.tick((), learn_enable=True, mod_valid=True, modulator=1, tick=0)
        self.assertEqual(tuple(neuron.weights), (7, 7, 7, 7))

    def test_refractory_blocks_next_tick(self) -> None:
        neuron = RtlReferenceNeuron(threshold=1, init_weight=2)
        first = neuron.tick((0,), tick=0)
        second = neuron.tick((0,), tick=1)
        self.assertEqual(first.spike, 1)
        self.assertEqual(second.spike, 0)

    def test_modulator_is_signed_and_delayed(self) -> None:
        neuron = RtlReferenceNeuron()
        neuron.eligibility[0] = 64
        before = tuple(neuron.weights)
        neuron.tick((), learn_enable=True, mod_valid=False, tick=0)
        self.assertEqual(tuple(neuron.weights), before)
        neuron.tick((), learn_enable=True, mod_valid=True, modulator=1, tick=1)
        self.assertGreater(neuron.weights[0], before[0])

    def test_signed_eligibility_decays_toward_zero(self) -> None:
        neuron = RtlReferenceNeuron()
        neuron.eligibility = [1, -1, 16, -16]
        neuron.tick((), tick=0)
        self.assertEqual(neuron.eligibility, [0, 0, 12, -12])

    def test_adaptive_threshold_rises_on_spike_then_relaxes(self) -> None:
        neuron = RtlReferenceNeuron(threshold=1, init_weight=2)
        fired = neuron.tick((0,), tick=0)
        self.assertEqual(fired.spike, 1)
        self.assertEqual(neuron.threshold, 2)
        neuron.tick((), tick=1)
        self.assertEqual(neuron.threshold, 1)

    def test_refractory_blocks_input_learning_state(self) -> None:
        neuron = RtlReferenceNeuron(threshold=1, init_weight=2, refractory_length=2)
        neuron.tick((0,), tick=0)
        before_current = neuron.current
        before_pre = tuple(neuron.pre_trace)
        before_eligibility = tuple(neuron.eligibility)
        neuron.tick((1,), tick=1)
        self.assertLess(neuron.current, before_current)
        self.assertEqual(tuple(neuron.pre_trace)[1], 0)
        self.assertEqual(tuple(neuron.eligibility)[1], 0)
        self.assertNotEqual(tuple(neuron.pre_trace), before_pre)
        self.assertNotEqual(tuple(neuron.eligibility), before_eligibility)

    def test_algorithm_and_rtl_reference_are_cycle_exact(self) -> None:
        rng = random.Random(19)
        algorithm = ThreeFactorNeuron(4)
        reference = RtlReferenceNeuron(n_inputs=4)

        for tick in range(128):
            active = tuple(index for index in range(4) if rng.random() < 0.3)
            modulator = rng.choice((-1, 0, 0, 0, 1))
            fired = algorithm.step(active, tick=tick, learn_enable=True)
            if modulator:
                algorithm.apply_modulator(modulator)
            state = reference.tick(
                active,
                learn_enable=True,
                mod_valid=modulator != 0,
                modulator=modulator,
                tick=tick,
            )

            self.assertEqual(state.current, algorithm.current, f"tick={tick} current")
            self.assertEqual(state.membrane, algorithm.v, f"tick={tick} membrane")
            self.assertEqual(state.spike, fired, f"tick={tick} spike")
            self.assertEqual(state.refractory, algorithm.refractory, f"tick={tick} refractory")
            self.assertEqual(state.threshold, algorithm.threshold, f"tick={tick} threshold")
            self.assertEqual(state.post_trace, algorithm.post_trace, f"tick={tick} post_trace")
            self.assertEqual(state.weights, tuple(algorithm.weights), f"tick={tick} weights")
            self.assertEqual(state.pre_trace, tuple(algorithm.pre_trace), f"tick={tick} pre_trace")
            self.assertEqual(state.eligibility, tuple(algorithm.eligibility), f"tick={tick} eligibility")


if __name__ == "__main__":
    unittest.main()
