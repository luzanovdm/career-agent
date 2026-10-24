"""Mechanics from the independent fresh-chat review; no evaluation workspace inputs."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_runtime_1 import Fixture
from career.contracts import SCHEMAS,Command,CareerError,canonical,schema
from career.policy import number_tokens


class CP4Behavior(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='career-cp4-behavior-',dir='/tmp');self.addCleanup(self.temp.cleanup);self.fx=Fixture(self.temp.name).seed()

    def case(self,record_id='case_one',policy='passed',unknowns=None):
        return self.fx.command('case.capture',id=record_id,company_id='company_one',title='Fictional operations role '+record_id,kind='vacancy',route='person',tracks=[dict(id='track_one',rationale='Supported workflow contribution')],source_ids=['source_one'],requisition='REQ-42' if record_id=='case_one' else 'REQ-'+record_id,person_id='person_one',essential_policy=policy,essential_unknowns=unknowns or [])

    def packet(self,case_id,packet_id):
        if packet_id!='packet_one':self.fx.command('packet.create',id=packet_id,case_id=case_id,purpose='application')
        return self.fx.command('packet.save',packet_id=packet_id,documents=[dict(slot=slot,text='Improved processing by 25%.' if slot=='resume' else 'Specific supported contribution and private preparation.') for slot in ('resume','message','dossier','interview')],used_claim_ids=['claim_one'],review=dict(findings='Compared actual sources and selected spans.',limitations='Does not certify independent source truth.',tone_findings='Confident factual wording.',claim_spans=[dict(claim_id='claim_one',text='Improved processing by 25%.')],coverage=[dict(claim_id='claim_one',disposition='included')]))

    def test_conditional_eligibility_is_structured_without_blocking_useful_reviewed_draft(self):
        self.case(policy='unknown',unknowns=[dict(code='REQUIRED_UDT_UNKNOWN',subject='UDT',message='Required UDT qualification is not established.',source_ids=['source_one'])]);self.packet('case_one','packet_one')
        selection=self.fx.tasks.query('selection',record_id='packet_one');assessment=selection['assessment']
        self.assertTrue(assessment['prepared']);self.assertEqual([],assessment['issues']);self.assertTrue(assessment['conditional']);self.assertEqual('conditional',assessment['eligibility']);self.assertEqual('REQUIRED_UDT_UNKNOWN',assessment['unknown_details'][0]['code']);self.assertTrue(assessment['limitations'])
        self.assertTrue(all(isinstance(x,str) for x in assessment['unknowns'])) # Existing UI string projection remains safe.
        self.fx.command('batch.save',id='conditional',task='research',requested_count=1,count_unit='cases',track_ids=['track_one'],criterion='Suitable verified role',selected_ids=['case_one'],required_outputs=[])
        result=self.fx.tasks.query('assess',record_id='conditional');self.assertEqual(0,result['qualified']);self.assertEqual(1,result['prepared']);self.assertFalse(result['task_complete'])
        self.assertFalse(self.fx.tasks.query('cases')['items'][0]['qualified'])

    def test_parent_job_search_keeps_original_four_cases_when_two_packets_are_done(self):
        f=self.fx;self.case();self.packet('case_one','packet_one')
        cases=['case_one']
        for index in range(2,5):
            cid='case_'+str(index);self.case(cid);cases.append(cid)
        f.command('batch.save',id='job_original',task='job_search',requested_count=4,count_unit='cases',track_ids=['track_one'],criterion='Original ordinary job search with four packets',selected_ids=[],required_outputs=[])
        f.command('batch.save',id='research_child',parent_id='job_original',task='research',requested_count=4,count_unit='cases',track_ids=['track_one'],criterion='Preliminary evidenced roles',selected_ids=cases,required_outputs=[])
        self.packet('case_2','packet_2')
        f.command('batch.save',id='packet_child',parent_id='job_original',task='packets',requested_count=2,count_unit='cases',track_ids=['track_one'],criterion='Two selected packets',selected_ids=cases[:2],required_outputs=[])
        child=f.tasks.query('assess',record_id='packet_child');self.assertTrue(child['scope_complete']);self.assertFalse(child['task_complete']);self.assertEqual(4,child['task']['requested_count'])
        work=next(x for x in child['remaining_work'] if x['kind']=='prepare_packet');self.assertEqual({'case_3','case_4'},set(work['case_ids']))
        research=f.tasks.query('assess',record_id='research_child');self.assertTrue(research['scope_complete']);self.assertFalse(research['task_complete'])
        selected=f.tasks.query('selection',record_id='packet_one');self.assertFalse(selected['task_progress'][0]['task_complete'])
        for index in (3,4):self.packet('case_'+str(index),'packet_'+str(index))
        final=f.tasks.query('assess',record_id='job_original');self.assertTrue(final['task_complete']);self.assertEqual([],final['remaining_work']);self.assertEqual(4,final['prepared'])

    def test_detail_task_progress_reads_metadata_while_explicit_assess_verifies_full_set(self):
        f=self.fx;self.case('case_2');self.packet('case_2','packet_2')
        f.command('packet.save',packet_id='packet_2',used_claim_ids=['claim_one'],documents=[dict(slot=slot,text='Improved processing by 25%.' if slot=='resume' else 'A different supported contribution.') for slot in ('resume','message','dossier','interview')],review=dict(findings='Compared actual source spans.',limitations='No independent truth guarantee.',tone_findings='Factual wording.',claim_spans=[dict(claim_id='claim_one',text='Improved processing by 25%.')],coverage=[dict(claim_id='claim_one',disposition='included')]))
        f.command('batch.save',id='job_scope',task='job_search',requested_count=2,count_unit='cases',track_ids=['track_one'],criterion='Two selected cases',selected_ids=['case_one','case_2'],required_outputs=[])
        other=next(slot['artifact_id'] for slot in f.tasks.query('selection',record_id='packet_2')['slots'] if slot['name']=='message')
        with f.tasks.repository.open() as snapshot:
            original=snapshot.object;read=[]
            def observed(artifact_id):read.append(artifact_id);return original(artifact_id)
            snapshot.object=observed
            projection=snapshot.selection('packet_one');self.assertNotIn(other,read);self.assertEqual('cached_review_state_with_selected_packet_check',projection['task_progress'][0]['integrity_scope'])
            snapshot.assess('job_scope');self.assertIn(other,read)

    def test_pending_is_not_user_unknown_or_a_reusable_answer(self):
        values=dict(meaning='location.preference',scope=dict(track_id='track_one'),units={},disposition='pending',value=None,evidence='Open question: which location is acceptable?',response_state='pending')
        receipt=self.fx.command('answer.save',**values);rid=receipt['saved_ids'][0]
        answer=self.fx.tasks.context(answer_id=rid,track_id='track_one')['answer'];self.assertEqual('pending',answer['response_state']);self.assertFalse(answer['reusable_here'])
        with self.assertRaises(CareerError) as error:self.fx.command('answer.save',**dict(values,disposition='unknown',response_state='pending'))
        self.assertEqual('ANSWER_STATE_REQUIRED',error.exception.code)
        receipt=self.fx.command('answer.save',**dict(values,disposition='unknown',response_state='provided',evidence='User explicitly says they do not know.'));self.assertEqual(rid,receipt['saved_ids'][0])
        answer=self.fx.tasks.context(answer_id=rid,track_id='track_one')['answer'];self.assertEqual('provided',answer['response_state']);self.assertTrue(answer['reusable_here']);self.assertFalse(answer['value_reusable_here'])
        details=self.fx.tasks.query('selection',record_id='packet_one')['assessment']['unknown_details'];self.assertTrue(any(x['code']=='EXPLICIT_UNKNOWN' and not x['requires_response'] for x in details))

    def test_pending_phone_cannot_suppress_disclosure_check(self):
        self.fx.command('answer.save',meaning='contact.phone.preference',scope=dict(purpose='application'),units={},disposition='pending',value=None,evidence='Open phone preference question.',response_state='pending')
        self.fx.save('Improved processing by 25%. Phone +1 202 555 0142',review=False)
        issues=self.fx.tasks.query('selection',record_id='packet_one')['assessment']['issues']
        self.assertTrue({'CONTACT_DISCLOSURE_BLOCKED','CONTACT_PREFERENCE_UNKNOWN'}&{x['code'] for x in issues})

    def test_decimal_heads_next_to_non_latin_words_are_not_lost(self):
        phrase='\\u04413,2% \\u0434\\u043e1,8%'.encode().decode('unicode_escape')
        self.assertEqual(['3,2','1,8'],number_tokens(phrase));self.assertEqual(['-3.2','+1.8'],number_tokens('from-3.2 to+1.8'))
        self.fx.command('source.capture',id='source_one',locator='https://northstar.example/team',excerpt='Morgan Example leads product. Alex Example reduced defects from 3,2% to 1,8%.',observed_at='2026-10-24T00:00:00Z',readable=True)
        self.fx.command('claim.save',id='claim_one',assertion='Reduced defects from 3,2% to 1,8%.',meaning='Personal reduction in defect rate from 3,2% to 1,8%.',source_ids=['source_one'],confirmation='confirmed',disclosure='allowed')
        self.fx.command('packet.save',packet_id='packet_one',used_claim_ids=['claim_one'],documents=[dict(slot=slot,text=phrase if slot=='resume' else 'Specific supported contribution.') for slot in ('resume','message','dossier','interview')],review=dict(findings='Compared exact decimal tokens.',limitations='Mechanical numeric check does not prove causal meaning.',tone_findings='Factual wording.',claim_spans=[dict(claim_id='claim_one',text=phrase)],coverage=[dict(claim_id='claim_one',disposition='included')]))
        self.assertTrue(self.fx.tasks.query('selection',record_id='packet_one')['assessment']['prepared'])

    def test_introduction_display_preference_is_persistent_and_grants_no_permission(self):
        before=self.fx.tasks.context();self.assertFalse(before['preferences']['introduction_shown']);self.assertFalse(before['runtime']['installed']);self.assertIsNone(before['recent_job_search'])
        revision=before['revision'];self.fx.command('preferences.set',introduction_shown=True)
        from career.facade import Tasks
        resumed=Tasks(self.temp.name).context();self.assertTrue(resumed['preferences']['introduction_shown']);self.assertEqual('system',resumed['preferences']['theme']);self.assertEqual('en',resumed['preferences']['ui_locale']);self.assertEqual(before['research'],resumed['research']);self.assertEqual(revision+1,resumed['revision'])
        self.fx.command('preferences.set',theme='dark');self.assertTrue(self.fx.tasks.context()['preferences']['introduction_shown'])
        with self.assertRaises(CareerError):self.fx.command('preferences.set',introduction_shown='yes')
        self.assertFalse(self.fx.tasks.query('research-check')['allowed'])

    def test_catalog_and_nested_examples_are_available_without_source_inspection(self):
        catalog=schema();self.assertEqual(set(SCHEMAS),{x['intent'] for x in catalog['intents']});self.assertLess(len(canonical(catalog).encode()),65536)
        for intent in SCHEMAS:
            detail=schema(intent);self.assertEqual('object',detail['input_schema']['type']);self.assertLess(len(canonical(detail).encode()),65536)
            for i,example in enumerate(detail['examples']):Command.parse(dict(request_id='example_'+str(i),expected_revision=0,intent=intent,input=example))
        detail=schema('packet.save');self.assertIn('claim_spans',detail['input_schema']['properties']['review']['properties'])
        self.assertIn('pending',schema('answer.save')['input_schema']['properties']['disposition']['enum'])
        result=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve().parents[1]/'scripts/career.py'),'--workspace',self.temp.name,'schema'],capture_output=True,text=True)
        self.assertEqual(0,result.returncode,result.stderr);self.assertIn('research.control',{x['intent'] for x in json.loads(result.stdout)['intents']})

if __name__=='__main__':unittest.main()
