#!/usr/bin/env python3
"""Agent-operated, dependency-free private XLSX/CSV snapshots. Never a state database."""

import argparse
from datetime import datetime, timezone
import hashlib
import csv
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import quote, urlsplit
import xml.etree.ElementTree as ET
import zipfile

import career_state as cs

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
ET.register_namespace("", NS)
ET.register_namespace("r", REL)
HEADERS = ["Employer", "Role", "Direction", "Fit / open questions", "Pay as observed", "Application stage",
           "Latest response", "Next action", "Action date", "Role status / date", "Posting", "Document versions"]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def clean(value):
    text = str(value) if value is not None else "Unknown"
    text = "".join(char for char in text if char in "\n\t\r" or 0x20 <= ord(char) <= 0xD7FF or
                   0xE000 <= ord(char) <= 0xFFFD or 0x10000 <= ord(char) <= 0x10FFFF)
    if len(text) > 32700:
        text = text[:32650] + " [truncated; see private state]"
    return text


def safe_link(value, workspace, document=False):
    try:
        if document:
            path = Path(value)
            if not path.is_absolute():
                path = workspace / path
            path = path.resolve()
            if workspace.resolve() not in path.parents or path.suffix.lower() not in {".pdf", ".docx", ".txt", ".md", ".html"}:
                return None
            return quote(os.path.relpath(path, workspace).replace(os.sep, "/"), safe="/")
        if clean(value) != value or any(ord(char) < 32 for char in value):
            return None
        return cs.canonical_url(value) if urlsplit(value).scheme in {"http", "https"} else None
    except (ValueError, TypeError, cs.Invalid):
        return None


def view_data(state, workspace, as_of):
    report = cs.stats(state, as_of)
    when = cs.timestamp(as_of)
    companies = {row["id"]: row for row in state["companies"]}
    sends = [a for a in cs.effective_sends(state) if a["occurred"] <= when]
    rows, metadata = [], []
    for role in state["opportunities"]:
        identifier = role["id"]
        artifacts = [a for a in state["artifacts"] if a["opportunity_id"] == identifier and cs.timestamp(a["at"]) <= when]
        application_attempts = [a for a in state["application_attempts"] if a["opportunity_id"] == identifier and cs.timestamp(a["at"]) <= when]
        sent = [a for a in sends if a["opportunity_id"] == identifier]
        responses = sorted([r for r in state["responses"] if r["opportunity_id"] == identifier and cs.timestamp(r["at"]) <= when],
                           key=lambda row: cs.timestamp(row["at"]))
        imported = [r for r in state["history_imports"] if r["opportunity_id"] == identifier]
        stage = "Not applied"
        if artifacts or application_attempts:
            stage = "Prepared"
        if any(a.get("review_required") for a in artifacts):
            stage = "Prepared: review required"
        if sent:
            stage = "Sent (confirmed report/evidence)"
        elif imported:
            stage = "History: " + ", ".join(sorted({r["status"] for r in imported})) + " (reported/observed)"
        roots = [a for a in state["attempts"] if a["opportunity_id"] == identifier and not a.get("resolves_attempt_id") and
                 cs.action_time(a, {r["id"]: r for r in state["attempts"]}) <= when]
        if roots:
            latest = max(roots, key=lambda a: cs.action_time(a, {r["id"]: r for r in state["attempts"]}))
            reconciled = next((a for a in state["attempts"] if a.get("resolves_attempt_id") == latest["id"]), latest)
            if reconciled["outcome"] == "uncertain":
                stage = "Submission uncertain: reconcile"
            elif reconciled["outcome"] == "not_sent":
                stage = "Not sent (confirmed)"
            else:
                stage = "Sent (confirmed report/evidence)"
                relevant = [r for r in responses if r["type"] != "rejected_before_application" and
                            cs.response_attempt(r, cs.effective_sends(state)) == latest["id"]]
                meaningful = [r for r in relevant if r["type"] != "auto_receipt"]
                if meaningful:
                    stage = meaningful[-1]["type"].replace("_", " ")
            latest_action = cs.action_time(latest, {r["id"]: r for r in state["attempts"]})
            if reconciled["outcome"] != "uncertain" and application_attempts and max(cs.timestamp(a["at"]) for a in application_attempts) > latest_action:
                stage = "Prepared next attempt; prior action recorded"
        elif responses:
            stage = responses[-1]["type"].replace("_", " ")
        saved_cases = [c for c in state.get("search_cases", []) if c["opportunity_id"] == identifier and c["phase"] == "saved"]
        if saved_cases and not roots:
            import career_search
            assessment = career_search.readiness(state, saved_cases[-1])
            stage = ("Company outreach prospect: " if role["kind"] == "company_outreach" else "Saved review package: ") + assessment["status"].replace("_", " ")
        guard = cs.reapplication_guard(state, identifier)
        next_action = role.get("next_action", "Reconcile history before reapplying" if guard["requires_review"] else "Choose next step in chat")
        observed = max(role["status_observations"], key=lambda item: cs.timestamp(item["at"]))
        materials = {m["id"]: m for m in state["materials"]}
        pinned = [(a, pin, materials[pin["material_id"]]) for a in application_attempts for pin in a["materials"]]
        documents = "; ".join(f"{a['kind']} v{a['version']}: {a['path']}" for a in artifacts) or "None prepared"
        if pinned:
            documents = "; ".join(f"{a['label']} / {pin['slot']} v{pin['version']}: {material['path']}" for a, pin, material in pinned)
        values = [companies[role["company_id"]]["name"], role["title"], role.get("direction", "Not selected"),
                  role.get("fit_summary", "Assessment pending"), role.get("pay_summary", "Unknown"), stage,
                  responses[-1]["type"].replace("_", " ") if responses else "No observed response",
                  next_action, max((a["occurred"] for a in sent), default="Unknown / not sent"),
                  ("Not an advertised opening" if role["kind"] == "company_outreach" else observed["status"]) + " / " + observed["at"], role["role_url"], documents]
        links = {10: safe_link(role["role_url"], workspace)}
        # A cell can have one hyperlink. All version paths remain readable in the cell/metadata.
        if artifacts:
            links[11] = safe_link(artifacts[-1]["path"], workspace, document=True)
        if pinned:
            links[11] = safe_link(pinned[-1][2]["path"], workspace, document=True)
        rows.append({"values": [clean(value) for value in values], "links": links})
        metadata.append([identifier, role["company_id"], ", ".join(role["source_ids"]),
                         ", ".join(a["id"] for a in artifacts), ", ".join(r["id"] for r in imported),
                         "Review required" if any(a.get("review_required") for a in artifacts) else "No flagged claims"])
        for a, pin, material in pinned:
            metadata.append({"values": [material["id"], a["id"], material["kind"], "v" + str(pin["version"]), material["path"], pin["sha256"]],
                             "links": {4: safe_link(material["path"], workspace, document=True)}})
        for artifact in artifacts:
            metadata.append({"values": [artifact["id"], identifier, artifact["kind"],
                                       "v" + str(artifact["version"]), artifact["path"],
                                       "Review required" if artifact.get("review_required") else artifact["status"]],
                             "links": {4: safe_link(artifact["path"], workspace, document=True)}})
    return report, rows, metadata


