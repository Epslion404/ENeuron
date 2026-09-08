import unittest

from pulse_mini_pruned_network_4x8x2_cosim import (
    compile_public_interfaces,
    run_host_error_and_latching_contract,
    run_network_contract,
)


class PulseMiniPrunedNetwork4x8x2Tests(unittest.TestCase):
    def test_l_and_l2_public_interfaces_compile(self) -> None:
        compile_public_interfaces()

    def test_route_training_commit_clear_and_accounting_contract(self) -> None:
        run_network_contract()

    def test_host_error_and_accepted_fields_are_latched(self) -> None:
        run_host_error_and_latching_contract()


if __name__ == "__main__":
    unittest.main()
