#!/usr/bin/env python3
"""Build a self-contained local skill bundle from a fixed source allowlist; no installation/network."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

import career_updates as updates


SOURCE = Path(__file__).resolve().parents[1]
HELPERS = ("career_state.py", "career_snapshot.py", "career_materials.py", "career_search.py", "career_achievements.py", "career_updates.py", "career_portal.py", "check_resume_render.py")
REFERENCES = ("profile.md", "discovery.md", "packets.md", "tracking.md", "interviews.md",
              "history-import.md", "research-tools.md", "materials.md", "records.md", "interaction.md", "context-enrichment.md", "host-capabilities.md", "search-cases.md", "achievement-adaptation.md", "updates.md", "portal.md")


class CompiledAssets:
    """Static template bytes in an already supported updater payload path."""
    def __init__(self, assets): self.data = ("# Generated from the fixed data-free portal templates.\nASSETS = " + repr(assets) + "\n").encode("utf-8")
    def read_bytes(self): return self.data
    def is_symlink(self): return False
    def is_file(self): return True


def payload_sources():
    core = SOURCE / "skills/career-agent"
    files = {"SKILL.md": core / "SKILL.md", "LICENSE": core / "LICENSE"}
    files.update({"references/" + name: core / "references" / name for name in REFERENCES})
    files.update({"scripts/" + name: SOURCE / "scripts" / name for name in HELPERS})
    files.update({"references/" + name: SOURCE / "references" / name for name in ("state.schema.json", "state-format.md")})
    template_files = {name: SOURCE / "templates/portal" / name for name in ("index.html", "style.css", "app.js")}
    if any(p.is_symlink() or not p.is_file() for p in template_files.values()): raise ValueError("Fixed portal templates must be regular source files")
    files["scripts/career_portal_assets.py"] = CompiledAssets({name: p.read_text(encoding="utf-8") for name, p in template_files.items()})
    for path in files.values():
        if path.is_symlink() or not path.is_file(): raise ValueError("Bundle sources must be regular allowlisted files")
    return files


def write_release(number, changes):
    updates.version(number)
    row = {"descriptor_version": 1, "release": {"version": number, "tag": "v" + number, "repository": updates.REPOSITORY,
           "state_schema_versions": [1]}, "changes": changes,
           "files": {name: updates.digest(path.read_bytes()) for name, path in payload_sources().items()}}
    updates.descriptor(row)
    (SOURCE / "release.json").write_text(json.dumps(row, indent=2) + "\n")
    return {"descriptor": str(SOURCE / "release.json"), "version": number}


def build(destination):
    destination = Path(destination)
    if destination.exists() or destination.is_symlink(): raise ValueError("Bundle output must be absent; existing content is never overwritten")
    sources = payload_sources()
    release = updates.descriptor(updates.cs.load_json(SOURCE / "release.json"))
    files = {name: updates.digest(path.read_bytes()) for name, path in sources.items()}
    if files != release["files"]: raise ValueError("Release descriptor is stale; maintainer must refresh it after payload edits")
    destination.mkdir(mode=0o755, parents=True)
    for name, source in sources.items():
        target = destination / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(source.read_bytes())
    (destination / "BUNDLE.json").write_text(json.dumps({"bundle_version": 1, "release": release["release"], "files": files}, indent=2) + "\n")
    return {"bundle": str(destination), "files": len(files) + 1, "version": release["release"]["version"]}


def archive_bundle(bundle, output):
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(Path(bundle).rglob("*")):
            if path.is_file():
                info = zipfile.ZipInfo("career-agent/" + path.relative_to(bundle).as_posix(), (1980, 1, 1, 0, 0, 0))
                info.external_attr = 0o100644 << 16; info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, path.read_bytes())



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", nargs="?")
    parser.add_argument("--write-release", action="store_true")
    parser.add_argument("--version")
    parser.add_argument("--change", action="append", default=[])
    parser.add_argument("--zip", dest="archive")
    args = parser.parse_args()
    try:
        if args.write_release:
            result = write_release(args.version, args.change)
        else:
            if not args.destination: raise ValueError("Choose an absent bundle output directory")
            result = build(args.destination)
            if args.archive: archive_bundle(args.destination, args.archive); result["archive"] = args.archive
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print("Error: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
