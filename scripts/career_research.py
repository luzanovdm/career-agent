#!/usr/bin/env python3
"""Private, disposable validation receipts for the read-only research permission gate."""

import copy
import hashlib
import hmac
import json
import os
from pathlib import Path
import stat
import tempfile


LOADED_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
FORMAT = 1
LIMIT = 2 * 1024 * 1024


def engine_signature(cs):
    root = Path(__file__).resolve().parents[1]
    expected = {"scripts/career_state.py": cs.VALIDATOR_SOURCE_SHA256,
                "scripts/career_research.py": LOADED_SOURCE_SHA256,
                "scripts/career_outreach.py": cs.outreach_owner().source_sha256}
    digest = hashlib.sha256()
    for name in ("scripts/career_state.py", "scripts/career_research.py", "scripts/career_outreach.py", "references/state.schema.json"):
        raw = (root / name).read_bytes()
        if name in expected and hashlib.sha256(raw).hexdigest() != expected[name]:
            raise ValueError("Validator source changed since import; reload before checking research")
        if name.endswith("state.schema.json") and _encoded(cs.state_schema()) != _encoded(cs.strict_json_loads(raw.decode("utf-8"))):
            raise ValueError("Validator schema changed since import; reload before checking research")
        digest.update(name.encode()); digest.update(raw)
    return digest.hexdigest()


def identity(path):
    value = path.lstat()
    if not stat.S_ISREG(value.st_mode): raise ValueError("Research state must be a regular, nonsymlink file")
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def writer_active(path):
    lock = path.with_name(path.name + ".lock")
    return lock.exists() or lock.is_symlink()


def _owned_private(value):
    return not value.st_mode & 0o077 and (not hasattr(os, "getuid") or value.st_uid == os.getuid())


def _read_private(path, limit):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or not _owned_private(info): raise ValueError("Untrusted research cache file")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if (info.st_dev, info.st_ino) != (opened.st_dev, opened.st_ino): raise ValueError("Research cache changed while opening")
        raw = handle.read(limit + 1)
    if len(raw) > limit: raise ValueError("Research cache exceeds its metadata limit")
    return raw


def _cache_context(cache_dir):
    if os.name != "posix": return None
    uid = str(os.getuid()) if hasattr(os, "getuid") else "local"
    directory = Path(cache_dir) if cache_dir is not None else Path(tempfile.gettempdir()) / ("career-agent-research-cache-" + uid)
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or not _owned_private(info): return None
        key_path = directory / "receipt.key"
        try:
            descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(os.urandom(32)); handle.flush(); os.fsync(handle.fileno())
        except FileExistsError:
            pass
        key = _read_private(key_path, 32)
        return (directory, key) if len(key) == 32 else None
    except (OSError, ValueError):
        return None


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _cached(path, context, cs):
    try:
        raw = _read_private(path, LIMIT)
        row = cs.strict_json_loads(raw.decode("utf-8"))
        if set(row) != {"payload", "mac"} or not isinstance(row["mac"], str): return None
        mac = hmac.new(context[1], _encoded(row["payload"]), hashlib.sha256).hexdigest()
        return row["payload"] if hmac.compare_digest(row["mac"], mac) else None
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        return None


def _save(path, context, payload):
    if path.is_symlink(): return
    temporary = None
    try:
        row = {"payload": payload, "mac": hmac.new(context[1], _encoded(payload), hashlib.sha256).hexdigest()}
        raw = _encoded(row)
        if len(raw) > LIMIT: return
        descriptor, temporary = tempfile.mkstemp(prefix=".research-receipt-", dir=context[0])
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    except (OSError, ValueError):
        pass
    finally:
        if temporary and os.path.exists(temporary): os.unlink(temporary)


def research_check(path, cs, context_id=None, at=None, cache_dir=None, use_cache=True):
    """Reuse validation only; every call re-evaluates the live context and current time."""
    path = Path(path).expanduser().absolute()
    # Resolve ancestors for profile identity, but do not accept a symlink state file.
    cs.require(not path.is_symlink(), "Research state cannot be a symlink")
    path = path.resolve(); before = identity(path)
    cs.require(not writer_active(path), "Research state is being written; recheck a fresh snapshot")
    engine = engine_signature(cs); context = _cache_context(cache_dir) if use_cache else None
    path_key = hashlib.sha256(str(path).encode()).hexdigest()
    cache_path = context[0] / (path_key + ".json") if context else None
    proof = _cached(cache_path, context, cs) if context else None
    expected = {"format": FORMAT, "path_sha256": path_key, "state_identity": before, "engine_sha256": engine}
    hit = isinstance(proof, dict) and set(proof) == set(expected) | {"revision", "state_sha256", "gate"} and all(proof.get(k) == v for k, v in expected.items())
    if hit:
        gate = proof["gate"]; revision = proof["revision"]
    else:
        # One strict load and one complete validation; no resume/material binaries are opened.
        raw = path.read_bytes()
        cs.require(identity(path) == before and not writer_active(path), "Research state changed while reading")
        state = cs.strict_json_loads(raw.decode("utf-8")); cs.validate(state)
        gate = {"control": copy.deepcopy(state["control"]), "profile": {"selected_directions": copy.deepcopy(state["profile"]["selected_directions"])}, "search_config": {"search_setup": copy.deepcopy(state["search_config"].get("search_setup", {}))}}
        revision = state["revision"]
        proof = {**expected, "revision": revision, "state_sha256": hashlib.sha256(raw).hexdigest(), "gate": gate}
    result = cs._research_decision(gate, context_id, at)
    cs.require(identity(path) == before and not writer_active(path) and engine_signature(cs) == engine,
               "Research state or validator changed during the check; recheck the current revision")
    if context and not hit: _save(cache_path, context, proof)
    # Cache publication is not a permission lease: a concurrent pause/revision still wins.
    cs.require(identity(path) == before and not writer_active(path), "Research state changed before returning permission")
    return {**result, "state_revision": revision, "validation_cache": "hit" if hit else "miss" if context else "unavailable",
            "material_files_verified": False}
