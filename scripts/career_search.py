#!/usr/bin/env python3
"""Agent-operated new-case gates and saved Markdown packets; no research or sending."""
import argparse
import copy
import csv
from fractions import Fraction
import io
import ipaddress
import json
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit

import career_state as cs
import career_materials as cm
import career_snapshot as snapshot

SLOTS = {"resume", "cover-letter", "dossier", "form-answers"}


def registry_inventory(workspace, extra=()):
    """Read only recognized review/index tables plus explicitly selected local tables."""
    root = cs.private_path(workspace).resolve()
    paths = set(extra)
    data = cm.inside(root, "Data")
    if data.exists():
        for path in data.iterdir():
            if path.suffix.lower() in {".json", ".csv", ".xlsx"} and any(word in path.stem.lower() for word in ("review", "registry", "index", "history")) and path.name != "report-index.json":
                paths.add(path.relative_to(root).as_posix())
    result, errors = [], []
    for relative in sorted(paths):
        try:
            path = cm.inside(root, relative)
            cs.require(path.is_file() and not path.is_symlink() and path.suffix.lower() in {".json", ".csv"}, "Registry must be a local JSON/CSV file")
            raw = path.read_bytes()
            if path.suffix.lower() == ".json":
                content = cs.strict_json_loads(raw)
                cs.require(isinstance(content, (dict, list)), "Registry must contain structured records")
                cs.require(not isinstance(content, dict) or not content.get("error"), "Registry contains failed-source evidence")
            else:
                records = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
                cs.require(bool(records) and all(records[0]) and len(records[0]) == len(set(records[0])), "CSV registry needs distinct nonempty headers")
                cs.require(all(len(row) == len(records[0]) for row in records[1:] if row), "CSV registry row width differs from header")
                content = [dict(zip(records[0], row)) for row in records[1:] if row]
            result.append({"path": relative, "sha256": cm.sha256(raw), "data": content})
        except (OSError, ValueError, TypeError, RecursionError) as error:
            errors.append({"path": relative, "error": str(error)})
    return result, errors


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, member in value.items():
            yield key
            yield from strings(member)
    elif isinstance(value, list):
        for member in value:
            yield from strings(member)


def exact_match(role, value):
    url = cs.canonical_url(role["role_url"])
    keys = {role["id"], role["identity"], *role.get("identity_aliases", [])}
    for text in strings(value):
        for observed in re.findall(r'https?://[^\s<>"\]\)]+', text):
            try:
                if cs.canonical_url(observed.rstrip(".,;")) == url:
                    return True
            except cs.Invalid:
                pass
        for key in keys:
            # Unscoped bare numeric IDs are not globally unique identities.
            if not key.isdigit() and re.search(r"(?<![\w-])" + re.escape(key) + r"(?![\w-])", text):
                return True
    return False


def novelty(state, workspace, role, extra=(), ignore_case=None):
    registries, errors = registry_inventory(workspace, extra)
    matches, contacts = [], []
    for old in state["opportunities"]:
        if ignore_case and old["id"] == ignore_case["opportunity_id"]:
            continue
        if exact_match(role, old):
            matches.append({"path": "Data/state.json", "id": old["id"]})
    for row in state["history_imports"]:
        if exact_match(role, row):
            matches.append({"path": "Data/state.json", "id": row["id"]})
    def rows(value):
        if isinstance(value, dict):
            yield value
            for member in value.values(): yield from rows(member)
        elif isinstance(value, list):
            for member in value: yield from rows(member)
    for registry in registries:
        for row in rows(registry["data"]):
            company = row.get("employer", row.get("company_name", row.get("company", row.get("company_id"))))
            status = row.get("submission_status", row.get("outcome", row.get("status")))
            named_role = any(row.get(k) not in (None, "", "unknown") for k in ("role", "role_url", "job_id", "role_id", "job_url", "requisition_id"))
            if isinstance(company, str) and company.casefold() in {role["company_id"].casefold(), role.get("company_name", "").casefold()} and status in {"sent", "uncertain", "bounced"} and not named_role:
                contacts.append({"path": registry["path"], "sha256": registry["sha256"], "status": status})
        if exact_match(role, registry["data"]):
            matches.append({"path": registry["path"], "sha256": registry["sha256"]})
    return {"status": "known" if matches else "unknown" if errors else "new", "matches": matches,
            "coverage": [{"path": r["path"], "sha256": r["sha256"]} for r in registries], "errors": errors, "uncertain_company_contacts": contacts}


