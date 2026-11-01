import re
import statistics
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


class ExampleDatasetTests(unittest.TestCase):
    """脱敏示例数据应复现文档中的结论。"""

    EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "iqoo10-demo"

    def run_example(self, align):
        results, _ = cp.build(self.EXAMPLE, self.EXAMPLE / "perfdog" / "perfdog_gpu_counters.csv",
                              5.0, align, "scene", "end")
        return results

    def test_calibrated_matches_documented_result(self):
        results = self.run_example("calibrated")
        gpu = [s["r"] for name, s in results.items() if name != "FPS"]
        self.assertEqual(len(gpu), 28)
        self.assertAlmostEqual(statistics.median(gpu), 0.937, places=3)
        self.assertEqual(sum(r >= 0.9 for r in gpu), 21)
        self.assertLess(results["FPS"]["r"], 0.2)

    def test_shift_only_is_worse(self):
        gpu = [s["r"] for name, s in self.run_example("shift").items() if name != "FPS"]
        self.assertAlmostEqual(statistics.median(gpu), 0.576, places=3)

    def test_example_has_no_identifying_strings(self):
        """示例数据只允许出现占位包名 com.example.demo，且不含本机路径。"""
        foreign_package = re.compile(r"com\.(?!example\.demo|android\.)[a-z]\w*\.[a-z]\w*")
        for path in self.EXAMPLE.rglob("*"):
            if path.is_file() and path.suffix in {".csv", ".json", ".html", ".md"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
                self.assertIsNone(foreign_package.search(text), f"外部包名出现在 {path.name}")
                for word in ("Administrator", "C:\\Users", "tencent"):
                    self.assertNotIn(word, text, f"{word} 出现在 {path.name}")


if __name__ == "__main__":
    unittest.main()
