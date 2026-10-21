#!/usr/bin/env python3
"""Optional local career records. Standard library only; no network or sending."""

import argparse
import copy
from datetime import date, datetime, timedelta, timezone
import json
import hashlib
import math
import re
from functools import lru_cache
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

COLLECTIONS = (
    "sources", "companies", "opportunities", "facts", "suggestions", "artifacts",
    "attempts", "responses", "coverage", "answers", "dossier", "cases",
    "interview_prep", "referrals", "referral_drafts", "contact_events", "forms", "history_imports", "materials", "application_attempts", "credentials", "rehearsals", "context_insights",
)
OPTIONAL_COLLECTIONS = {"context_insights"}
RESPONSE_TYPES = {"auto_receipt", "human_reply", "interview", "offer", "rejection",
                  "bounce", "withdrawal", "rejected_before_application"}
TRACKING_KEYS = {"fbclid", "gclid", "msclkid"}


class Invalid(ValueError):
    """A record violates a documented invariant."""


def require(condition, message):
    if not condition:
        raise Invalid(message)


def timestamp(value):
    require(isinstance(value, str), "Timestamp must be an ISO 8601 string")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise Invalid("Invalid timestamp: " + value) from error
    require(result.tzinfo is not None, "Timestamp needs an explicit time zone")
    return result.astimezone(timezone.utc)


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def canonical_url(value):
    require(isinstance(value, str), "URL must be a string")
    parsed = urlsplit(value)
    require(parsed.scheme in {"https", "http"} and parsed.hostname, "Expected HTTP(S) URL")
    require(not parsed.username and not parsed.password, "Credentials must not appear in URLs")
    query = [(key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in TRACKING_KEYS]
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/",
                       urlencode(sorted(query)), parsed.fragment))


def new_state():
    return {
        "schema_version": 1, "revision": 0, "change_history": [],
        "context_access": {"decision": "unasked", "source_scope": [], "purposes": [], "at": None, "evidence": None},
        "control": {"authorized": False, "paused": True, "scope": "", "history": []},
        "profile": {"timeline": [], "selected_directions": [], "metric_dispositions": []},
        "search_config": {"constraints": [], "salary_floor": None, "salary_goal": None},
        "report_preferences": {"frequency": "on_demand", "results_only": True},
        **{key: [] for key in COLLECTIONS},
    }


def _text(row, *fields):
    for field in fields:
        require(isinstance(row.get(field), str) and bool(row[field].strip()),
                "Nonempty text required: " + field)


def _one(row, field, choices):
    require(row.get(field) in choices, field + " must be one of " + ", ".join(sorted(choices)))


def _refs(row, field, index, nonempty=False):
    values = row.get(field)
    require(isinstance(values, list) and (not nonempty or bool(values)), field + " needs a list")
    require(all(isinstance(item, str) and item in index for item in values),
            "Missing referenced record in " + field)
    require(len(values) == len(set(values)), "Duplicate reference in " + field)


def blocked_facts(facts):
    return {identifier for row in facts.values() for identifier in
            ([row["id"]] + row["contradiction_ids"] if row["contradiction_ids"] else [])}


def claim_issues(row, facts):
    blocked = blocked_facts(facts)
    return [identifier for identifier in row["fact_ids"] if identifier in blocked or
            facts[identifier]["status"] != "confirmed" or facts[identifier]["disclosure"] != "allowed" or
            facts[identifier].get("private_interview_only") or facts[identifier].get("context_reuse_blocked")]


def _confirmed_claims(row, field, facts, historical=False):
    require(not row.get("context_insight_ids"), "Context insights require confirmed career facts before external reuse")
    _refs(row, field, facts)
    issues = claim_issues({"fact_ids": row[field]}, facts)
    require(not issues or (historical and row.get("review_required") is True and
                          set(issues) <= set(row.get("review_fact_ids", []))),
            "External claims require undisputed, confirmed, disclosure-allowed facts")


def private_artifact(row):
    return row.get("visibility", "private" if row.get("kind") == "private_fit_assessment"
                   else "external") == "private"


def flag_historical_claims(state):
    facts = {row["id"]: row for row in state["facts"]}
    for collection in ("artifacts", "interview_prep", "referral_drafts", "materials"):
        for row in state[collection]:
            if collection in {"artifacts", "materials"} and private_artifact(row):
                continue
            issues = claim_issues(row, facts)
            if issues:
                row["review_required"] = True
                row["review_fact_ids"] = sorted(set(row.get("review_fact_ids", [])) | set(issues))
    return state


