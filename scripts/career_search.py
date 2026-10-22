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
import zipfile
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
    skipped = config.get("search_setup", {}).get("compensation", {}).get("disposition") in {"no_preference", "skipped"}
    if config.get("salary_floor") is None and not (policy and policy.get("floor_disposition") == "no_floor") and not skipped:
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
    setup = cs.search_prerequisites(state)
    if not setup["ready"]: unknowns.append("Search intake decisions missing: " + ", ".join(setup["missing"]))
    if any(b["id"] == case["batch_id"] for b in state.get("search_batches", [])):
        preparation = [p for p in state["interview_prep"] if p["opportunity_id"] == role["id"] and ("interview_prep_ids" not in case or p["id"] in case["interview_prep_ids"])]
        if not preparation or any(p.get("review_required") for p in preparation): unknowns.append("Saved interview preparation is missing or requires review; continue preparing materials, not a live drill")
    if case["novelty"]["status"] != "new" and case.get("packet_purpose") != "existing_review": reasons.append("Not a verified new case")
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
    """Keep opportunity/scope evidence stable; form observations are versioned independently."""
    return cm.sha256(cs.canonical_json({k: v for k, v in request.items() if k not in {"documents", "resume_reference", "at", "revision_reason", "interview_preparation", "form"}}).encode())


def begin_batch(state, request):
    """Persist the user's requested scope/quota before discovery, without authorizing research."""
    cs.validate_shape(request, cs.state_schema()["$defs"]["search_batch"], cs.state_schema(), "search batch")
    existing = next((b for b in state.get("search_batches", []) if b["id"] == request["id"]), None)
    if existing:
        cs.require(existing == request, "Batch scope/quota is immutable; preserve it or start an explicitly revised batch")
        return state
    return cs.add_record(state, "search_batches", request)


def packet_evidence_digest(state):
    """Inputs that can change wording across every slot, independent of report/control revisions."""
    import career_achievements as achievements
    return cm.sha256(cs.canonical_json({
        "extraction": achievements.evidence_input_digest(state),
        "interpretations": state.get("achievement_interpretations", []),
        "profile": state["profile"],
        "credentials": state.get("credentials", []),
        "context_insights": state.get("context_insights", []),
        "contact_answers": [a for a in state["answers"] if a["meaning"].startswith("contact.")],
    }).encode())


def form_answer_markdown(form):
    """Project a changed form-answer observation rather than retaining a contradictory text copy."""
    lines = ["# Application form answers", "", "Observed form: " + form["status"] + "; source date: " + form["at"],
             "Preparation only. Consent pending is not acceptance."]
    for field in form["fields"]:
        lines.extend(["", "## " + field["label"], "Required: " + ("yes" if field["required"] else "no"),
                      "Control: " + field["control"], "Answer state: " + field.get("answer_state", "unknown")])
        if field.get("is_consent"): lines.append("Answer: fresh explicit choice required; no agreement accepted.")
        else: lines.append("Answer: " + json.dumps(field.get("answer"), ensure_ascii=False))
        if field.get("help_text"): lines.append("Help: " + field["help_text"])
        if field.get("choices"): lines.append("Observed choices: " + json.dumps(field["choices"], ensure_ascii=False))
    return "\n\n".join(lines) + "\n"