def income_assessment(config, pay, role=None):
    policy = config.get("income_policy")
    policy_status = "recorded" if policy else "absent"
    if policy:
        cs.validate_shape(policy, cs.state_schema()["$defs"]["income_policy"], cs.state_schema(), "income policy")
        cs.timestamp(policy["confirmed_at"])
        for name, disposition in (("salary_floor", "floor_disposition"), ("salary_goal", "goal_disposition")):
            if disposition in policy and (config.get(name) is not None) != (policy[disposition] == "stated"):
                return {"status": "intake_missing", "reason": "Recorded salary disposition conflicts with amount", "policy_status": policy_status}
    if config.get("salary_floor") is None and not (policy and policy.get("floor_disposition") == "no_floor"):
        return {"status": "intake_missing", "reason": "Confirm the floor or an explicit no-floor choice", "policy_status": policy_status}
    policy = policy or {}
    floor, goal = config.get("salary_floor"), config.get("salary_goal")
    def matching_units(item, required):
        calendar_pair = {item.get("period"), required["period"]} <= {"month", "year"}
        return (item.get("currency"), item.get("basis")) == (required["currency"], required["basis"]) and (item.get("period") == required["period"] or calendar_pair)
    def comparison_amount(amount, period):
        # Exact calendar normalization; source observations are never rewritten.
        return Fraction(str(amount)) * (12 if period == "month" else 1)
    floor_amount = comparison_amount(floor["amount"], floor["period"]) if floor else None
    def comparable(item):
        # Fixed calendar amounts and same-period hourly rates need no invented schedule.
        # Explicit work-hours requirements are evaluated as job constraints below.
        if policy.get("employment_type") and item.get("employment_type") and item["employment_type"] != policy["employment_type"]: return False
        if item.get("basis") not in {"gross", "net"} or not item.get("source_id") or not item.get("checked_at"): return False
        for required in (floor,):
            if required and not matching_units(item, required): return False
        cs.timestamp(item["checked_at"])
        return True
    def bounds(item):
        low, high = item.get("minimum"), item.get("maximum")
        cs.require(type(low) in {int, float} and type(high) in {int, float} and 0 <= low <= high, "Invalid observed pay interval")
        cs.require(item["kind"] != "exact" or low == high, "Exact pay requires equal bounds")
        return comparison_amount(low, item.get("period")), comparison_amount(high, item.get("period"))
    if pay and pay.get("kind") in {"exact", "range"} and pay.get("evidence_type") == "employer_confirmed" and comparable(pay):
        low, high = bounds(pay)
        if floor and high < floor_amount: return {"status": "fail", "reason": "Confirmed employer cap is below the hard floor", "source_ids": [pay["source_id"]], "comparison_basis": "fixed_calendar_12_month_year" if pay.get("period") in {"month", "year"} else "same_period_hourly_rate"}
        if not floor or low >= floor_amount:
            return {"status": "pass", "reason": "Comparable employer-confirmed pay meets the floor or explicit no-floor choice",
                    "source_ids": [pay["source_id"]], "goal": "not_requested" if not goal else "units_unmatched" if not matching_units(pay, goal) else "meets" if low >= comparison_amount(goal["amount"], goal["period"]) else "below_or_crosses_goal",
                    "policy_status": policy_status, "comparison_basis": "fixed_calendar_12_month_year" if pay.get("period") in {"month", "year"} else "same_period_hourly_rate"}
    for estimate in pay.get("estimates", []) if pay else []:
        if not role or estimate.get("evidence_type") not in {"company_comparable", "market_estimate"} or estimate.get("confidence") not in {"medium", "high"}: continue
        if estimate.get("geography") != role.get("hiring_geography") or estimate.get("level") != role.get("level") or not estimate.get("comparable_role"): continue
        if estimate.get("kind") not in {"exact", "range"} or not comparable(estimate): continue
        low, high = bounds(estimate)
        if not floor or high >= floor_amount:
            return {"status": "estimated_compatible", "reason": "Comparable company/market evidence supports reaching the floor; not an employer promise",
                    "source_ids": [estimate["source_id"]], "geography": estimate["geography"], "confidence": estimate["confidence"], "policy_status": policy_status}
    return {"status": "unknown", "reason": "Pay not established: unpublished/lower-bound/crossing range or mismatched units; retain uncertainty without inventing a cap", "policy_status": policy_status}


