"""Independent-review reproductions: cross-owner uncertainty, links and legacy repair."""
import copy
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from test_outreach import AT, LATER, ROOT, base, attempt, contact, payload, variant, request, prepared, authorized, dispatch, report, grant, state_with_contact, out, cs


def contact_fixture():
    import test_outreach
    return test_outreach.PersonalContactReconciliationTests()


class ReviewBlockerTests(unittest.TestCase):
    def followup(self,state):
        return prepared(state,request('follow','outreach',purpose='follow_up',prior_application_acknowledgment='The earlier application attempt needs reconciliation',
            inbound_check={'checked_at':AT,'coverage':'complete','obsolete':False,'evidence':'Fictional scoped inbox review'}),payload(recipient=contact()['endpoint']))

    def test_uncertain_application_blocks_every_outreach_purpose_despite_acknowledgment_grant_and_inbound(self):
        state=cs.add_record(state_with_contact(),'attempts',attempt(outcome='uncertain'))
        for purpose in ('application','cold_introduction','follow_up'):
            candidate=prepared(state,request('follow-'+purpose,'outreach',purpose=purpose,prior_application_acknowledgment='Previous attempt acknowledged',inbound_check={'checked_at':AT,'coverage':'complete','obsolete':False,'evidence':'Synthetic read'}),payload(recipient=contact()['endpoint']))
            candidate=out.grant_permission(candidate,grant(candidate['outbound_actions'][0]),True)
            with self.assertRaisesRegex(cs.Invalid,'uncertain application'):
                out.transition(candidate,'follow-'+purpose,'ready',AT,'Acknowledgment cannot override uncertainty')
        state=cs.add_record(state,'attempts',attempt('resolution',outcome='not_sent',at=LATER,resolves_attempt_id='send-a',occurred_at=AT))
        retry=prepared(state,request('proved-unsent-retry','outreach'),payload(recipient=contact()['endpoint']))
        self.assertTrue(out.action_check(retry,retry['outbound_actions'][0],LATER)['allowed'])
        state=self.followup(state);state['outbound_actions'][0]['inbound_check']['checked_at']=LATER
        self.assertTrue(out.action_check(state,state['outbound_actions'][0],LATER)['allowed'])

    def test_imported_uncertainty_requires_evidenced_reviewed_mapping(self):
        state=state_with_contact();rows=[{'employer':'Northstar Demo','role':'API Engineer','role_url':'https://northstar-demo.example/jobs/api-1','status':'uncertain','date_text':'unknown','channel':'email','source_locator':'Fictional old list','source_kind':'user_list'}]
        state=cs.apply_history(state,cs.preview_history(state,rows),'Reviewed original uncertain observation')
        state=self.followup(state);self.assertFalse(out.action_check(state,state['outbound_actions'][0],AT)['allowed'])
        state=cs.add_record(state,'attempts',attempt('known-not-sent',outcome='not_sent'))
        state=cs.reviewed_update(state,{'operation':'reconcile_import_uncertainty','history_id':state['history_imports'][0]['id'],'attempt_id':'known-not-sent','at':AT,'evidence':'Fictional provider proves no acceptance for this original observation'},'Reviewed provider evidence')
        self.assertEqual(state['history_imports'][0]['status'],'uncertain')
        self.assertTrue(out.action_check(state,state['outbound_actions'][0],AT)['allowed'])

    def test_temporary_bounce_and_unknown_auth_never_clear_known_auth_failure(self):
        state=out.transition(dispatch(),'diagnostic-a','sent',AT,'Synthetic receipt')
        state=out.record_report(state,'diagnostic-a',report(outcome='auth_failure',authentication={'spf':'fail','dkim':'pass','dmarc':'fail'}))
        fingerprint=state['outbound_actions'][0]['inspection']['variant_sha256']
        state=prepared(state,request('later-test'))
        state=out.grant_permission(state,grant(state['outbound_actions'][-1],identifier='later-grant'),True)
        state=out.transition(state,'later-test','ready',LATER,'New authorized test')
        state=out.transition(state,'later-test','dispatching',LATER,'Durable claim',permission_id='later-grant',raw=payload())
        state=out.transition(state,'later-test','sent',LATER,'Synthetic receipt')
        state=out.record_report(state,'later-test',report(at=LATER,outcome='temporary_bounce',authentication={'spf':'unknown','dkim':'unknown','dmarc':'unknown'},spamassassin_score=None,threshold=None))
        self.assertTrue(out.diagnostic_due(state,fingerprint,LATER)['affected_delivery_paused'])
        state=out.save_contact(state,contact(),AT,'Synthetic route')
        state=prepared(state,request('outreach','outreach'),payload(recipient=contact()['endpoint']))
        self.assertFalse(out.action_check(state,state['outbound_actions'][-1],LATER)['allowed'])

    def test_contact_action_links_validate_kind_identity_role_outcome_and_audit_fabrication(self):
        fixture=contact_fixture();state=fixture.state()
        bad=fixture.event(status='user_reported_sent',outbound_action_id='does-not-exist')
        with self.assertRaisesRegex(cs.Invalid,'Invalid contact/action link'):cs.add_record(state,'contact_events',bad)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'legacy.json';raw=copy.deepcopy(state);raw['contact_events'].append(bad);path.write_text(cs.canonical_json(raw))
            audit=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/career_outreach.py'),'audit',str(path),'--at',AT],capture_output=True,text=True)
            self.assertEqual(audit.returncode,0,audit.stderr);result=cs.strict_json_loads(audit.stdout)
            self.assertFalse(result['audit_complete']);self.assertEqual(result['invalid_contact_action_links'][0]['event_id'],bad['id'])
        state=prepared(state,request('intro','outreach',purpose='cold_introduction'),payload(recipient=contact()['endpoint']))
        state=authorized(state);state=dispatch(state,'intro');state=out.transition(state,'intro','sent',AT,'Synthetic observed send')
        correct=fixture.event('linked-send','user_reported_sent',outbound_action_id='intro')
        self.assertEqual(cs.add_record(state,'contact_events',correct)['contact_events'][-1]['id'],'linked-send')
        wrong=copy.deepcopy(correct);wrong['status']='not_sent'
        with self.assertRaises(cs.Invalid):cs.add_record(state,'contact_events',wrong)
        other=copy.deepcopy(state['referrals'][0]);other.update(id='other-referral',opportunity_id='role-b');state=cs.add_record(state,'referrals',other)
        wrong=copy.deepcopy(correct);wrong.update(opportunity_id='role-b',referral_id='other-referral')
        with self.assertRaises(cs.Invalid):cs.add_record(state,'contact_events',wrong)

    def test_legacy_repair_is_explicit_preserves_original_and_can_quarantine_unknown(self):
        fixture=contact_fixture();original=fixture.state()
        original['contact_events']=[fixture.event(),fixture.event('later-unlinked','user_reported_sent',at=LATER)]
        with self.assertRaises(cs.Invalid):cs.validate(original)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'state.json';path.write_text(cs.canonical_json(original));before=path.read_bytes()
            def cli(*args):return subprocess.run([sys.executable,'-B',str(ROOT/'scripts/career_outreach.py'),*map(str,args)],capture_output=True,text=True)
            preview=cli('repair-preview',path,'--at',LATER);self.assertEqual(preview.returncode,0,preview.stderr)
            evidence=cs.strict_json_loads(preview.stdout);self.assertTrue(evidence['legacy_validation_error'])
            row={'state_sha256':evidence['state_sha256'],'event_id':'later-unlinked','decision':'quarantine','evidence':'Fictional user cannot tell whether the later record resolved the earlier send'}
            request_path=root/'review.json';request_path.write_text(cs.canonical_json(row))
            denied=cli('repair-contact-history',path,request_path,'--at',LATER,'--expected-revision',0)
            self.assertEqual(denied.returncode,2);self.assertEqual(path.read_bytes(),before)
            accepted=cli('repair-contact-history',path,request_path,'--at',LATER,'--expected-revision',0,'--user-confirmed')
            self.assertEqual(accepted.returncode,0,accepted.stderr);updated=cs.read_state(path)
            self.assertEqual(updated['profile']['contact_history_review'][0]['event'],original['contact_events'][1])
            self.assertEqual(updated['contact_events'],[original['contact_events'][0]])
            self.assertTrue(cs.reapplication_guard(updated,'role-a')['requires_review'])
            self.assertTrue(any(p.read_bytes()==before for p in (root/'Backups/State').iterdir()))
            profile=root/'profile.json';profile.write_text(cs.canonical_json({k:v for k,v in updated['profile'].items() if k!='contact_history_review'}))
            bypass=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/career_state.py'),'settings',str(path),'profile',str(profile),'--expected-revision','1','--reason','Attempt to erase unresolved quarantine'],capture_output=True,text=True)
            self.assertEqual(bypass.returncode,2);self.assertIn('reviewed workflow owners',bypass.stderr)
            reconciled_quarantine={'state_sha256':hashlib.sha256(cs.canonical_json(updated).encode()).hexdigest(),'event_id':'later-unlinked','decision':'reconcile','uncertain_event_id':'uncertain-contact','resolved_status':'user_reported_sent','evidence':'New fictional provider evidence identifies the original message'}
            restored=out.repair_contact_history(updated,reconciled_quarantine,LATER,True)
            self.assertEqual(restored['profile']['contact_history_review'],[])
            self.assertEqual(restored['contact_events'][1]['resolves_contact_event_id'],'uncertain-contact')
            # A separate original copy can be reconciled only after an actual evidence review.
            second=root/'second.json';second.write_bytes(before);raw=cs.read_contact_review_state(second)
            reviewed={'state_sha256':hashlib.sha256(cs.canonical_json(raw).encode()).hexdigest(),'event_id':'later-unlinked','decision':'reconcile','uncertain_event_id':'uncertain-contact','resolved_status':'user_reported_sent','evidence':'Fictional provider located the exact original message and confirms the later observation describes it'}
            repaired=out.repair_contact_history(raw,reviewed,LATER,True)
            self.assertEqual(repaired['contact_events'][1]['occurred_at'],AT)
            self.assertEqual(repaired['contact_events'][1]['resolves_contact_event_id'],'uncertain-contact')


if __name__=='__main__':unittest.main()
