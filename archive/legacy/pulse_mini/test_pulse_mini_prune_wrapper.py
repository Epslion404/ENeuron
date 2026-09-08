import unittest

from pulse_mini_prune_wrapper_cosim import (
    compile_public_interfaces,
    run_auto_clear_contract,
    run_bypass_bit_exact_contract,
    run_feedback_contract,
    run_tick_gate_contract,
)


class PulseMiniPruneWrapperTests(unittest.TestCase):
    def test_public_wrapper_interfaces_compile(self) -> None:
        compile_public_interfaces()

    def test_feedback_observes_exactly_once_before_success_is_visible(self) -> None:
        run_feedback_contract()

    def test_commit_clear_policy_supports_single_core_and_network_barrier(self) -> None:
        run_auto_clear_contract()

    def test_tick_applies_mask_and_separates_refractory_skips(self) -> None:
        run_tick_gate_contract()

    def test_uncommitted_mask_is_bit_exact_with_bare_cores(self) -> None:
        run_bypass_bit_exact_contract()


if __name__ == "__main__":
    unittest.main()
