#!/usr/bin/env python3
"""Lossless source achievements, grouped clarification and private adaptation audits."""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import sys

import career_state as cs

FIELDS = ("problem", "scope", "decisions", "contribution", "outcome", "metric_context")


def capture(state, request):
    cs.require(isinstance(request, dict) and isinstance(request.get("original_text"), str), "Original achievement text required")
    record = copy.deepcopy(request)
    record["numeric_anchors"] = cs.numeric_anchors(record["original_text"])
    record.setdefault("metrics", [])
    if not record["metrics"] and len(record["numeric_anchors"]) > 1:
        # Preserve numerical relationships by default; the agent can supply precise grouped spans.
        record["metrics"].append({"id": "uninterpreted-1", "verbatim": record["original_text"], "units": [], "attribution": "unknown"})
    covered = Counter(n for metric in record["metrics"] for n in cs.numeric_anchors(metric["verbatim"]))
    remaining = Counter(record["numeric_anchors"]) - covered
    for number, count in remaining.items():
        for index in range(count):
            record["metrics"].append({"id": "uninterpreted-" + str(len(record["metrics"]) + 1), "verbatim": number,
                                      "units": [], "attribution": "unknown"})
    existing = next((r for r in state.get("achievement_evidence", []) if r["id"] == record["id"]), None)
    if existing:
        cs.require(cs.canonical_json(existing) == cs.canonical_json(record), "Original achievement evidence is immutable; retain another source version")
        return state
    return cs.add_record(state, "achievement_evidence", record)


def latest_interpretation(state, identifier):
    return max((r for r in state.get("achievement_interpretations", []) if r["achievement_id"] == identifier),
               key=lambda r: r["version"], default=None)


def meaningful(fields):
    supported = {key for key, value in fields.items() if value["status"] == "supported"}
    return "contribution" in supported and bool(supported & {"problem", "scope", "decisions", "outcome"})


def clarification_plan(state, selected_ids, limit=2):
    cs.validate(state)
    cs.require(type(limit) is int and 1 <= limit <= 3, "Use a small clarification batch of one to three groups")
    evidence = {r["id"]: r for r in state.get("achievement_evidence", [])}
    cs.require(all(i in evidence for i in selected_ids), "Choose existing priority achievement IDs")
    dispositions = {(r["fact_id"], r["question_key"]): r for r in state["profile"]["metric_dispositions"]}
    groups = {}
    for identifier in selected_ids:
        row = evidence[identifier]
        interpretation = latest_interpretation(state, identifier)
        fields = interpretation["fields"] if interpretation else {}
        needed = [] if meaningful(fields) else [key for key in ("problem", "contribution") if fields.get(key, {}).get("status") != "supported"]
        if row["metrics"] and fields.get("metric_context", {}).get("status") != "supported": needed.insert(0, "metric_context")
        for key in needed:
            question_key = "achievement." + key
            if (row["fact_id"], question_key) in dispositions: continue
            groups.setdefault(key, []).append({"achievement_id": identifier, "fact_id": row["fact_id"], "original_text": row["original_text"]})
    prompts = {
        "problem": {"question": "Which concrete problem or workflow made this work useful?", "choices": ["A user workflow need", "A technical constraint or reliability problem", "Unknown / edit the interpretation"]},
        "contribution": {"question": "Which contribution describes your work?", "choices": ["Implemented the mechanism", "Made design or trade-off decisions", "Contributed within a team; edit the scope"]},
        "metric_context": {"question": "Clarify the priority numbers together: meaning/units, baseline/result, period/evidence, team result versus personal contribution and disclosure.", "choices": ["Confirmed with the scope described", "Unknown / no metric interpretation", "Confidential / prefer not to disclose"]}}
    return {"groups": [{"question_key": "achievement." + key, "items": items, **prompts[key], "suggestions_are_hypotheses": True}
                       for key, items in list(groups.items())[:limit]], "remaining_groups": max(0, len(groups) - limit)}


