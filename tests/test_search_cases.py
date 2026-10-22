"""Synthetic acceptance gates for new, saved, income-aware application cases."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from test_state import ROOT, AT, LATER, base
sys.path.insert(0, str(ROOT / "scripts"))
import career_search as search
cs = search.cs


def configured():
    state = base(); state["opportunities"] = []; state["artifacts"] = []
    state["search_config"] = {"constraints": [], "salary_floor": {"amount": 60000, "currency": "USD", "basis": "gross", "period": "year"},
        "salary_goal": {"amount": 80000, "currency": "USD", "basis": "gross", "period": "year"},
        "income_policy": {"confirmed_at": AT, "confirmation_evidence": "Synthetic confirmed preferences", "employment_type": "full_time", "weekly_hours": 40,
            "floor_disposition": "stated", "goal_disposition": "stated", "case_types": ["vacancy", "contract_project", "company_outreach"]}}
    return state


def pay(**changes):
    return {"kind": "range", "employment_type": "full_time", "weekly_hours": 40, "currency": "USD", "basis": "gross", "period": "year",
            "minimum": 70000, "maximum": 90000, "source_id": "source-a", "checked_at": AT, "evidence_type": "employer_confirmed", **changes}


def request(**changes):
    role = copy.deepcopy(base()["opportunities"][0]); role.update(id="new-role", identity="northstar:new-api", role_url="https://northstar-demo.example/jobs/new-api", hiring_geography="Demo Region", level="Senior")
    source = copy.deepcopy(base()["sources"][0]); source["locator"] = role["role_url"]; source["id"] = "source-new"
    role["source_ids"] = ["source-new"]; role["status_observations"][0]["source_id"] = "source-new"
    docs = {slot: {"text": "# " + slot + "\n\nSupported synthetic importer work.\n", "language": "English", "fact_ids": ["fact-a"], "source_ids": ["source-user"]} for slot in search.SLOTS}
    return {"id": "case-a", "batch_id": "search-a", "requested_new": 1, "at": AT, "company": copy.deepcopy(base()["companies"][0]), "sources": [source], "opportunity": role,
            "form": {"id": "new-form", "opportunity_id": role["id"], "status": "observed", "at": AT, "source_ids": ["source-new"],
                     "fields": [{"id": "name", "label": "Name", "control": "text", "help_text": "", "choices": [], "required": True,
                                 "answer_state": "confirmed", "answer": "Alex Demo", "confirmation_evidence": "Synthetic user confirmation"}]},
            "compensation": pay(source_id="source-new"), "conditions": [], "documents": docs, "fit_summary": "Supported importer experience fits the role.", **changes}


class SearchCaseTests(unittest.TestCase):
    def fixture(self, directory):
        workspace = Path(directory) / "Private"; cs.initialize_workspace(workspace)
        path = workspace / "Data/state.json"; path.write_text(json.dumps(configured()))
        return workspace, path

    def test_exact_known_review_marker_with_empty_canonical_array_is_not_new_quota(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, path = self.fixture(directory); item = request()
            item["opportunity"]["identity_aliases"] = ["DEMO12345"]
            (workspace / "Data/campaign-review.json").write_text(json.dumps({"records": [{"id": "prior", "priorjob": "Exact priorjob DEMO12345", "prepared": False}]}))
            check = search.novelty(cs.read_state(path), workspace, item["opportunity"])
            self.assertEqual(check["status"], "known"); self.assertIn("sha256", check["matches"][0])
            result = search.prepare_case(path, workspace, item, 0)
            self.assertFalse(result["completed"]); self.assertTrue(result["saved"])
            report = search.case_report(path, workspace, "search-a", 2)
            self.assertEqual(report["new_ready"], 0); self.assertFalse(report["completed"])
            other = copy.deepcopy(item["opportunity"]); other.update(id="another", identity="another-role", role_url="https://northstar-demo.example/jobs/other", identity_aliases=[])
            self.assertEqual(search.novelty(cs.read_state(path), workspace, other)["status"], "new")

    def test_url_dedup_csv_registry_and_failed_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, path = self.fixture(directory); role = request()["opportunity"]
            (workspace / "Data/prior-index.csv").write_text('role_url\n'+role["role_url"]+'?utm_source=old\n')
            self.assertEqual(search.novelty(cs.read_state(path), workspace, role)["status"], "known")
            (workspace / "Data/prior-index.csv").unlink(); (workspace / "Data/failed-review.json").write_text('HTTP 502')
            check = search.novelty(cs.read_state(path), workspace, role)
            self.assertEqual(check["status"], "unknown"); self.assertTrue(check["errors"])
            self.assertTrue(search.registry_inventory(workspace, ['../../escape.json'])[1])

    def test_compensation_units_lower_bound_and_estimated_actual_hiring_market(self):
        config = configured()["search_config"]; role = request()["opportunity"]
        self.assertEqual(search.income_assessment(config, pay(), role)["status"], "pass")
        self.assertEqual(search.income_assessment(config, pay(minimum=20000, maximum=30000), role)["status"], "fail")
        for observed in ({"kind": "unpublished"}, pay(kind="lower_bound", minimum=20000), pay(period="hour"), pay(basis="net"), pay(currency="EUR"), pay(weekly_hours=20)):
            self.assertEqual(search.income_assessment(config, observed, role)["status"], "unknown")
        estimate = pay(evidence_type="market_estimate", geography="Demo Region", level="Senior", comparable_role="API Engineer", confidence="high")
        result = search.income_assessment(config, {"kind": "unpublished", "estimates": [estimate]}, role)
        self.assertEqual(result["status"], "estimated_compatible"); self.assertIn("not an employer promise", result["reason"])
        estimate["geography"] = "Company HQ Elsewhere"
        self.assertEqual(search.income_assessment(config, {"kind": "unpublished", "estimates": [estimate]}, role)["status"], "unknown")
        self.assertEqual(search.income_assessment({}, pay(), role)["status"], "intake_missing")

    def test_new_case_writes_actual_markdown_packet_reads_back_and_exports(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, path = self.fixture(directory)
            result = search.prepare_case(path, workspace, request(), 0)
            self.assertTrue(result["completed"]); self.assertEqual(result["new_ready"], 1)
            state = cs.read_state(path)
            self.assertEqual(len(state["artifacts"]), 4); self.assertEqual(len(state["forms"]), 1)
            self.assertEqual(len(state["application_attempts"]), 1)
            for artifact in state["artifacts"]:
                self.assertEqual(Path(artifact["path"]).suffix, ".md"); self.assertTrue((workspace / artifact["path"]).is_file())
            self.assertTrue((workspace / "Career.xlsx").is_file())
            self.assertEqual(len(list((workspace / "Materials/objects").glob('*.md'))), 4)
            self.assertFalse(list(workspace.rglob('*.pdf'))); self.assertFalse(list(workspace.rglob('*.txt')))
            report = search.case_report(path, workspace, "search-a", 2)
            self.assertEqual(report["new_ready"], 1); self.assertFalse(report["completed"])
            self.assertFalse(cs.research_allowed(state)); self.assertFalse(state["attempts"])

    def test_unpublished_salary_is_accepted_transparently_not_falsely_passed(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, path = self.fixture(directory)
            result = search.prepare_case(path, workspace, request(compensation={"kind": "unpublished"}), 0)
            self.assertTrue(result["completed"]); self.assertEqual(result["pay_uncertain_ready"], 1)
            self.assertEqual(result["cases"][0]["income"]["status"], "unknown")
            self.assertEqual(result["cases"][0]["status"], "ready_with_pay_uncertainty")

    def test_unknown_required_answer_and_unscoped_submission_never_ready(self):
        for scenario in ("answer", "submission"):
            with tempfile.TemporaryDirectory() as directory:
                workspace, path = self.fixture(directory); item = request()
                if scenario == "answer": item["form"]["fields"][0]["answer_state"] = "unknown"
                else:
                    (workspace / "Data/contact-review.json").write_text(json.dumps([{"company": item["company"]["name"], "submission_status": "uncertain"}]))
                result = search.prepare_case(path, workspace, item, 0)
                self.assertFalse(result["completed"]); self.assertEqual(result["new_ready"], 0)
                self.assertIn(result["cases"][0]["status"], {"conditional", "blocked"})

    def test_export_failure_preserves_canonical_packet_without_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, path = self.fixture(directory)
            with mock.patch.object(search.snapshot, 'export_snapshot', side_effect=OSError('Synthetic view failure')):
                result = search.prepare_case(path, workspace, request(), 0)
            self.assertTrue(result["saved"]); self.assertFalse(result["completed"]); self.assertFalse(result["view_refreshed"])
            state = cs.read_state(path); self.assertEqual(state["search_cases"][0]["phase"], "saved")
            self.assertEqual(search.case_report(path, workspace, "search-a", 1)["new_ready"], 0)
            artifact = workspace / state["artifacts"][0]["path"]; artifact.unlink()
            self.assertEqual(search.case_report(path, workspace, "search-a", 1)["new_ready"], 0)

    def test_state_write_failure_and_bad_markdown_cannot_report_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, path = self.fixture(directory); raw = path.read_bytes()
            with mock.patch.object(cs, '_write_atomic', side_effect=OSError('Synthetic state failure')):
                with self.assertRaises(OSError): search.prepare_case(path, workspace, request(), 0)
            self.assertEqual(path.read_bytes(), raw)
            item = request(); item["documents"]["resume"]["text"] = '%PDF synthetic wrong format'
            with self.assertRaises(cs.Invalid): search.prepare_case(path, workspace, item, 0)
            self.assertEqual(search.case_report(path, workspace, "search-a", 1)["new_ready"], 0)

    def test_company_outreach_is_actionable_without_inventing_a_vacancy(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, path = self.fixture(directory); item = request()
            item["opportunity"].update(kind="company_outreach", identity="outreach:demo:import-reliability", outreach_need="Specific source-backed importer reliability need",
                contact_route={"url": "https://northstar-demo.example/contact", "source_id": "source-new", "checked_at": AT})
            item["opportunity"]["status_observations"][0]["status"] = "unknown"
            result = search.prepare_case(path, workspace, item, 0)
            self.assertTrue(result["completed"])
            self.assertEqual(cs.read_state(path)["opportunities"][0]["kind"], "company_outreach")
            counts = cs.stats(cs.read_state(path), LATER)["counts"]
            self.assertEqual(counts["company_outreach_cases"], 1); self.assertEqual(counts["advertised_opportunities"], 0)
            rows = search.snapshot.view_data(cs.read_state(path), workspace, LATER)[1]
            self.assertIn("Company outreach prospect", rows[0]["values"][5]); self.assertIn("Not an advertised opening", rows[0]["values"][9])

    def test_exclusions_and_final_output_links_remain_blocking(self):
        for scenario in ("excluded", "markdown", "form-url"):
            with tempfile.TemporaryDirectory() as directory:
                workspace, path = self.fixture(directory); item = request()
                if scenario == "excluded":
                    state = cs.read_state(path); state["search_config"]["excluded_companies"] = [item["company"]["name"]]; path.write_text(json.dumps(state))
                elif scenario == "markdown": item["documents"]["cover-letter"]["text"] += "\n[Resume](file:///private/resume.pdf)\n"
                else: item["form"]["fields"][0].update(control="url", answer="/private/resume.pdf")
                result = search.prepare_case(path, workspace, item, 0)
                self.assertFalse(result["completed"]); self.assertEqual(result["new_ready"], 0)

    def test_noncritical_language_and_essential_unknowns_are_distinct(self):
        for priority in ("hard", "preference"):
            with tempfile.TemporaryDirectory() as directory:
                workspace, path = self.fixture(directory); item = request()
                item["conditions"] = [{"meaning": "role.requirement.language", "outcome": "fail", "priority": priority,
                    "source_ids": ["source-new"], "evidence": "Only the posting language is observed", "evidence_kind": "posting_language"}]
                result = search.prepare_case(path, workspace, item, 0)
                self.assertEqual(result["completed"], priority == "preference")
                self.assertNotEqual(result["cases"][0]["status"], "blocked")

    def test_approved_unchanged_resume_reference_and_retry_do_not_duplicate_files(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, path = self.fixture(directory); item = request()
            original = Path(directory) / "approved.pdf"; original.write_bytes(b"Synthetic immutable original bytes")
            metadata = {"id": "approved-resume", "family_id": "approved", "version": 1, "kind": "resume", "language": "English", "visibility": "external",
                        "at": AT, "fact_ids": ["fact-a"], "source_ids": ["source-user"]}
            state = search.cm.register_material(path, workspace, metadata, original, 0)
            item["documents"].pop("resume"); item["resume_reference"] = {"material_id": "approved-resume", "confirmation_evidence": "Synthetic approved unchanged version"}
            first = search.prepare_case(path, workspace, item, state["revision"]); self.assertTrue(first["completed"])
            raw_objects = sorted(p.name for p in (workspace / "Materials/objects").iterdir())
            state = cs.read_state(path); result = search.prepare_case(path, workspace, item, state["revision"])
            self.assertTrue(result["completed"]); self.assertEqual(len(cs.read_state(path)["application_attempts"]), 1)
            self.assertEqual(raw_objects, sorted(p.name for p in (workspace / "Materials/objects").iterdir()))

    def test_saved_packet_readback_failure_does_not_become_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, path = self.fixture(directory)
            with mock.patch.object(search, "verify_case", side_effect=cs.Invalid("Synthetic readback mismatch")):
                with self.assertRaises(cs.Invalid): search.prepare_case(path, workspace, request(), 0)
            self.assertEqual(search.case_report(path, workspace, "search-a", 1)["new_ready"], 0)

    def test_new_registry_duplicate_after_reservation_invalidates_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, path = self.fixture(directory); item = request()
            self.assertTrue(search.prepare_case(path, workspace, item, 0)["completed"])
            (workspace / "Data/new-review.json").write_text(json.dumps({"records": [{"url": item["opportunity"]["role_url"]}]}))
            self.assertFalse(search.case_report(path, workspace, "search-a", 1)["completed"])

    def test_estimated_pay_packet_is_explicit_and_confirmed_low_cap_is_blocked(self):
        for low_cap in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                workspace, path = self.fixture(directory)
                estimate = pay(source_id="source-new", evidence_type="company_comparable", geography="Demo Region", level="Senior", comparable_role="API Engineer", confidence="high")
                compensation = pay(source_id="source-new", minimum=10000, maximum=20000) if low_cap else {"kind": "unpublished", "estimates": [estimate]}
                result = search.prepare_case(path, workspace, request(compensation=compensation), 0)
                self.assertEqual(result["completed"], not low_cap)
                self.assertEqual(result["cases"][0]["income"]["status"], "fail" if low_cap else "estimated_compatible")

    def test_cached_answers_require_exact_scope_and_consents_are_not_auto_ready(self):
        for consent in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                workspace, path = self.fixture(directory); item = request()
                field = item["form"]["fields"][0]
                if consent: field.update(is_consent=True, consent_text_version="Synthetic terms version 1")
                else: field.update(answer_id="unknown-cache-id", answer_query={"meaning": "identity.name", "scope": {"opportunity_id": "different-role"}, "units": {}})
                result = search.prepare_case(path, workspace, item, 0)
                self.assertFalse(result["completed"]); self.assertEqual(result["new_ready"], 0)

    def test_new_helper_in_fresh_bundle_saves_packet_and_enforces_quota(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); workspace, path = self.fixture(directory); bundle = root / "bundle"
            built = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/build_skill_bundle.py'), str(bundle)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            request_path = root / "request.json"; request_path.write_text(json.dumps(request()))
            command = [sys.executable, '-B', str(bundle / 'scripts/career_search.py')]
            result = subprocess.run(command + ['prepare-case', str(path), str(workspace), str(request_path), '--expected-revision', '0'], cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)['completed'])
            result = subprocess.run(command + ['report', str(path), str(workspace), 'search-a', '--requested', '2'], cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertEqual(json.loads(result.stdout)['new_ready'], 1)

    def test_malformed_registry_columns_and_private_network_urls_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, path = self.fixture(directory)
            (workspace / "Data/old-index.csv").write_text("role_url,role_url\nhttps://demo.example/a,https://demo.example/b\n")
            self.assertEqual(search.novelty(cs.read_state(path), workspace, request()["opportunity"])["status"], "unknown")
        for url in ("http://localhost/resume", "http://127.0.0.1/resume", "http://192.168.1.2/resume", "file:///private/cv.md"):
            self.assertFalse(search.public_destination(url))

    def test_saved_requested_quota_cannot_be_silently_lowered_to_one(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, path = self.fixture(directory)
            result = search.prepare_case(path, workspace, request(requested_new=2), 0)
            self.assertFalse(result["completed"]); self.assertEqual(result["requested_new"], 2)
            self.assertFalse(search.case_report(path, workspace, "search-a", 1)["completed"])