def public_destination(value):
    if not isinstance(value, str): return False
    try:
        cs.canonical_url(value)
        host = urlsplit(value).hostname
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")): return False
        try:
            if not ipaddress.ip_address(host).is_global: return False
        except ValueError:
            pass
        return not any(ord(c) < 32 or c.isspace() for c in value)
    except cs.Invalid:
        return False


OPERATIONS_ONLY = {"submission.no_sends", "submission.authorization", "outreach.no_sends", "sending.authorization"}
SCOPE_KEYS = {"search.case_types", "search.opportunity_types"}
DIMENSION_KEYS = {
    "geography": {"work.residence", "work.geography", "geography", "geography.eligibility", "location.eligibility", "work.location", "geographic_eligibility"},
    "legal_eligibility": {"work.authorization", "work.rights", "legal.work_authorization", "contract.legal_eligibility"},
    "language": {"work.language", "role.requirement.language", "language.essential"},
    "management_language": {"management.team_language", "management.language", "leadership.team_language"},
    "contract_arrangement": {"contract.arrangement", "contract.model", "contract.ie_eor", "work.contract_model", "payment.arrangement", "contractor.arrangement"},
}


def condition_dimension(row):
    if row.get("dimension"): return row["dimension"]
    return next((name for name, keys in DIMENSION_KEYS.items() if row["meaning"] in keys), None)


def role_track(role):
    tracks = {role[k] for k in ("role_track", "role_scope", "management_scope")
              if role.get(k) in {"management", "individual_contributor"}}
    for key in ("management_role", "is_management", "people_management"):
        if type(role.get(key)) is bool: tracks.add("management" if role[key] else "individual_contributor")
    return next(iter(tracks)) if len(tracks) == 1 else "unknown"


def constraint_match(constraint, conditions):
    exact = next((c for c in conditions if c["meaning"] == constraint["meaning"] or constraint["meaning"] in c.get("covers", [])), None)
    if exact: return exact
    dimension = condition_dimension(constraint)
    matching = [c for c in conditions if dimension and condition_dimension(c) == dimension]
    # Conflicting evidence must not be hidden behind a convenient pass alias.
    return next((c for c in matching if c["outcome"] == "fail"), matching[0] if matching else None)


def case_scope(state, kind):
    config = state["search_config"]
    allowed = (config.get("income_policy") or {}).get("case_types")
    if allowed is None: allowed = config.get("case_types")
    if allowed is None:
        allowed = next((c["value"] for c in config["constraints"] if c["meaning"] in SCOPE_KEYS and c["status"] == "known"), None)
    if isinstance(allowed, list) and allowed and all(k in {"vacancy", "contract_project", "company_outreach"} for k in allowed):
        return {"status": "allowed" if kind in allowed else "excluded", "source": "recorded_case_types"}
    return {"status": "not_normalized", "source": "existing_research_scope", "evidence": state["control"]["scope"]}


def verified_failure(state, assessment):
    if assessment.get("verification") == "unverified": return False
    sources = {r["id"]: r for r in state["sources"]}
    return any(any(o["primary"] for o in sources[i]["observations"]) or
               sources[i]["kind"] == "user_statement" and assessment.get("verification") == "user_confirmed"
               for i in assessment["source_ids"])