def clarify(state, request):
    cs.validate_shape(request, cs.state_schema()["$defs"]["achievement_clarification"], cs.state_schema(), "clarification")
    candidate = copy.deepcopy(state)
    key = (request["fact_id"], request["question_key"])
    rows = candidate["profile"]["metric_dispositions"]
    old = next((r for r in rows if (r["fact_id"], r["question_key"]) == key), None)
    if old == request: return state
    cs.require(not old or old["disposition"] == "pending" or request.get("reopen_reason"), "Reuse the recorded answer; reopen only for new evidence or a requested revision")
    if old: rows.remove(old)
    rows.append(copy.deepcopy(request))
    candidate["change_history"].append({"operation": "achievement_clarification", "at": request["at"], "reason": request["evidence"],
                                       "revision_from": state["revision"], "request": copy.deepcopy(request), "before": old, "after": copy.deepcopy(request)})
    return cs.validate(candidate)


def omission_allowed(state, selection, original, entries, evidence):
    reason = selection.get("omission_reason")
    if not selection.get("omission_evidence"): return False
    if reason == "duplicate":
        other = selection.get("duplicate_of")
        if not (other in evidence and other != original["id"] and entries[other]["decision"] in {"include", "qualify"}): return False
        # Shared provenance can cover different work; only equal source wording proves a duplicate here.
        if " ".join(evidence[other]["original_text"].split()) != " ".join(original["original_text"].split()): return False
        retained = entries[other].get("rendered_text", "")
        return not (Counter(numeric for numeric in cs.numeric_anchors(original["original_text"])) - Counter(cs.numeric_anchors(retained))) and all(unit.casefold() in retained.casefold() for metric in original["metrics"] for unit in metric["units"])
    if reason == "confidential":
        fact = next(f for f in state["facts"] if f["id"] == original["fact_id"])
        return fact["disclosure"] == "private" or any(r["fact_id"] == original["fact_id"] and r["disposition"] in {"confidential", "prefer_not_to_disclose"} for r in state["profile"]["metric_dispositions"])
    if reason in {"owner_excluded", "superseded"}:
        return any(source["id"] == selection.get("omission_source_id") and source["kind"] == "user_statement" for source in state["sources"])
    return False


