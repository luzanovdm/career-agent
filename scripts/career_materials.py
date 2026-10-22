#!/usr/bin/env python3
"""Agent-operated immutable material library and exact application-attempt layout."""

import argparse
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile

import career_state as cs


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def component(label, stable_id):
    readable = re.sub(r"[^a-z0-9]+", "-", label.casefold()).strip("-")[:24] or "item"
    return readable + "--" + sha256(stable_id.encode())[:20]


def inside(workspace, relative):
    workspace = cs.private_path(workspace).resolve()
    part = PurePosixPath(relative)
    cs.require(not part.is_absolute() and part.parts and ".." not in part.parts and "\\" not in relative,
               "Managed path must be a portable relative path")
    target = workspace.joinpath(*part.parts)
    resolved = target.resolve()
    cs.require(workspace in resolved.parents, "Managed path or symlink escapes the private workspace")
    return target


def write_new_or_same(path, content, mode=0o600):
    if path.exists() or path.is_symlink():
        cs.require(not path.is_symlink() and path.is_file() and path.read_bytes() == content,
                   "Existing managed file differs; preserve it and review the conflict")
        return
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(path, mode)


def identity_directory(workspace, relative, kind, identifier):
    path = inside(workspace, relative)
    marker = path / ".identity.json"
    payload = (cs.canonical_json({"kind": kind, "id": identifier}) + "\n").encode()
    if path.exists():
        cs.require(marker.is_file() and not marker.is_symlink() and marker.read_bytes() == payload,
                   "Directory identity collision or unmanaged existing folder; preserve and review")
    else:
        path.mkdir(mode=0o700, parents=True)
        write_new_or_same(marker, payload)
    return path


def material_file(workspace, material):
    path = inside(workspace, material["path"])
    cs.require(not path.is_symlink() and path.is_file(), "Central material must be a real immutable file")
    cs.require(sha256(path.read_bytes()) == material["sha256"], "Material content hash changed; do not use it")
    return path


def register_material(state_path, workspace, request, input_path, expected_revision):
    workspace = cs.private_path(workspace).resolve()
    cs.require(workspace in Path(state_path).resolve().parents, "State must belong to the chosen private workspace")
    raw = Path(input_path).read_bytes()
    digest = sha256(raw)
    suffix = Path(input_path).suffix.lower()
    cs.require(suffix in {".pdf", ".docx", ".txt", ".md", ".html"}, "Unsupported material file type")
    record = {**request, "path": "Materials/objects/" + digest + suffix, "sha256": digest}
    # Source development does not create a candidate workspace; callers explicitly choose one.
    def update(state):
        existing = next((r for r in state["materials"] if r["id"] == record["id"]), None)
        if existing:
            cs.require(cs.canonical_json(existing) == cs.canonical_json(record), "Immutable material ID already has another version/content")
            material_file(workspace, existing)
            return state
        if record["kind"] == "resume" and record["visibility"] == "external" and state.get("achievement_evidence"):
            import career_achievements as achievements
            text = raw.decode("utf-8") if suffix in {".md", ".txt"} else record.get("extracted_text")
            cs.require(isinstance(text, str) and text.strip(), "Readable resume text required for source adaptation audit")
            achievements.require_resume_audit(state, text, record)
        candidate = cs.add_record(state, "materials", record)
        destination = inside(workspace, record["path"])
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        write_new_or_same(destination, raw, mode=0o400)
        return candidate
    return cs.transact(state_path, update, expected_revision)