def readiness(state, case):
    role = next(r for r in state["opportunities"] if r["id"] == case["opportunity_id"])
    reasons, unknowns, clarifications, pending_consents = [], [], [], []
    if case["novelty"]["status"] != "new": reasons.append("Not a verified new case")
    company = next(c for c in state["companies"] if c["id"] == role["company_id"])
    excluded = state["search_config"].get("excluded_companies", [])
    for constraint in state["search_config"]["constraints"]:
        if constraint["meaning"] == "company.exclusions" and isinstance(constraint["value"], list): excluded = [*excluded, *constraint["value"]]
    identities = {company["id"].casefold(), company["identity"].casefold(), company["name"].casefold(), urlsplit(role["role_url"]).hostname}
    if identities & {name.casefold() for name in excluded}: reasons.append("Company is explicitly excluded")
    income = income_assessment(state["search_config"], case["compensation"], role)
    if income["status"] == "fail": reasons.append(income["reason"])
    if income["status"] == "intake_missing": unknowns.append(income["reason"])
    if income.get("policy_status") == "absent": clarifications.append("Income policy metadata absent; existing salary records used without fabricating confirmation")
    observed = max(role["status_observations"], key=lambda r: cs.timestamp(r["at"]))
    if role["kind"] != "company_outreach" and observed["status"] != "open": unknowns.append("Current opening not verified")
    policy = state["search_config"].get("income_policy") or {}
    scope = case_scope(state, role["kind"])
    if scope["status"] == "excluded": reasons.append("Case type is outside the explicitly recorded search scope")
    elif scope["status"] == "not_normalized": clarifications.append("Case types not normalized; reuse existing authorized scope without inventing a restriction or confirmation")
    if case["novelty"].get("uncertain_company_contacts"): reasons.append("Unscoped prior company contact needs reconciliation")
    handled = set()
    def evaluate(meaning, constraint, assessment):
        if meaning in OPERATIONS_ONLY or meaning in SCOPE_KEYS or meaning == "company.exclusions": return
        dimension = condition_dimension(constraint)
        if constraint.get("applies_to") == "management" or dimension == "management_language":
            track = role_track(role)
            if track == "individual_contributor": return
            if track == "unknown":
                unknowns.append("Management criterion applicability not established: " + meaning); return
        if constraint.get("applies_to") == "individual_contributor":
            track = role_track(role)
            if track == "management": return
            if track == "unknown":
                unknowns.append("Individual-contributor criterion applicability not established: " + meaning); return
        if meaning == "work.residence" and not assessment:
            clarifications.append("Residence is user context; geographic eligibility remains to be checked"); return
        if constraint.get("status", "known") != "known" or not assessment:
            unknowns.append("Constraint unresolved: " + meaning); return
        outcome = assessment["outcome"]
        if assessment.get("verification") == "unverified":
            unknowns.append("Unverified requirement; not an established hard failure: " + meaning); return
        if assessment["evidence_kind"] in {"posting_language", "inference"} or assessment.get("verification") == "unverified": outcome = "unknown"
        if outcome == "fail":
            if verified_failure(state, assessment): reasons.append("Hard constraint failed: " + meaning)
            else: unknowns.append("Unverified requirement; not an established hard failure: " + meaning)
        elif outcome == "unknown": unknowns.append("Hard constraint unknown: " + meaning)
    for constraint in state["search_config"]["constraints"]:
        if constraint["priority"] != "hard": continue
        assessment = constraint_match(constraint, case["conditions"])
        if assessment: handled.add(assessment["meaning"])
        evaluate(constraint["meaning"], constraint, assessment)
    for condition in case["conditions"]:
        if condition.get("priority") in {"preference", "negotiable"} and condition_dimension(condition) == "contract_arrangement" and condition["outcome"] == "unknown":
            clarifications.append("Contract arrangement remains a recorded negotiation clarification: " + condition["meaning"])
        if condition.get("priority") != "hard" or condition["meaning"] in handled: continue
        evaluate(condition["meaning"], condition, condition)
    guard = cs.reapplication_guard(state, role["id"])
    if guard["requires_review"]: reasons.append("Prior submission/identity needs reconciliation")
    company = next(r for r in state["companies"] if r["id"] == role["company_id"])
    if any(r["opportunity_id"] is None and not r["role"] and r["employer"].casefold() == company["name"].casefold() and r["status"] in {"sent", "uncertain", "bounced"} for r in state["history_imports"]):
        reasons.append("Unscoped prior company submission needs reconciliation")
    form = next(r for r in state["forms"] if r["id"] == case["form_id"])
    if form["status"] != "observed": unknowns.append("Application form not observed")
    for field in form["fields"]:
        if field.get("control") == "url" and field.get("answer") and not public_destination(field["answer"]):
            unknowns.append("Destination is not a public HTTP(S) URL: " + field["id"])
        if field.get("is_consent"):
            pending_consents.append(field["id"])
            continue
        if not field.get("required"): continue
        complete = field.get("answer_state") == "confirmed" and bool(field.get("confirmation_evidence")) and field.get("answer") is not None and field.get("answer") != ""
        if field.get("answer_id"):
            matches = cs.lookup_answer(state, field["answer_query"], case["at"]) if field.get("answer_query") else []
            complete = any(r["id"] == field["answer_id"] and cs.canonical_json(r["value"]) == cs.canonical_json(field.get("answer")) for r in matches)
        if not complete:
            unknowns.append("Required factual answer unresolved: " + field["id"])
    if income["status"] in {"unknown", "estimated_compatible"} and policy.get("unknown_salary", "include") == "exclude": reasons.append("User explicitly excluded unconfirmed pay")
    return {"status": "blocked" if reasons else "conditional" if unknowns else "ready_with_pay_uncertainty" if income["status"] in {"unknown", "estimated_compatible"} else "ready", "blockers": reasons,
            "unknowns": unknowns, "clarifications": clarifications, "pending_consents": pending_consents,
            "draft_ready": not reasons and not unknowns, "submission_authorized": False, "scope": scope, "income": income}


