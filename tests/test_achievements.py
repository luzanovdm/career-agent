"""Synthetic lossless-source, clarification and actual resume-save regressions."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_state import ROOT, AT, LATER, base
from test_search_cases import configured, request
sys.path.insert(0, str(ROOT / "scripts"))
import career_achievements as achievements
import career_materials as materials
import career_search as search
cs = achievements.cs
from workflow_fixtures import reviewed

def reviewed_audit(state, text, record):
    state, record = reviewed(state, record, text)
    return achievements.audit_resume(state, text, record)


def fact(state, identifier, text, ownership="individual", confirmed=True):
    row = copy.deepcopy(state["facts"][0])
    row.update(id=identifier, statement=text, ownership=ownership, status="confirmed" if confirmed else "unconfirmed")
    if not confirmed: row.pop("confirmation", None)
    return cs.add_record(state, "facts", row)


def captured(text="Implemented retry handling for an invoice importer.", metrics=None, state=None):
    state = copy.deepcopy(state or base())
    state["achievement_evidence"] = []; state["achievement_interpretations"] = []
    state["profile"].pop("evidence_review", None)
    state = fact(state, "raw-fact", text, "unknown", False)
    return achievements.capture(state, {"id": "achievement-a", "fact_id": "raw-fact", "source_id": "source-user",
        "source_locator": "Synthetic resume version 1, page 1, experience", "original_text": text, "metrics": metrics or []})


def interpreted(state, contribution="fact-a", context="fact-a", metric_context=False):
    fields = {"contribution": {"status": "supported", "text": "Implemented the retry mechanism.", "fact_ids": [contribution]},
              "problem": {"status": "supported", "text": "Importer reliability workflow.", "fact_ids": [context]}}
    if metric_context: fields["metric_context"] = {"status": "supported", "text": "Confirmed measurement scope.", "fact_ids": [context]}
    return reviewed(cs.add_record(state, "achievement_interpretations", {"id": "meaning-a", "achievement_id": "achievement-a", "version": 1, "at": AT, "fields": fields}))


def audit(text="Implemented retry handling for an invoice importer.", draft=None, **changes):
    entry = {"achievement_id": "achievement-a", "decision": "include", "reason": "Relevant reliable import work.", "rendered_text": text,
             "fact_ids": ["fact-a"], "meaning_fields": ["contribution", "problem"], "metrics": []}
    entry.update(changes)
    record = {"target_role": "new-role", "at": AT, "entries": [entry]}
    record["semantic_review"] = reviewed(interpreted(captured()), record, "# Resume\n\n" + text if draft is None else draft)[1]["semantic_review"]
    return record


def clarification(disposition="unknown", key="metric_context", **changes):
    return {"fact_id": "raw-fact", "question_key": "achievement." + key, "disposition": disposition, "at": AT,
            "evidence": "Synthetic user answer recorded once.", **changes}


class AchievementTests(unittest.TestCase):
    def test_capture_retains_uninterpreted_numbers_and_immutable_original(self):
        text = "Importer latency changed from 950 ms to 210 ms across 8 weeks."
        state = captured(text)
        original = state["achievement_evidence"][0]
        self.assertEqual(original["original_text"], text)
        self.assertEqual(original["numeric_anchors"], ["950", "210", "8"])
        self.assertEqual(len(original["metrics"]), 1)
        self.assertEqual(original["metrics"][0]["verbatim"], text)
        request_ = {k: v for k, v in original.items() if k != "numeric_anchors"}
        self.assertEqual(achievements.capture(state, request_), state)
        request_["original_text"] = "Improved latency."
        with self.assertRaises(cs.Invalid): achievements.capture(state, request_)
        bad = copy.deepcopy(state); bad["achievement_evidence"][0]["metrics"] = []
        with self.assertRaises(cs.Invalid): cs.validate(bad)
        self.assertEqual(state["facts"][-1]["status"], "unconfirmed")

    def test_ambiguous_team_savings_keep_number_without_claiming_personal_causality(self):
        original = "The team reported USD 42000 annual savings from reconciliation."
        metric = {"id": "saving", "verbatim": "USD 42000 annual savings", "units": ["USD", "annual"], "attribution": "team"}
        state = captured(original, [metric]); state = interpreted(state)
        plan = achievements.clarification_plan(state, ["achievement-a"])
        self.assertEqual(plan["groups"][0]["question_key"], "achievement.metric_context")
        self.assertTrue(plan["groups"][0]["suggestions_are_hypotheses"])
        state = fact(state, "team-result", original, "team")
        wording = "Implemented importer retry handling; the team reported USD 42000 annual savings."
        selection = {"metric_id": "saving", "decision": "qualify", "rendered_text": "the team reported USD 42000 annual savings", "fact_ids": ["team-result"], "claim_scope": "team", "scope_phrase": "the team"}
        record = audit(wording, fact_ids=["fact-a", "team-result"], metrics=[selection])
        self.assertTrue(reviewed_audit(state, wording, record)["valid"])
        unsafe = copy.deepcopy(record); unsafe["entries"][0]["metrics"][0]["claim_scope"] = "individual"
        self.assertFalse(reviewed_audit(state, wording, unsafe)["valid"])
        self.assertEqual(state["achievement_evidence"][0]["original_text"], original)

    def test_before_after_values_and_units_cannot_silently_disappear(self):
        original = "Reduced parser latency from 950 ms to 210 ms."
        metric = {"id": "latency", "verbatim": "950 ms to 210 ms", "units": ["ms"], "attribution": "individual"}
        state = captured(original, [metric]); state = fact(state, "latency-fact", original)
        state = interpreted(state, "latency-fact", "latency-fact", True)
        span = "950 ms to 210 ms"
        choice = {"metric_id": "latency", "decision": "include", "rendered_text": span, "fact_ids": ["latency-fact"], "claim_scope": "individual"}
        record = audit(original, fact_ids=["latency-fact"], metrics=[choice])
        self.assertTrue(reviewed_audit(state, original, record)["valid"])
        for removed in ("Reduced parser latency to 210 ms.", "Reduced parser latency from 950 to 210.", "Reduced parser latency from 210 ms to 950 ms."):
            bad = copy.deepcopy(record); bad["entries"][0]["rendered_text"] = removed; bad["entries"][0]["metrics"][0]["rendered_text"] = removed
            self.assertFalse(reviewed_audit(state, removed, bad)["valid"])
        bad = copy.deepcopy(record); bad["entries"][0]["metrics"] = []
        self.assertFalse(reviewed_audit(state, original, bad)["valid"])

    def test_feature_label_is_not_meaning_and_pending_context_stays_preserved(self):
        state = captured("Owned the export panel.")
        state = cs.add_record(state, "achievement_interpretations", {"id": "label", "achievement_id": "achievement-a", "version": 1, "at": AT,
            "fields": {"contribution": {"status": "supported", "text": "Owned the export panel.", "fact_ids": ["fact-a"]}}})
        self.assertFalse(reviewed_audit(state, "Owned the export panel.", audit("Owned the export panel.", meaning_fields=["contribution"]))["valid"])
        plan = achievements.clarification_plan(state, ["achievement-a"])
        self.assertEqual(plan["groups"][0]["question_key"], "achievement.problem")
        state = achievements.clarify(state, clarification("pending", "problem"))
        record = audit("", decision="preserve_pending", fact_ids=[], meaning_fields=[])
        result = reviewed_audit(state, "# Resume\n", record)
        self.assertTrue(result["valid"]); self.assertEqual(result["pending_achievement_ids"], ["achievement-a"])
        self.assertEqual(state["achievement_evidence"][0]["original_text"], "Owned the export panel.")

    def test_qualitative_work_needs_no_metric_or_repeated_questions(self):
        state = interpreted(captured())
        self.assertTrue(reviewed_audit(state, "Implemented retry handling for an invoice importer.", audit())["valid"])
        self.assertEqual(achievements.clarification_plan(state, ["achievement-a"])["groups"], [])

    def test_reuse_answered_unknown_confidential_and_allow_audited_reopen(self):
        state = captured("Team savings of USD 42000.")
        for disposition in ("answered", "unknown", "confidential", "no_metric", "prefer_not_to_disclose"):
            current = achievements.clarify(state, clarification(disposition))
            self.assertNotIn("achievement.metric_context", [g["question_key"] for g in achievements.clarification_plan(current, ["achievement-a"])["groups"]])
            self.assertEqual(achievements.clarify(current, clarification(disposition)), current)
            with self.assertRaises(cs.Invalid): achievements.clarify(current, clarification("pending"))
            reopened = achievements.clarify(current, clarification("pending", reopen_reason="New source supplied", evidence="User requested revision"))
            self.assertEqual(reopened["change_history"][-1]["before"]["disposition"], disposition)
        pending = achievements.clarify(state, clarification("pending"))
        answered = achievements.clarify(pending, clarification("answered", evidence="Meaning now explained"))
        self.assertEqual(answered["profile"]["metric_dispositions"][0]["disposition"], "answered")

    def test_relevance_alone_cannot_omit_source_strengths(self):
        state = captured("Ran a volunteer archive for 12 months.")
        metrics = [{"metric_id": "uninterpreted-1", "decision": "omit_irrelevant", "fact_ids": [], "claim_scope": "unknown"}]
        record = audit("", decision="omit_irrelevant", fact_ids=[], meaning_fields=[], metrics=metrics,
                       relevance_evidence="Target requires parser implementation; this unrelated archive administration does not support it.")
        self.assertFalse(reviewed_audit(state, "# Resume\n", record)["valid"])
        del record["entries"][0]["relevance_evidence"]
        self.assertFalse(reviewed_audit(state, "# Resume\n", record)["valid"])
        record["entries"] = []
        with self.assertRaises(cs.Invalid): reviewed_audit(state, "# Resume\n", record)

    def test_confidential_number_remains_private_with_supported_qualitative_claim(self):
        state = interpreted(captured("Team savings of USD 42000."))
        state = achievements.clarify(state, clarification("confidential"))
        metric = {"metric_id": "uninterpreted-1", "decision": "private_hold", "fact_ids": [], "claim_scope": "unknown"}
        wording = "Implemented retry handling for an invoice importer."
        self.assertTrue(reviewed_audit(state, wording, audit(wording, metrics=[metric]))["valid"])
        self.assertNotIn("42000", wording)

    def test_external_audit_rejects_unconfirmed_private_and_unknown_evidence(self):
        state = interpreted(captured())
        for field, value in (("status", "unconfirmed"), ("disclosure", "private"), ("private_interview_only", True)):
            bad = copy.deepcopy(state); bad["artifacts"] = []; bad["facts"][0][field] = value
            if field == "private_interview_only": bad["facts"][0]["disclosure"] = "private"
            self.assertFalse(reviewed_audit(bad, "Implemented retry handling for an invoice importer.", audit())["valid"])
        bad = audit(fact_ids=["not-a-fact"])
        with self.assertRaises(cs.Invalid): reviewed_audit(state, "text", bad)

    def test_real_material_registration_requires_audit_and_preserves_failed_state(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)/"Private"; cs.initialize_workspace(workspace); path = workspace/"Data/state.json"
            state = interpreted(captured()); path.write_text(json.dumps(state))
            draft = Path(directory)/"resume.md"; draft.write_text("# Resume\n\nImplemented retry handling for an invoice importer.")
            metadata = {"id": "resume-a", "family_id": "general", "version": 1, "kind": "resume", "language": "English", "visibility": "external", "at": AT, "fact_ids": ["fact-a"], "source_ids": ["source-user"]}
            with self.assertRaises(cs.Invalid): materials.register_material(path, workspace, metadata, draft, 0)
            self.assertEqual(cs.read_state(path), state); self.assertFalse((workspace/"Materials/objects").exists())
            metadata["adaptation_audit"] = audit()
            saved = materials.register_material(path, workspace, metadata, draft, 0)
            self.assertEqual(saved["materials"][0]["adaptation_audit"], audit())
            self.assertEqual(len(saved["materials"]), 1)

    def test_search_writer_and_readback_check_actual_resume_and_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)/"Private"; cs.initialize_workspace(workspace); path=workspace/"Data/state.json"
            state = interpreted(captured(state=configured())); path.write_text(json.dumps(state))
            item=request(); item["documents"]["resume"]["text"] = "# Resume\n\nImplemented retry handling for an invoice importer."
            item["documents"]["resume"]["adaptation_audit"]=audit()
            self.assertTrue(search.prepare_case(path, workspace, item, 0)["completed"])
            saved=cs.read_state(path); resume=next(m for m in saved["materials"] if m["kind"]=="resume")
            self.assertEqual(resume["adaptation_audit"], audit())
            self.assertTrue(search.verify_case(saved, workspace, "case-a")["draft_ready"])
            self.assertEqual(search.verify_case(saved, workspace, "case-a")["achievement_review"]["source_achievement_count"],1)
            # A later evidence source must not silently disappear when reusing an old resume.
            expanded=copy.deepcopy(saved)
            extra={**expanded["achievement_evidence"][0],"id":"achievement-b","original_text":"Owned the archive panel.","numeric_anchors":[],"metrics":[]}
            expanded=cs.add_record(expanded,"achievement_evidence",extra)
            with self.assertRaises(cs.Invalid): search.verify_case(expanded,workspace,"case-a")
            review={"material_id":resume["id"],"sha256":resume["sha256"],"confirmation_evidence":"Reviewed unchanged version", "adaptation_audit":audit()}
            self.assertTrue(achievements.review_reference(saved,workspace,resume,review)["valid"])
            review["sha256"]="0"*64
            with self.assertRaises(cs.Invalid): achievements.review_reference(saved,workspace,resume,review)

    def test_grouped_questions_span_achievements_and_metrics_need_number_evidence(self):
        state=captured("Team savings of USD 42000.")
        state=achievements.capture(state,{"id":"achievement-b","fact_id":"fact-a","source_id":"source-user","source_locator":"Synthetic second source section","original_text":"Implemented the export panel.","metrics":[]})
        plan=achievements.clarification_plan(state,["achievement-a","achievement-b"],3)
        problem=next(g for g in plan["groups"] if g["question_key"]=="achievement.problem")
        self.assertEqual(len(problem["items"]),2)
        self.assertEqual(len(plan["groups"]),3)
        # A confirmed unrelated qualitative fact is not numerical support.
        state=interpreted(captured("The team saved USD 42000.",[{"id":"saving","verbatim":"USD 42000","units":["USD"],"attribution":"team"}]))
        wording="Implemented retry handling; the team saved USD 42000."
        choice={"metric_id":"saving","decision":"qualify","rendered_text":"the team saved USD 42000","fact_ids":["fact-a"],"claim_scope":"team","scope_phrase":"the team"}
        self.assertFalse(reviewed_audit(state,wording,audit(wording,metrics=[choice]))["valid"])

    def test_clarification_cli_is_transactional_strict_and_keeps_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace=Path(directory)/"Private"; cs.initialize_workspace(workspace)
            path=workspace/"Data/state.json"; path.write_text(json.dumps(captured()))
            supplied=Path(directory)/"answer.json"; supplied.write_text(json.dumps(clarification("unknown","problem")))
            cmd=[sys.executable,"-B",str(ROOT/"scripts/career_achievements.py"),"clarify",str(path),str(supplied),"--expected-revision","0"]
            run=subprocess.run(cmd,cwd="/tmp",capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            saved=path.read_bytes(); self.assertEqual(cs.read_state(path)["revision"],1)
            self.assertTrue(list((workspace/"Backups/State").glob("*")))
            run=subprocess.run(cmd,cwd="/tmp",capture_output=True,text=True)
            self.assertEqual(run.returncode,2); self.assertEqual(saved,path.read_bytes())
            supplied.write_text('{"fact_id":"raw-fact","fact_id":"fact-a"}')
            cmd[-1]="1"; run=subprocess.run(cmd,cwd="/tmp",capture_output=True,text=True)
            self.assertEqual(run.returncode,2); self.assertNotIn("Traceback",run.stderr); self.assertEqual(saved,path.read_bytes())

    def test_resume_reference_checks_role_and_fresh_per_target_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace=Path(directory)/"Private"; cs.initialize_workspace(workspace); path=workspace/"Data/state.json"
            state=interpreted(captured(state=configured())); path.write_text(json.dumps(state))
            draft=Path(directory)/"approved.md"; draft.write_text("# Resume\n\nImplemented retry handling for an invoice importer.")
            metadata={"id":"approved","family_id":"general","version":1,"kind":"resume","language":"English","visibility":"external","at":AT,"fact_ids":["fact-a"],"source_ids":["source-user"],"adaptation_audit":audit()}
            state=materials.register_material(path,workspace,metadata,draft,0); item=request(); del item["documents"]["resume"]
            resume=state["materials"][0]
            item["resume_reference"]={"material_id":"approved","confirmation_evidence":"Reviewed unchanged version","sha256":resume["sha256"],"adaptation_audit":audit()}
            self.assertTrue(search.prepare_case(path,workspace,item,1)["completed"])
            saved=cs.read_state(path); self.assertEqual(len([m for m in saved["materials"] if m["kind"]=="resume"]),1)
            wrong=copy.deepcopy(saved); wrong["search_cases"][0]["resume_review"]["adaptation_audit"]["target_role"]="another-role"
            with self.assertRaises(cs.Invalid): search.verify_case(wrong,workspace,"case-a")

    def test_incomplete_private_draft_is_saveable_and_pending_case_cannot_be_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace=Path(directory)/"Private"; cs.initialize_workspace(workspace); path=workspace/"Data/state.json"
            state=captured("Owned the archive panel.",state=configured()); state=achievements.clarify(state,clarification("pending","problem")); path.write_text(json.dumps(state))
            draft=Path(directory)/"work-in-progress.md"; draft.write_text("# Resume\n\nUnresolved working notes.")
            metadata={"id":"private-draft","family_id":"general","version":1,"kind":"resume","language":"English","visibility":"private","at":AT,"fact_ids":["raw-fact"],"source_ids":["source-user"]}
            saved=materials.register_material(path,workspace,metadata,draft,0)
            self.assertEqual(saved["materials"][0]["visibility"],"private")
            item=request(); item["documents"]["resume"]["adaptation_audit"]=audit("",decision="preserve_pending",fact_ids=[],meaning_fields=[])
            result=search.prepare_case(path,workspace,item,1)
            self.assertFalse(result["completed"]); self.assertEqual(result["new_ready"],0)
            assessment=search.verify_case(cs.read_state(path),workspace,"case-a")
            self.assertFalse(assessment["draft_ready"]); self.assertEqual(assessment["status"],"conditional")
            self.assertTrue(assessment["achievement_review"]["pending_achievement_ids"])
            self.assertEqual(cs.read_state(path)["search_cases"][0]["phase"],"preparing")

    def test_metric_exclusion_requires_specific_owner_choice_not_relevance(self):
        state=interpreted(captured("Implemented retry handling for an invoice importer during a 12 month support rotation."))
        wording="Implemented retry handling for an invoice importer."
        metric={"metric_id":"uninterpreted-1","decision":"omit_irrelevant","fact_ids":[],"claim_scope":"unknown",
                "relevance_evidence":"The target values importer design; the rotation duration does not establish its quality or technical scope."}
        selection=audit(wording,metrics=[metric])
        self.assertFalse(reviewed_audit(state,wording,selection)["ready"])
        metric.update(decision="omit_justified",omission_reason="owner_excluded",omission_evidence="Synthetic user excluded this exact rotation-duration detail",omission_source_id="source-user")
        self.assertTrue(reviewed_audit(state,wording,selection)["ready"])
        del metric["omission_evidence"]
        self.assertFalse(reviewed_audit(state,wording,selection)["valid"])

    def test_held_metric_disclosure_and_unsupported_added_number_are_not_ready(self):
        state=interpreted(captured("Team savings of USD 42000."))
        state=achievements.clarify(state,clarification("confidential"))
        wording="Implemented retry handling; team savings of USD 42000."
        hold={"metric_id":"uninterpreted-1","decision":"private_hold","fact_ids":[],"claim_scope":"unknown"}
        # Even separately confirmed numeric evidence cannot override the private hold.
        state=fact(state,"saving-public","The team reported USD 42000 savings.","team")
        result=reviewed_audit(state,wording,audit(wording,metrics=[hold],fact_ids=["fact-a","saving-public"]))
        self.assertFalse(result["valid"]);self.assertFalse(result["ready"])
        state=interpreted(captured());wording="Implemented retry handling, reducing costs by 73%."
        self.assertFalse(reviewed_audit(state,wording,audit(wording))["ready"])
        state=fact(state,"verified-extra",wording)
        self.assertTrue(reviewed_audit(state,wording,audit(wording,fact_ids=["fact-a","verified-extra"]))["ready"])

    def test_pending_metric_meaning_blocks_ready_without_reasking(self):
        original="Reduced parser latency from 950 ms to 210 ms."
        state=fact(captured(original),"latency",original);state=interpreted(state,"latency","latency",True)
        choice={"metric_id":"uninterpreted-1","decision":"include","rendered_text":original,"fact_ids":["latency"],"claim_scope":"individual"}
        record=audit(original,fact_ids=["latency"],metrics=[choice])
        self.assertTrue(reviewed_audit(state,original,record)["ready"])
        state=achievements.clarify(state,clarification("pending"))
        self.assertFalse(reviewed_audit(state,original,record)["ready"])
        self.assertEqual(achievements.clarification_plan(state,["achievement-a"])["groups"],[])
        state=achievements.clarify(state,clarification("answered",evidence="Confirmed the measurement context"))
        self.assertTrue(reviewed_audit(state,original,record)["ready"])
        state["achievement_interpretations"][0]["fields"].pop("metric_context")
        self.assertFalse(reviewed_audit(state,original,record)["ready"])

    def test_default_grouped_capture_rejects_reversed_before_after_values(self):
        original="Reduced parser latency from 950 ms to 210 ms."
        state=fact(captured(original),"latency",original);state=interpreted(state,"latency","latency",True)
        wrong="Reduced parser latency from 210 ms to 950 ms."
        choice={"metric_id":"uninterpreted-1","decision":"include","rendered_text":wrong,"fact_ids":["latency"],"claim_scope":"individual"}
        self.assertFalse(reviewed_audit(state,wrong,audit(wrong,fact_ids=["latency"],metrics=[choice]))["valid"])
        self.assertEqual(state["achievement_evidence"][0]["original_text"],original)

    def test_review_failures_save_real_search_drafts_without_filling_quota(self):
        for mode in ("private_hold","added_number","pending_context"):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                workspace=Path(directory)/"Private";cs.initialize_workspace(workspace);path=workspace/"Data/state.json"
                if mode=="private_hold":
                    state=interpreted(captured("Team savings of USD 42000.",state=configured()));state=achievements.clarify(state,clarification("confidential"))
                    wording="Implemented retry handling; team savings of USD 42000."
                    record=audit(wording,metrics=[{"metric_id":"uninterpreted-1","decision":"private_hold","fact_ids":[],"claim_scope":"unknown"}])
                elif mode=="added_number":
                    state=interpreted(captured(state=configured()));wording="Implemented retry handling, reducing costs by 73%.";record=audit(wording)
                else:
                    wording="Reduced parser latency from 950 ms to 210 ms."
                    state=fact(captured(wording,state=configured()),"latency",wording);state=interpreted(state,"latency","latency")
                    state=achievements.clarify(state,clarification("pending"))
                    record=audit(wording,fact_ids=["latency"],metrics=[{"metric_id":"uninterpreted-1","decision":"include","rendered_text":wording,"fact_ids":["latency"],"claim_scope":"individual"}])
                path.write_text(json.dumps(state));item=request();item["documents"]["resume"].update(text="# Resume\n\n"+wording,adaptation_audit=record,fact_ids=record["entries"][0]["fact_ids"])
                result=search.prepare_case(path,workspace,item,0);saved=cs.read_state(path)
                self.assertFalse(result["completed"]);self.assertEqual(result["new_ready"],0)
                review=search.verify_case(saved,workspace,"case-a");self.assertFalse(review["draft_ready"]);self.assertFalse(review["submission_authorized"])
                resume=next(m for m in saved["materials"] if m["kind"]=="resume")
                self.assertEqual((workspace/resume["path"]).read_text(),item["documents"]["resume"]["text"])
                self.assertEqual(saved["attempts"],[])
                if mode!="pending_context":self.assertEqual(resume["visibility"],"private")

    def test_missing_audit_is_repairable_under_same_case_with_history_and_pins(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace=Path(directory)/"Private";cs.initialize_workspace(workspace);path=workspace/"Data/state.json"
            state=captured("Owned the export panel.",state=configured());path.write_text(json.dumps(state));item=request()
            item["documents"]["resume"]["text"]="# Resume\n\nOwned the export panel."
            result=search.prepare_case(path,workspace,item,0);self.assertFalse(result["completed"])
            first=cs.read_state(path);novelty=copy.deepcopy(first["search_cases"][0]["novelty"]);pins=copy.deepcopy(first["application_attempts"][0]["materials"])
            original_resume=next(m for m in first["materials"] if m["kind"]=="resume");original_bytes=(workspace/original_resume["path"]).read_bytes()
            wording="Implemented export batching for large report workflows."
            def explain(current):
                current=fact(current,"export-fact",wording)
                return cs.add_record(current,"achievement_interpretations",{"id":"meaning-export","achievement_id":"achievement-a","version":1,"at":LATER,
                    "fields":{"contribution":{"status":"supported","text":"Implemented export batching.","fact_ids":["export-fact"]},
                              "problem":{"status":"supported","text":"Large report workflows.","fact_ids":["export-fact"]}}})
            explained=cs.transact(path,lambda current: reviewed(explain(current)),first["revision"])
            item["at"]=LATER;item["revision_reason"]="Clarified the panel's concrete contribution and workflow"
            item["documents"]["resume"].update(text="# Resume\n\n"+wording,fact_ids=["export-fact"],adaptation_audit=reviewed(explained,audit(wording,fact_ids=["export-fact"]),"# Resume\n\n"+wording)[1])
            result=search.prepare_case(path,workspace,item,explained["revision"]);self.assertTrue(result["completed"]);self.assertEqual(result["new_ready"],1)
            saved=cs.read_state(path);self.assertEqual(len(saved["search_cases"]),1);self.assertEqual(len(saved["opportunities"]),1)
            self.assertEqual(saved["search_cases"][0]["novelty"],novelty);self.assertEqual(saved["search_cases"][0]["preparation_revision"],2)
            self.assertEqual(saved["application_attempts"][0]["materials"],pins);self.assertEqual((workspace/original_resume["path"]).read_bytes(),original_bytes)
            self.assertTrue(any(r["operation"]=="revise_case_preparation" for r in saved["change_history"]))
            self.assertEqual(saved["attempts"],[])
            self.assertTrue(search.prepare_case(path,workspace,item,saved["revision"])["completed"])
            self.assertEqual(cs.read_state(path),saved)
            item["documents"]["resume"]["text"]+="\nAnother change."
            with self.assertRaises(cs.Invalid):search.prepare_case(path,workspace,item,saved["revision"])

    def test_preparing_revision_rejects_changed_identity_stale_revision_and_send(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace=Path(directory)/"Private";cs.initialize_workspace(workspace);path=workspace/"Data/state.json"
            path.write_text(json.dumps(captured("Owned the export panel.",state=configured())));item=request();search.prepare_case(path,workspace,item,0)
            saved=cs.read_state(path);changed=copy.deepcopy(item);changed["opportunity"]["title"]="A different role"
            with self.assertRaises(cs.Invalid):search.prepare_case(path,workspace,changed,saved["revision"])
            item["documents"]["resume"]["text"]+="\nWorking clarification."
            with self.assertRaises(cs.Invalid):search.prepare_case(path,workspace,item,0)
            sent=cs.transact(path,lambda current:cs.add_record(current,"attempts",{"id":"reported-send","opportunity_id":"new-role","outcome":"sent","at":AT,"evidence":"Synthetic user report","channel":"manual form"}),saved["revision"])
            with self.assertRaises(cs.Invalid):search.prepare_case(path,workspace,item,sent["revision"])

    def test_legacy_interrupted_reservation_retains_its_novelty_on_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace=Path(directory)/"Private";cs.initialize_workspace(workspace);path=workspace/"Data/state.json"
            path.write_text(json.dumps(captured("Owned the export panel.",state=configured())));item=request();search.prepare_case(path,workspace,item,0)
            legacy=cs.read_state(path);case=legacy["search_cases"][0]
            for key in ("preparation_identity_sha256","preparation_revision","draft_errors"):case.pop(key,None)
            case["attempt_id"]=None;path.write_text(json.dumps(legacy))
            item["documents"]["resume"]["text"]+="\nA preserved clarification draft."
            result=search.prepare_case(path,workspace,item,legacy["revision"])
            self.assertTrue(result["saved"]);self.assertFalse(result["completed"])
            saved=cs.read_state(path);self.assertEqual(saved["search_cases"][0]["novelty"]["status"],"new")
            self.assertEqual(len(saved["opportunities"]),1)

    def test_confirmed_team_impact_stays_secondary_in_individual_contributor_resume(self):
        state=interpreted(captured())
        original="The team reduced incident triage from 48 h to 6 h."
        state=fact(state,"team-triage",original,"team");state=fact(state,"personal-tooling","Built diagnostic summaries used in incident triage.")
        state=achievements.capture(state,{"id":"secondary","fact_id":"team-triage","source_id":"source-user","source_locator":"Synthetic older resume, impact section","original_text":original,
             "metrics":[{"id":"triage","verbatim":"48 h to 6 h","units":["h"],"attribution":"team"}]})
        state=cs.add_record(state,"achievement_interpretations",{"id":"secondary-meaning","achievement_id":"secondary","version":1,"at":AT,
             "fields":{"contribution":{"status":"supported","text":"Built diagnostic summaries.","fact_ids":["personal-tooling"]},
                       "problem":{"status":"supported","text":"Incident triage workflow.","fact_ids":["team-triage"]},
                       "metric_context":{"status":"supported","text":"Confirmed team triage duration, before and after.","fact_ids":["team-triage"]}}})
        primary="Implemented retry handling for an invoice importer.";secondary="Built diagnostic summaries; the team reduced incident triage from 48 h to 6 h."
        record=audit(primary);record["target_role"]="Synthetic individual-contributor role";record["entries"][0]["emphasis"]="primary"
        record["entries"].append({"achievement_id":"secondary","decision":"qualify","emphasis":"secondary","reason":"Retain meaningful team impact concisely; emphasize implementation in the primary achievement.","rendered_text":secondary,
             "fact_ids":["personal-tooling","team-triage"],"meaning_fields":["contribution","problem"],"metrics":[{"metric_id":"triage","decision":"qualify","rendered_text":"the team reduced incident triage from 48 h to 6 h","fact_ids":["team-triage"],"claim_scope":"team","scope_phrase":"the team"}]})
        text="# Resume\n\n"+primary+"\n\n"+secondary
        self.assertTrue(reviewed_audit(state,text,record)["ready"])
        bad=copy.deepcopy(record);bad["entries"][1].update(decision="omit_irrelevant",rendered_text="",relevance_evidence="Not selected by the individual-contributor template")
        bad["entries"][1]["metrics"][0].update(decision="omit_irrelevant",rendered_text="")
        self.assertFalse(reviewed_audit(state,"# Resume\n\n"+primary,bad)["ready"])

    def test_shared_fact_does_not_make_distinct_achievements_duplicates(self):
        state=interpreted(captured());state["facts"][-1]["statement"]="Implemented importer retries and introduced onboarding documentation."
        state=achievements.capture(state,{"id":"different","fact_id":"raw-fact","source_id":"source-user","source_locator":"Synthetic second bullet","original_text":"Introduced onboarding documentation.","metrics":[]})
        selection=audit();selection['entries'].append({"achievement_id":"different","decision":"omit_justified","reason":"Claimed shared-provenance duplicate","fact_ids":[],"meaning_fields":[],"metrics":[],"omission_reason":"duplicate","omission_evidence":"Shared source fact","duplicate_of":"achievement-a"})
        text="Implemented retry handling for an invoice importer."
        self.assertFalse(reviewed_audit(state,text,selection)['ready'])
        # A genuinely equal source version can point at the one retained paragraph.
        state=interpreted(captured());original=state['achievement_evidence'][0]
        state=achievements.capture(state,{"id":"different","fact_id":"raw-fact","source_id":"source-user","source_locator":"Synthetic repeated resume version","original_text":original['original_text'],"metrics":[]})
        self.assertTrue(reviewed_audit(state,text,selection)['ready'])

    def test_fresh_bundle_capture_plan_audit_outside_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); bundle=root/"bundle"
            built=subprocess.run([sys.executable,"-B",str(ROOT/"scripts/build_skill_bundle.py"),str(bundle)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            manifest=json.loads((bundle/"BUNDLE.json").read_text())
            self.assertIn("scripts/career_achievements.py",manifest["files"])
            state=root/"state.json"; state.write_text(json.dumps(interpreted(captured())))
            selection=root/"audit.json"; selection.write_text(json.dumps(audit())); draft=root/"resume.md"; draft.write_text("# Resume\n\nImplemented retry handling for an invoice importer.")
            run=subprocess.run([sys.executable,"-B",str(bundle/"scripts/career_achievements.py"),"audit",str(state),str(selection),"--draft",str(draft)],cwd="/tmp",capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr); self.assertTrue(json.loads(run.stdout)["valid"])
            draft.write_text("# Resume\n\nAn unsupported replacement.")
            run=subprocess.run([sys.executable,"-B",str(bundle/"scripts/career_achievements.py"),"audit",str(state),str(selection),"--draft",str(draft)],cwd="/tmp",capture_output=True,text=True)
            self.assertEqual(run.returncode,3,run.stderr)


if __name__ == "__main__": unittest.main()