def column(index):
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def sheet_xml(title, subtitle, summary, headers, rows, metadata=False):
    root = ET.Element("{" + NS + "}worksheet")
    views = ET.SubElement(root, "sheetViews")
    view = ET.SubElement(views, "sheetView", workbookViewId="0")
    ET.SubElement(view, "pane", xSplit="0" if metadata else "2", ySplit="5", topLeftCell="A6" if metadata else "C6",
                  activePane="bottomLeft" if metadata else "bottomRight", state="frozen")
    columns = ET.SubElement(root, "cols")
    widths = [30, 32, 24, 32, 22, 32, 26, 36, 28, 32, 42, 48] if not metadata else [32, 36, 42, 42, 42, 35]
    for position in range(len(headers)):
        ET.SubElement(columns, "col", min=str(position + 1), max=str(position + 1), width=str(widths[position]), customWidth="1")
    data = ET.SubElement(root, "sheetData")
    all_rows = [[title], [subtitle], [summary], [], headers] + [row["values"] for row in rows]
    for number, values in enumerate(all_rows, start=1):
        row_element = ET.SubElement(data, "row", r=str(number), ht="30" if number == 1 else "48" if number in {2, 3} or number > 5 else "28", customHeight="1")
        for position, value in enumerate(values, start=1):
            style = 1 if number == 1 else 2 if number == 5 else 3 if number % 2 == 0 else 0
            if not metadata and number > 5 and position == 6:
                stage = str(value).lower()
                style = 5 if "bounce" in stage or "review required" in stage else 4 if "sent" in stage and "history" not in stage else style
            cell = ET.SubElement(row_element, "c", r=column(position) + str(number), t="inlineStr", s=str(style))
            inline = ET.SubElement(cell, "is")
            ET.SubElement(inline, "t", {"{http://www.w3.org/XML/1998/namespace}space": "preserve"}).text = clean(value)
    ET.SubElement(root, "autoFilter", ref="A5:" + column(len(headers)) + str(max(len(all_rows), 5)))
    merges = ET.SubElement(root, "mergeCells", count="3")
    for number in range(1, 4):
        ET.SubElement(merges, "mergeCell", ref="A" + str(number) + ":" + column(len(headers)) + str(number))
    relationships = ET.Element("Relationships", xmlns=PKG)
    hyperlinks = ET.SubElement(root, "hyperlinks")
    for number, row in enumerate(rows, start=6):
        for position, target in row.get("links", {}).items():
            if target:
                rel_id = "rId" + str(len(relationships) + 1)
                ET.SubElement(hyperlinks, "hyperlink", ref=column(position + 1) + str(number), attrib={"{" + REL + "}id": rel_id})
                ET.SubElement(relationships, "Relationship", Id=rel_id, Type=REL + "/hyperlink", Target=target, TargetMode="External")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), ET.tostring(relationships, encoding="utf-8", xml_declaration=True)


