"""Synthetic permission-gate receipts; no real career records, services or material scans."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from test_state import ROOT, AT, LATER, base
from test_search_cases import configured
sys.path.insert(0,str(ROOT/'scripts'))
import career_state as cs
import career_research as gate
import career_search as search


def active():
    state=configured()
    state['profile']['selected_directions']=['Backend API engineering','Platform reliability','Integration projects']
    return cs.control_change(state,'start','Fictional explicit multi-direction research request','Selected fictional directions, shared company/opportunity history',True,'live-research',AT,LATER)


def write(path,state):
    path.write_text(cs.canonical_json(state))


class ResearchReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.path=self.root/'state.json';self.cache=self.root/'cache';write(self.path,active())
    def tearDown(self):self.temp.cleanup()
    def check(self,**extra):return gate.research_check(self.path,cs,context_id='live-research',at=AT,cache_dir=self.cache,**extra)

    def test_unchanged_snapshot_reuses_validation_not_permission(self):
        with mock.patch.object(cs,'validate',wraps=cs.validate) as validation:
            first=self.check();self.assertEqual(validation.call_count,1)
            second=self.check();self.assertEqual(validation.call_count,1)
        self.assertTrue(first['allowed']);self.assertTrue(second['allowed']);self.assertEqual(second['validation_cache'],'hit')
        self.assertFalse(second['material_files_verified'])
        self.assertFalse(gate.research_check(self.path,cs,'different-context',AT,self.cache)['allowed'])
        expired=gate.research_check(self.path,cs,'live-research',LATER,self.cache)
        self.assertFalse(expired['allowed']);self.assertEqual(expired['validation_cache'],'hit')

    def test_pause_profile_and_same_revision_edits_invalidate(self):
        self.check();state=active();state['profile']['selected_directions'].append('Developer tooling')
        write(self.path,state)
        with mock.patch.object(cs,'validate',wraps=cs.validate) as validation:
            result=self.check();self.assertEqual(validation.call_count,1)
        self.assertEqual(len(result['research_tracks']),4);self.assertEqual(result['validation_cache'],'miss')
        state=cs.control_change(state,'pause','Fictional immediate pause','',True,at=AT);write(self.path,state)
        paused=self.check();self.assertFalse(paused['allowed']);self.assertEqual(paused['validation_cache'],'miss')

    def test_different_profile_and_atomic_replacement_never_share_receipt(self):
        self.check();other=self.root/'other.json';write(other,active())
        with mock.patch.object(cs,'validate',wraps=cs.validate) as validation:
            result=gate.research_check(other,cs,'live-research',AT,self.cache);self.assertEqual(validation.call_count,1)
        self.assertEqual(result['validation_cache'],'miss')
        before=self.path.stat();replacement=self.root/'replacement.json';write(replacement,active());os.utime(replacement,ns=(before.st_atime_ns,before.st_mtime_ns));os.replace(replacement,self.path)
        self.assertEqual(self.check()['validation_cache'],'miss')

    def test_preserved_size_and_mtime_cannot_hide_a_state_edit(self):
        self.check();before=self.path.stat();raw=self.path.read_text();self.assertIn('Platform reliability',raw)
        self.path.write_text(raw.replace('Platform reliability','Platform Reliability'))
        os.utime(self.path,ns=(before.st_atime_ns,before.st_mtime_ns))
        self.assertEqual(self.path.stat().st_size,before.st_size)
        self.assertEqual(self.check()['validation_cache'],'miss')

    def test_validator_change_and_cache_tamper_force_full_validation(self):
        self.check()
        with mock.patch.object(gate,'engine_signature',return_value='f'*64):self.assertEqual(self.check()['validation_cache'],'miss')
        cache_path=next(self.cache.glob('*.json'));row=json.loads(cache_path.read_text());row['payload']['gate']['control']['scope']='Forged broader scope';cache_path.write_text(json.dumps(row))
        with mock.patch.object(cs,'validate',wraps=cs.validate) as validation:
            check=self.check();self.assertEqual(validation.call_count,1)
        self.assertNotEqual(check['scope'],'Forged broader scope');self.assertEqual(check['validation_cache'],'miss')

    def test_changed_loaded_engine_or_schema_cannot_sign_a_new_receipt(self):
        self.check()
        with mock.patch.object(cs,'VALIDATOR_SOURCE_SHA256','0'*64):
            with self.assertRaisesRegex(ValueError,'changed since import'):self.check()
        changed=copy.deepcopy(cs.state_schema());changed['required'].append('new-required-field')
        with mock.patch.object(cs,'state_schema',return_value=changed):
            with self.assertRaisesRegex(ValueError,'schema changed'):self.check()

    def test_cache_denial_corruption_or_symlink_falls_back_without_granting(self):
        self.check();cache_path=next(self.cache.glob('*.json'));cache_path.write_text('{broken')
        self.assertTrue(self.check()['allowed']);cache_path.chmod(0o644)
        self.assertEqual(self.check()['validation_cache'],'miss')
        target=self.root/'untouched';target.write_text('Do not overwrite');cache_path.unlink();cache_path.symlink_to(target)
        self.assertTrue(self.check()['allowed']);self.assertEqual(target.read_text(),'Do not overwrite')
        with mock.patch.object(gate,'_cache_context',return_value=None):self.assertEqual(self.check()['validation_cache'],'unavailable')
        self.assertTrue(self.check(use_cache=False)['allowed'])

    def test_full_invalid_state_not_just_control_still_blocks_cache_miss(self):
        self.check();state=active();state['facts'][0]['source_ids']=['missing-source'];write(self.path,state)
        with self.assertRaises(cs.Invalid):self.check()

    def test_live_writer_or_cold_validation_revision_race_fails_closed(self):
        lock=self.path.with_name('state.json.lock');lock.write_text('fictional writer')
        with self.assertRaisesRegex(cs.Invalid,'being written'):self.check()
        lock.unlink();original=cs.validate
        def replace_after_validation(state):
            result=original(state);changed=copy.deepcopy(state);changed['revision']+=1;write(self.path,changed);return result
        with mock.patch.object(cs,'validate',side_effect=replace_after_validation):
            with self.assertRaisesRegex(cs.Invalid,'changed during'):self.check()

    def test_warm_decision_revision_race_cannot_return_stale_allowed(self):
        self.check();original=cs._research_decision
        def change_after_decision(state,*args):
            result=original(state,*args);new=active();new['revision']+=1;write(self.path,new);return result
        with mock.patch.object(cs,'_research_decision',side_effect=change_after_decision):
            with self.assertRaisesRegex(cs.Invalid,'changed during'):self.check()

    def test_cli_uses_gate_once_and_tracks_share_exact_opportunity_identity(self):
        command=[sys.executable,'-B',str(ROOT/'scripts/career_state.py'),'research-check',str(self.path),'--context-id','live-research','--at',AT,'--cache-dir',str(self.cache)]
        first=subprocess.run(command,capture_output=True,text=True);second=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(first.returncode,0,first.stderr);self.assertEqual(second.returncode,0,second.stderr)
        result=json.loads(second.stdout);self.assertEqual(result['validation_cache'],'hit');self.assertEqual(result['research_tracks'],active()['profile']['selected_directions'])
        state=base();role=copy.deepcopy(state['opportunities'][0]);role['direction']='A second selected direction'
        self.assertEqual(search.novelty(state,self.root,role)['status'],'known')


class SchemaComparisonTests(unittest.TestCase):
    def test_fast_literal_keys_preserve_existing_json_identity(self):
        for a,b,equal in [(True,1,False),(False,0,False),(1,1.0,False),(0.0,-0.0,False),({'a':1},{'a':1},True),([1,True],[1,True],True),('role','role',True)]:
            self.assertEqual(cs._literal_key(a)==cs._literal_key(b),equal)
        with self.assertRaises(cs.Invalid):cs.validate_shape(True,{'enum':[1]})
        with self.assertRaises(cs.Invalid):cs.validate_shape([{'a':1},{'a':1}],{'type':'array','uniqueItems':True})
        cs.validate_shape([1,True],{'type':'array','uniqueItems':True})

    def test_reference_siblings_and_nonfinite_json_checks_are_retained(self):
        schema={'$defs':{'names':{'type':'array','items':{'type':'string'}}},'$ref':'#/$defs/names','minItems':2}
        with self.assertRaises(cs.Invalid):cs.validate_shape(['one'],schema)
        cs.validate_shape(['one','two'],schema)
        state=active();state['opaque']=[float('nan')]
        with self.assertRaises(cs.Invalid):cs.validate(state)
