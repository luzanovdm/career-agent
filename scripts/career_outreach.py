#!/usr/bin/env python3
"""Local contact, payload and delivery ledger. No network, sending or scheduling."""

import argparse
import copy
from datetime import timedelta
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

OWNED = {"employee_contacts", "contact_suppressions", "delivery_permissions", "outbound_actions"}
AXES = {"identity", "affiliation", "relevance", "address", "delivery"}
TRANSITIONS = {"draft": {"ready", "cancelled"}, "ready": {"dispatching", "cancelled"},
               "dispatching": {"sent", "failed", "uncertain"}, "uncertain": {"sent", "failed"}}
VARIANT_KEYS = {"sender", "provider", "delivery_revision", "template_revision", "stable_links", "attachment_revision"}


def api():
    import career_state
    return career_state


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def status(action):
    return action["events"][-1]["state"]


class MessageHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []; self.links = []; self.images = []; self.hidden = []; self.anchor = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.anchor = {"destination": attrs.get("href", ""), "visible": ""}
            self.links.append(self.anchor)
        if tag == "img": self.images.append(attrs.get("src", ""))
        style = attrs.get("style", "").lower().replace(" ", "")
        if tag in {"script", "style"} or "hidden" in attrs or any(x in style for x in ("display:none", "visibility:hidden", "font-size:0", "opacity:0")):
            self.hidden.append(tag)
        if tag in {"p", "br", "div", "li"}: self.text.append(" ")

    def handle_endtag(self, tag):
        if tag == "a": self.anchor = None
        if tag in {"p", "div", "li"}: self.text.append(" ")

    def handle_data(self, data):
        self.text.append(data)
        if self.anchor is not None: self.anchor["visible"] += data


