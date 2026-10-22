#!/usr/bin/env python3
"""Build a self-contained local skill bundle from a fixed source allowlist; no installation/network."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys


SOURCE = Path(__file__).resolve().parents[1]
HELPERS = ("career_state.py", "career_snapshot.py", "career_materials.py", "career_search.py", "career_achievements.py")
REFERENCES = ("profile.md", "discovery.md", "packets.md", "tracking.md", "interviews.md",
              "history-import.md", "research-tools.md", "materials.md", "records.md", "interaction.md", "context-enrichment.md", "host-capabilities.md", "search-cases.md", "achievement-adaptation.md")


def build(destination):
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Bundle output must be absent; existing content is never overwritten")
    core = SOURCE / "skills/career-agent"
    destination.mkdir(mode=0o755, parents=True)
    selected = [core / "SKILL.md", core / "LICENSE", *(core / "references" / name for name in REFERENCES)]
    for source in selected:
        if source.is_symlink() or not source.is_file():
            raise ValueError("Bundle sources must be regular allowlisted files")
        target = destination / source.relative_to(core)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    for name in HELPERS:
        if (SOURCE / "scripts" / name).is_symlink() or not (SOURCE / "scripts" / name).is_file():
            raise ValueError("Bundle helper must be a regular allowlisted file")
        target = destination / "scripts" / name
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(SOURCE / "scripts" / name, target)
    for name in ("state.schema.json", "state-format.md"):
        if (SOURCE / "references" / name).is_symlink() or not (SOURCE / "references" / name).is_file():
            raise ValueError("Bundle schema/reference must be a regular allowlisted file")
        shutil.copyfile(SOURCE / "references" / name, destination / "references" / name)
    files = {str(path.relative_to(destination)): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted(destination.rglob("*")) if path.is_file()}
    (destination / "BUNDLE.json").write_text(json.dumps({"bundle_version": 1, "files": files}, indent=2) + "\n")
    return {"bundle": str(destination), "files": len(files) + 1}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination")
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.destination), indent=2))
        return 0
    except (OSError, ValueError) as error:
        print("Error: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
