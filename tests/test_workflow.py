"""Synthetic cross-phase state contracts, separate from host-driven extraction/research."""
import copy
import sys
import tempfile
from pathlib import Path
import unittest
from test_state import ROOT, AT, LATER, base
sys.path.insert(0,str(ROOT/'scripts'))
import career_state as cs
import career_snapshot as snapshot

class WorkflowTests(unittest.TestCase):
    def test_fit_projection_preserves_legacy_assessment_and_independent_statuses(self):
        with tempfile.TemporaryDirectory() as directory:
            state=base();role=state['opportunities'][0]
            role.update(assessment='Adjacent fit',assessment_reason='Transferable component ownership; specific framework unverified.')
            result=cs.fit_assessment(role)
            self.assertEqual(result['state'],'assessed');self.assertEqual(result['summary'],'Adjacent fit')
            _,rows,_=snapshot.view_data(state,Path(directory),LATER)
            self.assertIn('Adjacent fit',rows[0]['values'][3]);self.assertIn('framework unverified',rows[0]['values'][3])
            self.assertNotIn('reject',rows[0]['values'][5].lower());self.assertNotIn('declin',rows[0]['values'][5].lower())
            self.assertEqual(state['attempts'],[]);self.assertEqual(state['responses'],[])
            self.assertEqual(role['status_observations'][0]['status'],'open')
            for shape in ({'fit_summary':'Supported fit'}, {'assessment':{'summary':'Review fit','reason':'Scope differs'}}, {'assessment_reason':'Existing assessment explanation'}):
                fresh={k:v for k,v in role.items() if k not in {'assessment','assessment_reason','fit_summary'}};fresh.update(shape)
                self.assertEqual(cs.fit_assessment(fresh)['state'],'assessed')
            fresh={k:v for k,v in role.items() if k not in {'assessment','assessment_reason','fit_summary'}}
            self.assertEqual(cs.fit_display(fresh),'Assessment pending')
            fresh.update(assessment='Old fit',fit_assessment={'state':'pending'})
            self.assertEqual(cs.fit_display(fresh),'Assessment pending')