def canonical_json(value):
    assert_json_value(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def answer_key(row):
    return canonical_json([row["meaning"], row["scope"], row["units"]])


def assert_json_value(value):
    stack = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        require(depth <= 100, "JSON nesting exceeds the supported depth of 100")
        if isinstance(item, dict):
            require(all(isinstance(key, str) for key in item), "JSON object keys must be strings")
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
        else:
            require(item is None or type(item) in {str, bool, int, float}, "Unsupported JSON value")
            require(type(item) is not float or math.isfinite(item), "Nonfinite JSON number is forbidden")


def strict_json_loads(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result
    def constant(value):
        raise Invalid("Nonfinite JSON number is forbidden: " + value)
    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
        assert_json_value(result)
        return result
    except RecursionError as error:
        raise Invalid("JSON nesting exceeds the supported depth") from error


@lru_cache(maxsize=1)
def state_schema():
    return strict_json_loads((Path(__file__).resolve().parents[1] /
                              "references/state.schema.json").read_text(encoding="utf-8"))


def validate_shape(value, schema, root=None, location="state"):
    """Evaluate the JSON Schema subset used by this project, without dependencies."""
    root = schema if root is None else root
    if "$ref" in schema:
        target = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        validate_shape(value, target, root, location)
    for member in schema.get("allOf", []):
        validate_shape(value, member, root, location)
    if "anyOf" in schema:
        for member in schema["anyOf"]:
            try:
                validate_shape(value, member, root, location)
                break
            except Invalid:
                pass
        else:
            raise Invalid(location + " does not match any permitted shape")
    if "if" in schema:
        try:
            validate_shape(value, schema["if"], root, location)
        except Invalid:
            branch = "else"
        else:
            branch = "then"
        if branch in schema:
            validate_shape(value, schema[branch], root, location)
    if "const" in schema:
        require(canonical_json(value) == canonical_json(schema["const"]), location + " has invalid constant")
    if "enum" in schema:
        require(canonical_json(value) in {canonical_json(item) for item in schema["enum"]},
                location + " has an unsupported value")
    types = schema.get("type")
    if types:
        choices = [types] if isinstance(types, str) else types
        matches = {"null": value is None, "object": type(value) is dict,
                   "array": type(value) is list, "string": type(value) is str,
                   "boolean": type(value) is bool, "integer": type(value) is int,
                   "number": type(value) in {int, float}}
        require(any(matches.get(item, False) for item in choices), location + " has the wrong JSON type")
    if isinstance(value, dict):
        require(all(key in value for key in schema.get("required", [])), location + " is missing required fields")
        for key, member in schema.get("properties", {}).items():
            if key in value:
                validate_shape(value[key], member, root, location + "." + key)
        if schema.get("additionalProperties") is False:
            require(set(value) <= set(schema.get("properties", {})), location + " has unsupported fields")
    elif isinstance(value, list):
        require(len(value) >= schema.get("minItems", 0), location + " has too few items")
        require(len(value) <= schema.get("maxItems", len(value)), location + " has too many items")
        if schema.get("uniqueItems"):
            require(len({canonical_json(item) for item in value}) == len(value), location + " has duplicates")
        for position, item in enumerate(value):
            validate_shape(item, schema.get("items", {}), root, location + "[" + str(position) + "]")
    elif isinstance(value, str):
        require(len(value) >= schema.get("minLength", 0), location + " is too short")
        if "pattern" in schema:
            require(re.fullmatch(schema["pattern"], value) is not None, location + " has invalid format")
        if schema.get("format") == "date-time":
            timestamp(value)
        elif schema.get("format") == "date":
            calendar_date(value)
    elif type(value) in {int, float}:
        require(value >= schema.get("minimum", value), location + " is below the minimum")


def validate(state):
    assert_json_value(state)
    validate_shape(state, state_schema())
    require(isinstance(state, dict) and state.get("schema_version") == 1, "Unsupported schema version")
    require(type(state.get("revision")) is int and state["revision"] >= 0, "Invalid revision")
    index = {}
    for collection in COLLECTIONS:
        rows = state.get(collection, [] if collection in OPTIONAL_COLLECTIONS else None)
        require(isinstance(rows, list), "Missing collection: " + collection)
        require(all(isinstance(row, dict) for row in rows), "Records must be objects")
        ids = [row.get("id") for row in rows]
        require(all(isinstance(item, str) and item.strip() for item in ids), "Record IDs required")
        require(len(ids) == len(set(ids)), "Duplicate ID in " + collection)
        index[collection] = {row["id"]: row for row in rows}
    control = state.get("control", {})
    require(type(control.get("authorized")) is bool and type(control.get("paused")) is bool,
            "Research control must use booleans")
    require(control["authorized"] or control["paused"], "Unauthorized research must stay paused")
    require(isinstance(control.get("scope"), str) and isinstance(control.get("history"), list),
            "Research scope/history required")
    authorized, paused, scope = False, True, ""
    previous_at = None
    for decision in control["history"]:
        _one(decision, "action", {"start", "pause", "resume"})
        _text(decision, "evidence")
        when = timestamp(decision["at"])
        require(previous_at is None or when >= previous_at, "Research decisions are out of order")
        previous_at = when
        if decision["action"] == "start":
            _text(decision, "scope")
            authorized, paused, scope = True, False, decision["scope"]
        else:
            require(decision["scope"] == scope, "Pause/resume must preserve the authorized scope")
            if decision["action"] == "resume":
                require(authorized, "Resume requires an earlier start decision")
                paused = False
            else:
                paused = True
    require((control["authorized"], control["paused"], control["scope"]) ==
            (authorized, paused, scope), "Current research flags contradict decision history")
    profile = state.get("profile", {})
    require(isinstance(profile.get("timeline"), list) and
            isinstance(profile.get("selected_directions"), list), "Profile lists required")
    metric_keys = set()
    for item in profile.get("metric_dispositions", []):
        _text(item, "fact_id", "question_key")
        require(item["fact_id"] in index["facts"], "Metric must refer to a fact")
        _one(item, "disposition", {"answered", "no_metric", "unknown", "confidential", "prefer_not_to_disclose"})
        key = (item["fact_id"], item["question_key"])
        require(key not in metric_keys, "Metric question already has a disposition")
        metric_keys.add(key)
    for item in profile["timeline"]:
        _text(item, "label", "date_precision")
        _one(item, "context", {"commercial", "side_project", "volunteer", "learning"})
        _refs(item, "source_ids", index["sources"], True)
    config = state.get("search_config", {})
    require(isinstance(config.get("constraints"), list), "Search constraints required")
    for item in config["constraints"]:
        _text(item, "meaning")
        _one(item, "priority", {"hard", "preference", "negotiable"})
        _one(item, "status", {"known", "unknown"})
        require("value" in item, "Constraint value required, null for unknown")
    for field in ("salary_floor", "salary_goal"):
        money = config.get(field)
        if money is not None:
            require(isinstance(money, dict), "Salary terms must be an object")
            require(type(money.get("amount")) in {int, float} and money["amount"] >= 0, "Invalid salary")
            _text(money, "currency")
            _one(money, "basis", {"gross", "net", "unknown"})
            _one(money, "period", {"hour", "month", "year"})
    preferences = state.get("report_preferences", {})
    _text(preferences, "frequency")
    require(type(preferences.get("results_only")) is bool, "results_only must be boolean")

    urls = set()
    for row in state["sources"]:
        _one(row, "kind", {"web", "document", "user_statement"})
        _text(row, "locator")
        key = canonical_url(row["locator"]) if row["kind"] == "web" else row["locator"]
        require((row["kind"], key) not in urls, "Duplicate source; merge observations and coverage")
        urls.add((row["kind"], key))
        require(isinstance(row.get("coverage"), list) and bool(row["coverage"]), "Source coverage required")
        require(isinstance(row.get("observations"), list) and row["observations"], "Source observations required")
        for observation in row["observations"]:
            timestamp(observation["at"])
            _text(observation, "evidence")
            _one(observation, "status", {"open", "closed", "unknown", "not_applicable"})
            require(type(observation.get("primary")) is bool, "Primary-source flag required")
    for row in state["companies"]:
        _text(row, "name", "identity")
        _refs(row, "source_ids", index["sources"])
        _one(row, "kind", {"company", "speculative_prospect"})
        if row["kind"] == "speculative_prospect":
            _text(row, "relevance_hypothesis")
    require(len({r["identity"] for r in state["companies"]}) == len(state["companies"]),
            "Duplicate company identity")
    role_keys = set()
    role_urls = set()
    for row in state["opportunities"]:
        _text(row, "company_id", "title", "identity")
        require(row["company_id"] in index["companies"], "Unknown company")
        _one(row, "kind", {"vacancy", "contract_project"})
        _refs(row, "source_ids", index["sources"], True)
        role_url = (row["company_id"], canonical_url(row["role_url"]))
        require(role_url not in role_urls, "Duplicate exact role URL; consolidate sources")
        role_urls.add(role_url)
        key = (row["company_id"], row["identity"])
        require(key not in role_keys, "Duplicate exact opportunity identity")
        role_keys.add(key)
        require(isinstance(row.get("status_observations"), list) and row["status_observations"],
                "Dated opportunity status required")
        for observation in row["status_observations"]:
            timestamp(observation["at"])
            _one(observation, "status", {"open", "closed", "unknown"})
            require(observation.get("source_id") in row["source_ids"], "Status source missing")
            if observation["status"] in {"open", "closed"}:
                source = index["sources"][observation["source_id"]]
                require(any(o["primary"] and o["status"] == observation["status"] and
                            timestamp(o["at"]) == timestamp(observation["at"])
                            for o in source["observations"]),
                        "Known vacancy status requires a matching primary observation")
    for row in state["facts"]:
        _text(row, "statement")
        _one(row, "status", {"unconfirmed", "confirmed", "disputed"})
        _one(row, "confidence", {"low", "medium", "high"})
        _one(row, "context", {"commercial", "side_project", "volunteer", "learning"})
        _one(row, "ownership", {"individual", "team", "mixed", "unknown"})
        _one(row, "disclosure", {"allowed", "private", "unknown"})
        _refs(row, "source_ids", index["sources"], True)
        _refs(row, "contradiction_ids", index["facts"])
        if row["status"] == "confirmed":
            confirmation = row.get("confirmation", {})
            _text(confirmation, "evidence")
            timestamp(confirmation["at"])
            require(confirmation.get("source_id") in row["source_ids"], "Confirmation source required")
            require(row["id"] not in row["contradiction_ids"], "A fact cannot contradict itself")
    for row in state["suggestions"]:
        _text(row, "statement")
        _one(row, "status", {"hypothesis", "declined"})
        _refs(row, "source_ids", index["sources"])
    for collection in ("artifacts", "attempts", "responses", "coverage", "dossier", "cases",
                       "interview_prep", "referrals", "referral_drafts", "contact_events", "forms"):
        for row in state[collection]:
            require(row.get("opportunity_id") in index["opportunities"],
                    "Unknown exact opportunity in " + collection)
    versions = set()
    for row in state["forms"]:
        _one(row, "status", {"observed", "provisional"})
        timestamp(row["at"])
        _refs(row, "source_ids", index["sources"], row["status"] == "observed")
        require(isinstance(row.get("fields"), list), "Form fields must be a list")
        field_ids = set()
        for field in row["fields"]:
            _text(field, "id", "label", "control")
            require(isinstance(field.get("help_text"), str), "Help text must be recorded, empty if absent")
            require(field["id"] not in field_ids, "Duplicate form field ID")
            field_ids.add(field["id"])
            require(type(field.get("required")) is bool or field.get("required") is None,
                    "Form requiredness must be boolean or null")
            require(isinstance(field.get("choices"), list), "Observed choices list required")
            if row["status"] == "observed":
                require(type(field.get("required")) is bool, "Observed form needs actual requiredness")
            if field.get("is_consent"):
                _text(field, "consent_text_version")
    for row in state["artifacts"]:
        require(type(row.get("version")) is int and row["version"] > 0, "Positive artifact version required")
        _text(row, "kind", "language", "path")
        timestamp(row["at"])
        _one(row, "status", {"prepared", "reviewed"})
        if private_artifact(row):
            _refs(row, "fact_ids", index["facts"])
            if "evidence_fact_ids" in row:
                _refs(row, "evidence_fact_ids", index["facts"])
        else:
            require(not row.get("evidence_fact_ids"), "Private evidence references belong in private artifacts")
            _confirmed_claims(row, "fact_ids", index["facts"], historical=True)
        key = (row["opportunity_id"], row["kind"], row["version"])
        require(key not in versions, "Duplicate artifact version")
        versions.add(key)
    resolved = set()
    for row in state["attempts"]:
        _one(row, "outcome", {"sent", "not_sent", "uncertain"})
        timestamp(row["at"])
        require(action_time(row, index["attempts"]) <= timestamp(row["at"]), "Action cannot follow recording time")
        _text(row, "evidence", "channel")
        if row.get("artifact_id"):
            artifact = index["artifacts"].get(row["artifact_id"], {})
            require(artifact.get("opportunity_id") == row["opportunity_id"], "Packet belongs to another role")
        previous = row.get("resolves_attempt_id")
        if previous:
            target = index["attempts"].get(previous, {})
            require(target.get("outcome") == "uncertain" and row["outcome"] != "uncertain" and
                    target.get("opportunity_id") == row["opportunity_id"] and previous not in resolved,
                    "Resolution must uniquely reconcile the same role's uncertain attempt")
            require(timestamp(row["at"]) >= timestamp(target["at"]), "Resolution predates attempt")
            require(action_time(row, index["attempts"]) == action_time(target, index["attempts"]),
                    "Reconciliation must preserve the original action time")
            resolved.add(previous)
    pending = {}
    for row in sorted(state["attempts"], key=lambda item: timestamp(item["at"])):
        role = row["opportunity_id"]
        if row.get("resolves_attempt_id"):
            require(pending.get(role) == row["resolves_attempt_id"], "Uncertain resolution must follow its attempt")
            del pending[role]
        else:
            require(role not in pending, "Reconcile uncertain submit before another attempt")
            if row["outcome"] == "uncertain":
                pending[role] = row["id"]
    for row in state["responses"]:
        _one(row, "type", RESPONSE_TYPES)
        timestamp(row["at"])
        _text(row, "evidence")
        if "recorded_at" in row:
            require(timestamp(row["recorded_at"]) >= timestamp(row["at"]), "Response recording predates event")
        sends = effective_sends(state)
        role_sent = any(a["opportunity_id"] == row["opportunity_id"] and a["occurred"] <= timestamp(row["at"])
                        for a in sends)
        require(not role_sent if row["type"] == "rejected_before_application" else role_sent,
                "Response must match the sent or pre-application funnel")
        if row["type"] != "rejected_before_application":
            response_attempt(row, sends)
    for row in state["coverage"]:
        _one(row, "status", {"complete", "partial", "unknown"})
        require(isinstance(row.get("channels"), list) and row["channels"], "Coverage channels required")
        timestamp(row["checked_at"])
        require(timestamp(row["through"]) <= timestamp(row["checked_at"]), "Coverage cannot predict the future")
    answer_keys = set()
    for row in state["answers"]:
        _text(row, "meaning")
        require(isinstance(row.get("scope"), dict) and isinstance(row.get("units"), dict),
                "Structured scope and units required")
        require("value" in row and type(row.get("confirmed")) is bool, "Answer value/confirmation required")
        start, end = timestamp(row["valid_from"]), timestamp(row["valid_until"])
        require(start < end, "Answer validity interval is empty")
        if row["confirmed"]:
            _text(row, "confirmation_evidence")
            require(timestamp(row["confirmed_at"]) <= start, "Answer must be confirmed before validity starts")
        elif row.get("confirmed_at") is not None:
            timestamp(row["confirmed_at"])
        require(type(row.get("is_consent")) is bool, "Explicit consent classification required")
        if row["meaning"].startswith("compensation."):
            require(all(row["units"].get(key) for key in ("currency", "basis", "period")),
                    "Compensation answer requires currency, gross/net basis and period")
        if row["meaning"].startswith(("privacy.", "consent.", "agreement.")):
            require(row["is_consent"], "Consent semantics must be marked as consent")
        if row["is_consent"]:
            require(all(row["scope"].get(key) for key in
                        ("company_id", "opportunity_id", "consent_text_version", "purpose")),
                    "Consent needs exact employer, role, text version and purpose")
        key = answer_key(row)
        for other_key, other_start, other_end in answer_keys:
            require(not row["confirmed"] or key != other_key or end <= other_start or start >= other_end,
                    "Overlapping answer validity for the same semantic key")
        if row["confirmed"]:
            answer_keys.add((key, start, end))
    for row in state["dossier"]:
        _text(row, "statement")
        _one(row, "classification", {"verified", "inference", "unknown"})
        timestamp(row["at"])
        _refs(row, "source_ids", index["sources"], row["classification"] != "unknown")
    for row in state["cases"]:
        _text(row, "prompt")
        _one(row, "classification", {"hypothetical", "publicly_documented"})
        _refs(row, "source_ids", index["sources"], row["classification"] == "publicly_documented")
    for row in state["interview_prep"]:
        _text(row, "language", "question", "outline")
        _one(row, "question_status", {"practice_hypothesis", "publicly_documented"})
        _confirmed_claims(row, "fact_ids", index["facts"], historical=True)
        _refs(row, "source_ids", index["sources"], row["question_status"] == "publicly_documented")
        require(isinstance(row.get("pressure_points"), list) and
                isinstance(row.get("employer_questions"), list), "Interview preparation lists required")
    for row in state["referrals"]:
        _text(row, "public_name", "observed_role", "relevance", "company_id")
        require(row["company_id"] == index["opportunities"][row["opportunity_id"]]["company_id"],
                "Referral company must match the selected role")
        _one(row, "relationship", {"acquaintance", "cold", "unknown"})
        _one(row, "affiliation", {"verified_current", "unknown", "former"})
        timestamp(row["verified_at"])
        _refs(row, "source_ids", index["sources"], True)
        if row["affiliation"] == "verified_current":
            _text(row, "affiliation_evidence")
        if row["relationship"] == "acquaintance":
            _text(row, "relationship_evidence")
    draft_versions = set()
    for row in state["referral_drafts"]:
        person = index["referrals"].get(row.get("referral_id"), {})
        require(person.get("opportunity_id") == row["opportunity_id"], "Referral draft role mismatch")
        _text(row, "text", "professional_reason")
        _confirmed_claims(row, "fact_ids", index["facts"], historical=True)
        _refs(row, "source_ids", index["sources"], True)
        require(type(row.get("version")) is int and row["version"] > 0, "Draft version required")
        key = (row["referral_id"], row["version"])
        require(key not in draft_versions, "Duplicate referral draft version")
        draft_versions.add(key)
    for row in state["contact_events"]:
        person = index["referrals"].get(row.get("referral_id"), {})
        require(person.get("opportunity_id") == row["opportunity_id"], "Contact role mismatch")
        _one(row, "status", {"user_reported_sent", "uncertain", "reply", "declined"})
        _text(row, "evidence")
        timestamp(row["at"])
    validate_imports(state)
    validate_materials_and_credentials(state, index)
    validate_context(state, index)
    return state


def add_record(state, collection, row):
    require(collection in COLLECTIONS, "Unknown collection")
    validate(state)
    row = copy.deepcopy(row)
    validate_shape(row, state_schema()["properties"][collection]["items"], state_schema(), "new record")
    if collection == "context_insights":
        require(context_scope_allowed(state, row), "Context enrichment requires active opt-in for these sources and purpose")
    if collection in {"artifacts", "interview_prep", "referral_drafts", "materials"} and not (
            collection in {"artifacts", "materials"} and private_artifact(row)):
        _confirmed_claims(row, "fact_ids", {fact["id"]: fact for fact in state["facts"]})
    candidate = copy.deepcopy(state)
    if collection == "sources":
        key = canonical_url(row["locator"]) if row["kind"] == "web" else row["locator"]
        for existing in candidate[collection]:
            existing_key = canonical_url(existing["locator"]) if existing["kind"] == "web" else existing["locator"]
            if existing["kind"] == row["kind"] and existing_key == key:
                require(existing["id"] == row["id"], "Duplicate source: reuse existing ID " + existing["id"])
                existing["coverage"] = sorted(set(existing["coverage"] + row["coverage"]))
                for observation in row["observations"]:
                    if canonical_json(observation) not in {canonical_json(o) for o in existing["observations"]}:
                        existing["observations"].append(observation)
                existing.setdefault("original_locators", [existing["locator"]])
                if row["locator"] not in existing["original_locators"]:
                    existing["original_locators"].append(row["locator"])
                return validate(candidate)
    if collection == "attempts" and not row.get("resolves_attempt_id"):
        resolved = {a.get("resolves_attempt_id") for a in candidate["attempts"]}
        require(not any(a["opportunity_id"] == row["opportunity_id"] and a["outcome"] == "uncertain" and
                        a["id"] not in resolved for a in candidate["attempts"]),
                "Reconcile the uncertain submit before recording another attempt")
    if collection == "responses" and row["type"] != "rejected_before_application":
        row["attempt_id"] = response_attempt(row, effective_sends(candidate))
    candidate.setdefault(collection, []).append(row)
    if collection in {"facts", "credentials"}:
        flag_historical_claims(candidate)
    return validate(candidate)


def lookup_answer(state, query, at):
    validate(state)
    when = timestamp(at)
    # Consent decisions are never automatically reused, even for identical text.
    return [row for row in state["answers"] if row["confirmed"] and not row["is_consent"] and
            answer_key(row) == answer_key(query) and
            timestamp(row["valid_from"]) <= when < timestamp(row["valid_until"])]


def research_allowed(state):
    try:
        validate(state)
    except (Invalid, KeyError, TypeError, ValueError):
        return False
    return state["control"]["authorized"] and not state["control"]["paused"]


def action_time(row, attempts):
    visited = set()
    current = row
    while current.get("resolves_attempt_id"):
        require(current["id"] not in visited, "Cyclic attempt reconciliation")
        visited.add(current["id"])
        require(current["resolves_attempt_id"] in attempts, "Unknown reconciliation target")
        current = attempts[current["resolves_attempt_id"]]
    return timestamp(row.get("occurred_at", current.get("occurred_at", current["at"])))


def effective_sends(state, evidence_at=None):
    attempts = {a["id"]: a for a in state["attempts"]}
    result = []
    for row in state["attempts"]:
        if row["outcome"] == "sent" and (evidence_at is None or timestamp(row["at"]) <= evidence_at):
            result.append({"id": row.get("resolves_attempt_id", row["id"]),
                           "resolution_id": row["id"], "opportunity_id": row["opportunity_id"],
                           "occurred": action_time(row, attempts), "recorded": timestamp(row["at"])})
    return result


def response_attempt(row, sends):
    candidates = [a for a in sends if a["opportunity_id"] == row["opportunity_id"] and
                  a["occurred"] <= timestamp(row["at"])]
    if row.get("attempt_id"):
        candidates = [a for a in candidates if row["attempt_id"] in {a["id"], a["resolution_id"]}]
    else:
        latest = max((a["occurred"] for a in candidates), default=None)
        candidates = [a for a in candidates if a["occurred"] == latest]
    require(len(candidates) == 1, "Response needs an unambiguous confirmed send attempt")
    return candidates[0]["id"]


def stats(state, as_of, wait_days=7, evidence_as_of=None):
    validate(state)
    require(type(wait_days) is int and wait_days >= 0, "wait_days must be a nonnegative integer")
    when = timestamp(as_of)
    # The default is all evidence in this file; explicit knowledge cutoffs reproduce earlier reports.
    evidence_at = timestamp(evidence_as_of) if evidence_as_of else max(
        [when] + [timestamp(a["at"]) for a in state["attempts"]] +
        [timestamp(r.get("recorded_at", r["at"])) for r in state["responses"]] +
        [timestamp(c["checked_at"]) for c in state["coverage"]])
    require(evidence_at >= when, "Evidence cutoff must reach the event/report cutoff")
    attempts = [a for a in state["attempts"] if timestamp(a["at"]) <= evidence_at]
    sends = [a for a in effective_sends(state, evidence_at) if a["occurred"] <= when]
    responses = [r for r in state["responses"] if timestamp(r["at"]) <= when and
                 timestamp(r.get("recorded_at", r["at"])) <= evidence_at]
    sent = {a["opportunity_id"] for a in sends}
    prepared = {a["opportunity_id"] for a in state["artifacts"] + state["application_attempts"] if timestamp(a["at"]) <= when}
    resolved = {a.get("resolves_attempt_id") for a in attempts}
    unresolved = {a["opportunity_id"] for a in attempts if a["outcome"] == "uncertain" and
                  a["id"] not in resolved and action_time(a, {r["id"]: r for r in state["attempts"]}) <= when}
    roles_by_response = {kind: {r["opportunity_id"] for r in responses if r["type"] == kind}
                         for kind in RESPONSE_TYPES}
    hiring = set().union(*(roles_by_response[k] for k in ("human_reply", "interview", "offer", "rejection")))
    silence, unobserved, waiting, delivery_problem = set(), set(), set(), set()
    for role in sent - hiring - roles_by_response["withdrawal"] - unresolved:
        latest_send = max((a for a in sends if a["opportunity_id"] == role),
                          key=lambda a: (a["occurred"], a["recorded"]))
        if any(r["type"] == "bounce" and r["opportunity_id"] == role and
               response_attempt(r, effective_sends(state)) == latest_send["id"] for r in responses):
            delivery_problem.add(role)
            continue
        if when - latest_send["occurred"] < timedelta(days=wait_days):
            waiting.add(role)
            continue
        coverage = [c for c in state["coverage"] if c["opportunity_id"] == role and
                    timestamp(c["checked_at"]) <= evidence_at]
        latest = max(coverage, key=lambda c: timestamp(c["checked_at"]), default=None)
        if latest and latest["status"] == "complete" and timestamp(latest["through"]) >= when:
            silence.add(role)
        else:
            unobserved.add(role)
    numerator = len(hiring & sent)
    reported = {r["opportunity_id"] for r in state["history_imports"] if r["opportunity_id"] and
                r["event_kind"] == "initial_application" and r["status"] in {"sent", "uncertain", "bounced"}}
    return {
        "as_of": as_of, "evidence_as_of": evidence_at.isoformat(), "wait_days": wait_days,
        "counts": {"companies": len(state["companies"]), "opportunities": len(state["opportunities"]),
                   "prepared_roles": len(prepared), "sent_roles": len(sent), "attempt_records": len(attempts),
                   "unresolved_submit_roles": len(unresolved),
                   **{kind + "_roles": len(roles) for kind, roles in sorted(roles_by_response.items())},
                   "known_silence_roles": len(silence), "unobserved_roles": len(unobserved),
                   "waiting_roles": len(waiting), "current_delivery_problem_roles": len(delivery_problem),
                   "historically_reported_application_roles": len(reported),
                   "unmapped_history_entries": sum(r["opportunity_id"] is None for r in state["history_imports"]),
                   "referral_prospects": len(state["referrals"]), "referral_drafts": len(state["referral_drafts"]),
                   "referral_contact_events": sum(timestamp(e["at"]) <= when for e in state["contact_events"])},
        "hiring_response_rate": {"numerator": numerator, "denominator": len(sent),
                                 "value": numerator / len(sent) if sent else None},
        "review_required_artifact_ids": [a["id"] for a in state["artifacts"] if a.get("review_required")],
        "notes": ["Unique role counts; response categories can overlap.",
                  "Inventory and imported-history counts describe current records, not a historic snapshot.",
                  "Event cutoff and evidence cutoff differ; later evidence can attest earlier events/coverage.",
                  "Send waiting windows use action occurrence, not reconciliation time.",
                  "Bounce totals retain history; current delivery problems concern the latest send only.",
                  "Auto receipts and bounces are excluded from hiring responses.",
                  "Imported observations are not provider delivery proof and do not inflate confirmed-sent totals.",
                  "Referral drafts/contact events do not count as job applications."],
    }


def private_path(path):
    path = Path(path).expanduser()
    source_root = Path(__file__).resolve().parents[1]
    resolved = path.resolve()
    require(resolved != source_root and source_root not in resolved.parents,
            "Private workspace must be outside the resolved source/installed helper directory")
    for ancestor in path.parents:
        if ancestor.name == "Backups":
            require(not ancestor.is_symlink(), "Backup parent must not be a symlink")
    return path


def initialize_workspace(root):
    root = private_path(root)
    require(not root.exists() or (root.is_dir() and not any(root.iterdir())),
            "Workspace already contains files; select the existing profile or a different location")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name in ("Originals", "Materials", "Applications", "Data", "Backups"):
        (root / name).mkdir(mode=0o700)
    state_path = root / "Data" / "state.json"
    with state_path.open("x", encoding="utf-8") as handle:
        json.dump(new_state(), handle, indent=2)
        handle.write("\n")
    os.chmod(state_path, 0o600)
    with (root / "Profile.md").open("x", encoding="utf-8") as handle:
        handle.write("# Career profile\n\nNo career facts have been confirmed yet. Continue the guided intake in chat.\n")
    os.chmod(root / "Profile.md", 0o600)
    return {"workspace": str(root), "state": str(state_path), "research": "paused"}


def protected_backup(path, revision):
    directory = (path.parent.parent if path.parent.name == "Data" else path.parent) / "Backups" / "State"
    require(not directory.is_symlink() and not directory.parent.is_symlink(), "Backup directory must not be a symlink")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    descriptor, name = tempfile.mkstemp(prefix="state-r" + str(revision) + "-", suffix=".json", dir=directory)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(path.read_bytes())
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(name, 0o600)
    return name


def reviewed_update(state, request, reason):
    validate(state)
    require(isinstance(reason, str) and bool(reason.strip()), "Review reason is required")
    candidate = copy.deepcopy(state)
    operation = request["operation"]
    before, after = None, None
    if operation == "confirm_fact":
        fact = next((r for r in candidate["facts"] if r["id"] == request["fact_id"]), None)
        require(fact is not None, "Unknown fact")
        require(fact["id"] not in blocked_facts({r["id"]: r for r in candidate["facts"]}),
                "Resolve declared contradictions before confirmation")
        before = copy.deepcopy(fact)
        fact["status"] = "confirmed"
        fact["confirmation"] = copy.deepcopy(request["confirmation"])
        source_id = fact["confirmation"]["source_id"]
        if source_id not in fact["source_ids"]:
            fact["source_ids"].append(source_id)
        after = copy.deepcopy(fact)
    elif operation == "confirm_answer":
        answer = next((r for r in candidate["answers"] if r["id"] == request["answer_id"]), None)
        require(answer is not None and not answer["confirmed"], "Choose an existing draft answer")
        before = copy.deepcopy(answer)
        answer.update(confirmed=True, confirmed_at=request["confirmed_at"],
                      confirmation_evidence=request["confirmation_evidence"],
                      valid_from=request["valid_from"], valid_until=request["valid_until"])
        after = copy.deepcopy(answer)
    elif operation == "supersede_answer":
        previous = next((r for r in candidate["answers"] if r["id"] == request["answer_id"]), None)
        require(previous is not None and previous["confirmed"], "Choose an existing confirmed answer")
        replacement = copy.deepcopy(request["replacement"])
        require(answer_key(previous) == answer_key(replacement) and replacement["confirmed"],
                "Replacement must confirm the same exact semantic key")
        require(replacement["id"] != previous["id"], "A superseding answer needs a new stable ID")
        require(timestamp(previous["valid_from"]) < timestamp(replacement["valid_from"]) <=
                timestamp(previous["valid_until"]), "Replacement must begin within the prior validity interval")
        before = copy.deepcopy(previous)
        previous["valid_until"] = replacement["valid_from"]
        replacement["supersedes_answer_id"] = previous["id"]
        candidate["answers"].append(replacement)
        after = {"expired": copy.deepcopy(previous), "replacement": replacement}
    elif operation == "observe_opportunity":
        role = next((r for r in candidate["opportunities"] if r["id"] == request["opportunity_id"]), None)
        require(role is not None, "Unknown opportunity")
        before = copy.deepcopy(role)
        observation = copy.deepcopy(request["observation"])
        if observation["source_id"] not in role["source_ids"]:
            role["source_ids"].append(observation["source_id"])
        if canonical_json(observation) not in {canonical_json(r) for r in role["status_observations"]}:
            role["status_observations"].append(observation)
        after = copy.deepcopy(role)
    elif operation == "set_context_access":
        before = copy.deepcopy(candidate.get("context_access"))
        access = copy.deepcopy(request["access"])
        validate_shape(access, state_schema()["$defs"]["context_access"], state_schema(), "context access")
        require(access["decision"] in {"declined", "opted_in", "withdrawn"}, "Record an actual context-use choice")
        candidate["context_access"] = access
        facts = {r["id"]: r for r in candidate["facts"]}
        insights = {r["id"]: r for r in candidate.get("context_insights", [])}
        for fact in facts.values():
            if fact.get("context_insight_ids"):
                fact["context_reuse_blocked"] = not all(context_scope_allowed(candidate, insights[i]) for i in fact["context_insight_ids"])
        after = {"access": copy.deepcopy(access), "blocked_fact_ids": [f["id"] for f in facts.values() if f.get("context_reuse_blocked")]}
    elif operation == "confirm_context_insight":
        insight = next((r for r in candidate.get("context_insights", []) if r["id"] == request["insight_id"]), None)
        require(insight is not None and context_scope_allowed(candidate, insight), "Context insight needs active scoped opt-in")
        before = copy.deepcopy(insight)
        insight["status"] = "confirmed"
        insight["confirmation"] = copy.deepcopy(request["confirmation"])
        after = copy.deepcopy(insight)
    elif operation == "map_history":
        observation = next((r for r in candidate["history_imports"] if r["id"] == request["history_id"]), None)
        require(observation is not None, "Unknown history observation")
        before = copy.deepcopy(observation)
        observation["opportunity_id"] = request["opportunity_id"]
        after = copy.deepcopy(observation)
    elif operation == "resolve_contradiction":
        ids = request["fact_ids"]
        require(len(ids) == 2 and len(set(ids)) == 2, "Choose the two facts whose contradiction was reviewed")
        facts = {r["id"]: r for r in candidate["facts"]}
        require(all(identifier in facts for identifier in ids), "Unknown fact")
        require(any(other in facts[identifier]["contradiction_ids"] for identifier, other in
                    (ids, list(reversed(ids)))), "No declared contradiction between these facts")
        _text(request, "resolution_evidence", "source_id")
        require(request["source_id"] in {r["id"] for r in candidate["sources"]}, "Resolution source required")
        before = [copy.deepcopy(facts[identifier]) for identifier in ids]
        for identifier in ids:
            facts[identifier]["contradiction_ids"] = [r for r in facts[identifier]["contradiction_ids"] if r not in ids]
        after = [copy.deepcopy(facts[identifier]) for identifier in ids]
    else:
        raise Invalid("Unsupported reviewed operation; arbitrary patches are not supported")
    candidate["change_history"].append({"operation": operation, "reason": reason, "at": utcnow(),
                                        "revision_from": state["revision"], "request": copy.deepcopy(request),
                                        "before": before, "after": after})
    flag_historical_claims(candidate)
    return validate(candidate)


IMPORT_FIELDS = {"source_locator", "source_kind", "employer", "role", "role_url", "date_text",
                 "date_precision", "occurred_at", "channel", "status", "event_kind", "opportunity_id",
                 "evidence_level", "provider_message_id", "provider_thread_id"}


def history_id(row):
    return "history-" + hashlib.sha256(canonical_json({key: row[key] for key in IMPORT_FIELDS if key != "opportunity_id"}).encode()).hexdigest()[:24]


def normalize_history(state, rows):
    require(isinstance(rows, list), "History input must contain a list of mapped rows")
    result = []
    for item in rows:
        require(isinstance(item, dict) and set(item) <= IMPORT_FIELDS, "Unsupported history fields; retain minimal metadata only")
        row = {"source_locator": "", "source_kind": "user_list", "employer": "", "role": "",
               "role_url": None, "date_text": "unknown", "date_precision": "unknown", "occurred_at": None,
               "channel": "unknown", "status": "unknown", "event_kind": "unknown", "opportunity_id": None,
               "evidence_level": "user_reported", "provider_message_id": None, "provider_thread_id": None,
               **copy.deepcopy(item)}
        for key in ("source_locator", "employer", "role", "channel", "date_text"):
            require(isinstance(row[key], str), "History text field has wrong type: " + key)
            row[key] = row[key].strip()
        if row["role_url"]:
            row["role_url"] = canonical_url(row["role_url"])
        if not row["opportunity_id"] and row["role_url"]:
            candidates = [r["id"] for r in state["opportunities"] if canonical_url(r["role_url"]) == row["role_url"]]
            if len(candidates) == 1:
                row["opportunity_id"] = candidates[0]
        row["id"] = history_id(row)
        result.append(row)
    return result


def validate_imports(state):
    roles = {row["id"]: row for row in state["opportunities"]}
    for row in state["history_imports"]:
        validate_shape(row, state_schema()["$defs"]["history_import"], state_schema(), "history row")
        require(row["id"] == history_id(row), "History fingerprint does not match its observation")
        require(row["employer"] or row["role"] or row["role_url"], "Sparse history needs at least an employer, role or URL")
        if row["opportunity_id"] is not None:
            require(row["opportunity_id"] in roles, "Unknown mapped exact opportunity")
            if row["role_url"]:
                require(row["role_url"] == canonical_url(roles[row["opportunity_id"]]["role_url"]),
                        "History URL conflicts with mapped role; resolve identity in preview")
            require(bool(row["role"] or row["role_url"]), "Company-level history cannot mark a role as applied")
        if row["occurred_at"] is not None:
            timestamp(row["occurred_at"])
            require(row["date_precision"] == "exact", "Approximate dates must not become exact timestamps")
        if row["source_kind"] == "connector":
            require(row["evidence_level"] == "provider_observed" and bool(row["provider_message_id"]),
                    "Connector observations require message provenance")
        else:
            require(row["evidence_level"] == "user_reported", "A user list is not provider delivery evidence")


def import_warnings(state, entries):
    warnings = []
    existing = state["history_imports"]
    for row in entries:
        role = row["opportunity_id"]
        if role is None:
            warnings.append({"id": row["id"], "type": "unresolved_identity", "detail": "Keep this entry unmapped until reviewed"})
        elif any(other["opportunity_id"] == role and other["status"] != row["status"] for other in existing + entries
                 if other["id"] != row["id"]):
            warnings.append({"id": row["id"], "type": "status_difference",
                             "detail": "May be chronology or conflict; preserve observations and inspect dates/sources"})
        if role and any(a["opportunity_id"] == role for a in state["attempts"]):
            warnings.append({"id": row["id"], "type": "existing_attempt_evidence",
                             "detail": "Imported history will not overwrite confirmed or uncertain attempts"})
        if row["source_kind"] == "connector" and row["event_kind"] == "unknown":
            warnings.append({"id": row["id"], "type": "message_classification_required",
                             "detail": "A thread/message is not automatically an application"})
    return warnings


def preview_history(state, rows):
    validate(state)
    entries = normalize_history(state, rows)
    existing_rows = {row["id"]: row for row in state["history_imports"]}
    mapping_requests = []
    for row in entries:
        retained = existing_rows.get(row["id"])
        if retained and row["opportunity_id"] != retained["opportunity_id"]:
            mapping_requests.append({"history_id": row["id"], "retained_opportunity_id": retained["opportunity_id"],
                                     "proposed_opportunity_id": row["opportunity_id"], "required_operation": "map_history"})
            row["opportunity_id"] = retained["opportunity_id"]
    candidate = copy.deepcopy(state)
    known = {row["id"] for row in candidate["history_imports"]}
    for row in entries:
        if row["id"] not in known:
            candidate["history_imports"].append(row)
            known.add(row["id"])
    validate(candidate)
    unique = {row["id"]: row for row in entries}
    payload = {"base_revision": state["revision"], "entries": list(unique.values()), "mapping_requests": mapping_requests}
    payload["digest"] = hashlib.sha256(canonical_json(payload).encode()).hexdigest()
    payload["warnings"] = import_warnings(state, payload["entries"]) + [
        {"id": item["history_id"], "type": "mapping_not_applied", "detail": "Preview retains the existing mapping; review a separate map_history operation"} for item in mapping_requests]
    payload["new_entries"] = sum(row["id"] not in {r["id"] for r in state["history_imports"]} for row in payload["entries"])
    return payload


def apply_history(state, plan, reason):
    validate(state)
    require(isinstance(reason, str) and reason.strip(), "Import review reason is required")
    payload = {"base_revision": plan["base_revision"], "entries": plan["entries"], "mapping_requests": plan["mapping_requests"]}
    require(plan["digest"] == hashlib.sha256(canonical_json(payload).encode()).hexdigest(), "Import preview changed")
    require(state["revision"] == plan["base_revision"], "State changed since import preview")
    candidate = copy.deepcopy(state)
    known = {r["id"] for r in candidate["history_imports"]}
    added = []
    existing_rows = {r["id"]: r for r in candidate["history_imports"]}
    for row in plan["entries"]:
        if row["id"] in existing_rows:
            require(canonical_json(row) == canonical_json(existing_rows[row["id"]]), "Existing history differs; use an explicit reviewed map_history operation")
        if row["id"] not in known:
            candidate["history_imports"].append(copy.deepcopy(row))
            known.add(row["id"])
            added.append(row["id"])
    if added:
        candidate["change_history"].append({"operation": "import_history", "at": utcnow(), "reason": reason,
                                            "revision_from": state["revision"], "request": {"added_ids": added},
                                            "before": None, "after": {"digest": plan["digest"], "warnings": plan["warnings"]}})
    return validate(candidate)


def reapplication_guard(state, opportunity_id):
    validate(state)
    require(opportunity_id in {r["id"] for r in state["opportunities"]}, "Unknown exact opportunity")
    role = next(r for r in state["opportunities"] if r["id"] == opportunity_id)
    attempts = [r["id"] for r in state["attempts"] if r["opportunity_id"] == opportunity_id and
                r["outcome"] in {"sent", "uncertain"}]
    imports = [r["id"] for r in state["history_imports"] if r["opportunity_id"] == opportunity_id and
               r["status"] in {"sent", "uncertain", "bounced"}]
    possible = [r["id"] for r in state["history_imports"] if r["opportunity_id"] is None and r["role"] and
                r["role"].casefold() == role["title"].casefold() and
                r["employer"].casefold() == next(c["name"].casefold() for c in state["companies"] if c["id"] == role["company_id"])]
    return {"opportunity_id": opportunity_id, "requires_review": bool(attempts or imports or possible),
            "attempt_ids": attempts, "import_ids": imports, "possible_identity_matches": possible,
            "message": "Reconcile prior history before any new application; this check never authorizes sending"}


def validate_slot(value):
    require(isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,39}", value) is not None,
            "Material slot must be a safe lowercase name such as resume or cover-letter")
    return value


def calendar_date(value):
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None,
            "Credential date must be YYYY-MM-DD or null")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise Invalid("Invalid credential date") from error


