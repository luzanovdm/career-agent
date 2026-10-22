"""Explicit synthetic extraction and semantic reviews for existing focused fixtures."""
import copy
from test_state import AT
import career_state as cs
import career_achievements as ca


def setup_decisions():
    return {key: {"disposition": "confirmed", "value": value, "at": AT, "evidence": "Synthetic user preference already supplied"}
            for key, value in {"target": "API engineering", "compensation": "Recorded USD gross annual floor and goal",
                               "schedule": "Full-time employee, 40 hours/week", "other_constraints": "Recorded location and legal preferences"}.items()}


def reviewed(state, audit=None, text=None):
    state = copy.deepcopy(state)
    source_ids = {i for f in state["facts"] for i in f["source_ids"]}
    source_ids.update(s["id"] for s in state["sources"] if s.get("purpose") == "career_evidence")
    items = []
    for fact in state["facts"]:
        links = [a["id"] for a in state.get("achievement_evidence", []) if a["fact_id"] == fact["id"]]
        items.append({"fact_id": fact["id"], "kind": "achievement" if links else "background", "achievement_ids": links,
                      "reason": "Original achievement captured" if links else "Supporting context or confirmation for captured work"})
    state = ca.review_sources(state, {"status": "reviewed", "at": AT, "source_ids": sorted(source_ids), "items": items,
                                    "evidence": "Synthetic source text reviewed for achievements, measurements, ownership and background"})
    if audit is None: return state
    audit = copy.deepcopy(audit)
    if text is None: text = "\n\n".join(e.get("rendered_text", "") for e in audit["entries"] if e.get("rendered_text"))
    audit["semantic_review"] = {"status": "reviewed", "at": AT, "evidence_review_sha256": ca.evidence_coverage(state)["review_sha256"],
       "interpretation_ids": sorted({ca.latest_interpretation(state, e["achievement_id"])["id"] for e in audit["entries"]
            if e["decision"] in {"include", "qualify"} and ca.latest_interpretation(state, e["achievement_id"])}),
       "evidence": "Synthetic human-readable wording reviewed against source meaning, personal/team attribution and secondary strengths",
       "unresolved_fields": [], **ca.semantic_bindings(text, audit)}
    return state, audit


def baseline_capture(state):
    state = ca.capture(state, {"id": "baseline-achievement", "fact_id": "fact-a", "source_id": "source-user",
        "source_locator": "Synthetic resume experience bullet", "original_text": state["facts"][0]["statement"], "metrics": []})
    state = cs.add_record(state, "achievement_interpretations", {"id": "baseline-meaning", "achievement_id": "baseline-achievement", "version": 1, "at": AT,
       "fields": {"contribution": {"status": "supported", "text": "Implemented retry handling", "fact_ids": ["fact-a"]},
                  "problem": {"status": "supported", "text": "Importer reliability", "fact_ids": ["fact-a"]}}})
    return reviewed(state)


def baseline_audit(state, draft=None):
    text = state["facts"][0]["statement"]
    return reviewed(state, {"target_role": "new-role", "at": AT, "entries": [{"achievement_id": "baseline-achievement", "decision": "include",
       "reason": "Supported importer reliability", "rendered_text": text, "fact_ids": ["fact-a"], "meaning_fields": ["contribution", "problem"], "metrics": []}]}, text if draft is None else draft)[1]
