"""Synthetic refresh/delivery regressions: exact selected bytes and complete scope receipts."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from test_state import AT, ROOT, attempt
from test_search_cases import configured, request
from workflow_fixtures import baseline_audit, reviewed
import career_achievements as achievements
import career_search as search
import career_materials as materials
cs = search.cs


class PacketRefreshTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory) / "Private"
        cs.initialize_workspace(root)
        path = root / "Data/state.json"
        path.write_text(cs.canonical_json(configured()))
        item = request()
        self.assertTrue(search.prepare_case(path, root, item, 0)["completed"])
        return root, path, item

    def clarify(self, path):
        def update(state):
            state = achievements.clarify(state, {"fact_id": "fact-a", "question_key": "achievement.scope", "disposition": "answered",
                "at": AT, "evidence": "User clarified design responsibility as well as implementation"})
            meaning = copy.deepcopy(state["achievement_interpretations"][0])
            meaning.update(id="meaning-revised", version=2)
            meaning["fields"]["decisions"] = {"status": "supported", "text": "Designed the retry policy", "fact_ids": ["fact-a"]}
            return reviewed(cs.add_record(state, "achievement_interpretations", meaning))
        return cs.transact(path, update, cs.read_state(path)["revision"])

    def revised(self, state, item):
        item = copy.deepcopy(item)
        item["revision_reason"] = "Apply the confirmed clarification to all selected unsent packet slots"
        # The reviewer must read the text and record a new meaning attestation, not rehash an old one.
        doc = item["documents"]["resume"]
        doc["text"] += "\n"
        doc["adaptation_audit"] = baseline_audit(state, doc["text"])
        item["documents"]["cover-letter"]["text"] += "\nUpdated supported responsibility.\n"
        return item

    def test_clarification_makes_old_priority_packet_stale_then_explicit_refresh_pins_new_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root, path, item = self.fixture(directory)
            old = cs.read_state(path)
            old_attempt = copy.deepcopy(old["application_attempts"][0])
            old_files = {m["id"]: materials.material_file(root,m).read_bytes() for m in old["materials"]}
            state = self.clarify(path)
            check = search.deliver_packets(path, root, [item["id"]])
            self.assertFalse(check["all_updated"]); self.assertFalse(check["completed"])
            self.assertIn("conditional", check["packets"][0]["label"])
            self.assertTrue(check["packets"][0]["documents"])
            refreshed = self.revised(state, item)
            self.assertTrue(search.prepare_case(path, root, refreshed, state["revision"], refresh=True)["completed"])
            state = cs.read_state(path)
            receipt = search.deliver_packets(path, root, [item["id"]])
            self.assertTrue(receipt["all_updated"]); self.assertTrue(receipt["completed"])
            self.assertEqual(receipt["workspace"], str(root.resolve()))
            self.assertNotEqual(receipt["packets"][0]["attempt_id"], old_attempt["id"])
            self.assertIn(old_attempt, state["application_attempts"])
            for m in state["materials"]:
                if m["id"] in old_files: self.assertEqual(materials.material_file(root,m).read_bytes(),old_files[m["id"]])
            self.assertEqual(state["search_cases"][0]["novelty"], old["search_cases"][0]["novelty"])
            self.assertTrue(any(h["operation"]=="refresh_saved_packet" for h in state["change_history"]))
            selected=[h for h in state["change_history"] if h["operation"]=="select_packet_version"][-1]
            self.assertEqual(selected["after"]["attempt_id"],receipt["packets"][0]["attempt_id"])
            self.assertEqual(selected["before"]["attempt_id"],old_attempt["id"])
            self.assertEqual(state["attempts"], [])

    def test_new_clarification_requires_new_meaning_review_not_a_fresh_packet_hash_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root,path,item=self.fixture(directory)
            def update(state):
                state=achievements.clarify(state,{"fact_id":"fact-a","question_key":"achievement.contribution","disposition":"answered", "at":AT,"evidence":"User explained an additional supported design responsibility"})
                return reviewed(state)
            state=cs.transact(path,update,cs.read_state(path)["revision"])
            item["revision_reason"]="Apply the clarification"
            result=search.prepare_case(path,root,item,state["revision"],refresh=True)
            self.assertTrue(result["saved"]);self.assertFalse(result["all_updated"])
            self.assertFalse(result["completed"])
            self.assertFalse(result["packets"][0]["assessment"]["achievement_review"]["ready"])

    def test_refresh_requires_reason_existing_case_and_exact_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root,path,item=self.fixture(directory); state=cs.read_state(path)
            for change in ("reason", "new-case", "identity"):
                revised=copy.deepcopy(item);revised["revision_reason"]="User requested updating saved wording"
                if change=="reason": revised.pop("revision_reason")
                if change=="new-case": revised["id"]="unregistered";revised["opportunity"].update(id="unknown-role",identity="unknown-role",role_url="https://northstar-demo.example/jobs/unknown")
                if change=="identity": revised["opportunity"]["role_url"]+="/another"
                raw=path.read_bytes()
                with self.assertRaises(cs.Invalid):search.prepare_case(path,root,revised,state["revision"],refresh=True)
                self.assertEqual(path.read_bytes(),raw)

    def test_sent_and_uncertain_pins_cannot_be_replaced(self):
        for outcome in ("sent", "uncertain"):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as directory:
                root,path,item=self.fixture(directory)
                state=cs.transact(path,lambda s:cs.add_record(s,"attempts",attempt(role="new-role",outcome=outcome)),cs.read_state(path)["revision"])
                revised=self.revised(state,item);raw=path.read_bytes()
                with self.assertRaises(cs.Invalid): search.prepare_case(path,root,revised,state["revision"],refresh=True)
                self.assertEqual(path.read_bytes(),raw)

    def test_noop_report_control_changes_do_not_invalidate_wording_but_answer_changes_do(self):
        with tempfile.TemporaryDirectory() as directory:
            root,path,item=self.fixture(directory)
            state=cs.transact(path,lambda s:{**s,"report_preferences":{"frequency":"on_request","results_only":True}},cs.read_state(path)["revision"])
            self.assertTrue(search.deliver_packets(path,root,[item["id"]])["all_updated"])
            state=self.clarify(path)
            self.assertFalse(search.deliver_packets(path,root,[item["id"]])["all_updated"])
            self.assertEqual(achievements.clarification_plan(state,["baseline-achievement"])["groups"],[])

    def test_entire_selected_scope_required_and_ad_hoc_pointer_never_selects_a_packet(self):
        with tempfile.TemporaryDirectory() as directory:
            root,path,item=self.fixture(directory)
            state=cs.read_state(path); state["current_packet_reviews"]={"path":"Reviews/wrong-resume.md"}
            path.write_text(cs.canonical_json(state))
            receipt=search.deliver_packets(path,root,[item["id"],"legacy-unregistered-packet"])
            self.assertFalse(receipt["all_updated"]);self.assertFalse(receipt["completed"])
            self.assertEqual(receipt["selected"],2);self.assertEqual(receipt["reviewed_current"],1)
            resume=next(d for d in receipt["packets"][0]["documents"] if d["slot"]=="resume")
            self.assertEqual(resume["text"],item["documents"]["resume"]["text"])
            self.assertTrue(Path(resume["path"]).is_relative_to(root.resolve()))
            with self.assertRaises(cs.Invalid):search.deliver_packets(path,root,[item["id"],item["id"]])

    def test_failed_audit_stays_saveable_but_delivery_and_outgoing_package_are_conditional(self):
        with tempfile.TemporaryDirectory() as directory:
            root,path,item=self.fixture(directory); state=cs.read_state(path)
            revised=self.revised(state,item)
            revised["documents"]["resume"]["adaptation_audit"]["semantic_review"]["status"]="pending"
            result=search.prepare_case(path,root,revised,state["revision"],refresh=True)
            self.assertTrue(result["saved"]);self.assertFalse(result["completed"])
            receipt=search.deliver_packets(path,root,[item["id"]]);self.assertFalse(receipt["all_updated"])
            self.assertEqual(len(receipt["packets"][0]["documents"]),4)
            state=cs.read_state(path);aid=state["search_cases"][0]["attempt_id"]
            with self.assertRaises(cs.Invalid):materials.package_attempt(state,root,aid,["resume"],root/"outgoing.zip",AT)
            self.assertFalse((root/"outgoing.zip").exists())

    def test_delivery_detects_missing_file_and_state_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root,path,item=self.fixture(directory)
            original=search.verify_case
            def drift(*args):
                result=original(*args);path.write_text(path.read_text()+" ");return result
            with mock.patch.object(search,"verify_case",side_effect=drift):
                with self.assertRaises(cs.Invalid):search.deliver_packets(path,root,[item["id"]])
            state=cs.read_state(path);materials.material_file(root,state["materials"][0]).unlink()
            receipt=search.deliver_packets(path,root,[item["id"]]);self.assertFalse(receipt["all_updated"])
            self.assertIn("error",receipt["packets"][0])

    def test_legacy_receipt_absent_and_stale_concurrent_refresh_are_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root,path,item=self.fixture(directory);state=cs.read_state(path)
            state["search_cases"][0].pop("packet_evidence_sha256");path.write_text(cs.canonical_json(state))
            receipt=search.deliver_packets(path,root,[item["id"]]);self.assertFalse(receipt["all_updated"])
            revised=self.revised(state,item)
            with self.assertRaises(cs.Invalid):search.prepare_case(path,root,revised,0,refresh=True)

    def test_existing_imported_role_can_receive_review_packet_without_becoming_a_new_find(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/"Private";cs.initialize_workspace(root);path=root/"Data/state.json"
            state=configured();item=request();state=cs.add_record(state,"sources",item["sources"][0]);state=cs.add_record(state,"opportunities",item["opportunity"])
            path.write_text(cs.canonical_json(state));item["revision_reason"]="Review an already known imported role"
            result=search.prepare_case(path,root,item,0,refresh=True)
            self.assertTrue(result["completed"]);self.assertEqual(result["new_cases_counted"],0)
            saved=cs.read_state(path);self.assertEqual(saved["search_cases"][0]["novelty"]["status"],"known")
            report=search.case_report(path,root,item["batch_id"],1)
            self.assertEqual(report["new_ready"],0);self.assertTrue(report["cases"][0]["revisit"])
            self.assertEqual(report["cases"][0]["status"],"ready")
            self.assertEqual(len(saved["opportunities"]),1);self.assertEqual(saved["attempts"],[])

    def test_bulk_receipt_cannot_drop_an_unfinished_selected_packet(self):
        with tempfile.TemporaryDirectory() as directory:
            root,path,item=self.fixture(directory)
            plan={"id":"refresh-all","at":AT,"case_ids":[item["id"],"legacy-packet"],"reason":"User asked to review every selected packet"}
            state=cs.transact(path,lambda s:search.plan_refresh(s,plan),cs.read_state(path)["revision"])
            with self.assertRaises(cs.Invalid):search.deliver_packets(path,root,[item["id"]],"refresh-all")
            receipt=search.deliver_packets(path,root,plan["case_ids"],"refresh-all")
            self.assertFalse(receipt["all_updated"]);self.assertEqual(receipt["selected"],2)
            with self.assertRaises(cs.Invalid):search.plan_refresh(state,{**plan,"case_ids":[item["id"]]})
            self.assertEqual(search.plan_refresh(state,plan),state)

    def test_team_metric_pending_selection_is_reinterpreted_and_reaches_chat_portal_and_package(self):
        from test_achievements import captured, interpreted, fact
        from workflow_fixtures import reviewed
        import career_portal as portal
        original="The team reported USD 42000 annual savings from reconciliation."
        metric={"id":"saving","verbatim":"USD 42000 annual savings","units":["USD","annual"],"attribution":"team"}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/"Private";cs.initialize_workspace(root);path=root/"Data/state.json"
            state=captured(original,[metric],state=configured());state=fact(state,"team-result",original,"team")
            state=interpreted(state,metric_context=True);item=request()
            item["documents"]["resume"]["text"]="# Resume\n\nImporter engineering experience."
            audit={"target_role":"new-role","at":AT,"entries":[{"achievement_id":"achievement-a","decision":"preserve_pending",
                "reason":"Measurement attribution was not yet expressed", "rendered_text":"", "fact_ids":[],"meaning_fields":[],"metrics":[]}]}
            state,audit=reviewed(state,audit,item["documents"]["resume"]["text"]);item["documents"]["resume"]["adaptation_audit"]=audit
            path.write_text(cs.canonical_json(state))
            first=search.prepare_case(path,root,item,0);self.assertTrue(first["saved"]);self.assertFalse(first["completed"])
            state=cs.read_state(path)
            wording="Implemented importer retry handling; the team reported USD 42000 annual savings."
            item["documents"]["resume"].update(text="# Resume\n\n"+wording,fact_ids=["fact-a","team-result"])
            audit["entries"]=[{"achievement_id":"achievement-a","decision":"qualify","reason":"Retain secondary team impact with personal contribution",
                "rendered_text":wording,"fact_ids":["fact-a","team-result"],"meaning_fields":["contribution","problem"],
                "metrics":[{"metric_id":"saving","decision":"qualify","rendered_text":"the team reported USD 42000 annual savings", "fact_ids":["team-result"],"claim_scope":"team","scope_phrase":"the team"}]}]
            _,audit=reviewed(state,audit,item["documents"]["resume"]["text"]);item["documents"]["resume"]["adaptation_audit"]=audit
            item["revision_reason"]="Clarified team attribution; reevaluate the old pending selection"
            fixed=search.prepare_case(path,root,item,state["revision"],refresh=True);self.assertTrue(fixed["completed"])
            receipt=search.deliver_packets(path,root,[item["id"]]);resume=next(d for d in receipt["packets"][0]["documents"] if d["slot"]=="resume")
            self.assertIn("USD 42000",resume["text"])
            export=portal.export_portal(path,root,item["batch_id"])
            manifest=json.loads((Path(export["path"]).parent/"snapshot.json").read_text());self.assertEqual(manifest["ready"],1)
            self.assertIn("USD 42000",(Path(export["path"]).parent/"documents"/(resume["sha256"]+".md")).read_text())
            state=cs.read_state(path);destination=root/"selected.zip"
            materials.package_attempt(state,root,receipt["packets"][0]["attempt_id"],["resume"],destination,AT)
            import zipfile
            with zipfile.ZipFile(destination) as archive:self.assertIn(b"USD 42000",archive.read("resume.md"))

    def test_delivery_cli_from_unrelated_directory_returns_pinned_markdown_and_truthful_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root,path,item=self.fixture(directory);query=Path(directory)/"query.json";query.write_text(json.dumps({"case_ids":[item["id"]]}))
            proc=subprocess.run([sys.executable,"-B",str(ROOT/"scripts/career_search.py"),"deliver",str(path),str(root),str(query)],cwd=directory,capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertEqual(len(json.loads(proc.stdout)["packets"][0]["documents"]),4)


if __name__ == "__main__": unittest.main()
