from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from live_metrics import LiveMetricsReader, parse_counter_tail


class LiveMetricsTests(unittest.TestCase):
    def test_partial_tail_falls_back_without_reformatting_cells(self):
        values=parse_counter_tail("Clocks / Second,GPU % Utilization\n80000000.123456,0.000006\n999\n")
        self.assertEqual(values,{"Clocks / Second":"80000000.123456","GPU % Utilization":"0.000006"})
        self.assertEqual(parse_counter_tail("Counter\nNaN\n"),{"Counter":"NaN"})

    def test_reads_fixed_complete_source_line_and_keeps_long_decimals(self):
        bridge=SimpleNamespace(shell=Mock(return_value=SimpleNamespace(ok=True,stderr="",stdout=
            "/data/local/tmp/test/counters.csv\n89\nAvg Preemption Delay,GPU % Utilization,\n4420390833203.615234,0.003214,")))
        reader=LiveMetricsReader(bridge)
        reader.source_file="/data/local/tmp/test/counters.csv"
        reader.source_line=88
        sample=reader.read({"remote_tmp_dir":"/data/local/tmp/test"})
        self.assertEqual(sample["source_line"],89)
        self.assertEqual(sample["cli_raw"]["Avg Preemption Delay"],"4420390833203.615234")
        self.assertEqual(sample["cli_raw"]["GPU % Utilization"],"0.003214")
        self.assertTrue(sample["findings"])
        command=bridge.shell.call_args.args[0]
        self.assertIn("wc -l",command)
        self.assertIn("sed -n",command)
        self.assertNotIn("kill",command)
        self.assertNotIn("sdpcli r",command)

    def test_polling_keeps_every_new_row_including_a_short_spike(self):
        bridge=SimpleNamespace(shell=Mock(side_effect=[
            SimpleNamespace(ok=True,stderr="",stdout="/tmp/session/c.csv\n6\nGPU % Utilization,\n1.000000,\n2.000000,\n65.272817,\n3.000000,\n4.000000,"),
            SimpleNamespace(ok=True,stderr="",stdout="/tmp/session/c.csv\n8\nGPU % Utilization,\n5.000000,\n6.000000,"),
            SimpleNamespace(ok=True,stderr="",stdout="/tmp/session/c.csv\n8\nGPU % Utilization,"),
        ]))
        reader=LiveMetricsReader(bridge)
        first=reader.read({"remote_tmp_dir":"/tmp/session"})
        self.assertEqual([row["source_line"] for row in first["samples"]],[2,3,4,5,6])
        self.assertEqual(first["samples"][2]["cli_raw"]["GPU % Utilization"],"65.272817")
        second=reader.read({"remote_tmp_dir":"/tmp/session"})
        self.assertEqual([row["source_line"] for row in second["samples"]],[7,8])
        self.assertFalse(second["reset_stream"])
        self.assertIn("then start=7",bridge.shell.call_args.args[0])
        self.assertFalse(reader.read({"remote_tmp_dir":"/tmp/session"})["counter_ready"])

    def test_new_cli_file_resets_cursor_without_losing_first_rows(self):
        bridge=SimpleNamespace(shell=Mock(return_value=SimpleNamespace(ok=True,stderr="",stdout="/tmp/new.csv\n3\nCounter\n1.123456\n2.654321")))
        reader=LiveMetricsReader(bridge)
        reader.source_file="/tmp/old.csv";reader.source_line=100
        result=reader.read({"remote_tmp_dir":"/tmp"})
        self.assertTrue(result["reset_stream"])
        self.assertEqual([sample["source_line"] for sample in result["samples"]],[2,3])

    def test_idle_preview_does_not_start_or_read_a_sampler(self):
        bridge=SimpleNamespace(shell=Mock())
        result=LiveMetricsReader(bridge).read({})
        self.assertFalse(result["counter_ready"])
        bridge.shell.assert_not_called()


if __name__=="__main__": unittest.main()
