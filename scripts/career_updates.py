#!/usr/bin/env python3
"""Opt-in release maintenance: public metadata, verified bundles and recoverable local replacement."""
import argparse
import ast
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid
import zipfile

import career_state as cs

REPOSITORY = "https://github.com/luzanovdm/career-agent"
RAW = "https://raw.githubusercontent.com/luzanovdm/career-agent/"
LATEST = RAW + "main/release.json"
DAY = 86400
LIMIT = 8 * 1024 * 1024
REQUIRED = {"SKILL.md", "LICENSE", "scripts/career_state.py", "scripts/career_updates.py", "references/state.schema.json", "references/state-format.md"}


def digest(raw): return hashlib.sha256(raw).hexdigest()
def encoded(value): return (cs.canonical_json(value) + "\n").encode()


def version(value):
    cs.require(isinstance(value, str) and re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", value), "Invalid release version")
    return tuple(map(int, value.split(".")))


def payload_path(value):
    cs.require(isinstance(value, str) and (value in {"SKILL.md", "LICENSE"} or re.fullmatch(r"scripts/[a-z][a-z0-9_-]*\.py|references/[a-z][a-z0-9_.-]*\.(?:md|json)", value)), "Invalid declared skill payload path")
    cs.require(".." not in value and "\\" not in value, "Unsafe payload path")
    return value


def file_map(value):
    cs.require(isinstance(value, dict) and 1 <= len(value) <= 200, "Invalid payload manifest")
    for name, sha in value.items():
        payload_path(name)
        cs.require(isinstance(sha, str) and re.fullmatch(r"[a-f0-9]{64}", sha), "Invalid payload digest")
    return value


def release_identity(row):
    cs.require(isinstance(row, dict) and set(row) == {"version", "tag", "repository", "state_schema_versions"}, "Invalid release identity")
    version(row["version"])
    cs.require(row["tag"] == "v" + row["version"] and row["repository"] == REPOSITORY, "Untrusted release origin/ref")
    schemas = row["state_schema_versions"]
    cs.require(isinstance(schemas, list) and schemas and all(type(n) is int and n > 0 for n in schemas) and len(schemas) == len(set(schemas)), "Invalid supported state schemas")
    return row


def descriptor(row):
    cs.require(isinstance(row, dict) and set(row) == {"descriptor_version", "release", "changes", "files"} and type(row["descriptor_version"]) is int and row["descriptor_version"] == 1, "Unsupported release descriptor")
    release_identity(row["release"]); file_map(row["files"])
    cs.require(REQUIRED <= set(row["files"]), "Incomplete release payload")
    cs.require(isinstance(row["changes"], list) and 1 <= len(row["changes"]) <= 20 and all(isinstance(s, str) and 0 < len(s) <= 500 for s in row["changes"]), "Invalid release changes")
    return row


def bundle(row):
    cs.require(isinstance(row, dict) and set(row) <= {"bundle_version", "release", "files"} and type(row.get("bundle_version")) is int and row["bundle_version"] == 1, "Unsupported bundle manifest")
    file_map(row.get("files"))
    if "release" in row: release_identity(row["release"])
    cs.require({"SKILL.md", "LICENSE"} <= set(row["files"]), "Not a managed career-agent bundle")
    return row


def managed(root, relative):
    cs.require(relative == "BUNDLE.json" or payload_path(relative), "Unsafe managed file")
    path = root / relative
    for part in [path, *path.parents]:
        if part == root.parent: break
        cs.require(not part.is_symlink(), "Symlink in managed path: " + relative)
    return path


def cache_root(path=None):
    root = Path(path or Path.home() / ".cache/career-agent/updates")
    cs.require(not root.is_symlink(), "Cache cannot be a symlink")
    root = root.resolve(); root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root


def local_install(path):
    root = Path(path)
    cs.require(root.is_dir() and not root.is_symlink(), "Choose an existing regular skill installation")
    root = root.resolve()
    manifest = bundle(cs.load_json(managed(root, "BUNDLE.json")))
    return root, manifest


def atomic(path, raw, mode=0o600):
    cs.require(not path.is_symlink(), "Refuse symlink destination")
    fd, temporary = tempfile.mkstemp(prefix=".career-update-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        os.chmod(temporary, mode); os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def asset_url(number):
    version(number)
    return REPOSITORY + "/releases/download/v" + number + "/career-agent.zip"


def fetch(url, limit):
    """Only fixed GitHub metadata/assets; redirects cannot select another code origin."""
    allowed = url == LATEST or (url.startswith(RAW) and re.fullmatch(r"v\d+\.\d+\.\d+/release\.json", url[len(RAW):])) or re.fullmatch(re.escape(REPOSITORY) + r"/releases/download/v\d+\.\d+\.\d+/career-agent\.zip", url)
    cs.require(allowed, "Untrusted download origin")
    class Redirects(HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            target = urlsplit(newurl)
            cs.require(url == asset_url(url.split("/v")[-1].split("/")[0]) and target.scheme == "https" and target.hostname in {"release-assets.githubusercontent.com", "objects.githubusercontent.com"} and not target.username and not target.password and target.port in {None, 443}, "Untrusted asset redirect")
            return super().redirect_request(request, fp, code, msg, headers, newurl)
    with build_opener(Redirects()).open(Request(url, headers={"User-Agent": "career-agent-update"}), timeout=15) as response:
        data = response.read(limit + 1)
    cs.require(len(data) <= limit, "Download exceeds size limit")
    return data


def check(install, cache=None, force=False, now=None, transport=fetch):
    """Failures are cached too; none prevent the ordinary career workflow."""
    now = time.time() if now is None else now
    try:
        root, current = local_install(install); store = cache_root(cache)
        cs.require(store != root and root not in store.parents, "Keep update cache outside the installed skill")
        path = store / "check.json"
        cs.require(not path.is_symlink(), "Unsafe update cache")
        saved = {}
        if path.exists() and not force:
            try:
                saved = cs.load_json(path)
                cs.require(isinstance(saved, dict) and type(saved.get("checked_at")) in {int, float}, "Invalid disposable cache")
                if set(saved) == {"checked_at", "descriptor"}: descriptor(saved["descriptor"])
                else: cs.require(set(saved) == {"checked_at", "error"} and isinstance(saved["error"], str), "Invalid disposable cache")
            except (OSError, ValueError, TypeError, KeyError, RecursionError): saved = {}
        recent = type(saved.get("checked_at")) in {int, float} and 0 <= now - saved["checked_at"] < DAY
        cached = recent and not force
        if not cached:
            try:
                remote = descriptor(cs.strict_json_loads(transport(LATEST, 256 * 1024)))
                saved = {"checked_at": now, "descriptor": remote}
            except (OSError, ValueError, TypeError, RecursionError) as error:
                saved = {"checked_at": now, "error": str(error)}
            atomic(path, encoded(saved))
        if saved.get("error"):
            return {"status": "unavailable", "cached": cached, "checked_at": saved["checked_at"], "error": saved["error"], "normal_use_allowed": True}
        remote = descriptor(saved["descriptor"]); latest = remote["release"]["version"]
        installed = current.get("release", {}).get("version")
        status = "bootstrap_required" if installed is None else "available" if version(latest) > version(installed) else "current" if latest == installed else "installed_ahead"
        if latest == installed and remote["files"] != current["files"]: status = "release_conflict"
        return {"status": status, "installed_version": installed, "available_version": latest, "cached": cached,
                "checked_at": saved["checked_at"], "changes": remote["changes"], "descriptor_sha256": digest(encoded(remote)),
                "download_url": asset_url(latest), "normal_use_allowed": True}
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        return {"status": "unavailable", "error": str(error), "normal_use_allowed": True}


def verified_download(number, expected, transport=fetch):
    version(number); cs.require(re.fullmatch(r"[a-f0-9]{64}", expected or ""), "Pin the approved descriptor digest")
    release = descriptor(cs.strict_json_loads(transport(RAW + "v" + number + "/release.json", 256 * 1024)))
    cs.require(release["release"]["version"] == number and digest(encoded(release)) == expected, "Release changed since approval; check again")
    raw = transport(asset_url(number), LIMIT)
    cs.require(len(raw) <= LIMIT, "Bundle exceeds size limit")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist(); names = [m.filename for m in members]
        cs.require(len(names) == len(set(names)) and len(names) <= 400, "Duplicate or oversized archive directory")
        expected_names = {"career-agent/" + name for name in release["files"]} | {"career-agent/BUNDLE.json"}
        actual = set()
        for member in members:
            name = member.filename
            cs.require(not PurePosixPath(name).is_absolute() and ".." not in PurePosixPath(name).parts and "\\" not in name and not (member.flag_bits & 1), "Unsafe archive path/encryption")
            cs.require(stat.S_IFMT(member.external_attr >> 16) in {0, stat.S_IFREG, stat.S_IFDIR}, "Archive links/devices are forbidden")
            if not member.is_dir(): actual.add(name)
            else: cs.require(name in {"career-agent/", "career-agent/scripts/", "career-agent/references/"}, "Unexpected archive directory")
            cs.require(member.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED} and member.file_size <= 2 * 1024 * 1024, "Unsupported/oversized archive member")
        cs.require(actual == expected_names and sum(m.file_size for m in members) <= LIMIT, "Archive differs from declared payload")
        payload = {name: archive.read("career-agent/" + name) for name in release["files"]}
        manifest_raw = archive.read("career-agent/BUNDLE.json"); manifest = bundle(cs.strict_json_loads(manifest_raw))
    cs.require(manifest == {"bundle_version": 1, "release": release["release"], "files": release["files"]}, "Bundle identity differs from approved release")
    for name, content in payload.items():
        cs.require(digest(content) == release["files"][name], "Payload digest mismatch: " + name)
        if name.endswith(".py"): ast.parse(content.decode("utf-8"))  # Parse only; never import downloaded code.
    cs.require(re.search(r"(?m)^name: career-agent\s*$", payload["SKILL.md"].decode()), "Wrong skill entrypoint")
    schema = cs.strict_json_loads(payload["references/state.schema.json"])
    schema_number = schema.get("properties", {}).get("schema_version", {}).get("const")
    cs.require(type(schema_number) is int and schema_number in release["release"]["state_schema_versions"], "Schema and release compatibility differ")
    return release, payload, manifest_raw, raw


def preflight(root, current, new):
    for folder in {root, *(managed(root, name).parent for name in current["files"])}:
        cs.require(os.access(folder, os.W_OK | os.X_OK), "Installation is read-only; use the verified bundle download")
    modified = []
    for name, sha in current["files"].items():
        path = managed(root, name)
        if not path.is_file() or digest(path.read_bytes()) != sha: modified.append(name)
    cs.require(not modified, "Local edits/missing managed files preserved: " + ", ".join(modified))
    for name in set(new["files"]) - set(current["files"]):
        path = managed(root, name)
        cs.require(not path.exists(), "Unmanaged file collision preserved: " + name)


def compatible(root, current, release, states):
    schemas = current.get("release", {}).get("state_schema_versions")
    if not schemas:
        schema = cs.load_json(managed(root, "references/state.schema.json"))
        old = schema.get("properties", {}).get("schema_version", {}).get("const")
        cs.require(type(old) is int, "Legacy schema unknown; cannot safely update")
        schemas = [old]
    supported = release["release"]["state_schema_versions"]
    cs.require(set(schemas) <= set(supported), "Release drops installed schema compatibility; no automatic migration")
    for state in states:
        path = Path(state)
        cs.require(not path.is_symlink() and not path.with_name(path.name + ".lock").exists(), "Private state is linked or currently locked")
        number = cs.load_json(path).get("schema_version")
        cs.require(type(number) is int and number in supported, "Private state schema is incompatible; files were not changed")


def journal_path(store, root): return store / ("transaction-" + digest(str(root).encode()) + ".json")


def rollback(root, store, record):
    cs.require(record.get("format") == 1 and record.get("root") == str(root) and re.fullmatch(r"job-[a-f0-9]{32}", record.get("job", "")), "Unsafe recovery journal")
    old, new = bundle(record["old"]), bundle(record["new"])
    backup = store / record["job"] / "backup"
    cs.require(not (store / record["job"]).is_symlink() and not backup.is_symlink(), "Unsafe backup ancestors")
    for name in set(old["files"]) | set(new["files"]) | {"BUNDLE.json"}:
        path = managed(root, name)
        if path.exists():
            known = {old["files"].get(name), new["files"].get(name)} if name != "BUNDLE.json" else {record["old_bundle_sha256"], record["new_bundle_sha256"]}
            cs.require(path.is_file() and digest(path.read_bytes()) in known, "Concurrent local change preserved; recovery needs review: " + name)
    for name, sha in {**old["files"], "BUNDLE.json": record["old_bundle_sha256"]}.items():
        source = managed(backup, name); cs.require(source.is_file() and digest(source.read_bytes()) == sha, "Backup is missing or modified")
    for name in old["files"]:
        path = managed(root, name)
        if path.is_file() and digest(path.read_bytes()) == old["files"][name]: continue
        path.parent.mkdir(parents=True, exist_ok=True); atomic(path, managed(backup, name).read_bytes(), 0o644)
    for name in set(new["files"]) - set(old["files"]): managed(root, name).unlink(missing_ok=True)
    manifest_path = managed(root, "BUNDLE.json")
    if not manifest_path.is_file() or digest(manifest_path.read_bytes()) != record["old_bundle_sha256"]:
        atomic(manifest_path, managed(backup, "BUNDLE.json").read_bytes(), 0o644)


def recover(install, cache=None, approved=False, idle=False):
    cs.require(approved and idle, "Recovery needs approval and an idle host operation")
    root = Path(install); cs.require(root.is_dir() and not root.is_symlink(), "Unsafe install root"); root = root.resolve()
    store = cache_root(cache); cs.require(store != root and root not in store.parents, "Keep update cache outside the installed skill")
    path = journal_path(store, root); cs.require(not path.is_symlink(), "Unsafe recovery journal")
    record = cs.load_json(path)
    cs.require(record.get("format") == 1 and record.get("root") == str(root) and re.fullmatch(r"job-[a-f0-9]{32}", record.get("job", "")), "Unsafe recovery journal")
    cs.require(record.get("phase") in {"replacing", "committed", "rolled_back"}, "No recoverable update transaction")
    with cs.skill_operation(root, exclusive=True, recovery=True) as lease:
        lease["retain"] = True
        preserved_committed = record["phase"] == "committed"
        if record["phase"] == "replacing":
            rollback(root, store, record); record["phase"] = "rolled_back"; atomic(path, encoded(record))
        else:
            side = "new" if preserved_committed else "old"
            expected = bundle(record[side])
            manifest_path = managed(root, "BUNDLE.json")
            cs.require(digest(manifest_path.read_bytes()) == record[side + "_bundle_sha256"] and cs.load_json(manifest_path) == expected, "Completed transaction manifest changed; preserve local files")
            for name, sha in expected["files"].items():
                current = managed(root, name)
                cs.require(current.is_file() and digest(current.read_bytes()) == sha, "Completed transaction payload changed; preserve local files: " + name)
        lease["retain"] = False
    return {"recovered": True, "preserved_committed": preserved_committed, "backup": str(store / record["job"] / "backup")}


def apply(install, number, expected, cache=None, approved=False, idle=False, states=(), transport=fetch, replace_hook=None):
    cs.require(approved and idle, "Update requires user approval and an idle host operation")
    root, current = local_install(install); store = cache_root(cache)
    cs.require(store != root and root not in store.parents, "Keep update cache outside the installed skill")
    path = journal_path(store, root)
    cs.require(not path.is_symlink(), "Unsafe transaction journal")
    previous = cs.load_json(path) if path.exists() else {}
    cs.require(previous.get("phase") != "replacing", "Interrupted update requires recovery before replacement")
    cs.require("release" in current, "Unversioned bundle needs a reviewed bootstrap; use the verified download route")
    cs.require(version(number) > version(current["release"]["version"]), "Install only a newer approved release")
    with cs.skill_operation(root, exclusive=True) as lease:
        baseline = descriptor(cs.strict_json_loads(transport(RAW + current["release"]["tag"] + "/release.json", 256 * 1024)))
        cs.require(baseline["release"] == current["release"] and baseline["files"] == current["files"], "Installed manifest differs from its published release; local changes preserved")
        release, payload, manifest_raw, _ = verified_download(number, expected, transport)
        compatible(root, current, release, states); preflight(root, current, release)
        job = store / ("job-" + uuid.uuid4().hex); backup = job / "backup"; backup.mkdir(mode=0o700, parents=True)
        for name in [*current["files"], "BUNDLE.json"]:
            target = managed(backup, name); target.parent.mkdir(parents=True, exist_ok=True); atomic(target, managed(root, name).read_bytes())
        new = bundle(cs.strict_json_loads(manifest_raw))
        record = {"format": 1, "root": str(root), "job": job.name, "phase": "replacing", "old": current, "new": new,
                  "old_bundle_sha256": digest(managed(root, "BUNDLE.json").read_bytes()), "new_bundle_sha256": digest(manifest_raw)}
        atomic(path, encoded(record))
        lease["retain"] = True
        try:
            for index, (name, content) in enumerate(payload.items()):
                target = managed(root, name)
                if name in current["files"]:
                    cs.require(target.is_file() and digest(target.read_bytes()) == current["files"][name], "Concurrent local change preserved: " + name)
                else: cs.require(not target.exists(), "Concurrent unmanaged collision preserved: " + name)
                target.parent.mkdir(parents=True, exist_ok=True); atomic(target, content, 0o644)
                if replace_hook: replace_hook(index, name)
            for name in set(current["files"]) - set(payload):
                old = managed(root, name); cs.require(old.is_file() and digest(old.read_bytes()) == current["files"][name], "Concurrent retired-file change preserved")
                old.unlink()
            atomic(managed(root, "BUNDLE.json"), manifest_raw, 0o644)
            for name, sha in new["files"].items(): cs.require(digest(managed(root, name).read_bytes()) == sha, "Installed hash verification failed")
            record["phase"] = "committed"; atomic(path, encoded(record)); lease["retain"] = False
        except Exception:
            rollback(root, store, record); record["phase"] = "rolled_back"; atomic(path, encoded(record)); lease["retain"] = False; raise
    return {"updated": True, "version": number, "backup": str(backup), "restart_or_reload_required": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "apply", "recover", "download"))
    parser.add_argument("--install", default=str(Path(__file__).resolve().parents[1])); parser.add_argument("--cache-dir")
    parser.add_argument("--force", action="store_true", help="Explicit fresh check; ordinary invocations reuse the daily cache")
    parser.add_argument("--version"); parser.add_argument("--descriptor-sha256"); parser.add_argument("--output")
    parser.add_argument("--approved", action="store_true"); parser.add_argument("--idle-confirmed", action="store_true")
    parser.add_argument("--state", action="append", default=[])
    args = parser.parse_args()
    try:
        if args.command == "check": result = check(args.install, args.cache_dir, args.force)
        elif args.command == "recover": result = recover(args.install, args.cache_dir, args.approved, args.idle_confirmed)
        elif args.command == "apply": result = apply(args.install, args.version, args.descriptor_sha256, args.cache_dir, args.approved, args.idle_confirmed, args.state)
        else:
            cs.require(args.output, "Choose a new bundle download path")
            _, _, _, raw = verified_download(args.version, args.descriptor_sha256)
            with open(args.output, "xb") as handle: handle.write(raw)
            result = {"downloaded": True, "verified": True, "path": args.output}
        print(json.dumps(result, indent=2)); return 0
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile, SyntaxError, RecursionError) as error:
        print("Error: " + str(error), file=sys.stderr); return 2


if __name__ == "__main__": sys.exit(main())