def credential_status(row, as_of):
    day = timestamp(as_of).date()
    if row["issued_on"] and calendar_date(row["issued_on"]) > day:
        expiry = "not_yet_issued"
    elif row["expires_on"] and calendar_date(row["expires_on"]) < day:
        expiry = "expired"
    elif row["expires_on"]:
        expiry = "within_recorded_dates"
    else:
        expiry = "expiry_unknown"
    return {"expiry_state": expiry, "verification": row["verification"]}


def _credential_claims(row, credentials):
    for claim in row.get("credential_claims", []):
        require(claim["credential_id"] in credentials, "Unknown credential claim")
        credential = credentials[claim["credential_id"]]
        require(credential["disclosure"] == "allowed", "Private credentials cannot enter external claims")
        state = credential_status(credential, row["at"])["expiry_state"]
        require(state != "not_yet_issued", "An unissued credential cannot be represented as earned")
        if claim["portrayal"] == "current":
            require(state == "within_recorded_dates", "Current credential claims need known, unexpired dates")


def validate_materials_and_credentials(state, index):
    from pathlib import PurePosixPath
    def relative(value):
        path = PurePosixPath(value)
        require(not path.is_absolute() and value and ".." not in path.parts and "\\" not in value,
                "Managed paths must be portable relative paths without traversal")
    for credential in state["credentials"]:
        _refs(credential, "source_ids", index["sources"], True)
        if credential["issued_on"]:
            calendar_date(credential["issued_on"])
        if credential["expires_on"]:
            calendar_date(credential["expires_on"])
        if credential["issued_on"] and credential["expires_on"]:
            require(calendar_date(credential["issued_on"]) <= calendar_date(credential["expires_on"]),
                    "Credential expires before issue")
        if credential["verification"] == "independently_verified":
            require(credential.get("verification_source_id") in credential["source_ids"], "Independent verification needs provenance")
            source = index["sources"][credential["verification_source_id"]]
            require(source["kind"] == "web" and any(o["primary"] for o in source["observations"]),
                    "User-provided evidence alone is not independent credential verification")
            timestamp(credential["verified_at"])
    versions = set()
    for material in state["materials"]:
        key = (material["family_id"], material["version"])
        require(key not in versions, "Duplicate material family/version")
        versions.add(key)
        relative(material["path"])
        require(material["path"].startswith("Materials/objects/"), "Managed material belongs in the central library")
        _refs(material, "source_ids", index["sources"])
        if material["visibility"] == "external":
            _confirmed_claims(material, "fact_ids", index["facts"], historical=True)
            _credential_claims(material, index["credentials"])
        else:
            _refs(material, "fact_ids", index["facts"])
    for artifact in state["artifacts"]:
        if not private_artifact(artifact):
            _credential_claims(artifact, index["credentials"])
        if artifact.get("material_id"):
            material = index["materials"].get(artifact["material_id"])
            require(material is not None and artifact.get("material_sha256") == material["sha256"],
                    "Artifact must pin an existing immutable material/hash")
    for record in state["application_attempts"]:
        require(record["opportunity_id"] in index["opportunities"], "Unknown application-attempt role")
        relative(record["path"])
        require(record["path"].startswith("Applications/"), "Attempt belongs in Applications")
        require(bool(record["materials"]), "Prepared application attempt requires at least one material")
        slots = set()
        for pin in record["materials"]:
            validate_slot(pin["slot"])
            require(pin["slot"] not in slots, "Duplicate attempt material slot")
            slots.add(pin["slot"])
            material = index["materials"].get(pin["material_id"])
            require(material is not None and pin["sha256"] == material["sha256"] and
                    pin["version"] == material["version"], "Attempt must pin exact immutable material version/hash")
            relative(pin["reference_path"])
            relative(pin["link_path"])
            require(pin["reference_path"].startswith(record["path"] + "/") and
                    pin["link_path"].startswith(record["path"] + "/"), "Material links must belong to the exact attempt")
    for delivery in state["attempts"]:
        if delivery.get("application_attempt_id"):
            parent = index["application_attempts"].get(delivery["application_attempt_id"])
            require(parent is not None and parent["opportunity_id"] == delivery["opportunity_id"],
                    "Delivery must reference an application attempt for the same exact role")
    for rehearsal in state["rehearsals"]:
        plan = index["interview_prep"].get(rehearsal["interview_prep_id"])
        require(plan is not None and plan["opportunity_id"] == rehearsal["opportunity_id"],
                "Rehearsal must reference the same role's practice question")