def expand_packet_edit(state, workspace, edit):
    """Reuse canonical case metadata and retained bytes, so an edit needs no reconstructed search request."""
    cs.validate_shape(edit, cs.state_schema()["$defs"]["packet_edit"], cs.state_schema(), "packet edit")
    case = next((c for c in state.get("search_cases", []) if c["id"] == edit["case_id"]), None)
    cs.require(case is not None and case["attempt_id"], "Map the selected legacy packet to an exact saved case before editing")
    role = next(o for o in state["opportunities"] if o["id"] == case["opportunity_id"])
    company = next(c for c in state["companies"] if c["id"] == role["company_id"])
    previous_form = next(f for f in state["forms"] if f["id"] == case["form_id"])
    form = copy.deepcopy(edit.get("form") or previous_form)
    query = {"meaning": "contact.phone.preference", "scope": {"purpose": "application"}, "units": {}}
    answers = cs.lookup_answer(state, query, edit["at"])
    if answers:
        answer = answers[0]; choice = answer["value"]
        for field in form["fields"]:
            if not cm.phone_field(field) or field.get("is_consent"): continue
            field.update(answer=choice["value"], answer_state="confirmed" if choice["disposition"] == "use" else
                         "not_applicable" if choice["disposition"] == "omit" and not field["required"] else "unknown",
                         confirmation_evidence=answer["confirmation_evidence"])
            field.pop("answer_id", None); field.pop("answer_query", None)
    attempt = next(a for a in state["application_attempts"] if a["id"] == case["attempt_id"])
    cm.verify_attempt(state, workspace, attempt)
    documents, reference = {}, None
    for pin in attempt["materials"]:
        slot = pin["slot"]
        if slot == "resume" and case.get("reference_resume_id"):
            reference = copy.deepcopy(case["resume_review"]); continue
        material = next(m for m in state["materials"] if m["id"] == pin["material_id"])
        path = cm.material_file(workspace, material)
        cs.require(path.suffix == ".md", "Read the existing binary through the host and choose a reviewed reference or Markdown replacement")
        document = {"text": path.read_bytes().decode("utf-8"), "language": material["language"],
                    "fact_ids": list(material["fact_ids"]), "source_ids": list(material["source_ids"])}
        audit = material.get("adaptation_audit", material.get("unverified_adaptation_audit"))
        if audit: document["adaptation_audit"] = copy.deepcopy(audit)
        if slot == "dossier":
            rows = [p for p in state["interview_prep"] if p["id"] in case.get("interview_prep_ids", [])]
            generated = interview_markdown(rows)
            if document["text"].endswith(generated): document["text"] = document["text"][:-len(generated)]
        documents[slot] = document
    if form != previous_form and "form-answers" not in edit.get("documents", {}):
        documents["form-answers"]["text"] = form_answer_markdown(form)
    documents.update(copy.deepcopy(edit.get("documents", {})))
    if "resume" in edit.get("documents", {}): reference = None
    if edit.get("resume_reference"):
        reference = copy.deepcopy(edit["resume_reference"]); documents.pop("resume", None)
    source_ids = set(role["source_ids"]) | set(form["source_ids"])
    request = {"id": case["id"], "batch_id": case["batch_id"], "requested_new": case["requested_new"],
        "at": edit["at"], "revision_reason": edit["reason"], "company": copy.deepcopy(company),
        "opportunity": {k:v for k,v in role.items() if k not in {"fit_summary", "fit_assessment", "pay_summary", "next_action"}},
        "sources": [copy.deepcopy(s) for s in state["sources"] if s["id"] in source_ids], "form": copy.deepcopy(form),
        "compensation": copy.deepcopy(case["compensation"]), "conditions": copy.deepcopy(case["conditions"]),
        "registry_paths": list(case["registry_paths"]), "fit_summary": cs.fit_display(role), "documents": documents}
    if reference: request["resume_reference"] = reference
    if "interview_preparation" in edit: request["interview_preparation"] = copy.deepcopy(edit["interview_preparation"])
    return request


def same_refresh_context(state, case, request):
    """Content edits retain exact opportunity identity, constraints and search scope."""
    role = next(o for o in state["opportunities"] if o["id"] == case["opportunity_id"])
    form = next(f for f in state["forms"] if f["id"] == case["form_id"])
    cs.require(all(request["opportunity"][k] == role[k] for k in ("id", "identity", "role_url", "company_id", "kind")) and
               request["company"]["id"] == role["company_id"] and request["batch_id"] == case["batch_id"] and
               request["form"]["opportunity_id"] == role["id"] and request["compensation"] == case["compensation"] and
               request["conditions"] == case["conditions"] and request.get("registry_paths", []) == case["registry_paths"],
               "Content refresh preserves exact role identity, constraints, scope and registry coverage")