def xlsx_bytes(rows, metadata_rows, marker, summary):
    output = io.BytesIO()
    meta = [row if isinstance(row, dict) else {"values": row, "links": {}} for row in metadata_rows]
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        archive.writestr("_rels/.rels", '<Relationships xmlns="' + PKG + '"><Relationship Id="rId1" Type="' + REL + '/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr("xl/workbook.xml", '<workbook xmlns="' + NS + '" xmlns:r="' + REL + '"><sheets><sheet name="Applications" sheetId="1" r:id="rId1"/><sheet name="Metadata" sheetId="2" r:id="rId2"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="' + PKG + '"><Relationship Id="rId1" Type="' + REL + '/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="' + REL + '/worksheet" Target="worksheets/sheet2.xml"/><Relationship Id="rId3" Type="' + REL + '/styles" Target="styles.xml"/></Relationships>')
        styles = '<styleSheet xmlns="' + NS + '"><fonts count="3"><font><sz val="11"/><name val="Calibri"/><color rgb="FF213047"/></font><font><b/><sz val="20"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/><color rgb="FFFFFFFF"/></font></fonts><fills count="6"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF213047"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF0F4F8"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFE5F2E9"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFBEDE5"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="6">'
        for font, fill in ((0, 0), (1, 0), (2, 2), (0, 3), (0, 4), (0, 5)):
            styles += f'<xf numFmtId="0" fontId="{font}" fillId="{fill}" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
        styles += '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'
        archive.writestr("xl/styles.xml", styles)
        for number, (title, headers, data) in enumerate((("Career applications", HEADERS, rows),
               ("Snapshot metadata", ["Key / role ID", "Value / company ID", "Source IDs", "Artifact IDs", "Imported observations", "Review flags"], meta)), start=1):
            xml, relationships = sheet_xml(title, marker, summary, headers, data, metadata=number == 2)
            archive.writestr(f"xl/worksheets/sheet{number}.xml", xml)
            archive.writestr(f"xl/worksheets/_rels/sheet{number}.xml.rels", relationships)
    return output.getvalue()


def csv_literal(value):
    text = clean(value)
    # Quoting alone does not prevent spreadsheet formula interpretation.
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def csv_bytes(rows, marker, summary, state_hash):
    output = io.StringIO(newline="")
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    data = [["Career applications"], [marker], [summary], ["State SHA-256", state_hash], [], HEADERS]
    data.extend(row["values"] for row in rows)
    for values in data:
        writer.writerow([csv_literal(value) for value in values])
    return output.getvalue().encode("utf-8-sig")


def snapshot_status(state_path, workspace, format="xlsx"):
    cs.require(format in {"xlsx", "csv"}, "Unsupported snapshot format")
    state_path, workspace = Path(state_path), cs.private_path(workspace)
    cs.require(workspace.resolve() in state_path.resolve().parents, "Snapshot state must belong to the chosen workspace")
    target = workspace / ("Career." + format)
    index_path = workspace / "Data" / "report-index.json"
    index = cs.load_json(index_path) if index_path.exists() else {}
    previous = index.get(target.name)
    exists = target.exists()
    changed = exists and (not previous or digest(target.read_bytes()) != previous["sha256"])
    stale = not previous or previous["state_sha256"] != digest(state_path.read_bytes())
    return {"path": str(target), "exists": exists, "manual_change": changed, "stale": stale,
            "exported_revision": previous["state_revision"] if previous else None,
            "current_revision": cs.read_state(state_path)["revision"]}


def atomic_bytes(path, content):
    descriptor, temporary = tempfile.mkstemp(prefix=".career-view-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def export_snapshot(state_path, workspace, as_of, format="xlsx"):
    cs.require(format in {"xlsx", "csv"}, "Unsupported snapshot format")
    workspace = cs.private_path(workspace)
    workspace.mkdir(mode=0o700, parents=True, exist_ok=True)
    data_directory = workspace / "Data"
    cs.require(not data_directory.is_symlink(), "Snapshot metadata directory must not be a symlink")
    data_directory.mkdir(mode=0o700, exist_ok=True)
    lock = data_directory / "report-index.json.lock"
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.close(descriptor)
        state_path = Path(state_path)
        state_raw = state_path.read_bytes()
        state = cs.validate(cs.strict_json_loads(state_raw))
        status = snapshot_status(state_path, workspace, format)
        if status["manual_change"]:
            return {**status, "written": False, "action": "Keep the edited copy; ask the user to reconcile changes before refreshing"}
        target = Path(status["path"])
        cs.require(not target.is_symlink(), "Snapshot must not be a symlink")
        report, rows, meta = view_data(state, workspace, as_of)
        exported_at = datetime.now(timezone.utc).isoformat()
        marker = f"GENERATED SNAPSHOT | state revision {state['revision']} | exported {exported_at} | events through {as_of}. Ask the agent for changes; this view does not edit state."
        counts = report["counts"]
        counted_unit = "cases" if counts["company_outreach_cases"] else "roles"
        response_summary = (f"Hiring responses: {report['hiring_response_rate']['numerator']} / {report['hiring_response_rate']['denominator']} sent {counted_unit}"
                            if report["hiring_response_rate"]["denominator"] else f"Hiring response rate unavailable: no confirmed-sent {counted_unit}")
        inventory_label = "unique application cases" if counts["company_outreach_cases"] else "unique roles"
        summary = f"{counts['opportunities']} {inventory_label} | {counts['prepared_roles']} prepared | {counts['sent_roles']} confirmed-sent {counted_unit}. {response_summary}. History observations and threads are not extra applications."
        meta = [["State revision", str(state["revision"]), "Schema version", str(state["schema_version"]), "Export time", exported_at],
                ["State SHA-256", digest(state_raw), "State file", str(state_path), "Evidence cutoff", report["evidence_as_of"]],
                ["View contract", "Generated snapshot; ask the agent for edits", "Manual edits", "Never silently overwritten", "Privacy", "No secrets or full email bodies"], *meta]
        content = xlsx_bytes(rows, meta, marker, summary) if format == "xlsx" else csv_bytes(rows, marker, summary, digest(state_raw))
        cs.require(digest(state_path.read_bytes()) == digest(state_raw), "State changed during export; retry with current revision")
        if target.exists():
            cs.require(digest(target.read_bytes()) == cs.load_json(data_directory / "report-index.json")[target.name]["sha256"], "View changed during export; preserve it")
            backups = workspace / "Backups" / "Views"
            cs.require(not backups.is_symlink() and not backups.parent.is_symlink(), "View backup directory must not be a symlink")
            backups.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd, backup = tempfile.mkstemp(prefix=target.stem + "-", suffix=target.suffix, dir=backups)
            with os.fdopen(fd, "wb") as handle:
                handle.write(target.read_bytes())
        atomic_bytes(target, content)
        index_path = data_directory / "report-index.json"
        index = cs.load_json(index_path) if index_path.exists() else {}
        index[target.name] = {"sha256": digest(content), "state_revision": state["revision"],
                              "state_sha256": digest(state_raw), "exported_at": exported_at, "as_of": as_of}
        atomic_bytes(index_path, (json.dumps(index, indent=2) + "\n").encode())
        return {"path": str(target), "written": True, "state_revision": state["revision"], "sha256": digest(content)}
    finally:
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("export", "status"))
    parser.add_argument("state")
    parser.add_argument("workspace")
    parser.add_argument("--format", choices=("xlsx", "csv"), default="xlsx")
    parser.add_argument("--as-of")
    args = parser.parse_args()
    try:
        if args.command == "export":
            cs.require(bool(args.as_of), "Snapshot export requires an event cutoff")
            result = export_snapshot(args.state, args.workspace, args.as_of, args.format)
        else:
            result = snapshot_status(args.state, args.workspace, args.format)
        print(json.dumps(result, indent=2))
        return 3 if result.get("manual_change") else 0
    except (cs.Invalid, OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        print("Error: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
