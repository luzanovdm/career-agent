"""Real document/selection transitions driven by raw synthetic conversation fixtures."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from test_state import AT, LATER
from test_search_cases import configured, request
from test_contact_preferences import preference, OLD, CURRENT
from workflow_fixtures import reviewed, baseline_audit
from test_achievements import fact
import career_search as search
import career_materials as materials
import career_achievements as achievements
cs=search.cs
FIXTURE=Path(__file__).parent/'fixtures/packet-conversation'


class ConsolidatedWorkflowTests(unittest.TestCase):
    def test_initial_cv_then_clarification_refreshes_two_packets_and_one_selection_reaches_every_format(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/"Private";cs.initialize_workspace(root);path=root/"Data/state.json"
            raw=(FIXTURE/'resume.md').read_text();claim=next(l[2:] for l in raw.splitlines() if l.startswith('- Team'))
            state=configured();state=cs.add_record(state,"answers",preference("202-555-0100"))
            state=fact(state,"team-result",claim,"team")
            state=achievements.capture(state,{"id":"team-saving","fact_id":"team-result","source_id":"source-user","source_locator":"Supplied resume bullet","original_text":claim,
                "metrics":[{"id":"saving","verbatim":"USD 57000 annual savings","units":["USD","annual"],"attribution":"team"}]})
            state=reviewed(state);path.write_text(cs.canonical_json(state));items=[]
            for n in range(2):
                item=request();item['id']='case-'+str(n);item['opportunity']['id']='role-'+str(n)
                item['opportunity']['identity']='demo:role-'+str(n);item['opportunity']['role_url']='https://northstar-demo.example/jobs/role-'+str(n)
                item['sources'][0]['id']='job-source-'+str(n);item['sources'][0]['locator']=item['opportunity']['role_url']
                item['opportunity']['source_ids']=[item['sources'][0]['id']];item['opportunity']['status_observations'][0]['source_id']=item['sources'][0]['id']
                item['form'].update(id='form-'+str(n),opportunity_id=item['opportunity']['id'],source_ids=[item['sources'][0]['id']])
                item['form']['fields'].append({'id':'phone','label':'Phone','control':'tel','help_text':'','choices':[],'required':False,'answer_state':'confirmed','answer':'202-555-0100','confirmation_evidence':'Initial user choice'})
                item['compensation']['source_id']=item['sources'][0]['id']
                doc=item['documents']['resume'];doc['text']='# Alex Rivers\nPhone: 202-555-0100\n\n'+state['facts'][0]['statement']
                audit=baseline_audit(configured(),doc['text']);audit['target_role']=item['opportunity']['id']
                audit['entries'].append({'achievement_id':'team-saving','decision':'preserve_pending','reason':'Personal contribution to team result remains unclear','rendered_text':'','fact_ids':[],'meaning_fields':[],'metrics':[]})
                _,audit=reviewed(state,audit,doc['text']);doc['adaptation_audit']=audit;items.append(item)
            initial=search.prepare_batch(path,root,items,0);self.assertFalse(initial['completed'])
            old=cs.read_state(path);old_attempts={c['id']:c['attempt_id'] for c in old['search_cases']};old_forms=copy.deepcopy(old['forms'])
            def clarification(state):
                state=cs.reviewed_update(state,{'operation':'supersede_answer','answer_id':'phone-old','replacement':preference('202-555-0199',identifier='phone-current',at=LATER)},'Later user contact choice')
                state=achievements.clarify(state,{'fact_id':'team-result','question_key':'achievement.metric_context','disposition':'answered','at':LATER,'evidence':'Later user message in messages.md'})
                state=cs.add_record(state,'achievement_interpretations',{'id':'saving-meaning','achievement_id':'team-saving','version':1,'at':LATER,'fields':{
                    'contribution':{'status':'supported','text':'Designed and implemented importer retries and operator review workflow','fact_ids':['fact-a']},
                    'problem':{'status':'supported','text':'Reconciliation workflow','fact_ids':['fact-a']},
                    'metric_context':{'status':'supported','text':'Team total over one reporting year from internal reports','fact_ids':['team-result']}}})
                return reviewed(state)
            state=cs.transact(path,clarification,old['revision']);edits=[]
            for item in items:
                doc=copy.deepcopy(item['documents']['resume']);wording='Implemented retry handling; the team reported USD 57000 annual savings.'
                doc['text']='# Alex Rivers\nPhone: 202-555-0199\n\n'+state['facts'][0]['statement']+'\n\n'+wording
                doc['fact_ids'].append('team-result');audit=copy.deepcopy(doc['adaptation_audit'])
                audit['entries'][-1]={'achievement_id':'team-saving','decision':'qualify','reason':'Keep secondary team impact with honest attribution','rendered_text':wording,'fact_ids':['fact-a','team-result'],'meaning_fields':['contribution','problem'],
                    'metrics':[{'metric_id':'saving','decision':'qualify','rendered_text':'the team reported USD 57000 annual savings','fact_ids':['team-result'],'claim_scope':'team','scope_phrase':'the team'}]}
                _,audit=reviewed(state,audit,doc['text']);doc['adaptation_audit']=audit
                edits.append({'case_id':item['id'],'at':LATER,'reason':'Later user clarification and contact choice','documents':{'resume':doc}})
            # One continuation operation updates all selected packets and returns their actual content.
            result=search.prepare_batch(path,root,edits,state['revision']);self.assertTrue(result['all_updated']);self.assertTrue(result['completed']);self.assertEqual(result['next_preparation'],[])
            state=cs.read_state(path);self.assertEqual(state['attempts'],[])
            for old_form in old_forms:self.assertIn(old_form,state['forms'])
            for packet in result['packets']:
                self.assertNotEqual(packet['attempt_id'],old_attempts[packet['id']])
                form=next(f for f in state['forms'] if f['id']==next(c['form_id'] for c in state['search_cases'] if c['id']==packet['id']))
                self.assertEqual(form['fields'][-1]['answer'],'202-555-0199')
            handoff=search.export_delivery(path,root,{'case_ids':[e['case_id'] for e in edits],'refresh_id':result['refresh_id'],'output_relative':'Reports/Review-current','formats':['portal','archive']})
            self.assertTrue(handoff['delivered']);self.assertTrue(handoff['completed'])
            portal=Path(handoff['outputs']['portal']).parent
            with zipfile.ZipFile(handoff['outputs']['archive']) as archive:
                selection=json.loads(archive.read('selection.json'));self.assertEqual(selection['state_sha256'],handoff['state_sha256'])
                for packet in handoff['packets']:
                    for doc in packet['documents']:
                        self.assertEqual((portal/'documents'/(doc['sha256']+'.md')).read_bytes(),doc['text'].encode())
                        members=[name for name in archive.namelist() if name.endswith('/'+doc['slot']+'.md')]
                        self.assertTrue(any(archive.read(name)==doc['text'].encode() for name in members))
                    resume=next(d for d in packet['documents'] if d['slot']=='resume')['text']
                    self.assertIn('USD 57000',resume);self.assertIn('202-555-0199',resume);self.assertNotIn('202-555-0100',resume)
            self.assertTrue(all(Path(d['path']).suffix=='.md' for packet in handoff['packets'] for d in packet['documents']))

    def test_readback_failure_cannot_leave_success_flags_set(self):
        from test_packet_refresh import PacketRefreshTests
        with tempfile.TemporaryDirectory() as directory:
            root,path,item=PacketRefreshTests().fixture(directory);original=search.verify_case
            def remove(*args):
                check=original(*args);state=cs.read_state(path);materials.material_file(root,state['materials'][0]).unlink();return check
            with mock.patch.object(search,'verify_case',side_effect=remove):receipt=search.deliver_packets(path,root,[item['id']])
            self.assertFalse(receipt['all_updated']);self.assertFalse(receipt['completed']);self.assertEqual(receipt['ready_for_review'],0)

    def test_local_phone_forms_and_tel_links_respect_omit_without_matching_achievement_measurements(self):
        state=cs.add_record(configured(),'answers',preference(None,'omit'))
        for value in ('Phone: 202-555-0100','Phone: (202) 555-0100','[Call](tel:2025550100)','202-555-0100'):
            self.assertFalse(materials.review_phone(state,[value],at=AT)['ready'],value)
        self.assertTrue(materials.review_phone(state,['Reduced parsing from 700 ms to 240 ms; team annual savings USD 57000.'],at=AT)['ready'])

    def test_full_refresh_versions_corrected_form_answers_without_changing_role(self):
        from test_packet_refresh import PacketRefreshTests
        for supplied_id in ('new-form','new-observation'):
            with self.subTest(supplied_id=supplied_id),tempfile.TemporaryDirectory() as directory:
                root,path,item=PacketRefreshTests().fixture(directory);state=cs.read_state(path);old_form=copy.deepcopy(state['forms'][0])
                item['form']['id']=supplied_id;item['form']['fields'][0].update(answer='Alex Rivers',confirmation_evidence='User corrected display name')
                item['revision_reason']='Use the corrected user-supplied form answer'
                result=search.prepare_case(path,root,item,state['revision'],refresh=True);self.assertTrue(result['completed'])
                state=cs.read_state(path);self.assertIn(old_form,state['forms']);self.assertNotEqual(state['search_cases'][0]['form_id'],old_form['id'])
                self.assertEqual(len(state['opportunities']),1)

    def test_local_omitted_phone_prevents_ready_packet_and_outgoing_archive(self):
        from test_packet_refresh import PacketRefreshTests
        with tempfile.TemporaryDirectory() as directory:
            root,path,item=PacketRefreshTests().fixture(directory)
            state=cs.transact(path,lambda s:cs.add_record(s,'answers',preference(None,'omit')),cs.read_state(path)['revision'])
            doc=item['documents']['resume'];doc['text']+='\nPhone: (202) 555-0100\n';doc['adaptation_audit']=baseline_audit(state,doc['text'])
            result=search.prepare_case(path,root,{'case_id':item['id'],'at':AT,'reason':'Refresh contact header','documents':{'resume':doc}},state['revision'],refresh=True)
            self.assertFalse(result['completed']);self.assertFalse(result['all_updated'])
            state=cs.read_state(path);destination=root/'outgoing.zip'
            with self.assertRaises(cs.Invalid):materials.package_attempt(state,root,state['search_cases'][0]['attempt_id'],['resume'],destination,AT)
            self.assertFalse(destination.exists())

    def test_focused_batch_keeps_unmapped_selected_case_in_delivery_coverage(self):
        from test_packet_refresh import PacketRefreshTests
        with tempfile.TemporaryDirectory() as directory:
            root,path,item=PacketRefreshTests().fixture(directory);state=cs.read_state(path)
            result=search.prepare_batch(path,root,[{'case_id':item['id'],'at':AT,'reason':'Review selected packets'}, {'case_id':'unmapped-legacy','at':AT,'reason':'Review selected packets'}],state['revision'])
            self.assertEqual(result['selected'],2);self.assertFalse(result['all_updated']);self.assertFalse(result['completed'])
            self.assertIn('unmapped-legacy',result['next_preparation']);self.assertTrue(any(row.get('error') for row in result['preparation_outcomes']))

    def test_rejected_requested_edit_cannot_be_completed_from_an_old_ready_packet(self):
        from test_packet_refresh import PacketRefreshTests
        with tempfile.TemporaryDirectory() as directory:
            root,path,item=PacketRefreshTests().fixture(directory);state=cs.read_state(path);old=state['search_cases'][0]['attempt_id']
            wrong_form=copy.deepcopy(state['forms'][0]);wrong_form['opportunity_id']='wrong-role'
            result=search.prepare_batch(path,root,[{'case_id':item['id'],'at':AT,'reason':'Correct the form answers','form':wrong_form}],state['revision'])
            self.assertFalse(result['all_updated']);self.assertFalse(result['completed']);self.assertEqual(result['reviewed_current'],0)
            self.assertEqual(result['next_preparation'],[item['id']]);self.assertFalse(result['preparation_outcomes'][0]['saved'])
            self.assertFalse(result['packets'][0]['requested_edit_saved']);self.assertIn('Previous packet',result['packets'][0]['label'])
            self.assertTrue(result['packets'][0]['documents']);self.assertEqual(cs.read_state(path)['search_cases'][0]['attempt_id'],old)

    def test_edit_batch_reports_view_failure_without_requesting_another_content_rebuild(self):
        from test_packet_refresh import PacketRefreshTests
        with tempfile.TemporaryDirectory() as directory:
            root,path,item=PacketRefreshTests().fixture(directory);state=cs.read_state(path)
            with mock.patch.object(search.snapshot,'export_snapshot',side_effect=OSError('Synthetic spreadsheet failure')):
                result=search.prepare_batch(path,root,[{'case_id':item['id'],'at':AT,'reason':'Review current text'}],state['revision'])
            self.assertTrue(result['all_updated']);self.assertFalse(result['completed']);self.assertFalse(result['view_refreshed'])
            self.assertEqual(result['next_preparation'],[]);self.assertTrue(result['presentation_errors']);self.assertTrue(result['preparation_outcomes'][0]['saved'])
            self.assertEqual(cs.read_state(path)['search_cases'][0]['phase'],'saved')

    def test_presentation_failure_keeps_valid_state_and_marks_delivery_incomplete(self):
        from test_packet_refresh import PacketRefreshTests
        with tempfile.TemporaryDirectory() as directory:
            root,path,item=PacketRefreshTests().fixture(directory);raw=path.read_bytes()
            with mock.patch.object(search.snapshot,'export_snapshot',side_effect=OSError('Synthetic view failure')):
                result=search.export_delivery(path,root,{'case_ids':[item['id']],'output_relative':'Reports/Failed','formats':['portal','archive']})
            self.assertFalse(result['delivered']);self.assertFalse(result['completed']);self.assertEqual(path.read_bytes(),raw)
            self.assertTrue((root/'Reports/Failed/INCOMPLETE.json').exists())


if __name__ == '__main__':unittest.main()