def inspect_payload(raw, variant):
    cs = api()
    cs.require(set(variant) == VARIANT_KEYS, "Variant needs sender/provider and delivery/template/link/attachment revisions")
    cs.require(all(isinstance(variant[k], str) and variant[k].strip() for k in VARIANT_KEYS - {"stable_links"}), "Variant revisions must be nonempty")
    cs.require(isinstance(variant["stable_links"], list) and all(isinstance(v, str) for v in variant["stable_links"]), "Stable links need explicit destinations")
    for link in variant["stable_links"]: cs.canonical_url(link)
    message = BytesParser(policy=policy.default).parsebytes(raw)
    cs.require(not message.defects, "Malformed representative MIME message")
    sender = getaddresses(message.get_all("From", []))
    recipients = getaddresses(message.get_all("To", []) + message.get_all("Cc", []) + message.get_all("Bcc", []))
    cs.require(len(sender) == 1 and sender[0][1].casefold() == variant["sender"].casefold(), "Actual From differs from variant sender")
    cs.require(len(recipients) == 1 and "@" in recipients[0][1], "Inspect one exact recipient; multi-person blasts are unsupported")
    plain = []; html = []; attachments = []
    for part in message.walk():
        cs.require(not part.defects, "Malformed MIME part")
        if part.is_multipart(): continue
        content = part.get_payload(decode=True) or b""
        if part.get_content_disposition() == "attachment" or part.get_filename():
            attachments.append({"name": part.get_filename(), "type": part.get_content_type(), "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
        elif part.get_content_type() in {"text/plain", "text/html"}:
            text = content.decode(part.get_content_charset() or "utf-8", errors="replace")
            (plain if part.get_content_type() == "text/plain" else html).append(text)
    parser = MessageHTML(); parser.feed("\n".join(html))
    normalize = lambda value: " ".join(value.split())
    flags = []
    parity = "plain_only" if plain and not html else "html_only" if html and not plain else "matching" if normalize(" ".join(plain)) == normalize(" ".join(parser.text)) else "different"
    if parity in {"html_only", "different"}: flags.append("Review actual plain/HTML content parity")
    if parser.hidden: flags.append("Review hidden content or executable/style markup")
    if parser.images: flags.append("Review image destinations and tracking pixels")
    links = parser.links + [{"visible": url, "destination": url} for url in re.findall(r"https?://[^\s<>]+", "\n".join(plain))]
    for link in links:
        target = urlsplit(link["destination"])
        link["check"] = "unfetched"
        if target.scheme not in {"https", "http", "mailto"}: flags.append("Review nonstandard link destination")
        if target.hostname in {"bit.ly", "t.co", "tinyurl.com"}: flags.append("Review shortened URL")
        if re.search(r"https?://", link["visible"]) and link["visible"].strip().rstrip("/") != link["destination"].rstrip("/"): flags.append("Review visible/destination URL mismatch")
        if any(x in link["destination"].lower() for x in ("utm_", "click", "track")): flags.append("Review tracking or redirect URL")
    cs.require(bool(plain or html), "Representative payload needs actual message content")
    headers = {name: [str(value) for value in message.get_all(name, [])] for name in dict.fromkeys(list(message.keys()) + ["From", "To", "Cc", "Bcc", "Reply-To", "Subject", "Content-Type", "MIME-Version", "List-Unsubscribe"])}
    structure = {"body_types": sorted(set(part.get_content_type() for part in message.walk() if not part.is_multipart() and not part.get_filename() and part.get_content_disposition() != "attachment")),
                 "attachments": [{"type": a["type"], "extension": Path(a["name"] or "").suffix.lower()} for a in attachments],
                 "reply_to": headers["Reply-To"], "list_unsubscribe": headers["List-Unsubscribe"],
                 "hidden_tags": sorted(parser.hidden), "remote_images": sorted(parser.images)}
    for stable in variant["stable_links"]:
        cs.require(any(link["destination"] == stable for link in links), "Declared stable link is absent from the actual payload")
    return {"payload_sha256": hashlib.sha256(raw).hexdigest(), "variant_sha256": digest({"configuration": variant, "structure": structure}), "variant": copy.deepcopy(variant), "structure": structure,
            "sender": variant["sender"], "provider": variant["provider"], "recipient": recipients[0][1],
            "headers": headers, "parity": parity, "attachments": attachments, "links": links, "hidden_tags": parser.hidden,
            "flags": sorted(set(flags)), "receiver_authentication": "unknown", "spam_score_interpretation": "heuristic_only",
            "limitations": ["No URL fetching, receiver authentication, mailbox validation or inbox-placement guarantee", "Variant revisions require review against the actual structure; text tailoring alone does not change them"]}


def url_observation(http_status):
    """Classify host-supplied HTTP observations without fetching or bypassing access controls."""
    return "inconclusive" if http_status in {None, 401, 403, 429, 999} or http_status >= 500 else "reachable" if 200 <= http_status < 400 else "broken" if http_status in {404, 410} else "inconclusive"


def contact_guard(state, contact_id, opportunity_id, at):
    cs = api(); when = cs.timestamp(at)
    contact = next((r for r in state.get("employee_contacts", []) if r["id"] == contact_id), None)
    cs.require(contact is not None, "Unknown employee contact")
    role = next((r for r in state["opportunities"] if r["id"] == opportunity_id), None)
    cs.require(role and role["company_id"] == contact["company_id"], "Contact must belong to this opportunity's company")
    reasons = []
    if opportunity_id not in contact["opportunity_ids"]: reasons.append("Role relevance is not evidenced for this opportunity")
    if contact["kind"] == "inferred_address" or contact["address_provenance"] == "inferred": reasons.append("Inferred address is not a published or correspondence-backed route")
    if contact["kind"] == "named_employee" and (contact["affiliation"] != "current" or not cs.timestamp(contact["checked_at"]) <= when < cs.timestamp(contact["valid_until"])): reasons.append("Current affiliation needs rechecking")
    if any(contact["confidence"][axis] in {"low", "unknown"} for axis in ("identity", "relevance", "address")): reasons.append("Insufficient identity, relevance or address evidence")
    for suppression in state.get("contact_suppressions", []):
        if cs.timestamp(suppression["at"]) > when or suppression["company_id"] != contact["company_id"]: continue
        value = {"endpoint": contact["endpoint"].casefold(), "person": contact["person_key"], "company": contact["company_id"], "opportunity": opportunity_id}[suppression["scope"]]
        if suppression["value"] == value: reasons.append("Suppressed: " + suppression["reason"])
    for action in state.get("outbound_actions", []):
        if action["kind"] == "outreach" and action.get("contact_id") == contact_id and action.get("receiver_report", {}).get("outcome") in {"hard_bounce", "missing_mailbox", "missing_domain"}:
            reasons.append("Known failed endpoint; select another evidenced channel")
    return {"usable": not reasons, "reasons": sorted(set(reasons)), "contact_id": contact_id,
            "person_key": contact["person_key"], "endpoint": contact["endpoint"], "confidence": contact["confidence"]}


def history_guard(state, action, at):
    cs = api(); contact = next(r for r in state.get("employee_contacts", []) if r["id"] == action["contact_id"])
    role_id = action["opportunity_id"]; reasons = []
    history = cs.reapplication_guard(state, role_id)
    resolved_attempts = {r.get("resolves_attempt_id") for r in state["attempts"]}
    if any(r["opportunity_id"] == role_id and r["outcome"] == "uncertain" and r["id"] not in resolved_attempts for r in state["attempts"]): reasons.append("Reconcile uncertain application delivery before any related outreach purpose")
    reconciled_imports = {r["history_id"] for r in state["profile"].get("history_reconciliations", [])}
    if any(r["opportunity_id"] == role_id and r["status"] == "uncertain" and r["id"] not in reconciled_imports for r in state["history_imports"]): reasons.append("Reconcile uncertain imported delivery before related outreach")
    if any(r["event"]["opportunity_id"] == role_id for r in state["profile"].get("contact_history_review", [])): reasons.append("Quarantined personal contact history remains unresolved")
    prior = [r for r in state.get("outbound_actions", []) if r["kind"] == "outreach" and r["id"] != action["id"] and cs.timestamp(r["events"][0]["at"]) <= cs.timestamp(at)]
    related = [r for r in prior if r["company_id"] == action["company_id"] and (r["opportunity_id"] == role_id or next(c for c in state["employee_contacts"] if c["id"] == r["contact_id"])["person_key"] == contact["person_key"])]
    company_name = next(c["name"] for c in state["companies"] if c["id"] == action["company_id"])
    unscoped = [r for r in state["history_imports"] if r["opportunity_id"] is None and r["employer"].casefold() == company_name.casefold() and r["status"] in {"sent", "uncertain", "bounced"}]
    if unscoped and not action.get("coordination_evidence"): reasons.append("Review unscoped company contact history without promoting it to an application")
    if any(status(r) in {"ready", "dispatching", "uncertain"} for r in related): reasons.append("Coordinate existing ready/dispatching/uncertain outreach first")
    if action["purpose"] == "application" and (history["requires_review"] or any(status(r) == "sent" for r in related)): reasons.append("Reconcile previous application/contact; duplicate application blocked")
    if action["purpose"] != "application" and history["requires_review"] and not action.get("prior_application_acknowledgment"): reasons.append("Acknowledge previous application/contact history and justify this separate outreach")
    if any(status(r) == "sent" for r in related) and not action.get("coordination_evidence"): reasons.append("Further contact needs documented reassignment, failure or approved waiting policy")
    referral_ids = {r["id"] for r in state["referrals"] if r["company_id"] == action["company_id"] and (r["opportunity_id"] == role_id or r.get("employee_contact_id") == contact["id"])}
    legacy_contacts = [r for r in cs.effective_contact_events(state) if r["referral_id"] in referral_ids and r["status"] in {"user_reported_sent", "uncertain"}]
    if any(r["status"] == "uncertain" for r in legacy_contacts): reasons.append("Reconcile uncertain historical personal outreach")
    elif legacy_contacts and not action.get("coordination_evidence"): reasons.append("Review historical personal outreach before another contact")
    return {"allowed": not reasons, "reasons": reasons, "prior_application": history, "related_action_ids": [r["id"] for r in related]}


def diagnostic_due(state, variant_sha256, at):
    cs = api(); when = cs.timestamp(at)
    config = state["report_preferences"].get("deliverability", {})
    days = config.get("interval_days", 7)
    cs.require(type(days) is int and 1 <= days <= 365, "Diagnostic interval must be 1..365 days")
    active = config.get("active_outbound", False)
    reports = [r for r in state.get("outbound_actions", []) if r["kind"] == "diagnostic" and r["inspection"]["variant_sha256"] == variant_sha256 and
               r.get("receiver_report", {}).get("status") == "completed" and cs.timestamp(r["receiver_report"]["at"]) <= when]
    latest = max(reports, key=lambda r: cs.timestamp(r["receiver_report"]["at"]), default=None)
    last = latest["receiver_report"]["at"] if latest else None
    due_at = (cs.timestamp(last) + timedelta(days=days)).isoformat() if last else None
    pending = [r["id"] for r in state.get("outbound_actions", []) if r["kind"] == "diagnostic" and r["inspection"]["variant_sha256"] == variant_sha256 and status(r) in {"ready", "dispatching", "uncertain"}]
    receiver_observations = [r["receiver_report"] for r in state.get("outbound_actions", []) if r["kind"] == "diagnostic" and r["inspection"]["variant_sha256"] == variant_sha256 and r.get("receiver_report", {}).get("receiver_evidence") and r["receiver_report"]["outcome"] in {"pass", "auth_failure", "spam_rejection"} and cs.timestamp(r["receiver_report"]["at"]) <= when]
    latest_observation = max(receiver_observations, key=lambda r: cs.timestamp(r["at"]), default=None)
    affected = latest_observation is not None and latest_observation["outcome"] in {"auth_failure", "spam_rejection"}
    return {"due": bool(active and (last is None or when >= cs.timestamp(due_at))), "reason": "inactive_outbound" if not active else "no_current_representative_test" if not last else "interval_elapsed" if when >= cs.timestamp(due_at) else "current",
            "last_test_at": last, "due_at": due_at, "pending_action_ids": pending, "affected_delivery_paused": affected,
            "mode": config.get("mode", "ask"), "autonomous_while_closed": False, "independent_preparation_allowed": True}


def permission_match(state, action, at):
    cs = api(); when = cs.timestamp(at); matches = []
    for grant in state.get("delivery_permissions", []):
        if not cs.timestamp(grant["valid_from"]) <= when < cs.timestamp(grant["valid_until"]): continue
        if grant.get("revoked_at") and cs.timestamp(grant["revoked_at"]) <= when: continue
        scope = grant["scope"]
        exact = {"kind": action["kind"], "purpose": action["purpose"], "sender": action["inspection"]["sender"], "provider": action["inspection"]["provider"], "service": action["service"], "recipient": action["inspection"]["recipient"]}
        if action["kind"] == "outreach": exact.update(company_id=action["company_id"], opportunity_id=action["opportunity_id"], contact_id=action["contact_id"])
        if any(scope.get(k) != v for k, v in exact.items()): continue
        if scope.get("payload_sha256") != action["inspection"]["payload_sha256"]:
            if grant["mode"] != "standing" or scope.get("variant_sha256") != action["inspection"]["variant_sha256"] or not scope.get("allows_tailored_text"): continue
        if not set(action["data_classes"]) <= set(scope["data_classes"]): continue
        uses = sum(any(e["state"] == "dispatching" for e in r["events"]) and r.get("permission_id") == grant["id"] and not (status(r) == "failed" and r.get("known_not_sent")) for r in state.get("outbound_actions", []))
        if uses < grant["max_uses"]: matches.append(grant["id"])
    return matches


def action_check(state, action, at):
    cs = api(); reasons = []; warnings = list(action["inspection"]["flags"])
    mode = state["report_preferences"].get("deliverability", {}).get("mode", "ask")
    if action["kind"] == "diagnostic" and mode == "local_only": reasons.append("Local-only mode forbids external diagnostic disclosure")
    if action["kind"] == "diagnostic":
        for other in state.get("outbound_actions", []):
            if other["id"] != action["id"] and other["kind"] == "diagnostic" and other["inspection"]["variant_sha256"] == action["inspection"]["variant_sha256"] and status(other) in {"ready", "dispatching", "uncertain"}:
                reasons.append("Existing representative diagnostic claim needs completion/reconciliation")
    if action["kind"] == "outreach":
        contact = contact_guard(state, action["contact_id"], action["opportunity_id"], at)
        reasons.extend(contact["reasons"]); reasons.extend(history_guard(state, action, at)["reasons"])
        due = diagnostic_due(state, action["inspection"]["variant_sha256"], at)
        if due["due"]: warnings.append("Representative external diagnostic is due; independent work may continue")
        auth_reports = [r["receiver_report"] for r in state.get("outbound_actions", []) if r["kind"] == "diagnostic" and r.get("receiver_report", {}).get("receiver_evidence") and r["receiver_report"]["outcome"] in {"pass", "auth_failure"} and cs.timestamp(r["receiver_report"]["at"]) <= cs.timestamp(at) and all(r["inspection"]["variant"][k] == action["inspection"]["variant"][k] for k in ("sender", "provider", "delivery_revision"))]
        latest_auth = max(auth_reports, key=lambda r: cs.timestamp(r["at"]), default=None)
        if latest_auth and latest_auth["outcome"] == "auth_failure": reasons.append("Resolve receiver authentication for this sender/provider/delivery configuration")
        if due["affected_delivery_paused"]: reasons.append("Receiver authentication/systematic spam rejection needs resolution for this variant")
        if action["purpose"] == "cold_introduction" and (action["inspection"]["attachments"] or action["inspection"]["links"]):
            warnings.append("Initial cold introduction normally uses short text without attachments/links; review this intentional exception")
        if action["purpose"] == "follow_up":
            check = action.get("inbound_check", {})
            fresh = check.get("checked_at") and timedelta(0) <= cs.timestamp(at) - cs.timestamp(check["checked_at"]) <= timedelta(minutes=10)
            if not fresh or check.get("coverage") != "complete": reasons.append("Follow-up needs a fresh scoped inbound check or user-attested read-only check")
            replied = any(r["opportunity_id"] == action["opportunity_id"] and r["type"] in {"human_reply", "interview", "offer", "rejection", "withdrawal"} and cs.timestamp(action["events"][0]["at"]) <= cs.timestamp(r["at"]) <= cs.timestamp(at) for r in state["responses"])
            if check.get("obsolete") or replied: reasons.append("Inbound makes this follow-up obsolete; cancel it")
    for previous in state.get("outbound_actions", []):
        if previous["id"] != action["id"] and previous["kind"] == action["kind"] and previous["service"] == action["service"] and previous.get("retry_after") and cs.timestamp(at) < cs.timestamp(previous["retry_after"]): reasons.append("Service retry window/quota has not elapsed")
    return {"allowed": not reasons, "reasons": sorted(set(reasons)), "warnings": warnings,
            "permission_ids": permission_match(state, action, at), "sends_performed": 0}


def _append(state, collection, row):
    result = copy.deepcopy(state); result.setdefault(collection, []).append(copy.deepcopy(row))
    return api().validate(result)


def save_contact(state, row, at, reason):
    cs = api(); result = copy.deepcopy(state)
    before = next((r for r in result.get("employee_contacts", []) if r["id"] == row["id"]), None)
    if before:
        cs.require(all(before[k] == row[k] for k in ("company_id", "person_key", "endpoint", "kind")), "Refresh cannot replace person/channel identity")
        result["employee_contacts"].remove(before)
        row = copy.deepcopy(row)
        row["provenance"] = list({cs.canonical_json(p): p for p in before["provenance"] + row["provenance"]}.values())
    result.setdefault("employee_contacts", []).append(copy.deepcopy(row))
    result["change_history"].append({"operation": "save_contact", "at": at, "reason": reason, "revision_from": state["revision"], "request": {"contact_id": row["id"]}, "before": before, "after": copy.deepcopy(row)})
    return cs.validate(result)


def grant_permission(state, row, user_confirmed):
    cs = api(); cs.require(user_confirmed, "Actual user-confirmed service/data/purpose permission required")
    return _append(state, "delivery_permissions", row)


def prepare_action(state, request, raw, variant):
    cs = api(); action = copy.deepcopy(request); action["inspection"] = inspect_payload(raw, variant)
    at = action.pop("at"); action["events"] = [{"state": "draft", "at": at, "evidence": action["reason"]}]
    action["permission_id"] = None
    for old in state.get("outbound_actions", []):
        if old["idempotency_key"] == action["idempotency_key"]:
            cs.require(old["id"] == action["id"] and {k: v for k, v in old.items() if k not in {"events", "permission_id", "receiver_report", "retry_after", "known_not_sent", "inbound_check"}} == {k: v for k, v in action.items() if k not in {"events", "permission_id"}}, "Idempotency key conflicts with another payload or action")
            return state
    return _append(state, "outbound_actions", action)


def transition(state, action_id, target, at, evidence, permission_id=None, known_not_sent=False, reconciliation=None, inbound_check=None, retry_after=None, raw=None):
    cs = api(); result = copy.deepcopy(state)
    action = next((r for r in result.get("outbound_actions", []) if r["id"] == action_id), None)
    cs.require(action is not None, "Unknown outbound action")
    current = status(action)
    if current == target: return state
    cs.require(target in TRANSITIONS.get(current, set()), "Invalid action transition; unresolved sends never expire into a retry")
    cs.require(cs.timestamp(at) >= cs.timestamp(action["events"][-1]["at"]), "Action transition predates its previous event")
    cs.require(bool(evidence.strip()), "Transition evidence required")
    if inbound_check is not None: action["inbound_check"] = copy.deepcopy(inbound_check)
    if target in {"ready", "dispatching"}:
        check = action_check(result, action, at)
        cs.require(check["allowed"], "; ".join(check["reasons"]))
        if target == "dispatching":
            cs.require(isinstance(raw, bytes) and hashlib.sha256(raw).hexdigest() == action["inspection"]["payload_sha256"], "Dispatch needs readback of the exact inspected payload bytes")
            cs.require(permission_id in check["permission_ids"], "No valid unused permission for this recipient/service/data/payload scope")
            action["permission_id"] = permission_id
    if target == "failed": cs.require(known_not_sent, "Unproved delivery failure must remain uncertain")
    if current == "uncertain": cs.require(reconciliation and reconciliation.strip(), "Provider/history reconciliation is required; a timeout is insufficient")
    if target in {"sent", "failed", "uncertain"}:
        action["known_not_sent"] = bool(known_not_sent)
        if retry_after: action["retry_after"] = retry_after
    action["events"].append({"state": target, "at": at, "evidence": evidence, **({"reconciliation": reconciliation} if reconciliation else {})})
    return cs.validate(result)


def record_report(state, action_id, report):
    cs = api(); result = copy.deepcopy(state)
    action = next((r for r in result.get("outbound_actions", []) if r["id"] == action_id), None)
    cs.require(action is not None, "Unknown diagnostic/report action")
    if status(action) != "sent":
        cs.require(action["kind"] == "diagnostic" and status(action) in {"draft", "ready", "failed"} and report["status"] in {"blocked", "skipped", "unknown"} and report["outcome"] != "pass" and not report["receiver_evidence"] and report["spamassassin_score"] is None and all(v == "unknown" for v in report["authentication"].values()), "Unsent diagnostics can only record honest blocked/skipped/unknown local status")
        if status(action) in {"draft", "ready"}: action["events"].append({"state": "cancelled", "at": report["at"], "evidence": report["evidence"]})
    cs.require(not action.get("receiver_report"), "Preserve the original receiver report; a new test needs its own action")
    action["receiver_report"] = copy.deepcopy(report)
    if action["kind"] == "outreach" and report["outcome"] in {"hard_bounce", "missing_mailbox", "missing_domain"}:
        contact = next(c for c in result["employee_contacts"] if c["id"] == action["contact_id"])
        result.setdefault("contact_suppressions", []).append({"id": "failure-" + action_id, "company_id": action["company_id"], "scope": "endpoint", "value": contact["endpoint"].casefold(), "reason": "hard_bounce", "at": report["at"], "evidence": report["evidence"], "source_ids": action["source_ids"]})
    return cs.validate(result)


def summary(state, at):
    contacts = {c["id"]: c for c in state.get("employee_contacts", [])}
    variants = sorted({a["inspection"]["variant_sha256"] for a in state.get("outbound_actions", [])})
    return {"initial_diagnostic_due": bool(state["report_preferences"].get("deliverability", {}).get("active_outbound", False) and not variants), "diagnostic_cadence": [dict(variant_sha256=v, **diagnostic_due(state, v, at)) for v in variants],
            "representative_payload_known": bool(variants), "active_outbound": state["report_preferences"].get("deliverability", {}).get("active_outbound", False),"at": at, "actions": [{"id": a["id"], "opportunity_id": a.get("opportunity_id"), "kind": a["kind"], "purpose": a["purpose"], "mode": a["mode"], "contact_id": a.get("contact_id"),
              "contact": {k: contacts.get(a.get("contact_id"), {}).get(k) for k in ("public_name", "observed_role", "endpoint", "relevance")},
              "source_urls": [p["url"] for p in contacts.get(a.get("contact_id"), {}).get("provenance", []) if p["url"]],
              "reason": a["reason"], "source_ids": a["source_ids"], "payload_sha256": a["inspection"]["payload_sha256"], "state": status(a), "packet": a.get("application_attempt_id"), "attachments": a["inspection"]["attachments"], "diagnostic_result": a.get("receiver_report"),
              "next_action": "Reconcile provider/history before retry" if status(a) in {"dispatching", "uncertain"} else "Review readiness and permission" if status(a) in {"draft", "ready"} else "Collect actual receiver report" if a["kind"] == "diagnostic" and not a.get("receiver_report") else "Observe actual response; no automatic follow-up"} for a in state.get("outbound_actions", [])],
            "enforcement": "Supported ledger commands enforce guards; Markdown cannot sandbox arbitrary tools or direct file edits", "sends_performed": 0, "autonomous_while_closed": False}


def validate_records(state, index, require, timestamp):
    """Called by the existing state validator; no import cycle or state mutations."""
    contacts = index["employee_contacts"]; endpoints = set(); keys = set()
    for c in contacts.values():
        require(c["company_id"] in index["companies"], "Unknown contact company")
        require(all(i in index["opportunities"] and index["opportunities"][i]["company_id"] == c["company_id"] for i in c["opportunity_ids"]), "Contact relevance must reference exact roles at this company")
        require(timestamp(c["valid_until"]) > timestamp(c["checked_at"]), "Affiliation validity needs a positive bounded interval")
        key = (c["company_id"], c["endpoint"].casefold())
        require(key not in endpoints, "Reuse the existing shared channel identity across opportunities")
        endpoints.add(key)
        require(set(c["confidence"]) == AXES, "Contact confidence requires five independent axes")
        require(all(c["confidence"][k] in {"high", "medium", "low", "unknown"} for k in AXES), "Invalid contact confidence")
        for p in c["provenance"]:
            require(p["source_id"] in index["sources"], "Contact provenance needs a known source")
            require(timestamp(p["checked_at"]) <= timestamp(c["checked_at"]), "Contact evidence postdates the contact check")
            source = index["sources"][p["source_id"]]
            if p["url"] is not None:
                require(source["kind"] == "web" and p["url"] in [source["locator"]] + source.get("original_locators", []), "Contact URL must match its actual source")
            require(any(o["at"] == p["checked_at"] for o in source["observations"]), "Contact evidence needs a dated source observation")
        purposes = {p["purpose"] for p in c["provenance"]}
        require({"identity", "relevance", "address"} <= purposes, "Contact needs identity, relevance and address provenance")
        if c["affiliation"] == "current": require("affiliation" in purposes, "Current affiliation needs source evidence")
        if c["address_provenance"] == "published_professional": require(any(p["purpose"] == "address" and p["url"] for p in c["provenance"]), "Published address requires a professional source URL")
        if c["confidence"]["delivery"] in {"high", "medium"}:
            require(c.get("delivery_evidence") and c.get("delivery_status") == "previous_delivery", "Publication/DNS cannot establish mailbox delivery")
        if c["kind"] == "inferred_address": require(c["address_provenance"] == "inferred", "Guessed address cannot be promoted to published")
    for s in index["contact_suppressions"].values():
        require(s["company_id"] in index["companies"], "Unknown suppressed company")
        require(all(i in index["sources"] for i in s["source_ids"]), "Suppression needs source provenance")
        if s["scope"] == "endpoint": require(s["value"] == s["value"].strip().casefold(), "Suppressed endpoints must use normalized shared-channel identity")
        if s["scope"] == "company": require(s["value"] == s["company_id"], "Company suppression must match its expressed company")
        if s["scope"] == "opportunity": require(index["opportunities"].get(s["value"], {}).get("company_id") == s["company_id"], "Suppression role must belong to its company")
        if s["reason"] == "hard_bounce": require(s["scope"] == "endpoint", "Hard bounce suppresses the failed endpoint, not the person/company")
    for grant in index["delivery_permissions"].values():
        require(timestamp(grant["valid_until"]) > timestamp(grant["valid_from"]), "Permission needs a positive validity interval")
        if grant["mode"] == "one_time": require(grant["max_uses"] == 1 and bool(grant["scope"].get("payload_sha256")), "One-time permission binds one exact payload")
        scope = grant["scope"]
        require(bool(scope.get("payload_sha256") or scope.get("variant_sha256")), "Permission must bind payload or explicitly authorized representative variant")
        if scope["kind"] == "outreach": require(grant["mode"] == "one_time" and scope.get("company_id") in index["companies"] and scope.get("opportunity_id") in index["opportunities"] and scope.get("contact_id") in contacts, "Employer outreach permission is exact and never standing diagnostic permission")
        if grant.get("revoked_at"): require(bool(grant.get("revocation_evidence")), "Revocation needs decision evidence"); require(timestamp(grant["revoked_at"]) >= timestamp(grant["valid_from"]), "Revocation predates permission")
    uses = {}
    for action in index["outbound_actions"].values():
        key = action["idempotency_key"]; require(key not in keys, "Duplicate durable action idempotency key"); keys.add(key)
        events = action["events"]; require(events[0]["state"] == "draft", "Actions must retain their original draft intent")
        for previous, event in zip(events, events[1:]):
            require(event["state"] in TRANSITIONS.get(previous["state"], set()), "Invalid outbound event transition")
            require(timestamp(event["at"]) >= timestamp(previous["at"]), "Outbound events are out of order")
            if previous["state"] == "uncertain": require(bool(event.get("reconciliation")), "Uncertain outcome requires provider/history reconciliation")
        if status(action) == "failed": require(action.get("known_not_sent") is True, "Failure needs evidence that no send occurred")
        inspection = action["inspection"]
        require(inspection["variant_sha256"] == digest({"configuration": inspection["variant"], "structure": inspection["structure"]}), "Representative variant fingerprint differs from declared configuration")
        require(inspection["sender"] == inspection["variant"]["sender"] and inspection["provider"] == inspection["variant"]["provider"], "Inspection sender/provider differs from its variant")
        require(all(i in index["sources"] for i in action["source_ids"]), "Action source provenance is missing")
        require({"message_headers", "message_body"} <= set(action["data_classes"]), "Permission data scope must include actual headers and message body")
        if inspection["attachments"]: require("attachments" in action["data_classes"], "Actual attachments must be included in permission data scope")
        if action.get("application_attempt_id"):
            require(index["application_attempts"].get(action["application_attempt_id"], {}).get("opportunity_id") == action["opportunity_id"], "Outgoing packet must belong to the same exact opportunity")
        if action["kind"] == "diagnostic": require(action["purpose"] == "diagnostic" and action["mode"] == "diagnostic" and all(action.get(k) is None for k in ("company_id", "opportunity_id", "contact_id")), "Diagnostic is never an employer application")
        else:
            require(action["purpose"] != "diagnostic" and action["mode"] != "diagnostic", "Outreach mode/purpose must remain separate from diagnostics")
            contact = contacts.get(action.get("contact_id"), {})
            role = index["opportunities"].get(action.get("opportunity_id"), {})
            require(contact.get("company_id") == action.get("company_id") == role.get("company_id") and bool(contact), "Outreach needs the correct company/person/role")
            expected_mode = {"vacancy": "vacancy", "company_outreach": "company_problem", "contract_project": "paid_project"}[role["kind"]]
            require(action["mode"] == expected_mode, "Outreach mode must preserve advertised vacancy, speculative opportunity or paid project identity")
            require(bool(action["source_ids"]), "Outreach rationale needs source evidence")
            require(inspection["recipient"].casefold() == contact["endpoint"].casefold(), "Actual payload recipient differs from evidenced route")
        dispatched = next((e for e in events if e["state"] == "dispatching"), None)
        if dispatched:
            grant = index["delivery_permissions"].get(action.get("permission_id"))
            require(bool(grant), "Dispatch needs a recorded scoped permission")
            t = timestamp(dispatched["at"]); require(timestamp(grant["valid_from"]) <= t < timestamp(grant["valid_until"]) and (not grant.get("revoked_at") or t < timestamp(grant["revoked_at"])), "Dispatch used invalid/revoked permission")
            scope = grant["scope"]
            required = {"kind": action["kind"], "purpose": action["purpose"], "sender": inspection["sender"], "provider": inspection["provider"], "service": action["service"], "recipient": inspection["recipient"]}
            if action["kind"] == "outreach": required.update({k: action[k] for k in ("company_id", "opportunity_id", "contact_id")})
            require(all(scope.get(k) == v for k, v in required.items()) and set(action["data_classes"]) <= set(scope["data_classes"]), "Dispatch permission scope mismatch")
            require(scope.get("payload_sha256") == inspection["payload_sha256"] or (grant["mode"] == "standing" and scope.get("allows_tailored_text") is True and scope.get("variant_sha256") == inspection["variant_sha256"]), "Permission does not cover these payload bytes/variant")
            uses[grant["id"]] = uses.get(grant["id"], 0) + int(not (status(action) == "failed" and action.get("known_not_sent")))
            require(uses[grant["id"]] <= grant["max_uses"], "Permission usage limit exceeded")
        report = action.get("receiver_report")
        if report:
            require((status(action) == "sent" or (action["kind"] == "diagnostic" and status(action) in {"cancelled", "failed"} and report["status"] in {"blocked", "skipped", "unknown"} and not report["receiver_evidence"] and report["spamassassin_score"] is None and all(v == "unknown" for v in report["authentication"].values()))) and timestamp(report["at"]) >= timestamp(events[-1]["at"]), "Receiver results need confirmed sending; unsent tests must remain explicitly blocked/skipped/unknown")
            require(report["tested_payload_sha256"] == inspection["payload_sha256"] and report["recipient"] == inspection["recipient"], "Receiver evidence must match this exact test payload and recipient")
            require(report["score_interpretation"] == "heuristic_only", "A spam score is never probability or inbox guarantee")
            if report["status"] == "completed": require(report["receiver_evidence"] and report["outcome"] != "unknown", "Completed diagnostic needs actual receiver evidence")
            if report["outcome"] == "pass": require(report["status"] == "completed" and all(report["authentication"].get(k) == "pass" for k in ("spf", "dkim", "dmarc")) and report["spamassassin_score"] is not None and report["threshold"] is not None and report["spamassassin_score"] < report["threshold"], "Passing diagnostics need receiver authentication and a SpamAssassin report")
    linked_attempts = {}
    for attempt in state["attempts"]:
        require(attempt.get("purpose") != "diagnostic", "Diagnostic tests never belong to employer attempts")
        if attempt.get("outbound_action_id"):
            action = index["outbound_actions"].get(attempt["outbound_action_id"], {})
            require(action.get("kind") == "outreach" and action.get("purpose") == "application" and action.get("opportunity_id") == attempt["opportunity_id"] and any(e["state"] == attempt["outcome"] and timestamp(e["at"]) <= timestamp(attempt["at"]) for e in action["events"]), "Application attempt must match the recorded application action outcome")
            previous = linked_attempts.get(action["id"])
            require(previous is None or attempt.get("resolves_attempt_id") == previous, "One application action cannot inflate attempt counts")
            linked_attempts[action["id"]] = attempt["id"]
    config = state["report_preferences"].get("deliverability", {})
    require(type(config.get("interval_days", 7)) is int and 1 <= config.get("interval_days", 7) <= 365, "Diagnostic cadence needs 1..365 days")


def repair_contact_history(state, request, at, user_confirmed):
    cs = api(); cs.require(user_confirmed, "Legacy repair requires actual evidence review, never inferred reconciliation")
    cs.require(request["state_sha256"] == hashlib.sha256(cs.canonical_json(state).encode()).hexdigest(), "Legacy state changed since repair preview")
    cs.require(bool(request["evidence"].strip()), "Reviewed repair evidence/disposition required")
    result = copy.deepcopy(state); row = next((r for r in result["contact_events"] if r["id"] == request["event_id"]), None)
    quarantined = next((r for r in result["profile"].get("contact_history_review", []) if r["event"]["id"] == request["event_id"]), None)
    if row is None and quarantined and request["decision"] == "reconcile":
        row = copy.deepcopy(quarantined["event"]); result["contact_events"].append(row)
        result["profile"]["contact_history_review"].remove(quarantined)
    cs.require(row is not None, "Unknown legacy event; unresolved quarantine needs explicit evidence-backed reconciliation")
    cs.require(cs.timestamp(at) >= cs.timestamp(row["at"]), "Repair predates the reviewed observation")
    cs.require(row["status"] in {"uncertain", "user_reported_sent"}, "Legacy repair is limited to ambiguous sending observations")
    before = copy.deepcopy(row)
    if request["decision"] == "reconcile":
        target = next((r for r in result["contact_events"] if r["id"] == request["uncertain_event_id"]), None)
        cs.require(target and target["status"] == "uncertain", "Select the actual uncertain event supported by the reviewed evidence")
        row.update(status=request["resolved_status"], resolves_contact_event_id=target["id"], occurred_at=target.get("occurred_at", target["at"]), reconciliation_evidence=request["evidence"])
        after = copy.deepcopy(row)
    else:
        cs.require(request["decision"] == "quarantine", "Choose evidence-backed reconciliation or unresolved quarantine")
        result["contact_events"].remove(row)
        after = {"event": before, "reviewed_at": at, "evidence": request["evidence"], "outcome": "unresolved"}
        result["profile"].setdefault("contact_history_review", []).append(after)
    result["change_history"].append({"operation": "repair_contact_history", "at": at, "reason": request["evidence"], "revision_from": state["revision"], "request": copy.deepcopy(request), "before": before, "after": after})
    return cs.validate(result)


def main(argv=None):
    cs = api(); parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect"); inspect.add_argument("payload"); inspect.add_argument("variant")
    for name in ("contact", "suppress", "grant", "revoke", "prepare", "transition", "receiver-report", "check", "contact-check", "due", "summary", "audit", "repair-preview", "repair-contact-history"):
        p = sub.add_parser(name); p.add_argument("state"); p.add_argument("--at", required=True)
        if name in {"contact", "suppress", "grant", "prepare", "transition", "receiver-report", "repair-contact-history"}: p.add_argument("request")
        if name in {"contact", "suppress", "grant", "revoke", "prepare", "transition", "receiver-report", "repair-contact-history"}: p.add_argument("--expected-revision", required=True, type=int)
        if name in {"prepare", "transition"}: p.add_argument("--payload", required=name == "prepare")
        if name == "prepare": p.add_argument("--variant", required=True)
        if name in {"grant", "revoke", "suppress", "repair-contact-history"}: p.add_argument("--user-confirmed", action="store_true")
        if name == "contact": p.add_argument("--reason", required=True)
        if name in {"revoke", "check", "contact-check", "receiver-report"}: p.add_argument("--id", required=True)
        if name == "contact-check": p.add_argument("--opportunity-id", required=True)
        if name == "revoke": p.add_argument("--reason", required=True)
        if name == "due": p.add_argument("--variant-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect": result = inspect_payload(Path(args.payload).read_bytes(), cs.load_json(args.variant))
        elif args.command in {"check", "contact-check", "due", "summary", "audit", "repair-preview"}:
            state = cs.read_contact_review_state(args.state) if args.command in {"audit", "repair-preview"} else cs.read_state(args.state)
            if args.command == "check":
                action = next((a for a in state.get("outbound_actions", []) if a["id"] == args.id), None)
                cs.require(action is not None, "Unknown action"); result = action_check(state, action, args.at)
            elif args.command == "contact-check": result = contact_guard(state, args.id, args.opportunity_id, args.at)
            elif args.command == "due": result = diagnostic_due(state, args.variant_sha256, args.at)
            else:
                result = summary(state, args.at)
                if args.command in {"audit", "repair-preview"}:
                    legacy = [a["id"] for a in state["attempts"] if cs.is_email_channel(a["channel"]) and not a.get("outbound_action_id")]
                    result["unlinked_legacy_email_attempts"] = legacy
                    result["unlinked_legacy_contact_events"] = [e["id"] for e in state["contact_events"] if not e.get("outbound_action_id")]
                    result["invalid_contact_action_links"] = cs.contact_action_link_issues(state)
                    result["quarantined_contact_ids"] = [r["event"]["id"] for r in state["profile"].get("contact_history_review", [])]
                    try: cs.validate(state); result["legacy_validation_error"] = None
                    except cs.Invalid as error: result["legacy_validation_error"] = str(error)
                    result["state_sha256"] = hashlib.sha256(cs.canonical_json(state).encode()).hexdigest()
                    result["audit_complete"] = not legacy and not result["unlinked_legacy_contact_events"] and not result["invalid_contact_action_links"] and not result["quarantined_contact_ids"] and not result["legacy_validation_error"]
        else:
            request = cs.load_json(args.request) if hasattr(args, "request") else None
            def transform(state):
                if args.command == "repair-contact-history": return repair_contact_history(state, request, args.at, args.user_confirmed)
                if args.command == "contact": return save_contact(state, request, args.at, args.reason)
                if args.command == "grant": return grant_permission(state, request, args.user_confirmed)
                if args.command == "suppress":
                    cs.require(args.user_confirmed, "Suppression needs an actual observed/confirmed decision")
                    return _append(state, "contact_suppressions", request)
                if args.command == "revoke":
                    cs.require(args.user_confirmed, "Actual permission withdrawal required")
                    result = copy.deepcopy(state); grant = next(g for g in result.get("delivery_permissions", []) if g["id"] == args.id)
                    grant["revoked_at"] = args.at; grant["revocation_evidence"] = args.reason; return cs.validate(result)
                if args.command == "prepare": return prepare_action(state, {**request, "at": args.at}, Path(args.payload).read_bytes(), cs.load_json(args.variant))
                if args.command == "receiver-report": return record_report(state, args.id, request)
                return transition(state, at=args.at, raw=Path(args.payload).read_bytes() if args.payload else None, **request)
            updated = cs.transact(args.state, transform, args.expected_revision, _reader=cs.read_contact_review_state if args.command == "repair-contact-history" else None)
            result = {"revision": updated["revision"], "valid": True, "sends_performed": 0,
                      "dispatch_claimed": args.command == "transition" and request.get("target") == "dispatching" and updated["revision"] != args.expected_revision}
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)); return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration) as error:
        print("Error: " + str(error), file=sys.stderr); return 2


if __name__ == "__main__":
    sys.exit(api().run_cli(main))
