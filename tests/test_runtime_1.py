"""Fictional 1.0 owner regressions: transactions, qualification and exact selection."""
import copy
import os
os.environ["CAREER_AGENT_DEVELOPMENT"]="1"  # Explicit synthetic source-test boundary.
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from career.contracts import CareerError
from career.facade import Tasks
from career.repository import Repository
from career.policy import resolve_policy


class Fixture:
    def __init__(self,root,editorial=True):
        self.editorial=editorial
        self.root=Path(root);Repository.initialize(root,'Alex Example');self.tasks=Tasks(root);self.serial=0

    def command(self,intent,**data):
        # Structural fixture attestation only, never evidence of writing quality.
        # Behavioral fixtures use real agent text/review and are evaluated separately.
        if self.editorial and intent=='packet.save' and data.get('review') and 'editorial' not in data['review']:
            value={k:data[k] for k in ('packet_id','documents','used_claim_ids','answer_ids') if k in data}
            bound=self.tasks.query('review-context',input=value)
            data=copy.deepcopy(data);data['review']['editorial']=dict(argument='Synthetic fixture targets the documented workflow contribution.',decision='approved',findings='Plumbing fixture attestation; this test does not rate prose.',binding=bound['binding'])
        self.serial+=1
        return self.tasks.command(dict(request_id='fictional_'+str(self.serial),expected_revision=self.tasks.context()['revision'],intent=intent,input=data))

    def seed(self):
        self.command('source.capture',id='source_one',locator='https://northstar.example/team',excerpt='Morgan Example leads the product team. Alex Example improved processing by 25%.',observed_at='2026-10-24T00:00:00Z',readable=True)
        self.command('claim.save',id='claim_one',assertion='Improved processing by 25%.',meaning='Personally improved processing by 25%.',source_ids=['source_one'],confirmation='confirmed',disclosure='allowed')
        self.command('track.save',id='track_one',name='Product work',positioning='Supported product contribution',selected=True,language='en',policies={},claim_ids=['claim_one'])
        self.command('company.capture',id='company_one',name='Northstar Demo',domain='northstar.example')
        self.command('contact.capture',id='person_one',name='Morgan Example',company_id='company_one',affiliation='current',relevance='Works on the evidenced workflow',sources=[dict(source_id='source_one',axes=['identity','affiliation','relevance'],assessment='supports')],route=dict(kind='profile',value='https://northstar.example/team/morgan',source_id='source_one'))
        self.command('case.capture',id='case_one',company_id='company_one',title='Product specialist',kind='vacancy',route='person',tracks=[dict(id='track_one',rationale='Supported workflow contribution')],source_ids=['source_one'],requisition='REQ-42',person_id='person_one',essential_policy='passed')
        self.command('packet.create',id='packet_one',case_id='case_one',purpose='application')
        self.save()
        return self

    def save(self,text='Improved processing by 25%.',review=True):
        data=dict(packet_id='packet_one',used_claim_ids=['claim_one'],documents=[dict(slot='resume',text=text),dict(slot='message',text='A relevant workflow contribution.'),dict(slot='dossier',text='Private evidence and gaps.'),dict(slot='interview',text='Supported story outline and employer questions.')])
        if review:data['review']=dict(findings='Compared source meaning and actual external spans; no unresolved supported changes.',limitations='Declared review does not independently prove source truth or exhaustive extraction.',claim_spans=[dict(claim_id='claim_one',text='Improved processing by 25%.')],tone_findings='Concrete professional relevance, no invented familiarity.',coverage=[dict(claim_id='claim_one',disposition='included')])
        return self.command('packet.save',**data)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='career-fictional-');self.addCleanup(self.temp.cleanup)
        self.fx=Fixture(self.temp.name)

    def test_init_refuses_legacy_and_reuses_clean_workspace(self):
        self.assertTrue(Repository.initialize(self.temp.name,'Different')['reused'])
        other=Path(self.temp.name)/'legacy';(other/'Data').mkdir(parents=True);(other/'Data/state.json').write_text('{}')
        with self.assertRaises(CareerError) as caught:Repository.initialize(other,'Example')
        self.assertEqual('IMPORT_REQUIRED',caught.exception.code)

    def test_atomic_idempotency_conflict_and_changes(self):
        value=dict(request_id='unique',expected_revision=0,intent='preferences.set',input=dict(theme='dark'))
        receipt=self.fx.tasks.command(value)
        self.assertEqual(receipt,self.fx.tasks.command(value))
        with self.assertRaises(CareerError):self.fx.tasks.command(dict(value,input=dict(theme='light')))
        with self.assertRaises(CareerError):self.fx.tasks.command(dict(value,request_id='another'))
        self.assertEqual(1,self.fx.tasks.context()['revision'])
        self.assertEqual(1,len(self.fx.tasks.query('changes',after=0)['changes']))
        self.assertEqual(1,len(list((self.fx.root/'Backups/Automatic').glob('*.sqlite3'))))

    def test_unknown_affiliation_changes_counts_and_current_selection(self):
        self.fx.seed()
        self.fx.command('batch.save',id='batch_one',task='contacts',requested_count=1,count_unit='people',track_ids=['track_one'],criterion='Current evidenced useful colleague',selected_ids=['person_one','person_one'],required_outputs=[])
        self.assertTrue(self.fx.tasks.query('assess',record_id='batch_one')['task_complete'])
        with self.fx.tasks.repository.open() as snapshot:
            person=snapshot.contact('person_one')
        data={key:person[key] for key in ('id','name','company_id','affiliation','relevance','sources','route')};data['affiliation']='unknown'
        self.fx.command('contact.capture',**data)
        assessment=self.fx.tasks.query('assess',record_id='batch_one')
        self.assertEqual(0,assessment['qualified']);self.assertFalse(assessment['task_complete'])
        self.assertFalse(self.fx.tasks.query('selection',record_id='packet_one')['assessment']['prepared'])

    def test_company_scoped_requisition_dedup(self):
        self.fx.seed()
        self.fx.command('company.capture',id='company_two',name='Harbor Demo',domain='harbor.example')
        self.fx.command('case.capture',company_id='company_two',title='Product specialist',kind='vacancy',route='unknown',tracks=[dict(id='track_one',rationale='Other employer')],source_ids=['source_one'],requisition='REQ-42')
        self.assertEqual(2,self.fx.tasks.context()['counts']['cases'])
        self.fx.command('case.capture',company_id='company_one',title='Product specialist updated',kind='vacancy',route='person',tracks=[dict(id='track_one',rationale='Same exact role')],source_ids=['source_one'],requisition='REQ-42',person_id='person_one')
        self.assertEqual(2,self.fx.tasks.context()['counts']['cases'])

    def test_selected_version_is_explicit_and_draft_edit_needs_review(self):
        self.fx.seed();old=self.fx.tasks.query('selection',record_id='packet_one')
        self.assertTrue(old['assessment']['prepared'])
        self.fx.save(review=False)
        newer=self.fx.tasks.query('selection',record_id='packet_one');self.assertNotEqual(old['version_id'],newer['version_id'])
        self.assertFalse(newer['assessment']['prepared'])
        self.fx.command('packet.select',packet_id='packet_one',version_id=old['version_id'])
        self.assertEqual(old['version_id'],self.fx.tasks.query('case',record_id='case_one')['selection']['version_id'])
        self.fx.command('case.note',case_id='case_one',text='Unrelated private note')
        self.assertTrue(self.fx.tasks.query('selection',record_id='packet_one')['assessment']['prepared'])

    def test_unsupported_number_and_disclosure_withdrawal_block_reuse(self):
        self.fx.seed();self.fx.save('Improved processing by 25%. Managed 999 engineers.')
        selection=self.fx.tasks.query('selection',record_id='packet_one')
        self.assertIn('UNMATCHED_NUMBER',{i['code'] for i in selection['assessment']['issues']})
        self.fx.command('claim.save',id='claim_one',assertion='Improved processing by 25%.',meaning='Personally improved processing by 25%.',source_ids=['source_one'],confirmation='confirmed',disclosure='withdrawn')
        self.assertFalse(self.fx.tasks.query('selection',record_id='packet_one')['assessment']['prepared'])

    def test_sealed_input_changed_prevents_partial_persistence(self):
        self.fx.seed()
        value=dict(request_id='sealed',expected_revision=self.fx.tasks.context()['revision'],intent='packet.save',input=dict(packet_id='packet_one',documents=[dict(slot='message',text='A private draft')],used_claim_ids=[]))
        plan=self.fx.tasks.plan(value)
        obj=next((self.fx.root/'Objects').glob('*.md'))
        # Corrupt a referenced staged object, retaining the failed bytes for doctor.
        for path in (self.fx.root/'Objects').glob('*.md'):
            if path.read_text()=='A private draft':obj=path;break
        obj.write_text('Changed')
        revision=self.fx.tasks.context()['revision']
        with self.assertRaises(CareerError):self.fx.tasks.apply(plan['plan_id'])
        self.assertEqual(revision,self.fx.tasks.context()['revision'])
        with self.assertRaises(CareerError):self.fx.tasks.repository.status('sealed')

    def test_uncertain_action_blocks_blind_retry_and_preserves_occurrence(self):
        self.fx.seed();selection=self.fx.tasks.query('selection',record_id='packet_one')
        action=dict(case_id='case_one',kind='uncertain',occurred_at='2026-10-24T10:00:00Z',evidence='User reports a lost provider response.',packet_id='packet_one',version_id=selection['version_id'])
        result=self.fx.command('activity.record',**action);activity=result['saved_ids'][0]
        with self.assertRaises(CareerError):self.fx.command('activity.record',**action)
        self.fx.command('activity.record',case_id='case_one',kind='not_sent',occurred_at=action['occurred_at'],evidence='Provider history confirms no submission.',resolves_activity_id=activity)
        self.fx.command('activity.record',**dict(action,kind='sent',evidence='User confirms actual manual transmission.'))
        self.assertEqual(3,len(self.fx.tasks.query('case',record_id='case_one')['history']))

    def test_research_scope_durable_pause_and_policy_isolation(self):
        self.fx.seed();scope=dict(track_ids=['track_one'],purpose='Find professional routes')
        self.fx.command('research.control',status='active',scope=scope,evidence='Explicit user start for this unchanged scope.')
        resumed=Tasks(self.temp.name);self.assertTrue(resumed.query('research-check')['allowed'])
        self.assertFalse(resumed.query('research-check',scope=dict(track_ids=['other'],purpose=scope['purpose']))['allowed'])
        self.fx.command('research.control',status='paused',scope=scope,evidence='Explicit user pause.')
        self.assertFalse(resumed.query('research-check')['allowed'])
        result=resolve_policy({'language':dict(state='known',value='en')},{'language':dict(state='unknown')},{})
        self.assertEqual('unknown',result['language']['state'])

    def test_missing_objects_fail_integrity_scan(self):
        self.fx.seed();next((self.fx.root/'Objects').glob('*.md')).unlink()
        self.assertFalse(self.fx.tasks.repository.doctor()['healthy'])


if __name__=='__main__':unittest.main()