def audit_resume(state, text, audit):
    """Check actual rendered text and explicit coverage; prose truth still needs evidence review."""
    cs.validate(state)
    cs.validate_shape(audit, cs.state_schema()["$defs"]["adaptation_audit"], cs.state_schema(), "adaptation audit")
    evidence = {r["id"]: r for r in state.get("achievement_evidence", [])}
    entries = {r["achievement_id"]: r for r in audit["entries"]}
    cs.require(len(entries) == len(audit["entries"]) and set(entries) == set(evidence), "Account for every source achievement; omissions cannot be silent")
    facts = {r["id"]: r for r in state["facts"]}
    for entry in audit["entries"]:
        cs._refs(entry, "fact_ids", facts)
        for metric in entry["metrics"]: cs._refs(metric, "fact_ids", facts)
    errors, pending, omitted = [], [], []
    for identifier, original in evidence.items():
        entry = entries[identifier]
        decision = entry["decision"]
        if decision == "omit_irrelevant":
            errors.append(identifier + ": relevance controls emphasis, not deletion; retain this strength concisely as secondary")
        if decision == "omit_justified":
            if not omission_allowed(state, entry, original, entries, evidence): errors.append(identifier + ": omission needs a specific duplicate/correction/privacy/owner decision and provenance")
            omitted.append(identifier)
            if entry.get("rendered_text"): errors.append(identifier + ": an omitted achievement must not declare rendered wording")
        rendered = entry.get("rendered_text", "")
        if decision in {"include", "qualify"} or rendered:
            if not entry["fact_ids"]: errors.append(identifier + ": external wording needs supporting facts")
            if not rendered or rendered not in text: errors.append(identifier + ": audited wording is absent from final draft")
            if cs.claim_issues({"fact_ids": entry["fact_ids"]}, facts): errors.append(identifier + ": wording requires confirmed disclosure-allowed facts")
        if rendered:
            known_numbers = {n for i in entry["fact_ids"] for n in cs.numeric_anchors(facts[i]["statement"])}
            if set(cs.numeric_anchors(rendered)) - known_numbers:
                errors.append(identifier + ": added numerical claims need separately confirmed supporting facts")
        interpretation = latest_interpretation(state, identifier)
        fields = interpretation["fields"] if interpretation else {}
        if decision in {"include", "qualify"}:
            if not meaningful(fields): errors.append(identifier + ": feature label plus ownership is not an interpreted achievement")
            for name in entry["meaning_fields"]:
                field = fields.get(name, {})
                if field.get("status") != "supported" or not set(field.get("fact_ids", [])) <= set(entry["fact_ids"]):
                    errors.append(identifier + ": unsupported meaning field " + name)
            if "contribution" not in entry["meaning_fields"] or not set(entry["meaning_fields"]) & {"problem", "scope", "decisions", "outcome"}:
                errors.append(identifier + ": record the contribution and why the work matters")
        if decision == "preserve_pending":
            pending.append(identifier)
            dispositions = [r for r in state["profile"]["metric_dispositions"] if r["fact_id"] == original["fact_id"] and r["question_key"].startswith("achievement.")]
            if not dispositions: errors.append(identifier + ": record the grouped clarification or its disposition before deferring")
        metric_entries = {m["metric_id"]: m for m in entry["metrics"]}
        if set(metric_entries) != {m["id"] for m in original["metrics"]} or len(metric_entries) != len(entry["metrics"]):
            errors.append(identifier + ": every source metric needs an explicit decision")
        for metric in original["metrics"]:
            selected = metric_entries.get(metric["id"])
            if not selected: continue
            action = selected["decision"]
            if action == "omit_irrelevant": errors.append(identifier + ": preserve secondary supported metrics; relevance is not an omission permission")
            if action == "omit_justified" and not ((decision == "omit_justified" and omission_allowed(state, entry, original, entries, evidence)) or omission_allowed(state, selected, original, entries, evidence)):
                errors.append(identifier + ": metric omission needs a specific supported exclusion, not template selection")
            if action in {"private_hold", "omit_irrelevant", "omit_justified"}:
                source_numbers = set(cs.numeric_anchors(metric["verbatim"]))
                visible = bool(source_numbers & set(cs.numeric_anchors(rendered))) if source_numbers else metric["verbatim"].casefold() in rendered.casefold()
                if visible: errors.append(identifier + ": possible disclosure or contradictory inclusion of a held/omitted metric; review actual wording")
            if action in {"preserve_pending", "private_hold"}:
                if action == "preserve_pending": pending.append(identifier)
                if action == "private_hold" and not any(r["fact_id"] == original["fact_id"] and r["disposition"] in {"confidential", "prefer_not_to_disclose"} for r in state["profile"]["metric_dispositions"]):
                    errors.append(identifier + ": private metric hold needs a recorded disclosure disposition")
                if action == "preserve_pending" and decision != "preserve_pending": errors.append(identifier + ": pending metric must stay visibly pending in the selection audit")
                continue
            if action not in {"include", "qualify"}: continue
            context = fields.get("metric_context", {})
            awaiting = any(r["fact_id"] == original["fact_id"] and r["question_key"] == "achievement.metric_context" and r["disposition"] == "pending" for r in state["profile"]["metric_dispositions"])
            if awaiting or context.get("status") != "supported" or not set(context.get("fact_ids", [])) <= set(entry["fact_ids"]):
                pending.append(identifier)
            span = selected.get("rendered_text", "")
            if not span or span not in rendered or span not in text: errors.append(identifier + ": metric wording is absent from final draft")
            if cs.numeric_anchors(metric["verbatim"]) != cs.numeric_anchors(span):
                errors.append(identifier + ": original numerical values disappeared or changed without evidence")
            if any(unit.casefold() not in span.casefold() for unit in metric["units"]): errors.append(identifier + ": metric units disappeared")
            support = selected["fact_ids"]
            if not set(support) <= set(entry["fact_ids"]) or cs.claim_issues({"fact_ids": support}, facts): errors.append(identifier + ": unsupported metric claim")
            if not support: errors.append(identifier + ": metric needs supporting facts")
            supported_numbers = Counter(n for i in support for n in cs.numeric_anchors(facts[i]["statement"]))
            if Counter(cs.numeric_anchors(metric["verbatim"])) - supported_numbers:
                errors.append(identifier + ": numerical claim is absent from its confirmed supporting facts")
            scope = selected["claim_scope"]
            if scope == "unknown": errors.append(identifier + ": resolve or qualify metric attribution before external use")
            if metric["attribution"] == "team" and scope not in {"team", "mixed"}: errors.append(identifier + ": team outcome cannot become personal impact")
            if scope in {"team", "mixed", "system"} and (not selected.get("scope_phrase") or selected["scope_phrase"] not in span):
                errors.append(identifier + ": qualify the outcome's actual scope in the wording")
            if scope == "individual" and not any(facts[i]["ownership"] == "individual" and not (Counter(cs.numeric_anchors(metric["verbatim"])) - Counter(cs.numeric_anchors(facts[i]["statement"]))) for i in support):
                errors.append(identifier + ": personal attribution of the number is unconfirmed")
    return {"valid": not errors, "ready": not errors and not pending, "errors": errors, "pending_achievement_ids": sorted(set(pending)), "omitted_irrelevant_ids": [], "omitted_justified_ids": omitted,
            "source_achievement_count": len(evidence), "semantic_review_required": True}


