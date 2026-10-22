"""Synthetic immutable-library, directory-layout, credential and CLI integration tests."""
import copy
import errno
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

from test_state import ROOT, AT, LATER, base
sys.path.insert(0, str(ROOT / "scripts"))
import career_materials as cm
import career_state as state_api
import career_snapshot as snapshot


def material(identifier="resume-1", version=1, **changes):
    return {"id": identifier, "family_id": "general-api-resume", "version": version, "kind": "resume",
            "language": "English", "visibility": "external", "at": AT, "fact_ids": ["fact-a"], "source_ids": ["source-user"], **changes}


def preparation(identifier="application-1", role="role-a", materials=None, **changes):
    return {"id": identifier, "opportunity_id": role, "label": "January application", "at": AT,
            "materials": materials or [{"slot": "resume", "material_id": "resume-1"}], **changes}


def credential(**changes):
    return {"id": "credential-1", "kind": "certificate", "title": "Demo Systems course", "issuer": "Demo Academy",
            "subjects": ["Reliable imports"], "issued_on": "2024-01-01", "expires_on": "2025-12-31",
            "source_ids": ["source-user"], "verification": "user_provided", "disclosure": "allowed", **changes}


class MaterialTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        state_api.initialize_workspace(root / "Private career")
        workspace = root / "Private career"
        path = workspace / "Data/state.json"
        path.write_text(json.dumps(base()))
        resume = root / "synthetic-resume.txt"; resume.write_text("Synthetic supported resume: implemented importer retry handling.")
        cm.register_material(path, workspace, material(), resume, 0)
        return workspace, path, resume

    def test_two_roles_two_attempts_share_one_immutable_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, path, resume = self.fixture(directory)
            for request in (preparation(), preparation("application-2"), preparation("application-3", "role-b")):
                cm.prepare_attempt(path, workspace, request, state_api.read_state(path)["revision"])
            state = state_api.read_state(path)
            self.assertEqual(len(list((workspace / "Materials/objects").iterdir())), 1)
            self.assertEqual(len(state["application_attempts"]), 3)
            self.assertEqual(len({a["path"] for a in state["application_attempts"]}), 3)
            company_parts = {Path(a["path"]).parts[1] for a in state["application_attempts"]}
            role_parts = {Path(a["path"]).parts[2] for a in state["application_attempts"]}
            self.assertEqual(len(company_parts), 1); self.assertEqual(len(role_parts), 2)
            for attempt in state["application_attempts"]:
                self.assertTrue(cm.verify_attempt(state, workspace, attempt))
                link = workspace / attempt["materials"][0]["link_path"]
                self.assertTrue(link.is_symlink()); self.assertFalse(Path(link.readlink()).is_absolute())
            counts = state_api.stats(state, LATER)["counts"]
            self.assertEqual((counts["prepared_roles"], counts["sent_roles"], counts["opportunities"]), (2, 0, 2))
            first_pin = copy.deepcopy(state["application_attempts"][0]["materials"])
            resume.write_text("A genuinely tailored synthetic resume.")
            cm.register_material(path, workspace, material("tailored-1", family_id="tailored-api"), resume, state["revision"])
            state = state_api.read_state(path)
            cm.prepare_attempt(path, workspace, preparation("application-4", materials=[{"slot": "resume", "material_id": "tailored-1"}]), state["revision"])
            state = state_api.read_state(path)
            self.assertEqual(state["application_attempts"][0]["materials"], first_pin)
            self.assertEqual(len(list((workspace / "Materials/objects").iterdir())), 2)
            self.assertNotEqual(state["application_attempts"][-1]["materials"][0]["sha256"], first_pin[0]["sha256"])

    def test_repeated_registration_and_preparation_are_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, path, resume = self.fixture(directory)
            before = state_api.read_state(path)
            cm.register_material(path, workspace, material(), resume, before["revision"])
            self.assertEqual(state_api.read_state(path), before)
            cm.prepare_attempt(path, workspace, preparation(), before["revision"])
            before = state_api.read_state(path)
            cm.prepare_attempt(path, workspace, preparation(), before["revision"])
            self.assertEqual(state_api.read_state(path), before)
            with self.assertRaises(state_api.Invalid):
                cm.prepare_attempt(path, workspace, preparation(materials=[{"slot": "another", "material_id": "resume-1"}]), before["revision"])

    def test_relative_links_and_references_survive_workspace_move(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, path, _ = self.fixture(directory)
            cm.prepare_attempt(path, workspace, preparation(), 1)
            moved = Path(directory) / "Moved career"
            shutil.move(workspace, moved)
            state = state_api.read_state(moved / "Data/state.json")
            self.assertTrue(cm.verify_attempt(state, moved, state["application_attempts"][0]))
            snapshot.export_snapshot(moved / "Data/state.json", moved, LATER)
            with zipfile.ZipFile(moved / "Career.xlsx") as archive:
                links = archive.read("xl/worksheets/_rels/sheet1.xml.rels").decode()
                self.assertIn("Materials/objects/", links)
                self.assertNotIn("file://", links)
                self.assertNotIn(str(workspace), links)

    def test_unsupported_symlinks_use_reference_without_copying_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, path, _ = self.fixture(directory)
            def unsupported(*args): raise OSError(errno.ENOTSUP, "Synthetic unsupported symlink")
            cm.prepare_attempt(path, workspace, preparation(), 1, symlink=unsupported)
            state = state_api.read_state(path); attempt = state["application_attempts"][0]
            pin = attempt["materials"][0]
            self.assertEqual(pin["link_mode"], "reference")
            self.assertFalse((workspace / pin["link_path"]).exists())
            self.assertTrue((workspace / pin["reference_path"]).is_file())
            self.assertTrue(cm.verify_attempt(state, workspace, attempt))
            self.assertEqual(len(list((workspace / "Materials/objects").iterdir())), 1)

    def test_path_traversal_collision_and_material_tampering_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, path, _ = self.fixture(directory)
            self.assertNotEqual(cm.component("C++", "first"), cm.component("C#", "second"))
            with self.assertRaises(state_api.Invalid): cm.inside(workspace, "../escape")
            with self.assertRaises(state_api.Invalid): cm.inside(workspace, "/absolute")
            with self.assertRaises(state_api.Invalid): cm.prepare_attempt(path, workspace, preparation(materials=[{"slot": "../resume", "material_id": "resume-1"}]), 1)
            cm.prepare_attempt(path, workspace, preparation(), 1)
            with mock.patch.object(cm, "component", return_value="same"):
                cm.prepare_attempt(path, workspace, preparation("collision-a"), 2)
                with self.assertRaises(state_api.Invalid): cm.prepare_attempt(path, workspace, preparation("collision-b"), 3)
            state = state_api.read_state(path)
            content = workspace / state["materials"][0]["path"]
            content.chmod(0o600); content.write_text("Synthetic unexpected replacement")
            with self.assertRaises(state_api.Invalid): cm.verify_attempt(state, workspace, state["application_attempts"][0])

    def test_package_only_selected_materials_and_refuses_escaping_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, path, resume = self.fixture(directory)
            private = material("private-note", family_id="private", visibility="private", kind="private_fit_assessment")
            cm.register_material(path, workspace, private, resume, 1)
            cm.prepare_attempt(path, workspace, preparation(materials=[{"slot": "resume", "material_id": "resume-1"}, {"slot": "private-note", "material_id": "private-note"}]), 2)
            state = state_api.read_state(path)
            out = Path(directory) / "selected.zip"
            cm.package_attempt(state, workspace, "application-1", ["resume"], out, LATER)
            with zipfile.ZipFile(out) as archive:
                self.assertEqual(set(archive.namelist()), {"resume.txt", "manifest.json"})
                self.assertNotIn(b"state.json", archive.read("manifest.json"))
            with self.assertRaises(state_api.Invalid): cm.package_attempt(state, workspace, "application-1", ["private-note"], Path(directory) / "private.zip", LATER)
            pin = state["application_attempts"][0]["materials"][0]
            link = workspace / pin["link_path"]; link.unlink()
            escaped = Path(directory) / "not-selected-secret.txt"; escaped.write_text("Synthetic secret excluded")
            link.symlink_to(escaped)
            with self.assertRaises(state_api.Invalid): cm.package_attempt(state, workspace, "application-1", ["resume"], Path(directory) / "escaping.zip", LATER)
            self.assertFalse((Path(directory) / "escaping.zip").exists())

    def test_credential_expiry_verification_and_sensitive_field_boundary(self):
        state = state_api.add_record(base(), "credentials", credential())
        self.assertEqual(state_api.credential_status(state["credentials"][0], LATER)["expiry_state"], "expired")
        self.assertEqual(state["credentials"][0]["verification"], "user_provided")
        artifact = copy.deepcopy(state["artifacts"][0]); artifact.update(id="credential-cv", version=2,
                    credential_claims=[{"credential_id": "credential-1", "portrayal": "current"}])
        with self.assertRaises(state_api.Invalid): state_api.add_record(state, "artifacts", artifact)
        artifact["credential_claims"][0]["portrayal"] = "earned"
        state_api.add_record(state, "artifacts", artifact)
        with self.assertRaises(state_api.Invalid): state_api.add_record(base(), "credentials", credential(serial_number="Do not retain"))
        with self.assertRaises(state_api.Invalid): state_api.add_record(base(), "credentials", credential(verification="independently_verified", verification_source_id="source-user", verified_at=AT))
        verified = credential(verification="independently_verified", source_ids=["source-a"], verification_source_id="source-a", verified_at=AT)
        state_api.add_record(base(), "credentials", verified)
        with self.assertRaises(state_api.Invalid): state_api.add_record(base(), "credentials", credential(issued_on="2027-01-01"))

    def test_delivery_and_rehearsal_references_preserve_exact_roles(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, path, _ = self.fixture(directory)
            cm.prepare_attempt(path, workspace, preparation(), 1)
            state = state_api.read_state(path)
            delivery = {"id": "delivery", "opportunity_id": "role-b", "application_attempt_id": "application-1",
                        "outcome": "sent", "at": AT, "evidence": "Synthetic report", "channel": "manual"}
            with self.assertRaises(state_api.Invalid): state_api.add_record(state, "attempts", delivery)
            plan = {"id": "practice", "opportunity_id": "role-a", "language": "English", "question": "Explain retries",
                    "outline": "Personal action and supported result", "question_status": "practice_hypothesis",
                    "fact_ids": ["fact-a"], "source_ids": [], "pressure_points": [], "employer_questions": []}
            state = state_api.add_record(state, "interview_prep", plan)
            rehearsal = {"id": "rehearsal", "opportunity_id": "role-a", "interview_prep_id": "practice", "at": AT,
                         "language": "English", "answer_summary": "Synthetic practice answer", "feedback": "Clarify individual contribution",
                         "next_step": "Retry one question", "status": "retry_requested"}
            state = state_api.add_record(state, "rehearsals", rehearsal)
            self.assertEqual(state_api.stats(state, LATER)["counts"]["sent_roles"], 0)
            rehearsal.update(id="wrong", opportunity_id="role-b")
            with self.assertRaises(state_api.Invalid): state_api.add_record(state, "rehearsals", rehearsal)

    def test_expired_current_claim_cannot_be_reused_in_a_later_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, path, resume = self.fixture(directory)
            state_api.transact(path, lambda state: state_api.add_record(state, "credentials", credential()), expected_revision=1)
            request = material("credential-resume", family_id="credential-cv", at="2025-01-01T12:00:00Z",
                     credential_claims=[{"credential_id": "credential-1", "portrayal": "current"}])
            cm.register_material(path, workspace, request, resume, 2)
            with self.assertRaises(state_api.Invalid): cm.prepare_attempt(path, workspace, preparation(materials=[{"slot": "resume", "material_id": "credential-resume"}]), 3)

    def test_self_contained_bundle_helpers_work_outside_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); bundle = root / "bundle" / "career-agent"
            build = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/build_skill_bundle.py"), str(bundle)], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            manifest = state_api.load_json(bundle / "BUNDLE.json")
            for relative, expected in manifest["files"].items():
                self.assertEqual(cm.sha256((bundle / relative).read_bytes()), expected)
            self.assertTrue((bundle / "LICENSE").exists())
            workspace = root / "Outside source"
            command = [sys.executable, "-B", str(bundle / "scripts/career_state.py")]
            result = subprocess.run(command + ["init-workspace", str(workspace)], cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run(command + ["validate", str(workspace / "Data/state.json")], cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for helper in ("career_materials.py", "career_snapshot.py"):
                result = subprocess.run([sys.executable, "-B", str(bundle / "scripts" / helper), "--help"], cwd=root, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run(command + ["init", str(bundle / "private/state.json")], cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2); self.assertFalse((bundle / "private").exists())

    def test_imported_unsafe_material_slots_fail_schema_runtime_and_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, path, _ = self.fixture(directory)
            cm.prepare_attempt(path, workspace, preparation(), 1)
            state = state_api.read_state(path)
            for slot in ("../../escape", "/absolute", "resume\\evil", "..", "Resume", "résumé", "resume\n", "a" * 41):
                malformed = copy.deepcopy(state)
                malformed["application_attempts"][0]["materials"][0]["slot"] = slot
                with self.subTest(slot=slot):
                    with self.assertRaises(state_api.Invalid): state_api.validate_shape(malformed, state_api.state_schema())
                    with self.assertRaises(state_api.Invalid): state_api.validate(malformed)
                    with self.assertRaises(state_api.Invalid): cm.verify_attempt(malformed, workspace, malformed["application_attempts"][0])
                    output = Path(directory) / "unsafe.zip"
                    with self.assertRaises(state_api.Invalid): cm.package_attempt(malformed, workspace, "application-1", [slot], output, LATER)
                    self.assertFalse(output.exists())

    def test_package_consumer_checks_selected_slot_even_if_state_validation_is_bypassed(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, path, _ = self.fixture(directory)
            cm.prepare_attempt(path, workspace, preparation(), 1)
            state = state_api.read_state(path)
            state["application_attempts"][0]["materials"][0]["slot"] = "../../escape"
            output = Path(directory) / "consumer-unsafe.zip"
            with mock.patch.object(cm.cs, "validate", return_value=state), mock.patch.object(cm, "verify_attempt", return_value=True):
                with self.assertRaises(state_api.Invalid): cm.package_attempt(state, workspace, "application-1", ["../../escape"], output, LATER)
            self.assertFalse(output.exists())

    def test_empty_preparation_is_rejected_without_freezing_an_attempt_id(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, path, _ = self.fixture(directory)
            original = path.read_bytes()
            request = preparation("not-yet-prepared", "role-b"); request["materials"] = []
            with self.assertRaises(state_api.Invalid): cm.prepare_attempt(path, workspace, request, 1)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list((workspace / "Applications").iterdir()), [])
            self.assertEqual(state_api.stats(state_api.read_state(path), LATER)["counts"]["prepared_roles"], 1)
            cm.prepare_attempt(path, workspace, preparation("not-yet-prepared", "role-b"), 1)
            state = state_api.read_state(path)
            self.assertEqual(state_api.stats(state, LATER)["counts"]["prepared_roles"], 2)
            malformed = copy.deepcopy(state); malformed["application_attempts"][0]["materials"] = []
            with self.assertRaises(state_api.Invalid): state_api.validate(malformed)
            with self.assertRaises(state_api.Invalid): state_api.stats(malformed, LATER)
            with self.assertRaises(state_api.Invalid): cm.verify_attempt(malformed, workspace, malformed["application_attempts"][0])

    def test_bundle_uses_explicit_reference_allowlist(self):
        import build_skill_bundle as builder
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / "synthetic-source"
            for name in ("skills", "scripts", "references"):
                shutil.copytree(ROOT / name, source / name, ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copyfile(ROOT / "release.json", source / "release.json")
            unexpected = source / "skills/career-agent/references/alex-demo-private.md"
            unexpected.write_text("Synthetic note excluded from distribution.")
            output = root / "bundle"
            with mock.patch.object(builder, "SOURCE", source): builder.build(output)
            self.assertFalse((output / "references/alex-demo-private.md").exists())
            manifest = state_api.load_json(output / "BUNDLE.json")
            self.assertNotIn("references/alex-demo-private.md", manifest["files"])
            self.assertEqual({p.name for p in (output / "references").glob("*.md")}, set(builder.REFERENCES) | {"state-format.md"})
            (source / "skills/career-agent/references/profile.md").unlink()
            with mock.patch.object(builder, "SOURCE", source):
                with self.assertRaises(ValueError): builder.build(root / "missing-required-reference")

    def test_review_update_and_history_cli_require_review_and_expected_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / "state.json"; path.write_text(json.dumps(base()))
            command = [sys.executable, "-B", str(ROOT / "scripts/career_state.py")]
            def run(*args): return subprocess.run(command + list(map(str, args)), capture_output=True, text=True)
            update = root / "update.json"; update.write_text(json.dumps({"operation": "observe_opportunity", "opportunity_id": "role-a", "observation": {"at": LATER, "source_id": "source-a", "status": "unknown"}}))
            denied = run("review-update", path, update, "--expected-revision", 0, "--reason", "Synthetic review")
            self.assertEqual(denied.returncode, 2)
            good = run("review-update", path, update, "--expected-revision", 0, "--reason", "Synthetic review", "--user-confirmed")
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertEqual(run("review-update", path, update, "--expected-revision", 0, "--reason", "Stale review", "--user-confirmed").returncode, 2)
            rows = root / "rows.json"; rows.write_text(json.dumps([{"source_locator": "synthetic-list", "employer": "Northstar Demo", "role": "API Engineer", "status": "uncertain"}]))
            preview = run("history-preview", path, rows); self.assertEqual(preview.returncode, 0, preview.stderr)
            plan = root / "plan.json"; plan.write_text(preview.stdout)
            good = run("history-apply", path, plan, "--expected-revision", 1, "--reason", "Reviewed import", "--user-confirmed")
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertFalse(state_api.research_allowed(state_api.read_state(path)))
            revised = run("history-preview", path, rows); plan.write_text(revised.stdout)
            before = path.read_bytes()
            good = run("history-apply", path, plan, "--expected-revision", 2, "--reason", "Same import", "--user-confirmed")
            self.assertEqual(good.returncode, 0, good.stderr); self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__": unittest.main()