def prepare_attempt(state_path, workspace, request, expected_revision, symlink=os.symlink):
    cs.require(isinstance(request.get("materials"), list) and bool(request["materials"]),
               "Prepared application attempt requires at least one selected material")
    workspace = cs.private_path(workspace).resolve()
    cs.require(workspace in Path(state_path).resolve().parents, "State must belong to the chosen private workspace")
    def update(state):
        role = next((r for r in state["opportunities"] if r["id"] == request["opportunity_id"]), None)
        cs.require(role is not None, "Unknown exact role")
        company = next(r for r in state["companies"] if r["id"] == role["company_id"])
        existing = next((r for r in state["application_attempts"] if r["id"] == request["id"]), None)
        if existing:
            desired = [(r["slot"], r["material_id"]) for r in request["materials"]]
            cs.require(existing["opportunity_id"] == role["id"] and desired ==
                       [(r["slot"], r["material_id"]) for r in existing["materials"]],
                       "Attempt already pins other materials; create a new attempt instead")
            verify_attempt(state, workspace, existing)
            return state
        cs.require(not cs.reapplication_guard(state, role["id"])["requires_review"] or request.get("history_review_evidence"),
                   "Prior sent/uncertain/bounced history requires review before preparing another attempt")
        company_relative = "Applications/" + component(company["name"], company["id"])
        role_relative = company_relative + "/" + component(role["title"], role["id"])
        attempt_relative = role_relative + "/Attempts/" + component(request["label"], request["id"])
        materials = {r["id"]: r for r in state["materials"]}
        pins = []
        slots = set()
        for selection in request["materials"]:
            slot = cs.validate_slot(selection["slot"])
            cs.require(re.fullmatch(r"[a-z][a-z0-9-]{0,39}", slot) is not None and slot not in slots,
                       "Use distinct safe material slots such as resume or cover-letter")
            slots.add(slot)
            material = materials.get(selection["material_id"])
            cs.require(material is not None and not material.get("review_required"), "Selected material needs review")
            if material["visibility"] == "external":
                cs._confirmed_claims(material, "fact_ids", {r["id"]: r for r in state["facts"]})
                cs._credential_claims({**material, "at": request["at"]}, {r["id"]: r for r in state["credentials"]})
            target = material_file(workspace, material)
            pins.append({"slot": slot, "material_id": material["id"], "sha256": material["sha256"],
                         "version": material["version"], "link_path": attempt_relative + "/" + slot + target.suffix,
                         "reference_path": attempt_relative + "/" + slot + ".material.json", "link_mode": "reference"})
        record = {"id": request["id"], "opportunity_id": role["id"], "label": request["label"],
                  "at": request["at"], "path": attempt_relative, "materials": pins}
        cs.add_record(state, "application_attempts", record)
        identity_directory(workspace, company_relative, "company", company["id"])
        identity_directory(workspace, role_relative, "opportunity", role["id"])
        folder = identity_directory(workspace, attempt_relative, "application_attempt", request["id"])
        for name in ("Letters", "Forms", "Evidence", "Correspondence"):
            inside(workspace, attempt_relative + "/" + name).mkdir(mode=0o700, exist_ok=True)
        inside(workspace, role_relative + "/Research").mkdir(mode=0o700, exist_ok=True)
        for pin in pins:
            material = materials[pin["material_id"]]
            target = material_file(workspace, material)
            link = inside(workspace, pin["link_path"])
            relative_target = os.path.relpath(target, folder)
            if link.is_symlink():
                cs.require(link.resolve() == target.resolve() and not Path(os.readlink(link)).is_absolute(), "Existing link has another target")
                pin["link_mode"] = "symlink"
            elif link.exists():
                raise cs.Invalid("Do not replace an existing attempt document")
            else:
                try:
                    symlink(relative_target, link)
                    pin["link_mode"] = "symlink"
                except OSError as error:
                    if error.errno not in {errno.EPERM, errno.EACCES, errno.ENOSYS, errno.ENOTSUP, errno.EOPNOTSUPP}:
                        raise
                    # A portable reference is the fallback; never copy another binary silently.
            reference = {"material_id": pin["material_id"], "version": pin["version"], "sha256": pin["sha256"],
                         "relative_target": relative_target.replace(os.sep, "/"), "link_mode": pin["link_mode"]}
            write_new_or_same(inside(workspace, pin["reference_path"]), (cs.canonical_json(reference) + "\n").encode())
        write_new_or_same(folder / "attempt.json", (cs.canonical_json(record) + "\n").encode())
        return cs.add_record(state, "application_attempts", record)
    return cs.transact(state_path, update, expected_revision)


