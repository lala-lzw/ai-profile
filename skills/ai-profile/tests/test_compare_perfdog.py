import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import compare_perfdog as cp


class CompareTests(unittest.TestCase):
    def test_bin_means_skips_missing_and_out_of_range(self):
        points = [(0.5, 1.0), (1.5, 3.0), (6.0, None), (7.0, 5.0), (99.0, 9.0)]
        self.assertEqual(cp.bin_means(points, 0, 10, 5), [2.0, 5.0])

    def test_identical_series_correlate_fully(self):
        a = [1.0, 3.0, 2.0, 5.0, 4.0]
        res = cp.compare_series(a, list(a))
        self.assertAlmostEqual(res["r"], 1.0)
        self.assertEqual(res["direction"], 1.0)
        self.assertEqual(res["gap"], 0.0)

    def test_constant_series_has_no_correlation(self):
        res = cp.compare_series([1.0] * 5, [1.0, 2.0, 3.0, 2.0, 1.0])
        self.assertIsNone(res["r"])

    def test_too_few_pairs(self):
        self.assertIsNone(cp.compare_series([1.0, None], [1.0, 2.0])["r"])


if __name__ == "__main__":
    unittest.main()