def require_resume_audit(state, text, metadata):
    if metadata.get("kind") != "resume" or metadata.get("visibility") != "external" or not state.get("achievement_evidence"): return None
    cs.require(metadata.get("adaptation_audit") is not None, "New adapted resume needs a lossless source-selection audit")
    result = audit_resume(state, text, metadata["adaptation_audit"])
    cs.require(result["valid"], "; ".join(result["errors"]))
    claimed = {i for entry in metadata["adaptation_audit"]["entries"] for i in entry["fact_ids"]}
    cs.require(claimed <= set(metadata["fact_ids"]), "Material claim IDs must cover its adaptation evidence")
    return result


def review_reference(state, workspace, material, review):
    import career_materials as cm
    path = cm.material_file(workspace, material)
    if not state.get("achievement_evidence"): return None
    cs.require(review and review.get("sha256") == material["sha256"], "Resume review must bind the exact immutable material hash")
    if path.suffix.lower() in {".md", ".txt"}:
        text = path.read_text(encoding="utf-8")
        cs.require(not review.get("extracted_text") or review["extracted_text"] == text, "Resume extraction differs from actual text")
    else:
        cs.require(review.get("extracted_text"), "Host-readable extracted resume text required; helper does not parse binary resumes")
        text = review["extracted_text"]
    return require_resume_audit(state, text, {**material, "adaptation_audit": review.get("adaptation_audit")})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("capture", "interpret", "clarify", "plan", "audit"))
    parser.add_argument("state"); parser.add_argument("input")
    parser.add_argument("--expected-revision", type=int); parser.add_argument("--draft")
    args = parser.parse_args()
    try:
        request = cs.load_json(args.input)
        if args.command in {"capture", "interpret", "clarify"}:
            cs.require(args.expected_revision is not None, "Expected revision required")
            operation = {"capture": capture, "interpret": lambda s, r: cs.add_record(s, "achievement_interpretations", r), "clarify": clarify}[args.command]
            state = cs.transact(args.state, lambda s: operation(s, request), args.expected_revision)
            result = {"valid": True, "revision": state["revision"]}
        elif args.command == "plan": result = clarification_plan(cs.read_state(args.state), request["achievement_ids"], request.get("limit", 2))
        else:
            cs.require(args.draft, "Actual draft path required")
            result = audit_resume(cs.read_state(args.state), Path(args.draft).read_text(), request)
        print(json.dumps(result, indent=2)); return 0 if result.get("valid", True) else 3
    except (cs.Invalid, OSError, ValueError, KeyError, TypeError) as error:
        print("Error: " + str(error), file=sys.stderr); return 2


if __name__ == "__main__":
    sys.exit(cs.run_cli(main))