def verify_attempt(state, workspace, attempt):
    cs.require(bool(attempt["materials"]), "Prepared application attempt requires materials")
    materials = {r["id"]: r for r in state["materials"]}
    for pin in attempt["materials"]:
        cs.validate_slot(pin["slot"])
        material = materials[pin["material_id"]]
        target = material_file(workspace, material)
        reference_path = inside(workspace, pin["reference_path"])
        cs.require(not reference_path.is_symlink(), "Material reference must not be a symlink")
        reference = cs.load_json(reference_path)
        cs.require(reference["sha256"] == pin["sha256"] and reference["material_id"] == pin["material_id"] and
                   reference["version"] == pin["version"] and reference["link_mode"] == pin["link_mode"],
                   "Attempt reference differs from its pinned material")
        relative = Path(reference["relative_target"])
        cs.require(not relative.is_absolute() and (reference_path.parent / relative).resolve() == target.resolve(),
                   "Portable reference escapes or resolves to another material")
        link = inside(workspace, pin["link_path"])
        if pin["link_mode"] == "symlink":
            cs.require(link.is_symlink() and not Path(os.readlink(link)).is_absolute() and link.resolve() == target.resolve(),
                       "Attempt symlink differs from its immutable material")
        else:
            cs.require(not link.exists() and not link.is_symlink(), "Unexpected binary at a reference-only slot")
    return True


def package_attempt(state, workspace, attempt_id, slots, destination, as_of):
    cs.validate(state)
    destination = cs.private_path(destination)
    attempt = next((r for r in state["application_attempts"] if r["id"] == attempt_id), None)
    cs.require(attempt is not None, "Unknown application attempt")
    cs.require(isinstance(slots, list) and bool(slots), "Explicit selected slots are required")
    for slot in slots:
        cs.validate_slot(slot)
    cs.require(len(slots) == len(set(slots)), "Explicit distinct selected slots are required")
    verify_attempt(state, workspace, attempt)
    pins = {r["slot"]: r for r in attempt["materials"]}
    cs.require(all(slot in pins for slot in slots), "Unknown selected material slot")
    materials = {r["id"]: r for r in state["materials"]}
    selected = []
    for slot in slots:
        pin = pins[slot]
        material = materials[pin["material_id"]]
        cs.require(material["visibility"] == "external" and not material.get("review_required"), "Private or flagged material cannot enter an outgoing package")
        cs._confirmed_claims(material, "fact_ids", {r["id"]: r for r in state["facts"]})
        cs._credential_claims({**material, "at": as_of}, {r["id"]: r for r in state["credentials"]})
        path = material_file(workspace, material)
        raw = path.read_bytes()
        cs.require(sha256(raw) == pin["sha256"], "Pinned material changed during packaging")
        member_name = cs.validate_slot(slot) + path.suffix
        cs.require(PurePosixPath(member_name).name == member_name and "\\" not in member_name, "Package member must be a flat safe filename")
        selected.append((member_name, raw, {"slot": slot, "material_id": material["id"], "version": pin["version"], "sha256": pin["sha256"]}))
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        with zipfile.ZipFile(handle, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, raw, pin in selected:
                archive.writestr(name, raw)
            archive.writestr("manifest.json", json.dumps({"application_attempt_id": attempt_id, "materials": [row[2] for row in selected]}, indent=2))
    return {"path": str(destination), "selected_slots": slots, "uploaded": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("register", "prepare-attempt", "verify-attempt", "package-attempt"))
    parser.add_argument("state")
    parser.add_argument("workspace")
    parser.add_argument("record", help="Agent-prepared request JSON, or application-attempt ID for verify/package")
    parser.add_argument("--input")
    parser.add_argument("--expected-revision", type=int)
    parser.add_argument("--slot", action="append")
    parser.add_argument("--output")
    parser.add_argument("--as-of")
    args = parser.parse_args()
    try:
        if args.command in {"register", "prepare-attempt"}:
            cs.require(args.expected_revision is not None, "Expected state revision required")
            request = cs.load_json(args.record)
            if args.command == "register":
                cs.require(bool(args.input), "Explicit source file required")
                state = register_material(args.state, args.workspace, request, args.input, args.expected_revision)
            else:
                state = prepare_attempt(args.state, args.workspace, request, args.expected_revision)
            result = {"revision": state["revision"], "valid": True}
        else:
            state = cs.read_state(args.state)
            if args.command == "verify-attempt":
                attempt = next((r for r in state["application_attempts"] if r["id"] == args.record), None)
                cs.require(attempt is not None, "Unknown application attempt")
                result = {"valid": verify_attempt(state, args.workspace, attempt)}
            else:
                cs.require(bool(args.output) and bool(args.as_of), "Selected output and date required")
                result = package_attempt(state, args.workspace, args.record, args.slot, args.output, args.as_of)
        print(json.dumps(result, indent=2))
        return 0
    except (cs.Invalid, OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        print("Error: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