class ReadinessLifecycleTests(unittest.TestCase):
    def ready_state(self):
        from test_search_cases import configured
        return configured()

    def start(self, state=None, context='run-a'):
        return cs.control_change(state or self.ready_state(), 'start', 'Synthetic explicit scoped request', 'One bounded synthetic research task',
                                 True, context, AT, LATER)

    def test_intake_is_explicit_and_reuses_resolved_decisions(self):
        state=self.start(); self.assertTrue(cs.research_allowed(state,'run-a',AT))
        state['search_config']['search_setup'].pop('schedule')
        self.assertEqual(cs.search_prerequisites(state)['missing'],['schedule'])
        self.assertFalse(cs.research_allowed(state,'run-a',AT))
        # Reading sources, validating and saving an intake checkpoint do not need research permission.
        cs.validate(state); self.assertTrue(state['facts'])
        state['search_config']['search_setup']['schedule']={'disposition':'skipped','value':None,'evidence':'Synthetic user explicitly skipped hours for now','at':AT}
        self.assertTrue(cs.research_allowed(state,'run-a',AT))
        self.assertEqual(cs.search_prerequisites(state)['missing'],[])
        state['search_config']['search_setup']['target']['value']=''
        with self.assertRaises(cs.Invalid):cs.validate(state)

    def test_explicit_no_compensation_preference_is_unknown_not_invented_pay(self):
        from test_search_cases import search
        state=self.ready_state(); config=state['search_config'];config['salary_floor']=None;config['salary_goal']=None;config.pop('income_policy')
        config['search_setup']['compensation'].update(disposition='no_preference',value=None,evidence='Synthetic explicit no-pay-filter choice')
        self.assertTrue(cs.search_prerequisites(state)['ready'])
        self.assertEqual(search.income_assessment(config,{'kind':'unpublished'})['status'],'unknown')
        config['search_setup']['compensation']['disposition']='pending'
        self.assertFalse(cs.search_prerequisites(state)['ready'])
        self.assertEqual(search.income_assessment(config,{'kind':'unpublished'})['status'],'intake_missing')

    def test_live_continuation_does_not_reconfirm_each_step(self):
        state=self.start(); before=copy.deepcopy(state)
        for _ in range(4):self.assertTrue(cs.research_allowed(state,'run-a',AT))
        self.assertEqual(cs.reconcile_session(state,'run-a','Same live task',AT),before)
        self.assertEqual(state,before)
        self.assertFalse(cs.research_allowed(state,'run-a',LATER))

    def test_stop_revokes_and_explicit_resume_preserves_scope(self):
        state=self.start();stopped=cs.control_change(state,'stop','Synthetic explicit stop','',True,at=AT)
        self.assertFalse(stopped['control']['authorized']);self.assertTrue(stopped['control']['paused'])
        self.assertFalse(cs.research_allowed(stopped,'run-a',AT))
        with self.assertRaises(cs.Invalid):cs.control_change(stopped,'resume','No actual new choice','',False,'run-b',AT,LATER)
        resumed=cs.control_change(stopped,'resume','Synthetic explicit resume','',True,'run-b',AT,LATER)
        self.assertTrue(cs.research_allowed(resumed,'run-b',AT));self.assertEqual(resumed['control']['scope'],state['control']['scope'])
        self.assertFalse(cs.research_allowed(resumed,'run-a',AT))

    def test_forced_interruption_needs_no_cleanup_to_fail_closed_in_new_context(self):
        state=self.start();serialized=cs.strict_json_loads(cs.canonical_json(state))
        self.assertTrue(serialized['control']['authorized']);self.assertFalse(serialized['control']['paused'])
        self.assertFalse(cs.research_allowed(serialized,'new-invocation',AT))
        self.assertFalse(cs.research_allowed(serialized,None,AT))
        recovered=cs.reconcile_session(serialized,'new-invocation','New invocation after interrupted host task',AT)
        cs.validate(recovered);self.assertTrue(recovered['control']['paused']);self.assertFalse(recovered['control']['authorized'])
        self.assertEqual(recovered['control']['run']['status'],'interrupted');self.assertEqual(recovered['facts'],state['facts'])
        self.assertEqual(cs.reconcile_session(recovered,'new-invocation','Repeated read-only inspection',AT),recovered)
        same_context_kill=cs.reconcile_session(state,'run-a','Host reports forced interruption',AT,True)
        self.assertFalse(cs.research_allowed(same_context_kill,'run-a',AT))

    def test_legacy_authorization_is_readable_but_not_current_permission(self):
        state=self.ready_state();state['control']={'authorized':True,'paused':False,'scope':'Legacy scope','history':[
            {'action':'start','at':AT,'scope':'Legacy scope','evidence':'Old explicit decision'}]}
        cs.validate(state);self.assertFalse(cs.research_allowed(state,'new-run',AT))
        with self.assertRaises(cs.Invalid):cs.control_change(state,'resume','Synthetic resume','',True)
        resumed=cs.control_change(state,'resume','Synthetic new resume','',True,'new-run',AT,LATER)
        self.assertTrue(cs.research_allowed(resumed,'new-run',AT))

    def test_run_provenance_and_history_cannot_contradict_flags(self):
        state=self.start();state['control']['run']['context_id']='invented'
        with self.assertRaises(cs.Invalid):cs.validate(state)
        self.assertFalse(cs.research_allowed(state,'invented',AT))
        state=self.start();state['control']['run']['expires_at']=AT
        with self.assertRaises(cs.Invalid):cs.validate(state)

    def test_missing_coverage_and_semantic_review_do_not_bypass_empty_inventory(self):
        import career_achievements as ca
        from test_search_cases import request,search
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'Private';cs.initialize_workspace(root);path=root/'Data/state.json'
            state=self.ready_state();state['achievement_evidence']=[];state['achievement_interpretations']=[];state['profile'].pop('evidence_review')
            path.write_text(cs.canonical_json(state));item=request();item['documents']['resume'].pop('adaptation_audit')
            result=search.prepare_case(path,root,item,0)
            self.assertTrue(result['saved']);self.assertFalse(result['completed'])
            saved=cs.read_state(path);self.assertTrue(saved['materials']);self.assertTrue(saved['application_attempts'])
            check=search.verify_case(saved,root,'case-a');self.assertFalse(check['draft_ready'])
            audit={'target_role':'new-role','at':AT,'entries':[]}
            checked=ca.audit_resume(state,'# Working draft',audit)
            self.assertTrue(checked['valid']);self.assertFalse(checked['ready'])
            self.assertFalse(checked['evidence_coverage']['ready']);self.assertEqual(checked['semantic_review']['status'],'pending')

    def test_current_semantic_review_and_source_inventory_are_required_separately(self):
        import career_achievements as ca
        from workflow_fixtures import baseline_audit
        state=self.ready_state();audit=baseline_audit(state);text=state['facts'][0]['statement']
        self.assertTrue(ca.audit_resume(state,text,audit)['ready'])
        without=copy.deepcopy(audit);without.pop('semantic_review')
        result=ca.audit_resume(state,text,without);self.assertTrue(result['valid']);self.assertFalse(result['ready'])
        changed=copy.deepcopy(state);changed['facts'][0]['statement']+=' Additional supported scope.'
        self.assertFalse(ca.evidence_coverage(changed)['ready'])
        self.assertFalse(ca.audit_resume(changed,text,audit)['ready'])
        conditional=copy.deepcopy(audit);conditional['semantic_review']['unresolved_fields']=['Meaning of personal versus team contribution']
        self.assertFalse(ca.audit_resume(state,text,conditional)['ready'])
        stale=copy.deepcopy(audit);stale['semantic_review']['interpretation_ids']=[]
        self.assertFalse(ca.audit_resume(state,text,stale)['ready'])

    def test_unreadable_sources_remain_conditional_without_repeating_answered_questions(self):
        import career_achievements as ca
        state=self.ready_state();review=copy.deepcopy(state['profile']['evidence_review']);review.pop('input_sha256');review['status']='unreadable'
        state=ca.review_sources(state,review);self.assertFalse(ca.evidence_coverage(state)['ready'])
        self.assertEqual(ca.clarification_plan(state,['baseline-achievement'])['groups'],[])
        invalid=copy.deepcopy(review);invalid['items'][0]['achievement_ids']=[]
        with self.assertRaises(cs.Invalid):ca.review_sources(state,invalid)

    def test_three_synthetic_directions_share_same_intake_and_packet_gates(self):
        from test_search_cases import request,search
        for title in ('Product Designer','Quality Engineer','Infrastructure Engineer'):
            with self.subTest(title=title),tempfile.TemporaryDirectory() as directory:
                state=self.ready_state();state['search_config']['search_setup']['target']['value']=title
                item=request();item['opportunity']['title']=title
                state['search_config']['search_setup']['compensation']['disposition']='pending'
                root=Path(directory)/'Private';cs.initialize_workspace(root);path=root/'Data/state.json';path.write_text(cs.canonical_json(state))
                result=search.prepare_case(path,root,item,0)
                self.assertTrue(result['saved']);self.assertFalse(result['completed']);self.assertEqual(result['new_ready'],0)
                state=cs.read_state(path);state['search_config']['search_setup']['compensation']['disposition']='confirmed';path.write_text(cs.canonical_json(state))
                snapshot.export_snapshot(path,root,AT)
                result=search.case_report(path,root,'search-a',1)
                self.assertTrue(result['completed']);self.assertEqual(result['new_ready'],1)
                self.assertEqual(state['attempts'],[])

    def test_cli_context_check_and_reconciliation_are_revision_safe(self):
        import subprocess,json
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'state.json';path.write_text(cs.canonical_json(self.ready_state()))
            tool=str(ROOT/'scripts/career_state.py')
            def run(*args):return subprocess.run([sys.executable,'-B',tool,*map(str,args)],capture_output=True,text=True,cwd=directory)
            start=run('control',path,'start','--evidence','Synthetic actual start','--scope','Bounded test','--context-id','cli-run','--user-confirmed')
            self.assertEqual(start.returncode,0,start.stderr)
            self.assertEqual(run('research-check',path,'--context-id','cli-run').returncode,0)
            self.assertEqual(run('research-check',path,'--context-id','new-cli-run').returncode,3)
            stale=run('reconcile-session',path,'--context-id','new-cli-run','--evidence','New invocation','--expected-revision',0)
            self.assertEqual(stale.returncode,2)
            fixed=run('reconcile-session',path,'--context-id','new-cli-run','--evidence','New invocation','--expected-revision',1)
            self.assertEqual(fixed.returncode,0,fixed.stderr)
            self.assertEqual(run('research-check',path,'--context-id','cli-run').returncode,3)
            self.assertTrue(cs.read_state(path)['control']['paused'])


