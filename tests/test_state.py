"""Synthetic regression cases for career workflow invariants."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("career_state", ROOT / "scripts/career_state.py")
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)
AT = "2026-01-01T12:00:00Z"
LATER = "2026-01-15T12:00:00Z"


def base():
    return json.loads((ROOT / "tests/fixtures/synthetic-state.json").read_text())


def attempt(identifier="send-a", role="role-a", outcome="sent", at=AT, **extras):
    return {"id": identifier, "opportunity_id": role, "outcome": outcome,
            "at": at, "evidence": "Synthetic user report", "channel": "manual form", **extras}


def response(identifier, kind, role="role-a"):
    return {"id": identifier, "opportunity_id": role, "type": kind,
            "at": LATER, "evidence": "Synthetic response evidence"}


def answer(identifier="answer-a", scope=None, units=None, **extras):
    return {"id": identifier, "meaning": "compensation.goal", "scope": scope or {"jurisdiction": "Demo Country"},
            "units": units or {"currency": "USD", "basis": "gross", "period": "year"},
            "value": 80000, "confirmed": True, "confirmed_at": AT,
            "confirmation_evidence": "Synthetic user confirmation", "is_consent": False,
            "valid_from": AT, "valid_until": "2027-01-01T00:00:00Z", **extras}


class StateTests(unittest.TestCase):
    def test_appended_record_does_not_alias_caller_input(self):
        state = base()
        item = attempt()
        updated = cs.add_record(state, "attempts", item)
        item["opportunity_id"] = "role-b"
        self.assertEqual(updated["attempts"][0]["opportunity_id"], "role-a")
        self.assertEqual(state["attempts"], [])

    def test_synthetic_fixture_valid_and_paused(self):
        state = cs.validate(base())
        self.assertFalse(cs.research_allowed(state))
        self.assertEqual(cs.stats(state, LATER)["counts"]["sent_roles"], 0)

    def test_two_roles_same_company_do_not_share_sent_status(self):
        state = cs.add_record(base(), "attempts", attempt())
        report = cs.stats(state, LATER)
        self.assertEqual(report["counts"]["opportunities"], 2)
        self.assertEqual(report["counts"]["sent_roles"], 1)
        with self.assertRaises(cs.Invalid):
            cs.add_record(state, "responses", response("wrong", "interview", "role-b"))

    def test_duplicate_sources_merge_coverage_and_keep_original_urls(self):
        state = base()
        duplicate = copy.deepcopy(state["sources"][0])
        duplicate["locator"] += "?utm_source=demo"
        duplicate["coverage"] = ["engineering_blog"]
        state = cs.add_record(state, "sources", duplicate)
        self.assertEqual(len(state["sources"]), 2)
        self.assertEqual(set(state["sources"][0]["coverage"]), {"company_careers", "engineering_blog"})
        self.assertEqual(len(state["sources"][0]["original_locators"]), 2)
        duplicate["id"] = "different-id"
        with self.assertRaises(cs.Invalid):
            cs.add_record(state, "sources", duplicate)

    def test_meaningful_job_query_parameters_survive(self):
        self.assertNotEqual(cs.canonical_url("https://demo.example/jobs?id=1"),
                            cs.canonical_url("https://demo.example/jobs?id=2"))
        with self.assertRaises(cs.Invalid):
            cs.canonical_url("https://name:secret@demo.example/jobs")

    def test_duplicate_role_identity_or_url_rejected(self):
        state = base()
        duplicate = copy.deepcopy(state["opportunities"][0])
        duplicate["id"] = "mirror"
        duplicate["role_url"] = "https://board.example/mirror"
        with self.assertRaises(cs.Invalid):
            cs.add_record(state, "opportunities", duplicate)
        duplicate["identity"] = "new-identity"
        duplicate["role_url"] = state["opportunities"][0]["role_url"] + "?utm_campaign=mirror"
        with self.assertRaises(cs.Invalid):
            cs.add_record(state, "opportunities", duplicate)

    def test_packet_versions_never_count_as_sent_or_additional_jobs(self):
        state = base()
        second = copy.deepcopy(state["artifacts"][0])
        second.update(id="packet-v2", version=2)
        state = cs.add_record(state, "artifacts", second)
        counts = cs.stats(state, LATER)["counts"]
        self.assertEqual((counts["prepared_roles"], counts["sent_roles"], counts["opportunities"]), (1, 0, 2))
        self.assertIsNone(cs.stats(state, LATER)["hiring_response_rate"]["value"])

    def test_bounce_and_receipt_are_not_hiring_progress_or_rejection(self):
        state = cs.add_record(base(), "attempts", attempt())
        for identifier, kind in (("receipt", "auto_receipt"), ("bounce", "bounce")):
            state = cs.add_record(state, "responses", response(identifier, kind))
        report = cs.stats(state, LATER)
        self.assertEqual(report["counts"]["rejection_roles"], 0)
        self.assertEqual(report["counts"]["known_silence_roles"], 0)
        self.assertEqual(report["hiring_response_rate"], {"numerator": 0, "denominator": 1, "value": 0.0})

    def test_unknown_coverage_is_not_silence(self):
        state = cs.add_record(base(), "attempts", attempt())
        counts = cs.stats(state, LATER)["counts"]
        self.assertEqual((counts["known_silence_roles"], counts["unobserved_roles"]), (0, 1))
        record = {"id": "coverage-a", "opportunity_id": "role-a", "status": "complete",
                  "channels": ["user_checked_inbox", "portal"], "checked_at": LATER, "through": LATER}
        state = cs.add_record(state, "coverage", record)
        self.assertEqual(cs.stats(state, LATER)["counts"]["known_silence_roles"], 1)
        self.assertEqual(cs.stats(state, AT)["counts"]["waiting_roles"], 1)

    def test_uncertain_submit_blocks_retry_until_reconciled(self):
        state = cs.add_record(base(), "attempts", attempt(outcome="uncertain"))
        with self.assertRaises(cs.Invalid):
            cs.add_record(state, "attempts", attempt("retry", at=LATER))
        invalid_import = copy.deepcopy(state)
        invalid_import["attempts"].append(attempt("retry", at=LATER))
        with self.assertRaises(cs.Invalid):
            cs.validate(invalid_import)
        state = cs.add_record(state, "attempts", attempt("resolution", at=LATER, resolves_attempt_id="send-a"))
        counts = cs.stats(state, LATER)["counts"]
        self.assertEqual((counts["sent_roles"], counts["unresolved_submit_roles"]), (1, 0))
        self.assertEqual(cs.stats(state, AT, evidence_as_of=AT)["counts"]["unresolved_submit_roles"], 1)

    def test_packet_cannot_be_attached_to_another_role(self):
        with self.assertRaises(cs.Invalid):
            cs.add_record(base(), "attempts", attempt(role="role-b", artifact_id="packet-v1"))

    def test_rejection_before_application_separate_funnel(self):
        state = cs.add_record(base(), "responses", response("screened-out", "rejected_before_application"))
        counts = cs.stats(state, LATER)["counts"]
        self.assertEqual((counts["rejected_before_application_roles"], counts["rejection_roles"], counts["sent_roles"]), (1, 0, 0))

    def test_scoped_cache_units_expiry_confirmation_and_consent(self):
        state = cs.add_record(base(), "answers", answer())
        query = {key: state["answers"][0][key] for key in ("meaning", "scope", "units")}
        self.assertEqual(len(cs.lookup_answer(state, query, LATER)), 1)
        for field, value in (("scope", {"jurisdiction": "Another Demo Country"}),
                             ("units", {"currency": "EUR", "basis": "net", "period": "month"}),
                             ("meaning", "compensation.floor")):
            changed = copy.deepcopy(query)
            changed[field] = value
            self.assertEqual(cs.lookup_answer(state, changed, LATER), [])
        self.assertEqual(cs.lookup_answer(state, query, "2027-01-01T00:00:00Z"), [])
        state["answers"][0]["confirmed"] = False
        self.assertEqual(cs.lookup_answer(state, query, LATER), [])
        consent = answer("consent", scope={"company_id": "company-a", "opportunity_id": "role-a",
                         "consent_text_version": "v1", "purpose": "retention"},
                         meaning="privacy.retention", is_consent=True)
        state = cs.add_record(state, "answers", consent)
        query = {key: consent[key] for key in ("meaning", "scope", "units")}
        self.assertEqual(cs.lookup_answer(state, query, LATER), [])

    def test_overlapping_answers_rejected(self):
        state = cs.add_record(base(), "answers", answer())
        with self.assertRaises(cs.Invalid):
            cs.add_record(state, "answers", answer("overlap"))

    def test_unverified_suggestions_do_not_become_confirmed_facts(self):
        state = base()
        state["artifacts"][0]["fact_ids"] = ["suggestion-a"]
        with self.assertRaises(cs.Invalid):
            cs.validate(state)
        state = base()
        state["facts"][0]["status"] = "unconfirmed"
        with self.assertRaises(cs.Invalid):
            cs.validate(state)
        state = base()
        del state["facts"][0]["confirmation"]
        with self.assertRaises(cs.Invalid):
            cs.validate(state)

    def test_confidential_claims_cannot_enter_external_artifact(self):
        state = base()
        state["facts"][0]["disclosure"] = "private"
        with self.assertRaises(cs.Invalid):
            cs.validate(state)

    def test_open_status_requires_dated_primary_evidence(self):
        state = base()
        state["sources"][0]["observations"][0]["primary"] = False
        with self.assertRaises(cs.Invalid):
            cs.validate(state)

    def test_metric_unknown_is_retained_once(self):
        state = base()
        state["profile"]["metric_dispositions"] = [{"fact_id": "fact-a", "question_key": "impact.baseline",
                                                     "disposition": "unknown"}]
        cs.validate(state)
        state["profile"]["metric_dispositions"] *= 2
        with self.assertRaises(cs.Invalid):
            cs.validate(state)

    def test_research_start_pause_resume_needs_explicit_decision(self):
        state = base()
        with self.assertRaises(cs.Invalid):
            cs.control_change(state, "start", "Demo user request", "Demo scope", False)
        from workflow_fixtures import setup_decisions
        state["search_config"]["search_setup"] = setup_decisions()
        state = cs.control_change(state, "start", "Demo user request", "Demo scope", True, "live-run")
        self.assertTrue(cs.research_allowed(state, "live-run"))
        state = cs.control_change(state, "pause", "Demo pause", "", True)
        self.assertFalse(cs.research_allowed(state))
        state = cs.control_change(state, "resume", "Demo resume", "", True, "live-run")
        self.assertTrue(cs.research_allowed(state, "live-run"))

    def test_interview_practice_requires_confirmed_candidate_facts(self):
        state = base()
        practice = {"id": "practice-a", "opportunity_id": "role-a", "language": "English",
                    "question": "How did you make imports reliable?", "outline": "Context, personal action, result",
                    "question_status": "practice_hypothesis", "fact_ids": ["fact-a"], "source_ids": [],
                    "pressure_points": ["Explain the team's contribution"],
                    "employer_questions": ["How is success measured?"]}
        state = cs.add_record(state, "interview_prep", practice)
        practice.update(id="practice-b", fact_ids=["suggestion-a"])
        with self.assertRaises(cs.Invalid):
            cs.add_record(state, "interview_prep", practice)

    def test_company_cases_cannot_claim_documented_without_sources(self):
        state = base()
        case = {"id": "case-a", "opportunity_id": "role-a", "prompt": "Design safe invoice retries",
                "classification": "hypothetical", "source_ids": []}
        state = cs.add_record(state, "cases", case)
        case.update(id="case-b", classification="publicly_documented")
        with self.assertRaises(cs.Invalid):
            cs.add_record(state, "cases", case)
        claim = {"id": "claim-a", "opportunity_id": "role-a", "statement": "May need retry expertise",
                 "classification": "inference", "at": AT, "source_ids": []}
        with self.assertRaises(cs.Invalid):
            cs.add_record(state, "dossier", claim)

    def test_referral_draft_is_not_contact_or_application(self):
        state = base()
        person = {"id": "person-a", "opportunity_id": "role-a", "public_name": "Morgan Demo", "company_id": "company-a",
                  "observed_role": "Engineer", "relevance": "Published a related technical article",
                  "relationship": "cold", "affiliation": "unknown", "verified_at": AT,
                  "source_ids": ["source-a"]}
        state = cs.add_record(state, "referrals", person)
        draft = {"id": "draft-a", "opportunity_id": "role-a", "referral_id": "person-a", "version": 1,
                 "text": "Your public article relates to my importer work. May I ask about the role?",
                 "professional_reason": "Related importer experience", "fact_ids": ["fact-a"],
                 "source_ids": ["source-a"]}
        state = cs.add_record(state, "referral_drafts", draft)
        counts = cs.stats(state, LATER)["counts"]
        self.assertEqual((counts["referral_drafts"], counts["referral_contact_events"], counts["sent_roles"]), (1, 0, 0))
        person.update(id="person-b", affiliation="verified_current")
        with self.assertRaises(cs.Invalid):
            cs.add_record(state, "referrals", person)
        person.update(affiliation="unknown", relationship="acquaintance")
        with self.assertRaises(cs.Invalid):
            cs.add_record(state, "referrals", person)

    def test_observed_forms_need_sources_and_actual_requiredness(self):
        state = base()
        form = {"id": "form-a", "opportunity_id": "role-a", "at": AT,
                "status": "provisional", "source_ids": [], "fields": [
                    {"id": "name", "label": "Full name", "control": "text", "help_text": "",
                     "required": None, "choices": []}]}
        state = cs.add_record(state, "forms", form)
        form.update(id="form-b", status="observed")
        with self.assertRaises(cs.Invalid):
            cs.add_record(state, "forms", form)
        form["source_ids"] = ["source-a"]
        with self.assertRaises(cs.Invalid):
            cs.add_record(state, "forms", form)
        form["fields"][0]["required"] = True
        state = cs.add_record(state, "forms", form)
        self.assertEqual(len(state["forms"]), 2)

    def test_cli_init_validation_transaction_and_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private" / "state.json"
            command = [sys.executable, str(ROOT / "scripts/career_state.py")]
            def run(*args):
                return subprocess.run(command + list(map(str, args)), capture_output=True, text=True)
            self.assertEqual(run("init", path).returncode, 0)
            original = path.read_bytes()
            self.assertEqual(run("init", path).returncode, 2)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(run("research-check", path).returncode, 3)
            record = Path(directory) / "source.json"
            record.write_text(json.dumps(base()["sources"][0]))
            self.assertEqual(run("put", path, "sources", record).returncode, 0)
            self.assertEqual(cs.read_state(path)["revision"], 1)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            lock = path.with_name(path.name + ".lock")
            lock.write_text("Synthetic writer")
            self.assertEqual(run("put", path, "sources", record).returncode, 2)
            lock.unlink()
            record.write_text(json.dumps({"id": "bad"}))
            original = path.read_bytes()
            self.assertEqual(run("put", path, "facts", record).returncode, 2)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(run("validate", path).returncode, 0)


if __name__ == "__main__":
    unittest.main()