CONTEXT_PURPOSE = {"strength": "strengths", "solved_problem": "solved_problems",
                   "latent_capability": "latent_capabilities", "growth_area": "private_interview_growth"}


def context_scope_allowed(state, insight):
    access = state.get("context_access", {})
    return (access.get("decision") == "opted_in" and bool(insight.get("source_scope")) and
            set(insight["source_scope"]) <= set(access.get("source_scope", [])) and
            CONTEXT_PURPOSE.get(insight.get("kind")) in access.get("purposes", []))


def validate_context(state, index):
    access = state.get("context_access")
    if access is not None:
        if access["decision"] == "unasked":
            require(access["at"] is None and access["evidence"] is None and not access["source_scope"] and not access["purposes"],
                    "Unasked context permission cannot imply a decision or scope")
        else:
            timestamp(access["at"])
            _text(access, "evidence")
            if access["decision"] == "opted_in":
                require(access["source_scope"] and access["purposes"], "Context opt-in needs explicit source scope and purpose")
    insights = index["context_insights"]
    for insight in insights.values():
        _refs(insight, "source_ids", index["sources"], True)
        if insight["status"] == "confirmed":
            confirmation = insight.get("confirmation", {})
            _text(confirmation, "evidence")
            timestamp(confirmation["at"])
            require(confirmation.get("source_id") in insight["source_ids"], "Context confirmation needs exact source provenance")
    for fact in state["facts"]:
        if fact.get("context_insight_ids"):
            _refs(fact, "context_insight_ids", insights, True)
            referenced = [insights[i] for i in fact["context_insight_ids"]]
            if fact["status"] == "confirmed":
                require(all(i["status"] == "confirmed" for i in referenced), "Suggested context insights are not verified career facts")
            if any(i["kind"] == "growth_area" for i in referenced):
                require(fact.get("private_interview_only") is True and fact["disclosure"] == "private",
                        "Growth areas remain private interview preparation and cannot become external career claims")
            if not all(context_scope_allowed(state, i) for i in referenced):
                require(fact.get("context_reuse_blocked") is True, "Withdrawn/out-of-scope context cannot be reused in future claims")
        if fact.get("private_interview_only"):
            require(fact["disclosure"] == "private", "Private interview growth cannot be published")
    for collection in ("artifacts", "materials", "interview_prep", "referral_drafts", "answers", "forms"):
        records = list(state[collection])
        if collection == "forms":
            records.extend(field for form in state[collection] for field in form["fields"])
        for record in records:
            if collection in {"answers", "forms"} and record.get("fact_ids"):
                _confirmed_claims(record, "fact_ids", index["facts"])
            if record.get("context_insight_ids"):
                _refs(record, "context_insight_ids", insights)
                require(collection == "artifacts" and private_artifact(record),
                        "Raw context/growth insights belong only in private preparation artifacts")