class SemanticBindingTests(unittest.TestCase):
    def test_semantic_attestation_is_invalidated_by_exact_text_target_or_selection_change(self):
        import career_achievements as ca
        from test_search_cases import configured
        from workflow_fixtures import baseline_audit, reviewed
        state=configured();text=state['facts'][0]['statement'];audit=baseline_audit(state)
        self.assertTrue(ca.audit_resume(state,text,audit)['ready'])
        for mode in ('appended_claim','changed_selected_wording','header_only','target','selection','unbound_legacy'):
            with self.subTest(mode=mode):
                edited=copy.deepcopy(audit);draft=text
                if mode=='appended_claim':draft+=' Led company-wide product strategy and hiring.'
                if mode=='changed_selected_wording':
                    draft+=' Led company-wide product strategy and hiring.'
                    edited['entries'][0]['rendered_text']=draft
                if mode=='header_only':draft='# Updated resume\n\n'+text
                if mode=='target':edited['target_role']='different-exact-role'
                if mode=='selection':edited['entries'][0]['reason']='Different selection emphasis after review'
                if mode=='unbound_legacy':
                    edited['semantic_review'].pop('draft_sha256');edited['semantic_review'].pop('selection_sha256')
                result=ca.audit_resume(state,draft,edited)
                self.assertTrue(result['valid']);self.assertFalse(result['ready']);self.assertFalse(result['semantic_review']['ready'])
                self.assertTrue(any('stale or unbound' in issue for issue in result['semantic_review']['issues']))
        # A deliberately renewed review can approve a supported formatting/selection revision.
        draft='# Updated resume\n\n'+text
        state,renewed=reviewed(state,audit,draft)
        self.assertTrue(ca.audit_resume(state,draft,renewed)['ready'])
        malformed=copy.deepcopy(renewed);malformed['semantic_review']['draft_sha256']='not-a-digest'
        with self.assertRaises(cs.Invalid):ca.audit_resume(state,draft,malformed)

    def test_stale_semantic_review_saves_packet_without_completing_new_quota(self):
        from test_search_cases import configured,request,search
        for mode in ('added_claim','selection_changed'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)/'Private';cs.initialize_workspace(root);path=root/'Data/state.json';state=configured();path.write_text(cs.canonical_json(state))
                item=request();resume=item['documents']['resume']
                if mode=='added_claim':
                    resume['text']+=' Led company-wide product strategy and hiring.'
                    resume['adaptation_audit']['entries'][0]['rendered_text']+=' Led company-wide product strategy and hiring.'
                else:resume['adaptation_audit']['entries'][0]['reason']+=' Selection changed after review.'
                result=search.prepare_case(path,root,item,0)
                self.assertTrue(result['saved']);self.assertFalse(result['completed']);self.assertEqual(result['new_ready'],0)
                saved=cs.read_state(path);check=search.verify_case(saved,root,'case-a')
                self.assertFalse(check['draft_ready']);self.assertFalse(check['achievement_review']['semantic_review']['ready'])
                material=next(m for m in saved['materials'] if m['kind']=='resume')
                self.assertEqual((root/material['path']).read_bytes(),resume['text'].encode('utf-8'))
                self.assertEqual(saved['attempts'],[])

    def test_exact_crlf_draft_binding_survives_saved_packet_readback(self):
        from test_search_cases import configured,request,search
        from workflow_fixtures import baseline_audit
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'Private';cs.initialize_workspace(root);path=root/'Data/state.json';state=configured();path.write_text(cs.canonical_json(state))
            item=request();resume=item['documents']['resume'];resume['text']=resume['text'].replace('\n','\r\n')
            resume['adaptation_audit']=baseline_audit(state,resume['text'])
            result=search.prepare_case(path,root,item,0);self.assertTrue(result['completed'])
            self.assertTrue(search.verify_case(cs.read_state(path),root,'case-a')['achievement_review']['semantic_review']['ready'])


if __name__ == "__main__":
    unittest.main()
