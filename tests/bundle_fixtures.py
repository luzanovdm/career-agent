"""Isolated pre-1.0 helper fixtures. Never a user runtime or forward-evaluation bundle."""
from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))


@contextmanager
def legacy_source():
    import build_skill_bundle as builder
    with tempfile.TemporaryDirectory(prefix='career-legacy-helper-fixture-') as directory:
        source=Path(directory)
        for name in ('skills','scripts','references','templates'):
            shutil.copytree(ROOT/name,source/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        (source/'skills/career-agent/SKILL.md').write_text('---\nname: career-agent\ndescription: Fictional legacy helper regression fixture; not for user installation.\n---\n\nOnly deterministic pre-1.0 helper invariants are under test.\n')
        with mock.patch.object(builder,'SOURCE',source):builder.write_release('0.3.0',['Fictional legacy helper regression fixture; never publish.'])
        yield source


def legacy_bundle_cli(destination):
    with legacy_source() as source:
        return subprocess.run([sys.executable,'-B',str(source/'scripts/build_skill_bundle.py'),str(destination)],capture_output=True,text=True)


def legacy_bundle(destination):
    import build_skill_bundle as builder
    with legacy_source() as source:
        with mock.patch.object(builder,'SOURCE',source):builder.build(destination)
        return json.loads((source/'release.json').read_text())