def preparation_identity(request):
    """Document/audit refinements cannot change opportunity, scope or selection evidence."""
    return cm.sha256(cs.canonical_json({k: v for k, v in request.items() if k not in {"documents", "resume_reference", "at", "revision_reason"}}).encode())


def prepare_case(state_path, workspace, request, expected_revision, requested=1):
    """Save a case reservation first; partial failures remain visible and never fill quota."""
    workspace = cs.private_path(workspace).resolve()
    cs.require(workspace in Path(state_path).resolve().parents, "State must belong to the selected workspace")
    cs.validate_shape(request, cs.state_schema()["$defs"]["search_case_request"], cs.state_schema(), "case request")
    fingerprint = cm.sha256(cs.canonical_json(request).encode())
    def reserve(state):
        existing = next((r for r in state.get("search_cases", []) if r["id"] == request["id"]), None)
        if existing:
            if existing["request_sha256"] == fingerprint: return state
            cs.require(existing["phase"] == "preparing", "Completed case request is immutable; preserve its packet")
            cs.require(not any(a["opportunity_id"] == existing["opportunity_id"] and a["outcome"] in {"sent", "uncertain"} for a in state["attempts"]), "Submission history prevents revising this preparation")
            identity = preparation_identity(request)
            if existing.get("preparation_identity_sha256"):
                cs.require(existing["preparation_identity_sha256"] == identity, "Preparation revision can change documents/audit only; preserve identity and scope")
            else:
                # Recover older interrupted v1 reservations without treating their own role as new.
                role = next(r for r in state["opportunities"] if r["id"] == existing["opportunity_id"])
                original_role = {k: v for k, v in role.items() if k not in {"fit_summary", "pay_summary", "next_action"}}
                form = next(r for r in state["forms"] if r["id"] == existing["form_id"])
                cs.require(cs.canonical_json(request["opportunity"]) == cs.canonical_json(original_role) and
                           cs.canonical_json(request["form"]) == cs.canonical_json(form) and
                           request["company"]["id"] == role["company_id"] and request["batch_id"] == existing["batch_id"] and
                           request["compensation"] == existing["compensation"] and request["conditions"] == existing["conditions"] and
                           request.get("registry_paths", []) == existing["registry_paths"], "Legacy preparation revision must retain its exact role, form, evidence and scope")
            candidate = copy.deepcopy(state)
            record = next(r for r in candidate["search_cases"] if r["id"] == request["id"])
            before = copy.deepcopy(record)
            record.update(request_sha256=fingerprint, preparation_identity_sha256=identity,
                          preparation_revision=record.get("preparation_revision", 1) + 1, at=request["at"],
                          reference_resume_id=request.get("resume_reference", {}).get("material_id"))
            if request.get("resume_reference"): record["resume_review"] = copy.deepcopy(request["resume_reference"])
            else: record.pop("resume_review", None)
            candidate["change_history"].append({"operation": "revise_case_preparation", "at": cs.utcnow(),
                "reason": request.get("revision_reason", "Revised unsent preparation documents/audit"), "revision_from": state["revision"],
                "request": {"case_id": record["id"], "request_sha256": fingerprint}, "before": before, "after": copy.deepcopy(record)})
            return cs.validate(candidate)
        candidate = copy.deepcopy(state)
        seen = novelty(state, workspace, {**request["opportunity"], "company_name": request["company"]["name"]}, request.get("registry_paths", []))
        for source in request["sources"]: candidate = cs.add_record(candidate, "sources", source)
        company = next((r for r in candidate["companies"] if r["id"] == request["company"]["id"]), None)
        if not company: candidate = cs.add_record(candidate, "companies", request["company"])
        role = request["opportunity"]
        old = next((r for r in candidate["opportunities"] if exact_match(role, r)), None)
        if old:
            cs.require(old["id"] == role["id"], "Reuse the canonical exact-role ID for a known role")
        else: candidate = cs.add_record(candidate, "opportunities", role)
        candidate = cs.add_record(candidate, "forms", request["form"])
        record = {"id": request["id"], "batch_id": request["batch_id"], "opportunity_id": role["id"],
                  "at": request["at"], "requested_new": max(request["requested_new"], requested), "request_sha256": fingerprint, "novelty": seen, "phase": "preparing",
                  "form_id": request["form"]["id"], "compensation": request["compensation"], "conditions": request["conditions"],
                  "registry_paths": request.get("registry_paths", []), "attempt_id": None,
                  "reference_resume_id": request.get("resume_reference", {}).get("material_id"),
                  "preparation_identity_sha256": preparation_identity(request), "preparation_revision": 1, "draft_errors": []}
        if request.get("resume_reference"): record["resume_review"] = copy.deepcopy(request["resume_reference"])
        return cs.add_record(candidate, "search_cases", record)
    state = cs.transact(state_path, reserve, expected_revision)
    case = next(r for r in state["search_cases"] if r["id"] == request["id"])
    if case["novelty"]["status"] != "new":
        return {"saved": True, "completed": False, "assessment": readiness(state, case), "novelty": case["novelty"]}
    cs.require("resume" in request["documents"] or request.get("resume_reference"), "A Markdown resume or approved unchanged resume reference is required")
    selections, draft_errors, resume_result = [], [], None
    with tempfile.TemporaryDirectory(prefix="career-markdown-") as temporary:
        if request.get("resume_reference"):
            reference = request["resume_reference"]
            material = next((m for m in state["materials"] if m["id"] == reference["material_id"]), None)
            cs.require(material and material["visibility"] == "external" and material["kind"] == "resume" and not material.get("review_required"), "Choose an existing approved external resume version")
            cm.material_file(workspace, material)
            import career_achievements as achievements
            try:
                if state.get("achievement_evidence"):
                    cs.require(reference.get("adaptation_audit", {}).get("target_role") == case["opportunity_id"], "Resume selection audit must target this exact role")
                resume_result = achievements.review_reference(state, workspace, material, reference)
            except cs.Invalid as error:
                draft_errors.append(str(error))
            selections.append({"slot": "resume", "material_id": material["id"]})
        for slot, document in request["documents"].items():
            cs.require(slot in SLOTS and (slot != "resume" or not request.get("resume_reference")), "Distinct document slot required")
            cs.require(document["text"].strip() and document["text"].lstrip().startswith("#"), "Draft document must contain Markdown")
            raw = document["text"].encode()
            path = Path(temporary) / (slot + ".md"); path.write_bytes(raw)
            metadata = {"version": 1, "kind": slot,
                        "language": document["language"], "visibility": "external" if slot in {"resume", "cover-letter"} else "private",
                        "at": request["at"], "fact_ids": document["fact_ids"], "source_ids": document["source_ids"]}
            if "adaptation_audit" in document: metadata["adaptation_audit"] = copy.deepcopy(document["adaptation_audit"])
            if slot == "resume" and state.get("achievement_evidence"):
                import career_achievements as achievements
                try:
                    cs.require(metadata.get("adaptation_audit", {}).get("target_role") == case["opportunity_id"], "Resume selection audit must target this exact role")
                    resume_result = achievements.require_resume_audit(state, document["text"], metadata)
                except cs.Invalid as error:
                    draft_errors.append(str(error))
                    metadata["visibility"] = "private"
                    if "adaptation_audit" in metadata: metadata["unverified_adaptation_audit"] = metadata.pop("adaptation_audit")
                    metadata["draft_review_issues"] = list(draft_errors)
            identity_data = [slot, document] + ([metadata["draft_review_issues"]] if metadata.get("draft_review_issues") else [])
            identity = "md-" + cm.sha256(cs.canonical_json(identity_data).encode())[:32]
            metadata.update(id=identity, family_id=identity)
            previous = next((m for m in state["materials"] if m["id"] == identity), None)
            if previous: metadata["at"] = previous["at"]
            state = cm.register_material(state_path, workspace, metadata, path, state["revision"])
            selections.append({"slot": slot, "material_id": identity})
    cs.require({r["slot"] for r in selections} == SLOTS, "Resume/reference, cover, dossier and form answers are all required")
    selections.sort(key=lambda item: item["slot"])
    attempt_id = "case-attempt-" + request["id"] + "-" + cm.sha256(cs.canonical_json(selections).encode())[:12]
    state = cm.prepare_attempt(state_path, workspace, {"id": attempt_id, "opportunity_id": case["opportunity_id"],
         "label": "Review package", "at": request["at"], "materials": selections,
         "history_review_evidence": "Preparation only; readiness remains blocked until history is reconciled"}, state["revision"])
    def finish(current):
        candidate = copy.deepcopy(current)
        record = next(r for r in candidate["search_cases"] if r["id"] == request["id"])
        record.update(phase="preparing" if draft_errors or (resume_result and not resume_result["ready"]) else "saved", attempt_id=attempt_id, draft_errors=list(draft_errors))
        attempt = next(a for a in candidate["application_attempts"] if a["id"] == attempt_id)
        for pin in attempt["materials"]:
            artifact_id = attempt_id + "-" + pin["slot"]
            if any(a["id"] == artifact_id for a in candidate["artifacts"]): continue
            material = next(m for m in candidate["materials"] if m["id"] == pin["material_id"])
            candidate = cs.add_record(candidate, "artifacts", {"id": artifact_id, "opportunity_id": record["opportunity_id"],
                "kind": pin["slot"], "version": 1 + max([a["version"] for a in candidate["artifacts"] if a["opportunity_id"] == record["opportunity_id"] and a["kind"] == pin["slot"]], default=0), "language": material["language"], "path": pin["link_path"] if pin["link_mode"] == "symlink" else material["path"],
                "at": request["at"], "status": "prepared", "fact_ids": material["fact_ids"], "visibility": material["visibility"],
                "material_id": material["id"], "material_sha256": material["sha256"]})
        role = next(r for r in candidate["opportunities"] if r["id"] == record["opportunity_id"])
        assessment = readiness(candidate, record)
        role.update(fit_summary=request["fit_summary"], pay_summary=assessment["income"]["status"] + ": " + assessment["income"]["reason"],
                    next_action="Continue saved draft review" if record["phase"] == "preparing" else "Review Markdown package: " + assessment["status"])
        return cs.validate(candidate)
    state = cs.transact(state_path, finish, state["revision"])
    # Read from disk, verify files, then export. Correct state survives a failed presentation step.
    verify_case(cs.read_state(state_path), workspace, request["id"])
    try:
        view = snapshot.export_snapshot(state_path, workspace, request["at"])
        cs.require(view.get("written"), "Snapshot was not refreshed; preserve edited report")
    except (cs.Invalid, OSError, ValueError) as error:
        return {"saved": True, "completed": False, "view_refreshed": False, "error": str(error)}
    return {"saved": True, "view_refreshed": True, **case_report(state_path, workspace, request["batch_id"], max(request["requested_new"], requested))}


