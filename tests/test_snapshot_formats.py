"""Supported spreadsheet formats, literal CSV cells and standalone release behavior."""
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_state import ROOT, LATER, base
from test_review import snapshot


class SnapshotFormatTests(unittest.TestCase):
    def test_csv_preserves_role_counts_markers_and_literal_values(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory); path = workspace / "state.json"
            state = base()
            state["companies"][0]["name"] = '=HYPERLINK("https://unsafe.example","Demo")'
            state["opportunities"][0]["title"] = 'Senior, "API" Engineer\nPlatform'
            state["opportunities"][0]["fit_summary"] = '\t=1+1'
            state["opportunities"][1]["fit_summary"] = '  @SUM(1,2)'
            raw = json.dumps(state).encode(); path.write_bytes(raw)
            result = snapshot.export_snapshot(path, workspace, LATER, "csv")
            rows = list(csv.reader(io.StringIO(Path(result["path"]).read_text(encoding="utf-8-sig"))))
            self.assertIn("GENERATED SNAPSHOT", rows[1][0]); self.assertIn("state revision 0", rows[1][0])
            self.assertIn("2 unique roles", rows[2][0]); self.assertIn("0 confirmed-sent roles", rows[2][0])
            self.assertEqual(rows[3], ["State SHA-256", hashlib.sha256(raw).hexdigest()])
            self.assertEqual(rows[5], snapshot.HEADERS); self.assertEqual(len(rows[6:]), 2)
            self.assertEqual(rows[6][0], "'" + state["companies"][0]["name"])
            self.assertEqual(rows[6][1], state["opportunities"][0]["title"])
            self.assertEqual(rows[6][3], "'\t=1+1"); self.assertEqual(rows[7][3], "'  @SUM(1,2)")
            self.assertEqual(path.read_bytes(), raw)
            for value in ("=1", "+cmd", " -1", "@value", "\rtext", "\ntext", "\ttext"):
                self.assertTrue(snapshot.csv_literal(value).startswith("'"))
            self.assertEqual(snapshot.csv_literal("Ordinary text"), "Ordinary text")

    def test_csv_manual_edits_and_staleness_preserve_state_and_view(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory); path = workspace / "state.json"; path.write_text(json.dumps(base()))
            snapshot.export_snapshot(path, workspace, LATER, "csv")
            self.assertFalse(snapshot.snapshot_status(path, workspace, "csv")["stale"])
            state = base(); state["revision"] = 1; path.write_text(json.dumps(state))
            self.assertTrue(snapshot.snapshot_status(path, workspace, "csv")["stale"])
            view = workspace / "Career.csv"; manual = view.read_bytes() + b'"Manual note"\r\n'; view.write_bytes(manual)
            state_raw = path.read_bytes()
            result = snapshot.export_snapshot(path, workspace, LATER, "csv")
            self.assertFalse(result["written"]); self.assertTrue(result["manual_change"])
            self.assertEqual(view.read_bytes(), manual); self.assertEqual(path.read_bytes(), state_raw)

    def test_unsupported_formats_fail_before_any_output_or_state_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); workspace = root / "absent"
            for format in ("html", "../../outside", "pdf"):
                with self.assertRaises(snapshot.cs.Invalid): snapshot.export_snapshot(root / "missing.json", workspace, LATER, format)
                with self.assertRaises(snapshot.cs.Invalid): snapshot.snapshot_status(root / "missing.json", workspace, format)
            self.assertFalse(workspace.exists())

    def test_fresh_bundle_supports_only_spreadsheet_reports_outside_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); bundle = root / "career-agent"; workspace = root / "private"
            built = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/build_skill_bundle.py"), str(bundle)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            workspace.mkdir(); path = workspace / "state.json"; path.write_text(json.dumps(base()))
            command = [sys.executable, "-B", str(bundle / "scripts/career_snapshot.py"), "export", str(path), str(workspace), "--as-of", LATER]
            for format in ("xlsx", "csv"):
                result = subprocess.run(command + ["--format", format], cwd=root, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr); self.assertTrue((workspace / ("Career." + format)).is_file())
            result = subprocess.run(command + ["--format", "html"], cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2); self.assertFalse((workspace / "Career.html").exists())
            self.assertEqual(sorted(p.suffix for p in bundle.rglob("*") if p.is_file() and p.suffix in {".html", ".htm"}), [])
            # Inspect the built module, rather than relying on source-only producer checks.
            probe = subprocess.run([sys.executable, "-B", "-c", "import sys;sys.path.insert(0,sys.argv[1]);import career_snapshot as s;assert not hasattr(s,'html_bytes')", str(bundle / "scripts")], cwd=root, capture_output=True, text=True)
            self.assertEqual(probe.returncode, 0, probe.stderr)


if __name__ == "__main__":
    unittest.main()
