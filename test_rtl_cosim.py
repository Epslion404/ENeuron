import unittest

from rtl_cosim import run


class RtlCosimTests(unittest.TestCase):
    def test_multiple_random_traces_and_control_cycles(self) -> None:
        for seed in (0, 1, 7, 19, 31):
            run(seed=seed, ticks=128)


if __name__ == "__main__":
    unittest.main()
