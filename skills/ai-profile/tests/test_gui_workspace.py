from pathlib import Path
import sys
import time
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from gui_workspace import PerfDogGui


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk()
        self.root.withdraw()
        self.manager=SimpleNamespace(
            adb=SimpleNamespace(serial=None),collector=SimpleNamespace(),
            get_current_session=Mock(return_value=None),start_session=Mock(),
            stop_session=Mock(),add_marker=Mock(return_value={"name":"Boss","time_s":2}),
        )
        self.app=PerfDogGui(self.root,self.manager,monitor=False)

    def tearDown(self):
        self.app.closed=True
        self.app.poll_stop.set()
        for timer in self.root.tk.call("after","info"):
            self.root.after_cancel(timer)
        self.root.destroy()

    def recording(self):
        self.app._on_start_success({"start_time":time.time(),"period_ms":200,
            "package":"com.example.game","serial":"device-a","labels":[],
            "device_env":{"model":"Test Phone"}})

    def test_opening_panel_does_not_start_a_recording(self):
        self.manager.start_session.assert_not_called()
        self.assertEqual(self.app.state,"idle")
        self.assertEqual(str(self.app.stop_btn["state"]),"disabled")
        self.assertEqual(self.app.group_var.get(),"GPU")
        self.assertEqual(self.app.charts[0][1].series[0][0],"GPU % Utilization")
        self.assertEqual(self.app.charts[2][1].series[0][1],"% Shaders Busy")

    def test_pause_only_freezes_charts_and_stop_discards_late_samples(self):
        self.recording()
        sample={"source_line":2,"GPU % Utilization":0,"counter_ready":True,"cli_raw":{"GPU % Utilization":"0.000000"}}
        self.app._on_sample((self.app.generation,sample))
        self.app._toggle_pause()
        self.app._on_sample((self.app.generation,{**sample,"source_line":7}))
        self.assertEqual(len(self.app.history),2)
        self.assertEqual(len(self.app.charts[0][1].history),1)
        self.assertEqual(self.app.metric_labels["GPU % Utilization"]["text"],"0 %")
        self.assertEqual(self.app.metric_labels["% Shaders Busy"]["text"],"—")
        self.manager.stop_session.assert_not_called()
        generation=self.app.generation
        self.app._background=Mock()
        self.app._on_stop()
        self.app._on_sample((generation,sample))
        self.assertEqual(len(self.app.history),2)
        self.assertEqual(self.app.state,"stopping")

    def test_marker_retained_after_completion_and_report_ready(self):
        self.recording()
        self.app.tag_entry.insert(0,"Boss")
        self.app._on_add_tag()
        self.assertEqual(len(self.app.markers),1)
        self.app.auto_open_var.set(False)
        self.app._on_stop_done({"timeline_html":Path("test/timeline.html"),"labels_count":1})
        self.app._draw_charts(force=True)
        self.assertEqual(len(self.app.charts[0][1].markers),1)
        self.assertEqual(str(self.app.report_btn["state"]),"normal")

    def test_restore_existing_session_without_starting_another(self):
        self.manager.get_current_session.return_value={"start_time":time.time()-4,
            "period_ms":200,"package":"com.example.game","serial":"device-a",
            "device_env":{"model":"Test Phone"},"labels":[{"name":"Scene","time_s":1}]}
        self.app._restore_session()
        self.manager.start_session.assert_not_called()
        self.assertEqual(self.app.state,"recording")
        self.assertEqual(self.manager.adb.serial,"device-a")
        self.assertEqual(self.app.tag_listbox.size(),1)

    def test_invalid_interval_does_not_reach_sampler(self):
        self.app.period_var.set("invalid")
        with patch("gui_workspace.messagebox.showerror") as error:
            self.app._on_start()
        error.assert_called_once()
        self.manager.start_session.assert_not_called()

    def test_raw_table_keeps_unknown_cli_fields_and_separates_system_gpu(self):
        self.recording()
        sample={"source_line":89,"% Shaders Busy":60,"counter_ready":True,
                "cli_raw":{"% Shaders Busy":"60.000000","Avg Preemption Delay":"4420390833203.615234","CPU 0 Core Utilization":"20.000000"}}
        self.app._on_sample((self.app.generation,sample))
        self.assertEqual(self.app.metric_labels["GPU % Utilization"]["text"],"—")
        self.assertEqual(self.app.metric_labels["% Shaders Busy"]["text"],"60 %")
        rows=[self.app.raw_table.item(item,"values") for item in self.app.raw_table.get_children()]
        self.assertEqual({row[0] for row in rows},set(sample["cli_raw"]))
        delay=next(row for row in rows if row[0]=="Avg Preemption Delay")
        self.assertEqual(delay[1],"4420390833203.615234")
        self.assertTrue(delay[2])
        self.app._on_sample((self.app.generation,sample))
        self.assertEqual(len(self.app.history),1)

    def test_small_raw_percent_is_not_rounded_to_zero_on_plot_axis(self):
        self.recording()
        sample={"source_line":2,"counter_ready":True,"cli_raw":{"GPU % Utilization":"0.003214"},
                "cli_metrics":{"GPU % Utilization":0.003214}}
        self.app._on_sample((self.app.generation,sample))
        chart=self.app.charts[0][1]
        with patch.object(chart.canvas,"winfo_width",return_value=700),patch.object(chart.canvas,"winfo_height",return_value=174):
            chart.draw()
        texts=[chart.canvas.itemcget(item,"text") for item in chart.canvas.find_all() if chart.canvas.type(item)=="text"]
        self.assertTrue(any(text.startswith("0.00") and float(text)>0 for text in texts if text and text[0].isdigit()))

    def test_fps_updates_while_cli_is_waiting_and_is_kept_separate(self):
        self.recording()
        sample={"counter_ready":False,"cli_raw":{},"cli_metrics":{},
                "fps_sample":{"fps":59.9,"source":"SurfaceFlinger actualPresentTime","status":"ok"},
                "fps_elapsed_s":1.25}
        self.app._on_sample((self.app.generation,sample))
        self.assertEqual(self.app.metric_labels["FPS"]["text"],"59.90")
        self.assertEqual(len(self.app.fps_history),1)
        self.assertEqual(len(self.app.history),0)
        self.assertEqual(self.app.last_cli,{})

    def test_live_curve_keeps_all_rows_between_preview_refreshes(self):
        self.recording()
        samples=[{"source_line":i+2,"counter_ready":True,
                  "cli_raw":{"GPU % Utilization":value},"cli_metrics":{"GPU % Utilization":float(value)}}
                 for i,value in enumerate(("1.000000","65.272817","2.000000","3.000000","4.000000"))]
        self.app._on_sample((self.app.generation,{**samples[-1],"samples":samples,"reset_stream":True}))
        self.assertEqual(len(self.app.history),5)
        self.assertEqual(self.app.charts[0][1].history[1]["cli_raw"]["GPU % Utilization"],"65.272817")
        self.assertEqual(self.app.metric_labels["GPU % Utilization"]["text"],"4 %")
        self.app._on_sample((self.app.generation,{**samples[-1],"samples":samples}))
        self.assertEqual(len(self.app.history),5)

    def test_graph_axis_and_time_window_follow_configured_sampling_period(self):
        self.recording()
        self.app.sample_period_ms=500
        sample={"source_line":122,"counter_ready":True,"cli_raw":{"GPU % Utilization":"9.123456"},
                "cli_metrics":{"GPU % Utilization":9.123456}}
        self.app._on_sample((self.app.generation,sample))
        chart=self.app.charts[0][1]
        self.assertEqual(chart.elapsed_at(122),60)

        self.assertEqual(chart.window_s,120)
        with patch.object(chart.canvas,"winfo_width",return_value=700),patch.object(chart.canvas,"winfo_height",return_value=174):
            chart.draw()
        texts=[chart.canvas.itemcget(item,"text") for item in chart.canvas.find_all() if chart.canvas.type(item)=="text"]
        self.assertTrue(any(":" in text for text in texts))
        self.assertFalse(any(text.startswith("L") and text[1:].isdigit() for text in texts))
        self.app.session=None
        self.app._draw_charts(force=True)
        self.assertEqual(chart.elapsed_at(122),60)

    def test_readable_axis_preserves_plot_values_and_raw_table(self):
        self.recording()
        samples=[{"source_line":i+2,"counter_ready":True,
                  "cli_raw":{"Read Total (Bytes/sec)":text,"GPU % Utilization":"9.123456"},
                  "cli_metrics":{"Read Total (Bytes/sec)":float(text),"GPU % Utilization":9.123456}}
                 for i,text in enumerate(("1000000000.123456","2000000000.654321"))]
        self.app._on_sample((self.app.generation,{**samples[-1],"samples":samples}))
        chart=next(chart for _,chart in self.app.charts if chart.series[0][0]=="Read Total (Bytes/sec)")
        with patch.object(chart.canvas,"winfo_width",return_value=700),patch.object(chart.canvas,"winfo_height",return_value=174):
            chart.draw()
            before=[chart.canvas.coords(item) for item in chart.canvas.find_all()
                    if chart.canvas.type(item)=="line" and chart.canvas.itemcget(item,"fill")=="#54c9ba"]
            texts=[chart.canvas.itemcget(item,"text") for item in chart.canvas.find_all() if chart.canvas.type(item)=="text"]
            self.assertIn("MB/s",texts)
            self.assertEqual(self.app.metric_labels["GPU % Utilization"]["text"],"9.12 %")
            self.app.readable_var.set(False)
            self.app._refresh_units()
            after=[chart.canvas.coords(item) for item in chart.canvas.find_all()
                   if chart.canvas.type(item)=="line" and chart.canvas.itemcget(item,"fill")=="#54c9ba"]
            self.assertEqual(before,after)
        self.assertEqual(self.app.metric_labels["GPU % Utilization"]["text"],"9.123456")
        raw_rows=[self.app.raw_table.item(item,"values") for item in self.app.raw_table.get_children()]
        self.assertEqual(next(row[1] for row in raw_rows if row[0]=="Read Total (Bytes/sec)"),"2000000000.654321")
        self.assertEqual(self.app.history[-1]["cli_metrics"]["Read Total (Bytes/sec)"],2000000000.654321)




if __name__=="__main__": unittest.main()
