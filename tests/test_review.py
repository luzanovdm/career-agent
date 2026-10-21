"""Regressions for independently reproduced review findings, using synthetic data only."""
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
import zipfile

from test_state import cs, ROOT, AT, LATER, base, attempt, answer, response
sys.path.insert(0, str(ROOT / "scripts"))
import career_snapshot as snapshot


def complete_coverage(checked="2026-01-15T12:05:00Z", status="complete"):
    return {"id": "coverage-a", "opportunity_id": "role-a", "status": status,
            "channels": ["inbox", "portal"], "checked_at": checked, "through": LATER}


def history(**extra):
    return {"source_locator": "synthetic-history-list", "employer": "Northstar Demo", "role": "API Engineer",
            "role_url": "https://northstar-demo.example/jobs/api-1?utm_source=demo", "status": "sent",
            "event_kind": "initial_application", "date_text": "Early January 2026", "date_precision": "approximate", **extra}


class ReviewTests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(ROOT / "scripts/career_state.py"), *map(str, args)],
                              capture_output=True, text=True)

    def test_strict_state_and_record_loading_never_modify_invalid_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.json"
            record = root / "record.json"
            valid = json.dumps(base())
            corrupt = [valid[:-1] + ', "attempts": []}', valid[:-1] + ', "annotation": NaN}',
                       valid[:-1] + ', "annotation": 1e999}', '[' * 1500 + '0' + ']' * 1500]
            for raw in corrupt:
                state_path.write_text(raw)
                original = state_path.read_bytes()
                result = self.cli("validate", state_path)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(state_path.read_bytes(), original)
            state_path.write_text(valid)
            original = state_path.read_bytes()
            for raw in ('{"id":"one","id":"two"}', '{"value":Infinity}', '[' * 1500 + '0' + ']' * 1500):
                record.write_text(raw)
                result = self.cli("put", state_path, "sources", record)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(state_path.read_bytes(), original)
            malformed_query = root / "query.json"
            malformed_query.write_text('{"meaning":"one","meaning":"two"}')
            self.assertEqual(self.cli("answer-get", state_path, malformed_query, "--at", LATER).returncode, 2)

    def test_structural_schema_parity_rejects_review_shapes(self):
        states = []
        state = base(); state["revision"] = True; states.append(state)
        state = base(); del state["profile"]["metric_dispositions"]; states.append(state)
        state = base(); del state["search_config"]["salary_floor"]; states.append(state)
        state = base(); state["sources"][0]["coverage"] = [{}]; states.append(state)
        state = base(); state["forms"] = [{"id": "form", "opportunity_id": "role-a", "status": "provisional", "at": AT,
                     "source_ids": [], "fields": [{"id": "field", "label": "Name", "control": "text", "help_text": "", "choices": [{}]}]}]; states.append(state)
        for state in states:
            with self.assertRaises(cs.Invalid):
                cs.validate_shape(state, cs.state_schema())
            with self.assertRaises(cs.Invalid):
                cs.validate(state)
        with self.assertRaises(cs.Invalid):
            cs.validate({**base(), "annotation": float("nan")})

    def test_inbound_and_outbound_contradictions_flag_history_block_new_claims(self):
        for outward in (False, True):
            state = base()
            disputed = copy.deepcopy(state["facts"][0])
            disputed.update(id="dispute", status="disputed", contradiction_ids=["fact-a"], statement="Conflicting synthetic account")
            if outward:
                state["artifacts"] = []
                state["facts"][0]["contradiction_ids"] = ["dispute"]
                state["facts"].append({**disputed, "contradiction_ids": []})
                cs.validate(state)
            else:
                state = cs.add_record(state, "facts", disputed)
                self.assertTrue(state["artifacts"][0]["review_required"])
                self.assertEqual(state["artifacts"][0]["fact_ids"], ["fact-a"])
                self.assertIn("packet-v1", cs.stats(state, LATER)["review_required_artifact_ids"])
            packet = copy.deepcopy(base()["artifacts"][0]); packet.update(id="new", version=2, review_required=True, review_fact_ids=["fact-a"])
            with self.assertRaises(cs.Invalid):
                cs.add_record(state, "artifacts", packet)

    def test_control_flags_cannot_override_latest_pause_or_scope(self):
        state = cs.control_change(base(), "start", "Synthetic explicit start", "Approved scope", True)
        state = cs.control_change(state, "pause", "Synthetic pause", "", True)
        state["control"]["paused"] = False
        self.assertFalse(cs.research_allowed(state))
        with self.assertRaises(cs.Invalid): cs.validate(state)
        state["control"]["paused"] = True
        state["control"]["scope"] = "Broader unapproved scope"
        self.assertFalse(cs.research_allowed(state))

    def test_later_check_can_attest_historical_coverage(self):
        state = cs.add_record(base(), "attempts", attempt())
        state = cs.add_record(state, "coverage", complete_coverage())
        self.assertEqual(cs.stats(state, LATER)["counts"]["known_silence_roles"], 1)
        self.assertEqual(cs.stats(state, LATER, evidence_as_of=LATER)["counts"]["unobserved_roles"], 1)
        self.assertEqual(cs.stats(state, "2026-01-15T12:05:00Z")["counts"]["unobserved_roles"], 1)
        for status in ("unknown", "partial"):
            state["coverage"][0]["status"] = status
            self.assertEqual(cs.stats(state, LATER)["counts"]["known_silence_roles"], 0)

    def test_reconciliation_preserves_action_time_and_earlier_receipt(self):
        state = cs.add_record(base(), "attempts", attempt(outcome="uncertain"))
        state = cs.add_record(state, "attempts", attempt("resolved", at="2026-01-10T12:00:00Z", resolves_attempt_id="send-a"))
        receipt = response("receipt", "auto_receipt"); receipt["at"] = "2026-01-02T12:00:00Z"
        state = cs.add_record(state, "responses", receipt)
        self.assertEqual(state["responses"][0]["attempt_id"], "send-a")
        state = cs.add_record(state, "coverage", complete_coverage())
        report = cs.stats(state, LATER)
        self.assertEqual(report["counts"]["known_silence_roles"], 1)
        self.assertEqual(report["counts"]["waiting_roles"], 0)
        self.assertEqual(cs.stats(state, AT, evidence_as_of=AT)["counts"]["unresolved_submit_roles"], 1)

    def test_old_bounce_does_not_suppress_silence_after_resend(self):
        state = cs.add_record(base(), "attempts", attempt())
        bounce = response("bounced", "bounce"); bounce["at"] = "2026-01-02T12:00:00Z"
        state = cs.add_record(state, "responses", bounce)
        state = cs.add_record(state, "attempts", attempt("resend", at="2026-01-03T12:00:00Z"))
        state = cs.add_record(state, "coverage", complete_coverage())
        counts = cs.stats(state, LATER)["counts"]
        self.assertEqual((counts["bounce_roles"], counts["current_delivery_problem_roles"], counts["known_silence_roles"]), (1, 0, 1))
        bounce = response("new-bounce", "bounce")
        state = cs.add_record(state, "responses", bounce)
        self.assertEqual(state["responses"][-1]["attempt_id"], "resend")
        self.assertEqual(cs.stats(state, LATER)["counts"]["current_delivery_problem_roles"], 1)

    def test_hash_router_roles_and_source_observations_remain_distinct(self):
        urls = ["https://jobs.demo.example/#/jobs/123", "https://jobs.demo.example/#/jobs/456"]
        self.assertNotEqual(cs.canonical_url(urls[0]), cs.canonical_url(urls[1]))
        state = base()
        for row, url in zip(state["opportunities"], urls): row["role_url"] = url
        cs.validate(state)
        source = copy.deepcopy(state["sources"][0]); source.update(id="hash-source", locator=urls[0])
        state = cs.add_record(state, "sources", source)
        source["locator"] = "https://jobs.demo.example/?utm_source=demo#/jobs/123"
        state = cs.add_record(state, "sources", source)
        self.assertEqual(len(state["sources"]), 3)
        source.update(id="other-source", locator=urls[1])
        self.assertEqual(len(cs.add_record(state, "sources", source)["sources"]), 4)

    def test_type_aware_cache_query_does_not_match_true_and_one(self):
        state = cs.add_record(base(), "answers", answer(scope={"relocation": True}))
        integer = answer("integer", scope={"relocation": 1}); integer["value"] = 30
        state = cs.add_record(state, "answers", integer)
        query = {key: state["answers"][0][key] for key in ("meaning", "scope", "units")}
        self.assertEqual([row["id"] for row in cs.lookup_answer(state, query, LATER)], ["answer-a"])
        query["scope"] = {"relocation": 1}
        self.assertEqual([row["id"] for row in cs.lookup_answer(state, query, LATER)], ["integer"])

    def test_draft_answers_confirm_without_fabricated_metadata(self):
        draft = answer(confirmed=False); draft.pop("confirmed_at"); draft.pop("confirmation_evidence")
        state = cs.add_record(base(), "answers", draft)
        query = {key: draft[key] for key in ("meaning", "scope", "units")}
        self.assertEqual(cs.lookup_answer(state, query, LATER), [])
        state = cs.reviewed_update(state, {"operation": "confirm_answer", "answer_id": draft["id"],
                    "confirmed_at": LATER, "confirmation_evidence": "Synthetic exact confirmation",
                    "valid_from": LATER, "valid_until": "2027-01-01T00:00:00Z"}, "User verified the proposed answer")
        self.assertEqual(len(cs.lookup_answer(state, query, LATER)), 1)
        self.assertEqual(state["change_history"][-1]["operation"], "confirm_answer")

    def test_confidential_evidence_allowed_only_in_private_assessment(self):
        state = base()
        fact = copy.deepcopy(state["facts"][0]); fact.update(id="private", disclosure="private")
        state = cs.add_record(state, "facts", fact)
        artifact = copy.deepcopy(state["artifacts"][0]); artifact.update(id="fit", kind="private_fit_assessment", fact_ids=["private"])
        state = cs.add_record(state, "artifacts", artifact)
        artifact.update(id="public", kind="resume", version=2, visibility="external")
        with self.assertRaises(cs.Invalid): cs.add_record(state, "artifacts", artifact)

    def test_reviewed_confirm_supersede_observe_preserve_ids_and_history(self):
        state = base(); state["artifacts"] = []; state["facts"][0]["status"] = "unconfirmed"; state["facts"][0].pop("confirmation")
        state = cs.reviewed_update(state, {"operation": "confirm_fact", "fact_id": "fact-a",
                    "confirmation": {"at": AT, "source_id": "source-user", "evidence": "Exact synthetic user confirmation"}}, "Confirmed in chat")
        self.assertEqual(state["facts"][0]["id"], "fact-a")
        state = cs.add_record(state, "answers", answer())
        replacement = answer("new", value=90000, confirmed_at=LATER, valid_from=LATER)
        state = cs.reviewed_update(state, {"operation": "supersede_answer", "answer_id": "answer-a", "replacement": replacement}, "Changed goal")
        query = {key: replacement[key] for key in ("meaning", "scope", "units")}
        self.assertEqual(cs.lookup_answer(state, query, AT)[0]["value"], 80000)
        self.assertEqual(cs.lookup_answer(state, query, LATER)[0]["value"], 90000)
        state = cs.reviewed_update(state, {"operation": "observe_opportunity", "opportunity_id": "role-a",
                    "observation": {"at": LATER, "status": "unknown", "source_id": "source-a"}}, "Recheck unavailable")
        self.assertEqual(len(state["opportunities"][0]["status_observations"]), 2)
        self.assertEqual(len(state["change_history"]), 3)
        with self.assertRaises(cs.Invalid): cs.reviewed_update(state, {"operation": "patch", "path": "control"}, "Not supported")

    def test_review_transaction_expected_revision_backup_and_failure_safety(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); state = root / "state.json"; state.write_text(json.dumps(base()))
            raw = state.read_bytes()
            with self.assertRaises(cs.Invalid):
                cs.transact(state, lambda data: data, expected_revision=99)
            self.assertEqual(state.read_bytes(), raw)
            updated = cs.transact(state, lambda data: cs.control_change(data, "pause", "Synthetic pause", "", True), expected_revision=0)
            backups = list((root / "Backups/State").glob("*.json"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), raw)
            self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
            stable = state.read_bytes()
            with mock.patch.object(cs.os, "replace", side_effect=OSError("Synthetic failure")):
                with self.assertRaises(OSError): cs.transact(state, lambda data: cs.control_change(data, "pause", "Another synthetic pause", "", True), expected_revision=1)
            self.assertEqual(state.read_bytes(), stable)
            self.assertFalse(state.with_name("state.json.lock").exists())

    def test_private_initialization_rejects_source_and_symlink_into_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in (ROOT / "private-synthetic-probe/state.json",):
                self.assertEqual(self.cli("init", path).returncode, 2)
                self.assertFalse(path.parent.exists())
            link = root / "source-link"; link.symlink_to(ROOT, target_is_directory=True)
            self.assertEqual(self.cli("init", link / "private-synthetic-probe/state.json").returncode, 2)
            workspace = root / "Private career"
            result = self.cli("init-workspace", workspace)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual({p.name for p in workspace.iterdir()}, {"Originals", "Materials", "Applications", "Data", "Backups", "Profile.md"})
            self.assertFalse(cs.research_allowed(cs.read_state(workspace / "Data/state.json")))
            self.assertEqual(self.cli("init-workspace", workspace).returncode, 2)

    def test_history_sparse_import_preview_idempotence_and_no_delivery_inference(self):
        state = base()
        rows = [history(), {"source_locator": "synthetic-list", "employer": "Other Demo", "status": "uncertain"}]
        plan = cs.preview_history(state, rows)
        self.assertEqual(plan["new_entries"], 2)
        self.assertEqual(plan["entries"][0]["opportunity_id"], "role-a")
        self.assertIsNone(plan["entries"][0]["occurred_at"])
        self.assertIsNone(plan["entries"][1]["opportunity_id"])
        self.assertEqual(state["history_imports"], [])
        state = cs.apply_history(state, plan, "Mappings reviewed in chat")
        repeated = cs.preview_history(state, rows)
        self.assertEqual(repeated["new_entries"], 0)
        self.assertEqual(cs.apply_history(state, repeated, "Repeat same list"), state)
        self.assertEqual(cs.stats(state, LATER)["counts"]["sent_roles"], 0)
        self.assertTrue(cs.reapplication_guard(state, "role-a")["requires_review"])
        self.assertFalse(cs.reapplication_guard(state, "role-b")["requires_review"])
        self.assertFalse(cs.research_allowed(state))

    def test_import_preserves_status_conflicts_and_stronger_attempts(self):
        state = cs.add_record(base(), "attempts", attempt())
        plan = cs.preview_history(state, [history(status="bounced")])
        self.assertTrue(any(w["type"] == "existing_attempt_evidence" for w in plan["warnings"]))
        state = cs.apply_history(state, plan, "Review historical bounce")
        plan = cs.preview_history(state, [history(status="uncertain")])
        self.assertTrue(any(w["type"] == "status_difference" for w in plan["warnings"]))
        state = cs.apply_history(state, plan, "Retain conflicting observations")
        self.assertEqual(len(state["history_imports"]), 2)
        self.assertEqual(state["attempts"][0]["outcome"], "sent")
        self.assertEqual(cs.stats(state, LATER)["counts"]["sent_roles"], 1)

    def test_provider_threads_are_not_applications_and_no_body_retention(self):
        state = base()
        rows = [history(source_kind="connector", source_locator="authorized-sent-scope",
                        provider_message_id="synthetic-message", provider_thread_id="synthetic-thread",
                        evidence_level="provider_observed", event_kind="follow_up", status="follow_up")]
        state = cs.apply_history(state, cs.preview_history(state, rows), "Reviewed read-only connector result")
        self.assertEqual(cs.stats(state, LATER)["counts"]["historically_reported_application_roles"], 0)
        self.assertEqual(state["attempts"], [])
        with self.assertRaises(cs.Invalid): cs.preview_history(state, [history(body="Do not retain full bodies")])
        with self.assertRaises(cs.Invalid): cs.preview_history(state, [history(evidence_level="provider_observed")])
        with self.assertRaises(cs.Invalid): cs.preview_history(state, [history(role="", role_url=None, opportunity_id="role-a")])

    def test_unmapped_history_can_be_reviewed_without_changing_stable_id(self):
        state = base()
        state = cs.apply_history(state, cs.preview_history(state, [history(role_url=None)]), "Keep unknown role identity")
        identifier = state["history_imports"][0]["id"]
        state = cs.reviewed_update(state, {"operation": "map_history", "history_id": identifier, "opportunity_id": "role-a"}, "User confirms exact role")
        self.assertEqual(state["history_imports"][0]["id"], identifier)
        self.assertTrue(cs.reapplication_guard(state, "role-a")["requires_review"])

    def test_snapshot_real_xlsx_two_sheets_literals_links_and_denominators(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory); state_path = workspace / "state.json"
            state = base(); state["companies"][0]["name"] = '=HYPERLINK("https://evil.example","Demo")'
            state["opportunities"][0]["fit_summary"] = '<synthetic & literal>'
            state["artifacts"][0]["path"] = "javascript:alert(1)"
            state_path.write_text(json.dumps(state))
            result = snapshot.export_snapshot(state_path, workspace, LATER)
            self.assertTrue(result["written"])
            with zipfile.ZipFile(result["path"]) as workbook:
                workbook_xml = ET.fromstring(workbook.read("xl/workbook.xml"))
                ns = {"s": snapshot.NS}
                self.assertEqual([node.attrib["name"] for node in workbook_xml.findall("s:sheets/s:sheet", ns)], ["Applications", "Metadata"])
                sheet = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
                self.assertEqual(len(sheet.findall("s:sheetData/s:row", ns)), 7)
                self.assertIsNotNone(sheet.find("s:autoFilter", ns)); self.assertIsNotNone(sheet.find("s:sheetViews/s:sheetView/s:pane", ns))
                self.assertEqual(sheet.findall(".//s:f", ns), [])
                text = " ".join(node.text or "" for node in sheet.findall(".//s:t", ns))
                self.assertIn("2 unique roles", text); self.assertIn("0 confirmed-sent roles", text)
                self.assertIn("state revision 0", text)
                rels = workbook.read("xl/worksheets/_rels/sheet1.xml.rels").decode()
                self.assertNotIn("javascript:", rels)
            self.assertEqual(state_path.read_text(), json.dumps(state))

    def test_snapshot_staleness_and_manual_changes_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory); path = workspace / "state.json"; path.write_text(json.dumps(base()))
            snapshot.export_snapshot(path, workspace, LATER)
            self.assertFalse(snapshot.snapshot_status(path, workspace)["stale"])
            state = base(); state["revision"] = 1; path.write_text(json.dumps(state))
            self.assertTrue(snapshot.snapshot_status(path, workspace)["stale"])
            view = workspace / "Career.xlsx"; manual = view.read_bytes() + b"synthetic manual edit"; view.write_bytes(manual)
            result = snapshot.export_snapshot(path, workspace, LATER)
            self.assertFalse(result["written"]); self.assertTrue(result["manual_change"])
            self.assertEqual(view.read_bytes(), manual)
            self.assertEqual(cs.read_state(path)["revision"], 1)

    def test_backup_ancestor_symlink_cannot_escape_private_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); workspace = root / "workspace"; (workspace / "Data").mkdir(parents=True)
            path = workspace / "Data/state.json"; path.write_text(json.dumps(base()))
            outside = root / "outside"; outside.mkdir(); (workspace / "Backups").symlink_to(outside, target_is_directory=True)
            original = path.read_bytes()
            with self.assertRaises(cs.Invalid):
                cs.transact(path, lambda data: cs.control_change(data, "pause", "Synthetic pause", "", True), expected_revision=0)
            self.assertEqual(path.read_bytes(), original); self.assertEqual(list(outside.iterdir()), [])

    def test_settings_require_expected_revision_and_preserve_concurrent_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / "state.json"; path.write_text(json.dumps(base()))
            first = root / "first.json"; stale = root / "stale.json"
            profile = copy.deepcopy(base()["profile"]); profile["selected_directions"] = ["API lane"]
            first.write_text(json.dumps(profile)); stale.write_text(json.dumps(base()["profile"]))
            one = self.cli("settings", path, "profile", first, "--expected-revision", 0, "--reason", "Selected direction")
            self.assertEqual(one.returncode, 0, one.stderr)
            original = path.read_bytes()
            two = self.cli("settings", path, "profile", stale, "--expected-revision", 0, "--reason", "Stale choice")
            self.assertEqual(two.returncode, 2); self.assertEqual(path.read_bytes(), original)
            self.assertEqual(cs.read_state(path)["profile"]["selected_directions"], ["API lane"])
            self.assertEqual(cs.read_state(path)["change_history"][-1]["operation"], "settings_profile")
            self.assertEqual(self.cli("settings", path, "profile", stale).returncode, 2)

    def test_history_preview_retains_mapping_and_requires_explicit_review_for_change(self):
        state = base(); rows = [history(role_url=None)]
        state = cs.apply_history(state, cs.preview_history(state, rows), "Keep sparse history")
        plan = cs.preview_history(state, [history(role_url=None, opportunity_id="role-a")])
        self.assertIsNone(plan["entries"][0]["opportunity_id"])
        self.assertEqual(plan["mapping_requests"][0]["proposed_opportunity_id"], "role-a")
        self.assertEqual(plan["mapping_requests"][0]["required_operation"], "map_history")
        self.assertTrue(any(w["type"] == "mapping_not_applied" for w in plan["warnings"]))
        self.assertEqual(cs.apply_history(state, plan, "Retain preview mapping"), state)
        identifier = state["history_imports"][0]["id"]
        mapped = cs.reviewed_update(state, {"operation": "map_history", "history_id": identifier,
                                           "opportunity_id": "role-a"}, "User confirms role")
        self.assertEqual(mapped["history_imports"][0]["opportunity_id"], "role-a")

    def test_snapshot_stage_uses_latest_attempt_and_exposes_uncertainty(self):
        state = cs.add_record(base(), "attempts", attempt())
        bounce = response("old-bounce", "bounce"); bounce["at"] = "2026-01-02T12:00:00Z"
        state = cs.add_record(state, "responses", bounce)
        state = cs.add_record(state, "attempts", attempt("resend", at="2026-01-03T12:00:00Z"))
        report, rows, _ = snapshot.view_data(state, Path("/tmp/synthetic-workspace"), LATER)
        self.assertIn("Sent", rows[0]["values"][5]); self.assertEqual(rows[0]["values"][6], "bounce")
        state = cs.add_record(state, "attempts", attempt("maybe", outcome="uncertain", at="2026-01-05T12:00:00Z"))
        state = cs.add_record(state, "coverage", complete_coverage())
        report, rows, _ = snapshot.view_data(state, Path("/tmp/synthetic-workspace"), LATER)
        self.assertIn("uncertain", rows[0]["values"][5]); self.assertEqual(report["counts"]["known_silence_roles"], 0)

    def test_xml_forbidden_characters_and_surrogates_are_safe_literals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / "state.json"; state = base()
            state["opportunities"][0]["title"] = "Engineer\ufffe\uffff\ud800"
            path.write_text(json.dumps(state))
            result = snapshot.export_snapshot(path, root, LATER)
            self.assertTrue(result["written"])
            with zipfile.ZipFile(result["path"]) as archive:
                for name in archive.namelist():
                    if name.endswith(".xml") or name.endswith(".rels"):
                        ET.fromstring(archive.read(name))

    def test_snapshot_failure_never_rolls_back_valid_state(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory); path = workspace / "state.json"; path.write_text(json.dumps(base()))
            original = path.read_bytes()
            with mock.patch.object(snapshot, "xlsx_bytes", side_effect=OSError("Synthetic rendering failure")):
                with self.assertRaises(OSError): snapshot.export_snapshot(path, workspace, LATER)
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse((workspace / "Data/report-index.json").exists())
            self.assertFalse((workspace / "Data/report-index.json.lock").exists())
            with self.assertRaises(snapshot.cs.Invalid): snapshot.export_snapshot(path, ROOT, LATER)


if __name__ == "__main__":
    unittest.main()
