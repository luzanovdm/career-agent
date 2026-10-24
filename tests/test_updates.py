"""Synthetic release/cache/transaction tests; no network or candidate material."""
from bundle_fixtures import legacy_bundle

import copy
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import subprocess
import warnings
import zipfile

from test_state import ROOT
sys.path.insert(0, str(ROOT / "scripts"))
import career_updates as updates
cs = updates.cs


def release(number="0.2.0", schemas=None, extra=None):
    payload={"SKILL.md":b"---\nname: career-agent\ndescription: Synthetic release fixture.\n---\n", "LICENSE":b"Synthetic license fixture.\n",
             "scripts/career_state.py":b"VALUE = 1\n", "scripts/career_updates.py":b"VALUE = 2\n",
             "references/state.schema.json":json.dumps({"properties":{"schema_version":{"const":(schemas or [1])[0]}}}).encode(),
             "references/state-format.md":b"Synthetic state format.\n", "references/notes.md":number.encode()}
    payload.update(extra or {})
    row={"descriptor_version":1,"release":{"version":number,"tag":"v"+number,"repository":updates.REPOSITORY,"state_schema_versions":schemas or [1]},
         "changes":["Synthetic release changes."],"files":{k:updates.digest(v) for k,v in payload.items()}}
    manifest={"bundle_version":1,"release":row["release"],"files":row["files"]}
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,"w",compression=zipfile.ZIP_DEFLATED) as archive:
        for name,raw in {**payload,"BUNDLE.json":updates.encoded(manifest)}.items():archive.writestr("career-agent/"+name,raw)
    return row,payload,stream.getvalue()


def install(root,number="0.1.0",legacy=False):
    row,payload,_=release(number)
    if legacy:payload.pop("scripts/career_updates.py")
    for name,raw in payload.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    manifest={"bundle_version":1,"files":{k:updates.digest(v) for k,v in payload.items()}}
    if not legacy:manifest["release"]=row["release"]
    (root/"BUNDLE.json").write_bytes(updates.encoded(manifest))
    return manifest


def transport(row,archive,old=None):
    baseline=release("0.1.0")[0] if old is None else {"descriptor_version":1,"release":old["release"],"files":old["files"],"changes":["Synthetic prior release."]}
    def fetch(url,limit):
        if url==updates.RAW+baseline["release"]["tag"]+"/release.json":return updates.encoded(baseline)
        return archive if url.endswith(".zip") else updates.encoded(row)
    return fetch


