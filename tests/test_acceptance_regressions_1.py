"""Independent CP2 failure reproductions against the public fictional runtime facade."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from test_runtime_1 import Fixture
from career.contracts import CareerError,canonical
from career.repository import Repository

ROOT=Path(__file__).resolve().parents[1]


class AcceptanceRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='career-cp3-fictional-',dir='/tmp');self.addCleanup(self.tmp.cleanup)
        self.fx=Fixture(self.tmp.name).seed()

    def selection(self):return self.fx.tasks.query('selection',record_id='packet_one')

    def reviewed(self,text,used=None,coverage=None,base=None):
        review=dict(findings='Compared the exact fictional content and saved evidence.',limitations='Mechanical checks do not certify semantics or source truth.',tone_findings='Specific factual contribution.',claim_spans=[dict(claim_id='claim_one',text=text)] if used else [],coverage=coverage if coverage is not None else [dict(claim_id='claim_one',disposition='included')])
        if base:review['base_coverage_version_id']=base
        return self.fx.command('packet.save',packet_id='packet_one',documents=[dict(slot=slot,text=text if slot=='resume' else 'Fictional supporting content.') for slot in ('resume','message','dossier','interview')],used_claim_ids=used or [],review=review)

    def test_coverage_requires_used_actual_resume_metric_and_units_even_with_base(self):
        base=self.selection()['version_id']
        self.reviewed('Prepared synthetic content')
        self.assertFalse(self.selection()['assessment']['prepared'])
        self.assertIn('COVERAGE_SPAN_MISSING',{x['code'] for x in self.selection()['assessment']['issues']})
        self.reviewed('Improved processing.',used=['claim_one'])
        self.assertIn('METRIC_MISSING',{x['code'] for x in self.selection()['assessment']['issues']})
        self.reviewed('Improved processing by 25.',used=['claim_one'])
        self.assertIn('METRIC_UNIT_MISSING',{x['code'] for x in self.selection()['assessment']['issues']})
        self.reviewed('Improved processing.',used=['claim_one'],coverage=[],base=base)
        self.assertFalse(self.selection()['assessment']['prepared'])
        self.assertIn('METRIC_MISSING',{x['code'] for x in self.selection()['assessment']['issues']})
        self.reviewed('Improved processing by 25%.',used=['claim_one'],coverage=[],base=base)
        self.assertTrue(self.selection()['assessment']['prepared'])
        self.reviewed('Tailored contribution.',coverage=[dict(claim_id='claim_one',disposition='excluded',reason='Owner requested exclusion for this explicitly scoped target.')],base=base)
        self.assertTrue(self.selection()['assessment']['prepared'])

    def test_wrong_track_batches_and_immutable_quota_cannot_claim_completion(self):
        self.fx.command('track.save',id='track_two',name='Hospitality training',positioning='Evidenced training',selected=True,language='en',policies={})
        for unit,task,selected in [('cases','research','case_one'),('cases','packets','case_one'),('people','contacts','person_one')]:
            bid='batch_'+task
            values=dict(id=bid,task=task,requested_count=1,count_unit=unit,track_ids=['track_two'],criterion='Hospitality only',selected_ids=[selected],required_outputs=[])
            self.fx.command('batch.save',**values)
            result=self.fx.tasks.query('assess',record_id=bid)
            self.assertFalse(result['task_complete']);self.assertEqual(0,result['qualified']);self.assertEqual(0,result['qualifying'])
            with self.assertRaises(CareerError) as error:self.fx.command('batch.save',**dict(values,track_ids=['track_one']))
            self.assertEqual('BATCH_CONTRACT_CONFLICT',error.exception.code)
        self.fx.command('case.capture',id='case_one',company_id='company_one',title='Product specialist',kind='vacancy',route='person',tracks=[dict(id='track_one',rationale='Supported workflow contribution')],source_ids=['source_one'],requisition='REQ-42',person_id='person_one',essential_policy='unknown')
        self.fx.command('batch.save',id='batch_pass',task='research',requested_count=1,count_unit='cases',track_ids=['track_one'],criterion='Verified essential requirements',selected_ids=['case_one'],required_outputs=[],predicate=dict(kind='evidenced_cases',essential_policy='verified_pass'))
        self.assertFalse(self.fx.tasks.query('assess',record_id='batch_pass')['task_complete'])

    def test_exact_identity_retarget_rejected_atomically_and_metadata_invalidates_review(self):
        values=dict(id='case_one',company_id='company_one',title='Different Role',kind='vacancy',route='person',tracks=[dict(id='track_one',rationale='Supported workflow contribution')],source_ids=['source_one'],requisition='REQ-42',canonical_url='https://northstar.example/other-role',person_id='person_one')
        before=self.fx.tasks.context()['revision']
        with self.assertRaises(CareerError) as error:self.fx.command('case.capture',**values)
        self.assertEqual('IDENTITY_CONFLICT',error.exception.code);self.assertEqual(before,self.fx.tasks.context()['revision'])
        with self.fx.tasks.repository.open() as s:
            self.assertEqual(1,s.one('SELECT count(*) AS n FROM opportunities')['n']);self.assertEqual('Product specialist',s.get('case','case_one')['title'])
        self.assertTrue(self.selection()['assessment']['prepared'])
        self.fx.command('case.note',case_id='case_one',text='Unrelated private note')
        self.assertTrue(self.selection()['assessment']['prepared'])
        values.pop('canonical_url');self.fx.command('case.capture',**values)
        self.assertFalse(self.selection()['assessment']['prepared'])
        self.assertIn('REVIEW_STALE',{x['code'] for x in self.selection()['assessment']['issues']})

    def test_source_cli_and_facade_require_explicit_development_without_locator(self):
        environment=dict(os.environ);environment.pop('CAREER_AGENT_DEVELOPMENT',None)
        for args in [('context',),('init','--name','Fictional Example')]:
            result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/career.py'),'--workspace',self.tmp.name,*args],env=environment,capture_output=True,text=True)
            self.assertEqual(2,result.returncode,result.stdout+result.stderr);self.assertIn('INSTALLED_COPY_REQUIRED',result.stderr)
        with patch.dict(os.environ,environment,clear=True):
            with self.assertRaises(CareerError):Repository(self.tmp.name)
            with self.assertRaises(CareerError):Repository.initialize(Path(self.tmp.name)/'new','Synthetic Applicant')
        self.assertFalse((Path(self.tmp.name)/'new').exists())

    def test_unreadable_claim_or_role_requires_actual_readable_support(self):
        self.fx.command('source.capture',id='source_one',locator='https://northstar.example/unavailable',excerpt='',readable=False,observed_at='2026-10-24T00:00:00Z')
        self.fx.save();assessment=self.selection()['assessment']
        self.assertFalse(assessment['prepared']);self.assertIn('SOURCE_UNREADABLE',{x['code'] for x in assessment['issues']})
        self.fx.command('source.capture',id='source_confirmed',locator='user:fictional-confirmation',excerpt='Alex Example confirms processing improved by 25%.',readable=True,observed_at='2026-10-24T00:00:00Z')
        self.fx.command('claim.save',id='claim_one',assertion='Improved processing by 25%.',meaning='Personally improved processing by 25%.',source_ids=['source_confirmed'],confirmation='confirmed',disclosure='allowed')
        self.fx.save();self.assertFalse(self.selection()['assessment']['prepared']) # Role/contact evidence remains unreadable.
        self.fx.command('source.capture',id='source_one',locator='https://northstar.example/team',excerpt='Morgan Example leads product. The role needs the evidenced workflow.',readable=True,observed_at='2026-10-24T00:00:00Z')
        self.fx.save();self.assertTrue(self.selection()['assessment']['prepared'])

    def test_context_pagination_targeted_claim_answer_and_track_scope_are_explicit(self):
        self.fx.command('track.save',id='track_two',name='Training',positioning='Training',selected=True,language='en',policies={})
        self.fx.command('answer.save',id='answer_two',meaning='location.preference',scope=dict(track_id='track_two'),units={},disposition='answered',value='Training track only',evidence='Synthetic user answer')
        for n in range(27):self.fx.command('claim.save',id='claim_extra_'+str(n).zfill(2),assertion='Synthetic achievement '+chr(65+n%26),meaning='Synthetic achievement',source_ids=['source_one'],confirmation='unknown',disclosure='private')
        page=self.fx.tasks.context(task='profile');self.assertTrue(page['partial']);self.assertEqual(28,page['pagination']['claims']['total'])
        ids={x['id'] for x in page['evidence']['claims']}
        while page['next_cursor']:
            page=self.fx.tasks.context(task='profile',cursor=page['next_cursor']);ids.update(x['id'] for x in page['evidence']['claims']);self.assertLessEqual(len(canonical(page).encode()),65536)
        self.assertEqual(28,len(ids))
        scoped=self.fx.tasks.context(task='packets',case_id='case_one',track_id='track_one')
        self.assertEqual([],scoped['evidence']['answers']);self.assertEqual(27,scoped['pagination']['claims']['omitted_by_scope'])
        self.assertEqual('claim_extra_26',self.fx.tasks.context(claim_id='claim_extra_26')['claim']['id'])
        answer=self.fx.tasks.context(answer_id='answer_two',case_id='case_one',track_id='track_one')['answer'];self.assertFalse(answer['reusable_here'])
        old=self.fx.tasks.context(task='profile')['next_cursor'];self.fx.command('case.note',case_id='case_one',text='Cursor revision changed')
        with self.assertRaises(CareerError):self.fx.tasks.context(task='profile',cursor=old)

    def test_resumed_multitrack_intent_does_not_expand_context_to_new_tracks(self):
        self.fx.command('track.save',id='track_two',name='Fictional training',positioning='Training',selected=True,language='en',policies={})
        descriptor=self.fx.tasks.query('agent-intent',intent='agent.prepare')['descriptor']
        self.fx.command('track.save',id='track_three',name='Fictional hospitality',positioning='Hospitality',selected=True,language='en',policies={})
        self.fx.command('answer.save',id='answer_three',meaning='location.preference',scope=dict(track_id='track_three'),units={},disposition='answered',value='New track only',evidence='Synthetic supplied answer')
        resumed=self.fx.tasks.query('resolve-intent',descriptor=descriptor)
        self.assertTrue(resumed['context_refreshed'])
        self.assertEqual({'track_one','track_two'},{t['id'] for t in resumed['context']['tracks']})
        self.assertEqual([],resumed['context']['evidence']['answers'])

    def test_missing_and_corrupt_selected_materials_downgrade_bounded_views_and_restore(self):
        self.assertEqual(1,self.fx.tasks.query('board')['counts']['columns']['ready'])
        version=self.selection()['version_id'];slot=next(x for x in self.selection()['slots'] if x['name']=='resume')
        with self.fx.tasks.repository.open() as s:_,path=s.object(slot['artifact_id'])
        original=path.read_bytes();revision=self.fx.tasks.context()['revision']
        for damage in (None,b'X'*len(original)):
            if damage is None:path.unlink()
            else:path.write_bytes(damage)
            board=self.fx.tasks.query('board');self.assertEqual(0,board['counts']['columns']['ready']);self.assertEqual(1,board['counts']['columns']['prepare'])
            table=self.fx.tasks.query('cases');self.assertEqual('prepare',table['items'][0]['column']);self.assertIn('MATERIAL_CHANGED',{x['code'] for x in table['items'][0]['blockers']})
            with self.assertRaises(CareerError) as error:self.selection()
            self.assertEqual('MATERIAL_CHANGED',error.exception.code)
            changes=self.fx.tasks.query('changes',after=revision);self.assertTrue(changes['resync_required']);self.assertIsNotNone(changes['integrity_token'])
            self.assertEqual(revision,self.fx.tasks.context()['revision'])
            path.write_bytes(original)
            restored=self.fx.tasks.query('board');self.assertEqual(1,restored['counts']['columns']['ready']);self.assertEqual(version,self.selection()['version_id'])
            self.assertTrue(self.selection()['assessment']['prepared'])

if __name__=='__main__':unittest.main()