def verify_case(state, workspace, case_id):
    case = next(r for r in state.get("search_cases", []) if r["id"] == case_id)
    cs.require(case["attempt_id"], "Case preparation is incomplete")
    attempt = next(r for r in state["application_attempts"] if r["id"] == case["attempt_id"])
    cm.verify_attempt(state, workspace, attempt)
    cs.require({p["slot"] for p in attempt["materials"]} == SLOTS, "Packet slots are incomplete")
    achievement_review = None
    draft_issues = list(case.get("draft_errors", []))
    for pin in attempt["materials"]:
        material = next(m for m in state["materials"] if m["id"] == pin["material_id"])
        if pin["slot"] != "resume" or material["id"] != case["reference_resume_id"]:
            cs.require(Path(material["path"]).suffix == ".md", "New case drafts must be Markdown only")
        cs.require(not material.get("review_required"), "Pinned material requires claim review")
        if pin["slot"] == "resume" and material["visibility"] != "external":
            draft_issues.extend(material.get("draft_review_issues", ["Resume remains a private draft"]))
        if pin["slot"] == "resume" and draft_issues:
            achievement_review = {"valid": False, "ready": False, "errors": list(dict.fromkeys(draft_issues)),
                                  "pending_achievement_ids": [], "source_achievement_count": len(state.get("achievement_evidence", [])), "semantic_review_required": True}
        elif pin["slot"] == "resume" and state.get("achievement_evidence"):
            import career_achievements as achievements
            audit = case.get("resume_review", {}).get("adaptation_audit") if material["id"] == case["reference_resume_id"] else material.get("adaptation_audit")
            cs.require(audit and audit["target_role"] == case["opportunity_id"], "Resume selection audit must target this exact role")
            if material["id"] == case["reference_resume_id"]:
                achievement_review = achievements.review_reference(state, workspace, material, case.get("resume_review"))
            else:
                achievement_review = achievements.require_resume_audit(state, cm.material_file(workspace, material).read_text(encoding="utf-8"), material)
    assessment = readiness(state, case)
    if case["phase"] == "preparing":
        assessment.update(draft_ready=False, status="blocked" if assessment["status"] == "blocked" else "conditional",
                          unknowns=[*assessment["unknowns"], "Saved preparation needs review/finalization"])
    if achievement_review is not None:
        assessment["achievement_review"] = achievement_review
        if not achievement_review["ready"]:
            assessment.update(draft_ready=False, status="blocked" if assessment["status"] == "blocked" else "conditional",
                              unknowns=[*assessment["unknowns"], "Source achievement clarification remains unresolved; draft saved for review"])
    bad_links = []
    for pin in attempt["materials"]:
        material = next(m for m in state["materials"] if m["id"] == pin["material_id"])
        if material["visibility"] != "external" or Path(material["path"]).suffix != ".md": continue
        text = cm.material_file(workspace, material).read_text()
        for destination in re.findall(r"\]\(([^)]+)\)", text):
            if not public_destination(destination) and not re.fullmatch(r"mailto:[^\s@]+@[^\s@]+", destination): bad_links.append(pin["slot"] + ": " + destination)
    if bad_links:
        assessment = {**assessment, "draft_ready": False, "status": "blocked" if assessment["status"] == "blocked" else "conditional", "unknowns": [*assessment["unknowns"], "Final Markdown contains a local/unsafe destination; verify before sharing"], "link_issues": bad_links}
    return assessment