def prepare_case(state_path, workspace, request, expected_revision, requested=1, discovery_only=False, refresh=False):
    """Save a case reservation first; partial failures remain visible and never fill quota."""
    workspace = cs.private_path(workspace).resolve()
    cs.require(workspace in Path(state_path).resolve().parents, "State must belong to the selected workspace")
    if refresh and "case_id" in request: request = expand_packet_edit(cs.read_state(state_path), workspace, request)
    cs.validate_shape(request, cs.state_schema()["$defs"]["search_case_discovery" if discovery_only else "search_case_request"], cs.state_schema(), "case request")
    request = copy.deepcopy(request)
    saved_form = next((f for f in cs.read_state(state_path)["forms"] if f["id"] == request["form"]["id"]), None)
    if saved_form is not None and saved_form != request["form"]:
        previous_id = request["form"]["id"]
        request["form"]["id"] = "form-" + cm.sha256(cs.canonical_json(request["form"]).encode())[:32]
        request["form"]["supersedes_form_id"] = previous_id
    if discovery_only: request["documents"] = {}
    cs.require(not refresh or (not discovery_only and bool(request.get("revision_reason", "").strip())),
               "Refreshing a saved packet requires a reviewed revision reason")
    fingerprint = cm.sha256(cs.canonical_json(request).encode())
    def reserve(state):
        existing = next((r for r in state.get("search_cases", []) if r["id"] == request["id"]), None)
        if existing:
            if existing["request_sha256"] == fingerprint and not refresh: return state
            if existing["phase"] == "discovered" and not discovery_only:
                role = next(r for r in state["opportunities"] if r["id"] == existing["opportunity_id"])
                cs.require(all(request["opportunity"][k] == role[k] for k in ("id", "identity", "role_url", "company_id", "kind")) and
                           request["batch_id"] == existing["batch_id"], "Discovery promotion must preserve exact case identity and batch")
                candidate = copy.deepcopy(state)
                for source in request["sources"]: candidate = cs.add_record(candidate, "sources", source)
                saved_form = next((f for f in candidate["forms"] if f["id"] == request["form"]["id"]), None)
                if saved_form: cs.require(saved_form == request["form"], "Keep the earlier form observation; use a new observation ID")
                else: candidate = cs.add_record(candidate, "forms", request["form"])
                record = next(c for c in candidate["search_cases"] if c["id"] == existing["id"])
                record.update(phase="preparing", at=request["at"], request_sha256=fingerprint,
                              requested_new=max(existing["requested_new"], request["requested_new"], requested),
                              preparation_identity_sha256=preparation_identity(request), preparation_revision=1,
                              form_id=request["form"]["id"], compensation=request["compensation"], conditions=request["conditions"],
                              reference_resume_id=request.get("resume_reference", {}).get("material_id"), draft_errors=[])
                if request.get("resume_reference"): record["resume_review"] = copy.deepcopy(request["resume_reference"])
                candidate["change_history"].append({"operation": "promote_discovery_to_preparation", "at": cs.utcnow(), "reason": "Prepare the saved discovery without counting it as a second opportunity",
                    "revision_from": state["revision"], "request": {"case_id": record["id"]}, "before": copy.deepcopy(existing), "after": copy.deepcopy(record)})
                return cs.validate(candidate)
            cs.require(existing["phase"] == "preparing" or (refresh and existing["phase"] == "saved"),
                       "Use explicit refresh-case for a saved packet; preserve its historical versions")
            cs.require(not cs.reapplication_guard(state, existing["opportunity_id"])["requires_review"], "Submission history prevents revising this preparation")
            identity = preparation_identity(request)
            if refresh:
                same_refresh_context(state, existing, request)
            elif existing.get("preparation_identity_sha256"):
                cs.require(existing["preparation_identity_sha256"] == identity, "Preparation revision can change documents/audit only; preserve identity and scope")
            else:
                # Recover older interrupted v1 reservations without treating their own role as new.
                role = next(r for r in state["opportunities"] if r["id"] == existing["opportunity_id"])
                original_role = {k: v for k, v in role.items() if k not in {"fit_summary", "fit_assessment", "pay_summary", "next_action"}}
                form = next(r for r in state["forms"] if r["id"] == existing["form_id"])
                cs.require(cs.canonical_json(request["opportunity"]) == cs.canonical_json(original_role) and
                           cs.canonical_json(request["form"]) == cs.canonical_json(form) and
                           request["company"]["id"] == role["company_id"] and request["batch_id"] == existing["batch_id"] and
                           request["compensation"] == existing["compensation"] and request["conditions"] == existing["conditions"] and
                           request.get("registry_paths", []) == existing["registry_paths"], "Legacy preparation revision must retain its exact role, form, evidence and scope")
            candidate = copy.deepcopy(state)
            for source in request["sources"]: candidate = cs.add_record(candidate, "sources", source)
            observation = next((f for f in candidate["forms"] if f["id"] == request["form"]["id"]), None)
            if observation: cs.require(observation == request["form"], "Form observation ID has different content; preserve history")
            else: candidate = cs.add_record(candidate, "forms", request["form"])
            record = next(r for r in candidate["search_cases"] if r["id"] == request["id"])
            before = copy.deepcopy(record)
            record.update(request_sha256=fingerprint, preparation_identity_sha256=identity,
                          preparation_revision=record.get("preparation_revision", 1) + 1, at=request["at"],
                          reference_resume_id=request.get("resume_reference", {}).get("material_id"),
                          phase="preparing", draft_errors=[], form_id=request["form"]["id"])
            record.pop("packet_evidence_sha256", None)
            if request.get("resume_reference"): record["resume_review"] = copy.deepcopy(request["resume_reference"])
            else: record.pop("resume_review", None)
            candidate["change_history"].append({"operation": "refresh_saved_packet" if refresh else "revise_case_preparation", "at": cs.utcnow(),
                "reason": request.get("revision_reason", "Revised unsent preparation documents/audit"), "revision_from": state["revision"],
                "request": {"case_id": record["id"], "request_sha256": fingerprint}, "before": before, "after": copy.deepcopy(record)})
            return cs.validate(candidate)
        if refresh:
            known = next((o for o in state["opportunities"] if exact_match(request["opportunity"], o)), None)
            cs.require(known is not None and known["id"] == request["opportunity"]["id"],
                       "Refresh requires an existing exact opportunity; it never reserves a new opportunity")
            cs.require(all(request["opportunity"][k] == known[k] for k in ("identity", "role_url", "company_id", "kind")),
                       "Refresh must retain canonical exact-role identity")
            cs.require(not cs.reapplication_guard(state, known["id"])["requires_review"],
                       "Prior sent/uncertain/bounced history must be reconciled; preserve its pinned packet")
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
        saved_form = next((f for f in candidate["forms"] if f["id"] == request["form"]["id"]), None)
        if saved_form: cs.require(saved_form == request["form"], "Preserve the earlier form; use a new observation ID for changed fields")
        else: candidate = cs.add_record(candidate, "forms", request["form"])
        record = {"id": request["id"], "batch_id": request["batch_id"], "opportunity_id": role["id"],
                  "at": request["at"], "requested_new": max(request["requested_new"], requested), "request_sha256": fingerprint, "novelty": seen, "phase": "discovered" if discovery_only else "preparing",
                  "form_id": request["form"]["id"], "compensation": request["compensation"], "conditions": request["conditions"],
                  "registry_paths": request.get("registry_paths", []), "attempt_id": None,
                  "reference_resume_id": request.get("resume_reference", {}).get("material_id"),
                  "preparation_identity_sha256": preparation_identity(request), "preparation_revision": 1, "draft_errors": []}
        if request.get("resume_reference"): record["resume_review"] = copy.deepcopy(request["resume_reference"])
        if refresh: record["packet_purpose"] = "existing_review"
        candidate = cs.add_record(candidate, "search_cases", record)
        if refresh:
            candidate["change_history"].append({"operation": "register_existing_packet_review", "at": cs.utcnow(),
                "reason": request["revision_reason"], "revision_from": state["revision"],
                "request": {"case_id": record["id"]}, "before": None, "after": copy.deepcopy(record)})
        return cs.validate(candidate)
    state = cs.transact(state_path, reserve, expected_revision)
    if request.get("interview_preparation"):
        def save_preparation(current):
            candidate = current
            for row in request["interview_preparation"]:
                cs.require(row["opportunity_id"] == request["opportunity"]["id"], "Preparation must target the exact case")
                old = next((p for p in candidate["interview_prep"] if p["id"] == row["id"]), None)
                if old: cs.require(old == row, "Preserve previous preparation; record a new version ID")
                else: candidate = cs.add_record(candidate, "interview_prep", row)
            return candidate
        state = cs.transact(state_path, save_preparation, state["revision"])
    case = next(r for r in state["search_cases"] if r["id"] == request["id"])
    if not discovery_only and any(b["id"] == case["batch_id"] for b in state.get("search_batches", [])) and case["phase"] != "saved":
        def pin_preparation(current):
            candidate = copy.deepcopy(current)
            row = next(c for c in candidate["search_cases"] if c["id"] == case["id"])
            row["interview_prep_ids"] = [p["id"] for p in candidate["interview_prep"] if p["opportunity_id"] == row["opportunity_id"]]
            return cs.validate(candidate)
        state = cs.transact(state_path, pin_preparation, state["revision"])
        case = next(c for c in state["search_cases"] if c["id"] == case["id"])
    if discovery_only:
        return {"saved": True, "completed": False, "case_id": case["id"], "status": "discovered", "missing_packet_slots": sorted(SLOTS),
                "next_action": "Prepare Markdown resume/reference, cover, dossier and observed form answers; discovery alone is not ready"}
    if case["novelty"]["status"] != "new" and not refresh:
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
                cs.require(reference.get("adaptation_audit", {}).get("target_role") == case["opportunity_id"], "Resume selection audit must target this exact role")
                resume_result = achievements.review_reference(state, workspace, material, reference)
            except cs.Invalid as error:
                draft_errors.append(str(error))
            selections.append({"slot": "resume", "material_id": material["id"]})
        for slot, document in request["documents"].items():
            document = copy.deepcopy(document)
            if slot == "dossier" and any(b["id"] == case["batch_id"] for b in state.get("search_batches", [])):
                prepared = [p for p in state["interview_prep"] if p["id"] in case.get("interview_prep_ids", [])]
                generated_preparation = interview_markdown(prepared)
                if not document["text"].endswith(generated_preparation): document["text"] += generated_preparation
                document["fact_ids"] = sorted(set(document["fact_ids"]) | {f for p in prepared for f in p["fact_ids"]})
                document["source_ids"] = sorted(set(document["source_ids"]) | {s for p in prepared for s in p["source_ids"]})
            cs.require(slot in SLOTS and (slot != "resume" or not request.get("resume_reference")), "Distinct document slot required")
            cs.require(document["text"].strip() and document["text"].lstrip().startswith("#"), "Draft document must contain Markdown")
            raw = document["text"].encode()
            path = Path(temporary) / (slot + ".md"); path.write_bytes(raw)
            metadata = {"version": 1, "kind": slot,
                        "language": document["language"], "visibility": "external" if slot in {"resume", "cover-letter"} else "private",
                        "at": request["at"], "fact_ids": document["fact_ids"], "source_ids": document["source_ids"]}
            if "adaptation_audit" in document: metadata["adaptation_audit"] = copy.deepcopy(document["adaptation_audit"])
            if slot == "resume":
                import career_achievements as achievements
                try:
                    cs.require(metadata.get("adaptation_audit", {}).get("target_role") == case["opportunity_id"], "Resume selection audit must target this exact role")
                    resume_result = achievements.require_resume_audit(state, document["text"], metadata, required=True)
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
        previous_selection = copy.deepcopy(record)
        record.update(phase="preparing" if draft_errors or (resume_result and not resume_result["ready"]) else "saved",
                      attempt_id=attempt_id, draft_errors=list(draft_errors), packet_evidence_sha256=packet_evidence_digest(candidate))
        if previous_selection != record:
            candidate["change_history"].append({"operation": "select_packet_version", "at": cs.utcnow(),
                "reason": request.get("revision_reason", "Select the saved reviewed/conditional packet version"),
                "revision_from": current["revision"], "request": {"case_id": record["id"]},
                "before": previous_selection, "after": copy.deepcopy(record)})
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
        role.update(fit_assessment={"state": "assessed", "summary": request["fit_summary"], "reason": "", "at": request["at"], "source_ids": list(role["source_ids"])},
                    fit_summary=request["fit_summary"], pay_summary=assessment["income"]["status"] + ": " + assessment["income"]["reason"],
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
    if refresh:
        return {"saved": True, "view_refreshed": True, "new_cases_counted": 0,
                **deliver_packets(state_path, workspace, [request["id"]])}
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
        elif pin["slot"] == "resume":
            import career_achievements as achievements
            audit = case.get("resume_review", {}).get("adaptation_audit") if material["id"] == case["reference_resume_id"] else material.get("adaptation_audit")
            cs.require(audit and audit["target_role"] == case["opportunity_id"], "Resume selection audit must target this exact role")
            if material["id"] == case["reference_resume_id"]:
                achievement_review = achievements.review_reference(state, workspace, material, case.get("resume_review"))
            else:
                achievement_review = achievements.require_resume_audit(state, cm.material_file(workspace, material).read_bytes().decode("utf-8"), material, required=True)
    assessment = readiness(state, case)
    assessment["evidence_current"] = case.get("packet_evidence_sha256") == packet_evidence_digest(state)
    if not assessment["evidence_current"]:
        assessment.update(draft_ready=False, status="blocked" if assessment["status"] == "blocked" else "conditional",
                          unknowns=[*assessment["unknowns"], "Packet predates current career evidence/clarifications or has no refresh receipt"])
    if case["phase"] == "preparing":
        assessment.update(draft_ready=False, status="blocked" if assessment["status"] == "blocked" else "conditional",
                          unknowns=[*assessment["unknowns"], "Saved preparation needs review/finalization"])
    if achievement_review is not None:
        assessment["achievement_review"] = achievement_review
        if not achievement_review["ready"]:
            assessment.update(draft_ready=False, status="blocked" if assessment["status"] == "blocked" else "conditional",
                              unknowns=[*assessment["unknowns"], "Source achievement clarification remains unresolved; draft saved for review",
                                        *achievement_review.get("errors", []),
                                        *achievement_review.get("semantic_review", {}).get("issues", [])])
    form = next(f for f in state["forms"] if f["id"] == case["form_id"])
    external_texts = []
    for pin in attempt["materials"]:
        material = next(m for m in state["materials"] if m["id"] == pin["material_id"])
        if pin["slot"] in {"resume", "cover-letter", "form-answers"}:
            path = cm.material_file(workspace, material)
            external_texts.append(path.read_text() if path.suffix == ".md" else material.get("extracted_text", ""))
    assessment["contacts"] = cm.review_phone(state, external_texts, form["fields"])
    if not assessment["contacts"]["ready"]:
        assessment.update(draft_ready=False, status="blocked" if assessment["status"] == "blocked" else "conditional",
                          unknowns=[*assessment["unknowns"], *assessment["contacts"]["issues"]])
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


def plan_refresh(state, request):
    """Pin the requested review scope before editing; this never starts research or sending."""
    cs.require(isinstance(request, dict) and set(request) == {"id", "at", "case_ids", "reason"}, "Refresh plan requires id, at, case_ids and reason")
    cs.require(isinstance(request["id"], str) and request["id"].strip() and isinstance(request["reason"], str) and request["reason"].strip(), "Refresh ID and reason required")
    cs.timestamp(request["at"])
    ids = request["case_ids"]
    cs.require(isinstance(ids, list) and bool(ids) and all(isinstance(i, str) and i for i in ids) and len(ids) == len(set(ids)), "Pin distinct requested packet IDs, including unresolved legacy entries")
    old = next((h for h in state["change_history"] if h["operation"] == "plan_packet_refresh" and h["request"]["id"] == request["id"]), None)
    if old:
        cs.require(old["request"] == request, "Refresh scope is immutable; retain unresolved entries or record an explicitly revised plan")
        return state
    candidate = copy.deepcopy(state)
    candidate["change_history"].append({"operation": "plan_packet_refresh", "at": request["at"], "reason": request["reason"],
        "revision_from": state["revision"], "request": copy.deepcopy(request), "before": None,
        "after": {"packet_evidence_sha256": packet_evidence_digest(state), "case_ids": list(ids)}})
    return cs.validate(candidate)


def deliver_packets(state_path, workspace, case_ids, refresh_id=None):
    """Read the selected immutable versions, never a directory's newest filename or an ad hoc pointer."""
    workspace = cs.private_path(workspace).resolve()
    path = Path(state_path).resolve()
    cs.require(workspace in path.parents, "State must belong to the selected workspace")
    cs.require(isinstance(case_ids, list) and bool(case_ids) and all(isinstance(i, str) and i for i in case_ids)
               and len(case_ids) == len(set(case_ids)), "Select explicit distinct case IDs for delivery coverage")
    raw = path.read_bytes(); state = cs.validate(cs.strict_json_loads(raw))
    if refresh_id is not None:
        plan = next((h for h in state["change_history"] if h["operation"] == "plan_packet_refresh" and h["request"]["id"] == refresh_id), None)
        cs.require(plan is not None and set(case_ids) == set(plan["request"]["case_ids"]), "Delivery must cover the whole recorded refresh scope, including unresolved packets")
    rows = []
    for identifier in case_ids:
        row = {"id": identifier, "review_current": False, "ready_for_review": False, "documents": []}
        try:
            case = next(c for c in state.get("search_cases", []) if c["id"] == identifier)
            row.update(opportunity_id=case["opportunity_id"], attempt_id=case["attempt_id"])
            check = verify_case(state, workspace, identifier)
            row["assessment"] = check
            review_current = bool(check["evidence_current"] and case["phase"] == "saved" and
                                          check.get("achievement_review", {}).get("ready") and check["contacts"]["ready"])
            ready_for_review = bool(review_current and check["draft_ready"])
            row["label"] = "Ready for review" if ready_for_review else "Saved draft — conditional/stale review"
            attempt = next(a for a in state["application_attempts"] if a["id"] == case["attempt_id"])
            for pin in attempt["materials"]:
                material = next(m for m in state["materials"] if m["id"] == pin["material_id"])
                document = cm.material_file(workspace, material); content = document.read_bytes()
                cs.require(cm.sha256(content) == pin["sha256"], "Selected material changed during delivery readback")
                row["documents"].append({"slot": pin["slot"], "material_id": material["id"], "sha256": cm.sha256(content),
                    "path": str(document), "visibility": material["visibility"],
                    "text": content.decode("utf-8") if document.suffix == ".md" else None})
            row.update(review_current=review_current, ready_for_review=ready_for_review)
        except (cs.Invalid, OSError, ValueError, StopIteration, KeyError) as error:
            row.update(review_current=False, ready_for_review=False, label="Incomplete/unregistered packet — review required", error=str(error) or "No canonical case for selected ID")
        rows.append(row)
    cs.require(path.read_bytes() == raw, "State changed during delivery; read the selected versions again")
    return {"workspace": str(workspace), "state_path": str(path), "revision": state["revision"], "state_sha256": cm.sha256(raw),
            "selected": len(case_ids), "reviewed_current": sum(r["review_current"] for r in rows),
            "ready_for_review": sum(r["ready_for_review"] for r in rows), "all_updated": all(r["review_current"] for r in rows),
            "completed": all(r["ready_for_review"] for r in rows), "packets": rows, "sent": False}


def export_delivery(state_path, workspace, request):
    """One selected-version receipt supplies chat, fixed portal and private review archive."""
    receipt = deliver_packets(state_path, workspace, request["case_ids"], request.get("refresh_id"))
    formats = request.get("formats", [])
    cs.require(isinstance(formats, list) and len(formats) == len(set(formats)) and set(formats) <= {"portal", "archive"},
               "Delivery formats are portal and/or private archive")
    if not formats: return receipt
    cs.require(request.get("output_relative"), "Choose a private relative directory for the requested delivery")
    destination = cm.inside(workspace, request["output_relative"])
    cs.require(not destination.exists() and not destination.is_symlink(), "Preserve existing delivery; choose an absent versioned destination")
    destination.mkdir(parents=True, mode=0o700)
    outputs = {}
    def require_current():
        cs.require(cm.sha256(Path(state_path).read_bytes()) == receipt["state_sha256"], "State changed during handoff; preserve outputs and deliver the current selection again")
    try:
        require_current()
        if "portal" in formats:
            import career_portal as portal
            view = snapshot.export_snapshot(state_path, workspace, cs.utcnow())
            cs.require(view.get("written"), "Spreadsheet view not refreshed; preserve the edited view")
            exported = portal.export_portal(state_path, workspace, "selected-packets",
                request["output_relative"] + "/Portal", case_ids=request["case_ids"])
            outputs["portal"] = exported["path"]
        if "archive" in formats:
            archive_path = destination / "Review-packets.zip"
            with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
                for packet in receipt["packets"]:
                    folder = cm.component(packet.get("opportunity_id", packet["id"]), packet["id"])
                    for document in packet["documents"]:
                        require_current()
                        selected = cm.inside(workspace, str(Path(document["path"]).resolve().relative_to(Path(workspace).resolve())))
                        raw = selected.read_bytes()
                        cs.require(cm.sha256(raw) == document["sha256"], "Selected document changed during archive readback")
                        slot = cs.validate_slot(document["slot"])
                        member = folder + "/" + ("PRIVATE/" if document["visibility"] == "private" else "") + slot + selected.suffix
                        archive.writestr(member, raw)
                archive.writestr("selection.json", json.dumps(receipt, indent=2))
                archive.writestr("README.md", "# Private review packet snapshot\n\nContains private assessment/form records and saved drafts. Not an outgoing employer package or proof of sending. See selection.json for per-case review status and exact versions.\n")
            outputs["archive"] = str(archive_path)
        require_current()
        result = {**receipt, "outputs": outputs, "delivered": True}
        (destination / "delivery.json").write_text(json.dumps(result, indent=2) + "\n")
        require_current()
        return result
    except (cs.Invalid, OSError, ValueError, KeyError) as error:
        if (destination / "Portal" / "OPEN.html").exists():
            import career_portal as portal
            portal.mark_incomplete(destination / "Portal")
        result = {**receipt, "completed": False, "delivered": False, "outputs": outputs,
                  "presentation_error": str(error), "output_status": "Incomplete; preserved for inspection, not a current handoff"}
        (destination / "INCOMPLETE.json").write_text(json.dumps(result, indent=2) + "\n")
        if (destination / "delivery.json").exists(): (destination / "delivery.json").write_text(json.dumps(result, indent=2) + "\n")
        return result


def case_report(state_path, workspace, batch_id, requested):
    cs.require(type(requested) is int and requested > 0, "Positive requested new-case count required")
    state = cs.read_state(state_path)
    requested = max([requested, *[b["requested_new"] for b in state.get("search_batches", []) if b["id"] == batch_id], *[c["requested_new"] for c in state.get("search_cases", []) if c["batch_id"] == batch_id]])
    views = [snapshot.snapshot_status(state_path, workspace, format) for format in ("xlsx", "csv")]
    current_view = any(r["exists"] and not r["stale"] and not r["manual_change"] for r in views)
    results, counted = [], set()
    for case in state.get("search_cases", []):
        if case["batch_id"] != batch_id: continue
        if case["novelty"]["status"] != "new" and case.get("packet_purpose") != "existing_review":
            results.append({"id": case["id"], "status": "revisit" if case["novelty"]["status"] == "known" else "coverage_unresolved", "novelty": case["novelty"]})
            continue
        try:
            check = verify_case(state, workspace, case["id"])
            role = next(r for r in state["opportunities"] if r["id"] == case["opportunity_id"])
            company = next(c for c in state["companies"] if c["id"] == role["company_id"])
            seen = novelty(state, workspace, {**role, "company_name": company["name"]}, case["registry_paths"], ignore_case=case)
            if (case["novelty"]["status"] == "new" and seen["status"] != "new") or seen["uncertain_company_contacts"]:
                check = {**check, "draft_ready": False, "status": "blocked", "novelty": seen}
            if case["novelty"]["status"] == "new" and check["status"] in {"ready", "ready_with_pay_uncertainty"} and current_view: counted.add(case["opportunity_id"])
            results.append({"id": case["id"], "opportunity_id": case["opportunity_id"], "revisit": case["novelty"]["status"] != "new", **check})
        except (cs.Invalid, OSError, ValueError, StopIteration, KeyError) as error:
            results.append({"id": case["id"], "opportunity_id": case["opportunity_id"], "status": "incomplete", "error": str(error), "missing_packet_slots": sorted(SLOTS) if not case["attempt_id"] else []})
    return {"requested_new": requested, "new_ready": len(counted), "conditional": sum(r["status"] == "conditional" for r in results),
            "pay_uncertain_ready": sum(r["status"] == "ready_with_pay_uncertainty" for r in results),
            "completed": len(counted) >= requested, "view_current": current_view, "cases": results,
            "shortfall": max(0, requested-len(counted)), "discovered_cases": len(results),
            "unrecorded_slots": max(0, requested-len(results)), "delivery_contract": "Saved Markdown packets or specific incomplete/blocker reasons; links never count as ready"}


def interview_markdown(rows):
    sections = ["\n\n## Saved interview preparation\n\nPrivate suggested answers; no live mock interview has started.\n"]
    if not rows: return "\n".join(sections + ["Preparation is incomplete: profile/role questions and supported answer outlines have not been saved."])
    for row in rows:
        sections.extend(["### Interviewer (" + row["question_status"] + ")", row["question"], "### Candidate — suggested answer outline", row["outline"]])
        for heading, key in [("Clarify", "unknowns"), ("Possible resume follow-ups", "pressure_points"), ("Questions for the company", "employer_questions")]:
            if row.get(key): sections.append(heading + ": " + "; ".join(x if isinstance(x, str) else cs.canonical_json(x) for x in row[key]))
        if row.get("concept_links"): sections.append("Checked concepts: " + "; ".join("[" + x["term"].replace("]", "\\]") + "](" + x["url"].replace(")", "%29") + ")" for x in row["concept_links"]))
        sections.append("Evidence facts: " + ", ".join(row["fact_ids"]) + "; sources: " + ", ".join(row["source_ids"]))
    return "\n\n".join(sections) + "\n"


def prepare_batch(state_path, workspace, requests, expected_revision):
    """Continue staged discoveries through actual packet preparation in one agent operation."""
    cs.require(isinstance(requests, list) and bool(requests), "Prepare the selected packet scope")
    cs.require(cs.read_state(state_path)["revision"] == expected_revision, "State revision changed")
    if all("case_id" in item for item in requests):
        ids = [item["case_id"] for item in requests]
        cs.require(len(ids) == len(set(ids)), "Select each exact packet once per edit batch")
        for item in requests: cs.validate_shape(item, cs.state_schema()["$defs"]["packet_edit"], cs.state_schema(), "packet edit")
        refresh_id = "edit-" + cm.sha256(cs.canonical_json(requests).encode())[:32]
        state = cs.transact(state_path, lambda s: plan_refresh(s, {"id": refresh_id, "at": requests[0]["at"],
            "case_ids": ids, "reason": requests[0]["reason"]}), expected_revision)
        outcomes = []
        for edit in requests:
            try:
                result = prepare_case(state_path, workspace, edit, cs.read_state(state_path)["revision"], refresh=True)
                outcomes.append({"id": edit["case_id"], "saved": result.get("saved", False),
                                 "view_refreshed": result.get("view_refreshed", False), "error": result.get("error")})
            except (cs.Invalid, OSError, ValueError, KeyError, StopIteration) as error:
                outcomes.append({"id": edit["case_id"], "saved": False, "error": str(error)})
        receipt = deliver_packets(state_path, workspace, ids, refresh_id)
        failed = {row["id"]: row for row in outcomes if not row["saved"]}
        view_errors = [row for row in outcomes if row["saved"] and not row.get("view_refreshed")]
        for packet in receipt["packets"]:
            packet["requested_edit_saved"] = packet["id"] not in failed
            if packet["id"] in failed:
                packet.update(previous_review_current=packet["review_current"], review_current=False, ready_for_review=False,
                              label="Previous packet retained — requested edit failed", update_error=failed[packet["id"]]["error"])
        return {**receipt, "all_updated": receipt["all_updated"] and not failed,
                "completed": receipt["completed"] and not failed and not view_errors,
                "reviewed_current": sum(row["review_current"] for row in receipt["packets"]),
                "ready_for_review": sum(row["ready_for_review"] for row in receipt["packets"]),
                "view_refreshed": not failed and not view_errors, "presentation_errors": view_errors,
                "refresh_id": refresh_id, "preparation_outcomes": outcomes,
                "next_preparation": [row["id"] for row in receipt["packets"] if not row["review_current"]]}
    cs.require(len(requests) <= 30, "Prepare new discoveries in coherent groups of at most thirty; retain the original stored quota")
    cs.require(all("batch_id" in item for item in requests), "Use new-case requests or focused existing-case edits in one coherent batch")
    batch_id = requests[0]["batch_id"]
    cs.require(all(r["batch_id"] == batch_id for r in requests), "Keep one requested search scope per preparation batch")
    outcomes = []
    for request in requests:
        try:
            result = prepare_case(state_path, workspace, request, cs.read_state(state_path)["revision"])
            outcomes.append({"id": request["id"], "saved": result.get("saved", False), "error": result.get("error")})
        except (cs.Invalid, OSError, ValueError, KeyError) as error:
            outcomes.append({"id": request.get("id"), "saved": False, "error": str(error)})
    report = case_report(state_path, workspace, batch_id, max(r["requested_new"] for r in requests))
    return {**report, "preparation_outcomes": outcomes,
            "next_preparation": [r["id"] for r in report["cases"] if r["status"] in {"incomplete", "conditional"}]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("novelty", "begin-batch", "stage-case", "prepare-case", "refresh-case", "plan-refresh", "prepare-batch", "deliver", "report"))
    parser.add_argument("state"); parser.add_argument("workspace"); parser.add_argument("input")
    parser.add_argument("--expected-revision", type=int); parser.add_argument("--requested", type=int, default=1)
    args = parser.parse_args()
    try:
        if args.command == "deliver":
            request = cs.load_json(args.input)
            result = export_delivery(args.state, args.workspace, request)
        elif args.command == "plan-refresh":
            cs.require(args.expected_revision is not None, "Expected state revision required")
            request = cs.load_json(args.input)
            state = cs.transact(args.state, lambda s: plan_refresh(s, request), args.expected_revision)
            result = {"saved": True, "revision": state["revision"], "selected": len(request["case_ids"]), "refresh_id": request["id"], "completed": False}
        elif args.command == "begin-batch":
            cs.require(args.expected_revision is not None, "Expected state revision required")
            updated = cs.transact(args.state, lambda s: begin_batch(s, cs.load_json(args.input)), args.expected_revision)
            result = {"saved": True, "revision": updated["revision"], "completed": False, "next_action": "Stage each discovery, then prepare its Markdown packet or report a specific blocker"}
        elif args.command == "prepare-batch":
            cs.require(args.expected_revision is not None, "Expected state revision required")
            result = prepare_batch(args.state, args.workspace, cs.load_json(args.input), args.expected_revision)
        elif args.command in {"prepare-case", "stage-case", "refresh-case"}:
            cs.require(args.expected_revision is not None, "Expected state revision required")
            result = prepare_case(args.state, args.workspace, cs.load_json(args.input), args.expected_revision, args.requested, discovery_only=args.command == "stage-case", refresh=args.command == "refresh-case")
        elif args.command == "novelty":
            result = novelty(cs.read_state(args.state), args.workspace, cs.load_json(args.input))
        else: result = case_report(args.state, args.workspace, args.input, args.requested)
        print(json.dumps(result, indent=2))
        return 0 if result.get("completed", True) else 3
    except (cs.Invalid, OSError, ValueError, KeyError, TypeError, RecursionError, StopIteration) as error:
        print("Error: " + str(error), file=sys.stderr); return 2


if __name__ == "__main__":
    sys.exit(cs.run_cli(main))