class UpdateTests(unittest.TestCase):
    def test_same_new_legacy_versions_and_daily_cache_including_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/"skill";root.mkdir();install(root);cache=Path(directory)/"cache";row,_,raw=release();calls=[]
            def fetch(url,limit):calls.append(url);return updates.encoded(row)
            result=updates.check(root,cache,now=100000,transport=fetch)
            self.assertEqual(result["status"],"available");self.assertFalse(result["cached"])
            self.assertTrue(updates.check(root,cache,now=100001,transport=fetch)["cached"]);self.assertEqual(len(calls),1)
            updates.check(root,cache,True,now=100002,transport=fetch);self.assertEqual(len(calls),2)
            def unavailable(*args):raise OSError("Synthetic network failure")
            result=updates.check(root,cache,now=200000,transport=unavailable)
            self.assertEqual(result["status"],"unavailable");self.assertTrue(result["normal_use_allowed"])
            self.assertEqual(updates.check(root,cache,now=200001,transport=fetch)["status"],"unavailable")
            same,_,_=release("0.1.0");self.assertEqual(updates.check(root,cache,True,now=200002,transport=transport(same,raw))["status"],"current")
            install(root,legacy=True);self.assertEqual(updates.check(root,cache,True,now=200003,transport=fetch)["status"],"bootstrap_required")

    def test_manifest_origin_paths_duplicates_and_archive_digest_fail_closed(self):
        row,_,raw=release()
        for key,value in [("../escape.py","0"*64),("scripts/../../escape.py","0"*64),("scripts/evil.py","not-a-hash"),("references/state.schema.json",True)]:
            bad=copy.deepcopy(row);bad["files"][key]=value
            with self.assertRaises(cs.Invalid):updates.descriptor(bad)
        bad=copy.deepcopy(row);bad["release"]["repository"]="https://untrusted.example/repository"
        with self.assertRaises(cs.Invalid):updates.descriptor(bad)
        bad=copy.deepcopy(row);bad["release"]["tag"]="../main"
        with self.assertRaises(cs.Invalid):updates.descriptor(bad)
        for mode in ("extra","symlink","wrong_bytes"):
            archive=io.BytesIO(raw)
            with zipfile.ZipFile(archive,"a") as z:
                if mode=="extra":z.writestr("../escape",b"bad")
                elif mode=="symlink":
                    entry=zipfile.ZipInfo("career-agent/link");entry.external_attr=0o120777<<16;z.writestr(entry,"outside")
                else:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore",UserWarning);z.writestr("career-agent/references/notes.md",b"changed")
            with self.assertRaises((cs.Invalid,ValueError)):updates.verified_download("0.2.0",updates.digest(updates.encoded(row)),transport(row,archive.getvalue()))
        with self.assertRaises(cs.Invalid):updates.verified_download("0.2.0","0"*64,transport(row,raw))
        with self.assertRaises(cs.Invalid):cs.strict_json_loads('{"release":1,"release":2}')

    def test_approved_update_preserves_extras_and_private_state_no_remote_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/"skill";root.mkdir();old=install(root);(root/"custom.md").write_text("Synthetic personal customization.")
            private=Path(directory)/"state.json";private.write_text('{"schema_version":1,"private":"unchanged"}')
            row,payload,raw=release();before=private.read_bytes()
            result=updates.apply(root,"0.2.0",updates.digest(updates.encoded(row)),Path(directory)/"cache",True,True,[private],transport(row,raw))
            self.assertTrue(result["updated"]);self.assertEqual(private.read_bytes(),before);self.assertTrue((root/"custom.md").exists())
            self.assertEqual(cs.load_json(root/"BUNDLE.json")["release"]["version"],"0.2.0")
            for name,data in payload.items():self.assertEqual((root/name).read_bytes(),data)
            self.assertEqual(cs.load_json(Path(result["backup"])/"BUNDLE.json"),old)

    def test_refuse_local_changes_collisions_schema_busy_state_and_missing_approval(self):
        for mode in ("local_edit","manifest_edit","collision","schema","state_lock","approval","busy"):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)/"skill";root.mkdir();install(root);cache=Path(directory)/"cache";row,_,raw=release()
                state=Path(directory)/"state.json";state.write_text('{"schema_version":1}')
                if mode=="local_edit":(root/"SKILL.md").write_text("Edited locally")
                if mode=="manifest_edit":
                    (root/"SKILL.md").write_text("Edited locally")
                    local=cs.load_json(root/"BUNDLE.json");local["files"]["SKILL.md"]=updates.digest((root/"SKILL.md").read_bytes());(root/"BUNDLE.json").write_bytes(updates.encoded(local))
                if mode=="collision":
                    row,_,raw=release(extra={"scripts/addition.py":b"VALUE = 3\n"})
                    (root/"scripts/addition.py").write_text("Synthetic unrelated local addition")
                if mode=="schema":state.write_text('{"schema_version":2}')
                if mode=="state_lock":state.with_name("state.json.lock").touch()
                before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
                if mode=="busy":
                    with cs.skill_operation(root):
                        with self.assertRaises(cs.Invalid):updates.apply(root,"0.2.0",updates.digest(updates.encoded(row)),cache,True,True,[state],transport(row,raw))
                else:
                    with self.assertRaises(cs.Invalid):updates.apply(root,"0.2.0",updates.digest(updates.encoded(row)),cache,mode!="approval",True,[state],transport(row,raw))
                self.assertEqual({str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()},before)

    def test_download_failure_failed_replace_rollback_and_interrupt_recovery(self):
        for mode in ("download","failure","interrupt"):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)/"skill";root.mkdir();install(root);cache=Path(directory)/"cache";row,_,raw=release()
                original={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
                def fetch(url,limit):
                    if mode=="download" and url.endswith('.zip'):raise OSError("Synthetic failed download")
                    return transport(row,raw)(url,limit)
                class Interrupted(BaseException):pass
                def hook(index,name):
                    if index==2:
                        if mode=="interrupt":raise Interrupted()
                        if mode=="failure":raise OSError("Synthetic replacement failure")
                with self.assertRaises((OSError,Interrupted)):updates.apply(root,"0.2.0",updates.digest(updates.encoded(row)),cache,True,True,transport=fetch,replace_hook=hook)
                if mode=="interrupt":
                    self.assertTrue(updates.recover(root,cache,True,True)["recovered"])
                self.assertEqual({str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()},original)

    def test_symlink_ancestor_and_legacy_bootstrap(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/"skill";root.mkdir();install(root,legacy=True);row,_,raw=release()
            with self.assertRaises(cs.Invalid):updates.apply(root,"0.2.0",updates.digest(updates.encoded(row)),Path(directory)/"cache",True,True,transport=transport(row,raw))
            install(root)
            self.assertTrue(updates.apply(root,"0.2.0",updates.digest(updates.encoded(row)),Path(directory)/"cache",True,True,transport=transport(row,raw))["updated"])
            saved=cs.load_json(root/"BUNDLE.json");outside=Path(directory)/"outside";shutil.move(root/"references",outside);(root/"references").symlink_to(outside,target_is_directory=True)
            with self.assertRaises(cs.Invalid):updates.preflight(root,saved,row)

    def test_concurrent_edit_is_preserved_and_recovery_blocks_helpers_until_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/"skill";root.mkdir();install(root);cache=Path(directory)/"cache";row,_,raw=release()
            original=(root/"references/state-format.md").read_bytes()
            def hook(index,name):
                if index==0:(root/"references/state-format.md").write_text("Synthetic concurrent edit")
            with self.assertRaises(cs.Invalid):updates.apply(root,"0.2.0",updates.digest(updates.encoded(row)),cache,True,True,transport=transport(row,raw),replace_hook=hook)
            self.assertEqual((root/"references/state-format.md").read_text(),"Synthetic concurrent edit")
            with self.assertRaises(cs.Invalid):
                with cs.skill_operation(root):pass
            with self.assertRaises(cs.Invalid):updates.recover(root,cache,True,True)
            (root/"references/state-format.md").write_bytes(original)
            self.assertTrue(updates.recover(root,cache,True,True)["recovered"])
            with cs.skill_operation(root):pass

    def test_real_built_bundle_roundtrip_and_cached_cli_outside_source(self):
        import build_skill_bundle as builder
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory);root=parent/"skill";fixture_descriptor=legacy_bundle(root);archive=parent/"career-agent.zip";builder.archive_bundle(root,archive)
            row=updates.descriptor(fixture_descriptor);raw=archive.read_bytes()
            manifest=cs.load_json(root/"BUNDLE.json");manifest["release"]={**manifest["release"],"version":"0.0.1","tag":"v0.0.1"};(root/"BUNDLE.json").write_bytes(updates.encoded(manifest))
            cache=parent/"cache"
            result=updates.apply(root,row["release"]["version"],updates.digest(updates.encoded(row)),cache,True,True,transport=transport(row,raw,manifest))
            self.assertTrue(result["updated"])
            updates.check(root,cache,transport=transport(row,raw))
            run=subprocess.run([sys.executable,"-B",str(root/"scripts/career_updates.py"),"check","--cache-dir",str(cache)],cwd="/tmp",capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr);self.assertEqual(json.loads(run.stdout)["status"],"current")
            run=subprocess.run([sys.executable,"-B",str(root/"scripts/career_state.py"),"validate",str(ROOT/"tests/fixtures/synthetic-state.json")],cwd="/tmp",capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)


    def test_committed_or_rolled_back_crash_clears_stale_lease_without_wrong_rollback(self):
        from unittest import mock
        for phase in ("committed","rolled_back"):
            with self.subTest(phase=phase),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)/"skill";root.mkdir();install(root);cache=Path(directory)/"cache";row,_,raw=release()
                class Interrupted(BaseException):pass
                atomic=updates.atomic
                def crash(path,data,mode=0o600):
                    atomic(path,data,mode)
                    if path.name.startswith('transaction-') and json.loads(data).get('phase')==phase:raise Interrupted()
                def failed_write(index,name):
                    if phase=="rolled_back" and index==0:raise OSError("Synthetic failed write")
                with mock.patch.object(updates,'atomic',crash):
                    with self.assertRaises(Interrupted):updates.apply(root,"0.2.0",updates.digest(updates.encoded(row)),cache,True,True,transport=transport(row,raw),replace_hook=failed_write)
                with self.assertRaises(cs.Invalid):
                    with cs.skill_operation(root):pass
                before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
                result=updates.recover(root,cache,True,True)
                self.assertEqual(result["preserved_committed"],phase=="committed")
                self.assertEqual({str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()},before)
                with cs.skill_operation(root):pass
                self.assertEqual(cs.load_json(root/'BUNDLE.json')['release']['version'],"0.2.0" if phase=="committed" else "0.1.0")

    def test_corrupt_disposable_cache_never_prevents_an_explicit_fresh_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/"skill";root.mkdir();install(root);cache=Path(directory)/"cache";cache.mkdir();row,_,raw=release();calls=[]
            def fetch(url,limit):calls.append(url);return updates.encoded(row)
            for broken in ('{bad','[]','{"checked_at":1,"descriptor":{}}'):
                (cache/'check.json').write_text(broken)
                before=len(calls);result=updates.check(root,cache,force=True,transport=fetch)
                self.assertEqual(result['status'],'available');self.assertEqual(len(calls),before+1)
                result=updates.check(root,cache,transport=fetch)
                self.assertTrue(result['cached']);self.assertEqual(len(calls),before+1)
            (cache/'check.json').write_text('{bad')
            self.assertEqual(updates.check(root,cache,transport=fetch)['status'],'available')



if __name__=='__main__':unittest.main()