def case_report(state_path, workspace, batch_id, requested):
    cs.require(type(requested) is int and requested > 0, "Positive requested new-case count required")
    state = cs.read_state(state_path)
    requested = max([requested, *[c["requested_new"] for c in state.get("search_cases", []) if c["batch_id"] == batch_id]])
    views = [snapshot.snapshot_status(state_path, workspace, format) for format in ("xlsx", "csv")]
    current_view = any(r["exists"] and not r["stale"] and not r["manual_change"] for r in views)
    results, counted = [], set()
    for case in state.get("search_cases", []):
        if case["batch_id"] != batch_id: continue
        if case["novelty"]["status"] != "new":
            results.append({"id": case["id"], "status": "revisit" if case["novelty"]["status"] == "known" else "coverage_unresolved", "novelty": case["novelty"]})
            continue
        try:
            check = verify_case(state, workspace, case["id"])
            role = next(r for r in state["opportunities"] if r["id"] == case["opportunity_id"])
            company = next(c for c in state["companies"] if c["id"] == role["company_id"])
            seen = novelty(state, workspace, {**role, "company_name": company["name"]}, case["registry_paths"], ignore_case=case)
            if seen["status"] != "new" or seen["uncertain_company_contacts"]: check = {**check, "draft_ready": False, "status": "blocked", "novelty": seen}
            if check["status"] in {"ready", "ready_with_pay_uncertainty"} and current_view: counted.add(case["opportunity_id"])
            results.append({"id": case["id"], "opportunity_id": case["opportunity_id"], **check})
        except (cs.Invalid, OSError, ValueError, StopIteration, KeyError) as error:
            results.append({"id": case["id"], "status": "incomplete", "error": str(error)})
    return {"requested_new": requested, "new_ready": len(counted), "conditional": sum(r["status"] == "conditional" for r in results),
            "pay_uncertain_ready": sum(r["status"] == "ready_with_pay_uncertainty" for r in results),
            "completed": len(counted) >= requested, "view_current": current_view, "cases": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("novelty", "prepare-case", "report"))
    parser.add_argument("state"); parser.add_argument("workspace"); parser.add_argument("input")
    parser.add_argument("--expected-revision", type=int); parser.add_argument("--requested", type=int, default=1)
    args = parser.parse_args()
    try:
        if args.command == "prepare-case":
            cs.require(args.expected_revision is not None, "Expected state revision required")
            result = prepare_case(args.state, args.workspace, cs.load_json(args.input), args.expected_revision, args.requested)
        elif args.command == "novelty":
            result = novelty(cs.read_state(args.state), args.workspace, cs.load_json(args.input))
        else: result = case_report(args.state, args.workspace, args.input, args.requested)
        print(json.dumps(result, indent=2))
        return 0 if result.get("completed", True) else 3
    except (cs.Invalid, OSError, ValueError, KeyError, TypeError, RecursionError, StopIteration) as error:
        print("Error: " + str(error), file=sys.stderr); return 2


if __name__ == "__main__":
    sys.exit(cs.run_cli(main))
