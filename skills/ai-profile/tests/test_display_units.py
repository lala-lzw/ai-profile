import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from display_units import display_spec, format_metric
from timeline_report import generate_timeline


CASES = [
    ("Read Total (Bytes/sec)","1150000000","1150 MB/s"),
    ("Write Total (Bytes/sec)","571290000","571.29 MB/s"),
    ("CPU 0 Core Frequency","1804800000","1804.8 MHz"),
    ("Used Memory","7602405376","7602.41 MB"),
    ("Clocks / Second","129940000","129.94 M cycles/s"),
    ("Fragments Shaded / Second","631380000","631.38 M/s"),
    ("Vertex Instructions / Second","339160000","339.16 M inst/s"),
    ("Fragment Instructions / Second","75070000000","75.07 G inst/s"),
    ("Fragment ALU Instructions / Sec (Full)","52020000000","52.02 G inst/s"),
    ("% Shaders Busy","85.126588","85.13 %"),
    ("GPU % Utilization","0.003214","0.003214 %"),
    ("Preemptions / second","99287.734555","99.29 K/s"),
    ("Avg Preemption Delay","4420390833203.615234","4.42 T"),
    ("Vendor Future Counter","1234567.000001","1.23 M"),
    ("Avg Bytes / Vertex","28.049578","28.05"),
]


class DisplayUnitsTests(unittest.TestCase):
    def test_units_follow_counter_meaning_without_fps_conversion(self):
        for column,raw,expected in CASES:
            with self.subTest(column=column):
                self.assertEqual(format_metric(column,raw),expected)
                self.assertEqual(format_metric(column,raw,readable=False),raw)
        self.assertNotIn("Hz",display_spec("Clocks / Second")["unit"])
        self.assertEqual(display_spec("Avg Preemption Delay")["unit"],"")
        self.assertEqual(format_metric("Counter","NaN"),"NaN")
        self.assertEqual(format_metric("Counter",""),"—")

    @unittest.skipUnless(shutil.which("node"),"Node viewer behavior checks")
    def test_html_formats_same_units_and_raw_toggle_preserves_original_cells(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=root/"native.csv"
            with raw.open("w",newline="",encoding="utf-8") as stream:
                writer=csv.writer(stream)
                writer.writerow([case[0] for case in CASES])
                writer.writerow([case[1] for case in CASES])
            output=root/"timeline.html"
            generate_timeline("units",{"raw_csv":str(raw)},output)
            bootstrap=Path(__file__).with_name("stage_filter_check.cjs").read_text(encoding="utf-8").split("assert.equal(run('stages.length'), 3);")[0]
            check=bootstrap+"\nconst cases="+json.dumps(CASES)+";\n"+r'''
for(const [column,raw,expected] of cases){
  assert.equal(run('formatMetric('+JSON.stringify(column)+','+JSON.stringify(raw)+')'),expected,column);
}
const view=run('views.find(view=>view.spec.id==="bandwidth")');
const paths=JSON.stringify(view.canvas.context.paths.filter(path=>path.color==="#137f83"));
elements.get('toggle-units').click();
for(const [column,raw] of cases){assert.equal(run('formatMetric('+JSON.stringify(column)+','+JSON.stringify(raw)+')'),raw);}
assert.equal(JSON.stringify(view.canvas.context.paths.filter(path=>path.color==="#137f83")),paths);
assert.equal(run('metricNodes.get("Vertex Instructions / Second").textContent'),'339160000');
elements.get('toggle-units').click();
assert.equal(run('metricNodes.get("Vertex Instructions / Second").textContent'),'339.16 M inst/s');
const rawRows=elements.get('raw-metrics').children;
assert.equal(rawRows.find(row=>row.children[0].textContent==='Avg Preemption Delay').children[1].textContent,'4420390833203.615234');
assert.equal(run('JSON.stringify(report.rawColumns)'),valuesBefore);
assert.equal(run('report.sourceBase64'),sourceBefore);
console.log('Display units and raw toggle verified.');
'''
            script=root/"check.cjs";script.write_text(check,encoding="utf-8")
            result=subprocess.run([shutil.which("node"),str(script),str(output)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=="__main__":unittest.main()