def read_state(path):
    return validate(load_json(path))


def _write_atomic(path, state):
    validate(state)
    fd, temporary = tempfile.mkstemp(prefix=".career-state-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def transact(path, transform, expected_revision=None):
    path = private_path(path)
    require(not path.is_symlink(), "State file cannot be a symlink")
    lock = path.with_name(path.name + ".lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise Invalid("State is locked; inspect the writer before removing a stale lock") from error
    try:
        os.close(descriptor)
        state = read_state(path)
        if expected_revision is not None:
            require(type(expected_revision) is int and state["revision"] == expected_revision,
                    "State revision changed; preview/review the latest state before retrying")
        updated = transform(state)
        validate(updated)
        if canonical_json(updated) == canonical_json(state):
            return state
        protected_backup(path, state["revision"])
        updated["revision"] = state["revision"] + 1
        _write_atomic(path, updated)
        return updated
    finally:
        lock.unlink()


def load_json(path):
    return strict_json_loads(Path(path).read_text(encoding="utf-8"))


def control_change(state, action, evidence, scope, confirmed):
    validate(state)
    require(action in {"start", "pause", "resume"}, "Unknown control action")
    require(confirmed, "Attest an actual explicit user decision with --user-confirmed")
    require(bool(evidence.strip()), "User decision evidence required")
    candidate = copy.deepcopy(state)
    control = candidate["control"]
    if action == "start":
        require(bool(scope.strip()), "Starting research needs a scope")
        control.update(authorized=True, paused=False, scope=scope)
    elif action == "resume":
        require(control["authorized"] and control["scope"], "Start research before resuming")
        control["paused"] = False
    else:
        control["paused"] = True
    control["history"].append({"action": action, "evidence": evidence, "at": utcnow(), "scope": control["scope"]})
    return validate(candidate)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Create private empty state; never overwrite")
    init.add_argument("state")
    workspace_init = sub.add_parser("init-workspace", help="Agent initializes the user-chosen private workspace")
    workspace_init.add_argument("state", help="Private workspace directory")
    for name in ("validate", "stats", "research-check", "put", "answer-get", "control", "settings", "review-update", "history-preview", "history-apply", "reapply-check"):
        command = sub.add_parser(name)
        command.add_argument("state")
        if name == "stats":
            command.add_argument("--as-of", required=True)
            command.add_argument("--wait-days", type=int, default=7)
            command.add_argument("--evidence-as-of")
        elif name == "put":
            command.add_argument("collection", choices=COLLECTIONS)
            command.add_argument("record", help="Path to one JSON object")
        elif name == "answer-get":
            command.add_argument("query", help="JSON with meaning, scope and units")
            command.add_argument("--at", required=True)
        elif name == "settings":
            command.add_argument("section", choices=("profile", "search_config", "report_preferences"))
            command.add_argument("record", help="Replacement section as JSON")
            command.add_argument("--expected-revision", type=int, required=True)
            command.add_argument("--reason", required=True)
        elif name in {"review-update", "history-apply"}:
            command.add_argument("record", help="Agent-prepared reviewed operation or import plan")
            command.add_argument("--expected-revision", type=int, required=True)
            command.add_argument("--reason", required=True)
            command.add_argument("--user-confirmed", action="store_true")
        elif name == "history-preview":
            command.add_argument("record", help="Normalized history rows prepared from supplied text/table/file")
        elif name == "reapply-check":
            command.add_argument("opportunity_id")
        elif name == "control":
            command.add_argument("action", choices=("start", "pause", "resume"))
            command.add_argument("--evidence", required=True)
            command.add_argument("--scope", default="")
            command.add_argument("--user-confirmed", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "init-workspace":
            result = initialize_workspace(args.state)
        elif args.command == "init":
            path = private_path(args.state)
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(new_state(), handle, indent=2)
                handle.write("\n")
            result = {"created": str(path), "research": "paused"}
        elif args.command in {"put", "settings", "control", "review-update", "history-apply"}:
            if args.command == "put":
                row = load_json(args.record)
                transform = lambda state: add_record(state, args.collection, row)
            elif args.command == "settings":
                row = load_json(args.record)
                def transform(state):
                    candidate = copy.deepcopy(state)
                    require(bool(args.reason.strip()), "Settings review reason required")
                    candidate[args.section] = row
                    candidate["change_history"].append({"operation": "settings_" + args.section,
                        "reason": args.reason, "at": utcnow(), "revision_from": state["revision"],
                        "request": {"section": args.section}, "before": copy.deepcopy(state[args.section]),
                        "after": copy.deepcopy(row)})
                    return validate(candidate)
            elif args.command in {"review-update", "history-apply"}:
                require(args.user_confirmed, "Reviewed changes require an actual user-confirmed decision")
                request = load_json(args.record)
                if args.command == "review-update":
                    transform = lambda state: reviewed_update(state, request, args.reason)
                else:
                    transform = lambda state: apply_history(state, request, args.reason)
            else:
                transform = lambda state: control_change(state, args.action, args.evidence,
                                                        args.scope, args.user_confirmed)
            updated = transact(args.state, transform, getattr(args, "expected_revision", None))
            result = {"revision": updated["revision"], "valid": True}
        else:
            state = read_state(args.state)
            if args.command == "stats":
                result = stats(state, args.as_of, args.wait_days, args.evidence_as_of)
            elif args.command == "history-preview":
                result = preview_history(state, load_json(args.record))
            elif args.command == "reapply-check":
                result = reapplication_guard(state, args.opportunity_id)
            elif args.command == "answer-get":
                result = lookup_answer(state, load_json(args.query), args.at)
            elif args.command == "research-check":
                allowed = research_allowed(state)
                result = {"allowed": allowed, "scope": state["control"]["scope"]}
                print(json.dumps(result, indent=2))
                return 0 if allowed else 3
            else:
                result = {"valid": True, "revision": state["revision"]}
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 0
    except (Invalid, OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError, OverflowError) as error:
        print("Error: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
