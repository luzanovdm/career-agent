"""Synthetic discovery-to-packet completion and fixed paged portal regressions."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from test_state import ROOT, AT
from test_search_cases import configured, request, search, cs
sys.path.insert(0, str(ROOT/'scripts'))
import career_portal as portal
from workflow_fixtures import reviewed


def discovery(item):
    return {k: copy.deepcopy(v) for k,v in item.items() if k not in {'documents','resume_reference'}}


def records(count):
    for index in range(count):
        yield {'id': hashlib.sha256(str(index).encode()).hexdigest(), 'company': 'Company '+str(index), 'role': 'Synthetic engineer',
            'focus': 'Supported synthetic work', 'person': '', 'packet_status': 'incomplete', 'opportunity_id': 'role-'+str(index),
            'kind': 'vacancy', 'fit': 'Pending review', 'concerns': ['Packet not prepared'], 'links': [], 'sources': [], 'source_date': AT,
            'documents': [], 'fields': [], 'form_status': 'Not observed'}


class PortalTests(unittest.TestCase):
    def workspace(self,directory):
        root=Path(directory)/'Private';cs.initialize_workspace(root);state=root/'Data/state.json';state.write_text(cs.canonical_json(configured()));return root,state

    def test_normal_batch_continues_discovery_to_all_actual_markdown_packets(self):
        with tempfile.TemporaryDirectory() as directory:
            root,path=self.workspace(directory)
            batch={'id':'search-a','at':AT,'requested_new':2,'scope':'Two new application cases including Markdown review packets','evidence':'Synthetic explicit search request'}
            state=cs.transact(path,lambda s:search.begin_batch(s,batch),0)
            first=request(requested_new=2);second=copy.deepcopy(first);second['id']='case-b';second['opportunity'].update(id='role-b',identity='northstar:second-role',role_url='https://northstar-demo.example/jobs/second-role')
            second['opportunity'].update(kind='company_outreach',identity='northstar:integrations-outreach',role_url='https://northstar-demo.example/contact',outreach_need='Investigate a supported integration reliability need',contact_route={'url':'https://northstar-demo.example/contact','source_id':'source-contact','checked_at':AT},source_ids=['source-contact'])
            second['sources'][0].update(id='source-contact',locator='https://northstar-demo.example/contact')
            second['opportunity']['status_observations'][0].update(status='unknown',source_id='source-contact')
            second['form']['source_ids']=['source-contact'];second['compensation']['source_id']='source-contact'
            second['form'].update(id='form-b',opportunity_id='role-b')
            audit=second['documents']['resume']['adaptation_audit'];audit['target_role']='role-b'
            second['documents']['resume']['adaptation_audit']=reviewed(state,audit,second['documents']['resume']['text'])[1]
            for item in [first,second]:
                item['interview_preparation']=[{'id':'prep-'+item['id'],'opportunity_id':item['opportunity']['id'],'language':'English','question':'How did you handle importer retries?','outline':'Explain the confirmed retry mechanism and personal contribution.','question_status':'practice_hypothesis','fact_ids':['fact-a'],'source_ids':['source-user'],'pressure_points':['Clarify team outcome versus personal work.'],'employer_questions':['What does successful reliability work look like?'],'unknowns':['Current team practices are not yet verified.']}]
            for item in [first,second]:
                result=search.prepare_case(path,root,discovery(item),cs.read_state(path)['revision'],discovery_only=True)
                self.assertTrue(result['saved']);self.assertFalse(result['completed']);self.assertEqual(set(result['missing_packet_slots']),search.SLOTS)
            pending=search.case_report(path,root,'search-a',1)
            self.assertEqual(pending['requested_new'],2);self.assertEqual(pending['new_ready'],0);self.assertEqual(pending['shortfall'],2)
            self.assertTrue(all(c['status']=='incomplete' for c in pending['cases']))
            ready=search.prepare_batch(path,root,[first,second],cs.read_state(path)['revision'])
            self.assertTrue(ready['completed']);self.assertEqual(ready['new_ready'],2);self.assertEqual(ready['next_preparation'],[])
            saved=cs.read_state(path);self.assertEqual(len(saved['opportunities']),2);self.assertEqual(saved['attempts'],[])
            self.assertEqual(len(saved['application_attempts']),2)
            for attempt in saved['application_attempts']:
                for pin in attempt['materials']:
                    material=next(m for m in saved['materials'] if m['id']==pin['material_id'])
                    self.assertEqual(Path(material['path']).suffix,'.md');self.assertTrue((root/material['path']).is_file())
                    if pin['slot']=='dossier':self.assertIn('Saved interview preparation',(root/material['path']).read_text())
            original_attempt=saved['search_cases'][0]['attempt_id']
            extra=copy.deepcopy(saved['interview_prep'][0]);extra.update(id='later-prep-version',outline='Later preparation must not silently replace a completed attempt.')
            saved=cs.transact(path,lambda s:cs.add_record(s,'interview_prep',extra),saved['revision'])
            search.prepare_case(path,root,first,saved['revision'])
            self.assertEqual(cs.read_state(path)['search_cases'][0]['attempt_id'],original_attempt)
            self.assertNotIn('later-prep-version',cs.read_state(path)['search_cases'][0]['interview_prep_ids'])
            exported=portal.export_portal(path,root,'search-a')
            manifest=json.loads((Path(exported['path']).parent/'snapshot.json').read_text());self.assertEqual(manifest['ready'],2)
            with self.assertRaises(cs.Invalid):portal.export_portal(path,root,'search-a')

    def test_batch_quota_remains_recorded_with_no_discoveries_or_packets(self):
        with tempfile.TemporaryDirectory() as directory:
            root,path=self.workspace(directory);batch={'id':'search-a','at':AT,'requested_new':30,'scope':'Thirty cases','evidence':'Synthetic request'}
            state=cs.transact(path,lambda s:search.begin_batch(s,batch),0)
            self.assertEqual(search.begin_batch(state,batch),state)
            with self.assertRaises(cs.Invalid):search.begin_batch(state,{**batch,'requested_new':1})
            report=search.case_report(path,root,'search-a',1)
            self.assertEqual(report['requested_new'],30);self.assertEqual(report['unrecorded_slots'],30);self.assertFalse(report['completed'])

    def test_discovery_is_idempotent_and_cannot_promote_another_exact_role(self):
        with tempfile.TemporaryDirectory() as directory:
            root,path=self.workspace(directory);item=request();stage=discovery(item)
            search.prepare_case(path,root,stage,0,discovery_only=True);before=path.read_bytes()
            search.prepare_case(path,root,stage,cs.read_state(path)['revision'],discovery_only=True);self.assertEqual(before,path.read_bytes())
            item['opportunity']['role_url']='https://northstar-demo.example/jobs/unrelated'
            with self.assertRaises(cs.Invalid):search.prepare_case(path,root,item,cs.read_state(path)['revision'])
            self.assertEqual(before,path.read_bytes())

    def test_unresolved_required_answer_stays_visible_after_bulk_preparation(self):
        with tempfile.TemporaryDirectory() as directory:
            root,path=self.workspace(directory);item=request();item['form']['fields'][0]['answer_state']='unknown';item['form']['fields'][0].pop('answer')
            result=search.prepare_batch(path,root,[item],0)
            self.assertFalse(result['completed']);self.assertEqual(result['next_preparation'],['case-a'])
            self.assertTrue(any('Required factual answer' in x for x in result['cases'][0]['unknowns']))
            result=portal.export_portal(path,root,'search-a');manifest=json.loads((Path(result['path']).parent/'snapshot.json').read_text())
            self.assertEqual(manifest['ready'],0);self.assertEqual(manifest['incomplete'],1)

    def test_paged_template_has_no_inline_campaign_data_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'portal';source=list(records(101));source[0]['company']='</script><img src=x onerror=alert(1)>'
            result=portal.write_portal(root,{'campaign_id':'synthetic','revision':1,'generated_at':AT,'title':'Synthetic campaign'},source)
            self.assertEqual(result['cases'],101)
            manifest=json.loads((root/'snapshot.json').read_text());self.assertEqual(manifest['chunks'],2)
            self.assertEqual(len(json.loads((root/'data/index-0.json').read_text())),100)
            self.assertEqual(len(json.loads((root/'data/index-1.json').read_text())),1)
            self.assertNotIn('onerror', (root/'OPEN.html').read_text());self.assertNotIn('</script>',(root/'data/index-0.js').read_text())
            self.assertEqual((root/'assets/style.css').read_bytes(),(ROOT/'templates/portal/style.css').read_bytes())
            with self.assertRaises(cs.Invalid):portal.write_portal(root,{},[])
            self.assertEqual(source[0]['company'],'</script><img src=x onerror=alert(1)>')

    def test_large_data_writer_bounds_index_size_and_startup_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'portal';start=time.monotonic()
            result=portal.write_portal(root,{'campaign_id':'synthetic','revision':1,'generated_at':AT,'title':'Synthetic campaign'},records(2000))
            self.assertEqual(result['cases'],2000);self.assertLess(time.monotonic()-start,15)
            self.assertLess((root/'data/manifest.js').stat().st_size,10000)
            self.assertLess((root/'data/index-0.js').stat().st_size,40000)
            self.assertLess((root/'OPEN.html').stat().st_size,5000)
            self.assertEqual(len(list((root/'data').glob('index-*.json'))),20)

    def test_export_rejects_escape_and_tampered_selected_material(self):
        with tempfile.TemporaryDirectory() as directory:
            root,path=self.workspace(directory);search.prepare_batch(path,root,[request()],0)
            with self.assertRaises(cs.Invalid):portal.export_portal(path,root,'search-a','../../outside')
            state=cs.read_state(path);material=state['materials'][0];p=root/material['path'];p.chmod(0o600);p.write_text('tampered')
            with self.assertRaises(cs.Invalid):portal.export_portal(path,root,'search-a')

    def test_portal_paths_are_explicitly_allowlisted_for_distribution(self):
        import career_updates as updates
        for path in ['scripts/career_portal.py','scripts/career_portal_assets.py']:self.assertEqual(updates.payload_path(path),path)
        for path in ['templates/portal/index.html','templates/portal/style.css','templates/portal/app.js','templates/portal/evil.js','templates/portal/../../evil.js','templates/portal/data.js']:
            with self.assertRaises(cs.Invalid):updates.payload_path(path)

    def test_bundled_portal_runs_outside_checkout_with_actual_packet(self):
        with tempfile.TemporaryDirectory() as directory:
            root,path=self.workspace(directory);search.prepare_batch(path,root,[request()],0)
            bundle=Path(directory)/'bundle'
            built=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/build_skill_bundle.py'),str(bundle)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            self.assertTrue((bundle/'scripts/career_portal_assets.py').is_file());self.assertFalse((bundle/'templates').exists())
            command=[sys.executable,'-B',str(bundle/'scripts/career_portal.py'),str(path),str(root),'search-a','--destination','Reports/Bundled']
            result=subprocess.run(command,cwd=directory,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            data=json.loads(result.stdout);self.assertEqual(data['ready'],1);self.assertTrue(Path(data['path']).is_file())
            self.assertEqual((Path(data['path']).parent/'assets/style.css').read_bytes(),(ROOT/'templates/portal/style.css').read_bytes())

    def test_concept_links_require_actual_observed_source_and_cannot_invent_url(self):
        state=configured();item=request()
        for source in item['sources']:state=cs.add_record(state,'sources',source)
        state=cs.add_record(state,'opportunities',item['opportunity'])
        source=copy.deepcopy(state['sources'][0]);source.update(id='concept-doc',locator='https://docs.northstar-demo.example/idempotency')
        source['observations']=[{'at':AT,'status':'not_applicable','primary':True,'evidence':'Synthetic documentation content checked for this fixture'}]
        state=cs.add_record(state,'sources',source)
        prep={'id':'prep-a','opportunity_id':'new-role','language':'English','question':'How do you reason about idempotency?','outline':'Explain the confirmed retry mechanism; do not invent production impact.','question_status':'practice_hypothesis','fact_ids':['fact-a'],'source_ids':['concept-doc','source-user'],'pressure_points':[],'employer_questions':[],
              'concept_links':[{'term':'idempotency','url':source['locator'],'source_id':'concept-doc','checked_at':AT,'kind':'official','reliability':'Synthetic primary documentation fixture'}]}
        saved=cs.add_record(state,'interview_prep',prep);self.assertEqual(saved['interview_prep'][-1]['concept_links'][0]['url'],source['locator'])
        for change in [{'url':'javascript:alert(1)'},{'url':'https://invented.example/term'},{'checked_at':'2020-01-01T12:00:00Z'},{'term':'An absent term'}]:
            bad=copy.deepcopy(prep);bad['concept_links'][0].update(change)
            with self.assertRaises(cs.Invalid):cs.add_record(state,'interview_prep',bad)

    def test_portal_refuses_state_drift_after_report_without_mixing_revision_and_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root,path=self.workspace(directory);search.prepare_batch(path,root,[request()],0)
            original=search.case_report
            def changed_report(*args):
                report=original(*args)
                def change(state):
                    candidate=copy.deepcopy(state);candidate['report_preferences']['results_only']=not candidate['report_preferences']['results_only'];return candidate
                cs.transact(path,change,cs.read_state(path)['revision'])
                return report
            before=cs.read_state(path)['revision']
            with mock.patch.object(search,'case_report',changed_report):
                with self.assertRaisesRegex(cs.Invalid,'State changed during portal export'):portal.export_portal(path,root,'search-a')
            self.assertEqual(cs.read_state(path)['revision'],before+1)
            self.assertFalse(list(root.glob('Reports/**/OPEN.html')))
            self.assertFalse((root/'Data/portal-identity.json').exists())

    def test_drift_during_or_after_render_invalidates_only_new_portal_not_state(self):
        for timing in ('during','after'):
            with self.subTest(timing=timing),tempfile.TemporaryDirectory() as directory:
                root,path=self.workspace(directory);search.prepare_batch(path,root,[request()],0);before=cs.read_state(path)['revision']
                target=root/'Reports/Racing';changed=False
                def mutate():
                    nonlocal changed
                    if changed:return
                    changed=True
                    def change(state):
                        candidate=copy.deepcopy(state);candidate['report_preferences']['results_only']=not candidate['report_preferences']['results_only'];return candidate
                    cs.transact(path,change,cs.read_state(path)['revision'])
                original=portal.data_file if timing=='during' else portal.write_portal
                def trigger(*args,**kwargs):
                    result=original(*args,**kwargs);mutate();return result
                with mock.patch.object(portal,'data_file' if timing=='during' else 'write_portal',trigger):
                    with self.assertRaisesRegex(cs.Invalid,'State changed during portal export'):portal.export_portal(path,root,'search-a','Reports/Racing')
                self.assertEqual(cs.read_state(path)['revision'],before+1)
                self.assertFalse((target/'OPEN.html').exists());self.assertTrue((target/'INCOMPLETE.html').exists())
                self.assertFalse((target/'data/manifest.js').exists())
                if timing=='after':self.assertFalse(json.loads((target/'snapshot.json').read_text())['completed'])

    def test_source_ignore_exception_is_narrow(self):
        rules=(ROOT/'.gitignore').read_text()
        self.assertIn('*.html',rules);self.assertIn('!/templates/portal/index.html',rules)
        self.assertEqual(sum(line.startswith('!') and 'html' in line for line in rules.splitlines()),1)

if __name__=='__main__':unittest.main()
