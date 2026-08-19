"""多周期数字神经元的事务级回归。"""

import unittest

from rtl_multicycle_cosim import run


class MulticycleRtlCosimTests(unittest.TestCase):
    def test_random_transaction_streams(self) -> None:
        for seed in (0, 1, 7, 19, 31):
            run(seed=seed, transaction_count=128, n_inputs=4)

    def test_scan_boundaries_and_non_power_of_two_inputs(self) -> None:
        for n_inputs in (1, 3, 5):
            run(seed=101 + n_inputs, transaction_count=64, n_inputs=n_inputs)


if __name__ == "__main__":
    unittest.main()
