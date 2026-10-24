"""Behavioral coverage for synthetic contacts, diagnostic claims and scoped permissions."""
from bundle_fixtures import legacy_bundle

import copy
from email.message import EmailMessage
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from test_state import AT, LATER, ROOT, base, attempt
sys.path.insert(0, str(ROOT / 'scripts'))
import career_state as cs
import career_outreach as out

WEEK = '2026-01-08T12:00:00Z'
BEFORE_WEEK = '2026-01-08T11:59:59Z'
EXPIRY = '2026-02-01T12:00:00Z'


def variant(**extra):
    return {'sender': 'applicant@example.org', 'provider': 'synthetic-mail', 'delivery_revision': '1',
            'template_revision': '1', 'stable_links': [], 'attachment_revision': '1', **extra}


def payload(text='Implemented retry handling; team saved USD 57000.', recipient='receiver@example.net', html=None, attachment=False):
    message = EmailMessage(); message['From'] = 'Alex Example <applicant@example.org>'
    message['To'] = recipient; message['Subject'] = 'Synthetic professional inquiry'
    message.set_content(text)
    if html is not None: message.add_alternative(html, subtype='html')
    if attachment: message.add_attachment(b'Synthetic resume bytes', maintype='application', subtype='pdf', filename='Resume.pdf')
    return message.as_bytes()


def contact(identifier='person-route', endpoint='owner@northstar-demo.example', person='owner-a', **extra):
    return {'id': identifier, 'company_id': 'company-a', 'person_key': person, 'public_name': 'Morgan Example',
            'observed_role': 'Engineering manager', 'relevance': 'Owns the documented API hiring area',
            'opportunity_ids': ['role-a', 'role-b'], 'kind': 'named_employee', 'endpoint': endpoint,
            'address_provenance': 'published_professional', 'affiliation': 'current', 'checked_at': AT,
            'valid_until': EXPIRY, 'confidence': {k: 'unknown' if k == 'delivery' else 'high' for k in out.AXES},
            'provenance': [{'source_id': 'source-a', 'url': 'https://northstar-demo.example/jobs/api-1',
                            'checked_at': AT, 'evidence': 'Synthetic official professional evidence: ' + purpose,
                            'purpose': purpose} for purpose in ('identity', 'affiliation', 'relevance', 'address')], **extra}


def state_with_contact():
    return out.save_contact(base(), contact(), AT, 'Reviewed synthetic public sources')


def request(identifier='diagnostic-a', kind='diagnostic', **extra):
    return {'id': identifier, 'idempotency_key': identifier, 'kind': kind, 'purpose': 'diagnostic' if kind == 'diagnostic' else 'application',
            'mode': 'diagnostic' if kind == 'diagnostic' else 'vacancy', 'company_id': None if kind == 'diagnostic' else 'company-a',
            'opportunity_id': None if kind == 'diagnostic' else 'role-a', 'contact_id': None if kind == 'diagnostic' else 'person-route',
            'reason': 'Supported source → API owner → relevant inquiry', 'source_ids': ['source-a'],
            'service': 'synthetic-receiver' if kind == 'diagnostic' else 'synthetic-mail', 'data_classes': ['message_headers', 'message_body'], 'at': AT, **extra}


def prepared(state=None, req=None, raw=None, config=None):
    return out.prepare_action(state or base(), req or request(), raw or payload(), config or variant())


def grant(action, identifier='permission-a', mode='one_time', **extra):
    scope = {'kind': action['kind'], 'purpose': action['purpose'], 'sender': action['inspection']['sender'],
             'provider': action['inspection']['provider'], 'service': action['service'], 'recipient': action['inspection']['recipient'],
             'data_classes': action['data_classes'], 'payload_sha256': action['inspection']['payload_sha256']}
    if action['kind'] == 'outreach': scope.update({k: action[k] for k in ('company_id', 'opportunity_id', 'contact_id')})
    return {'id': identifier, 'mode': mode, 'scope': scope, 'max_uses': 1 if mode == 'one_time' else 3,
            'valid_from': AT, 'valid_until': EXPIRY, 'evidence': 'Synthetic explicit recipient/service/data/purpose approval', **extra}


def authorized(state=None):
    state = state or prepared()
    return out.grant_permission(state, grant(state['outbound_actions'][0]), True)


def dispatch(state=None, identifier='diagnostic-a', at=AT):
    state = state or authorized()
    state = out.transition(state, identifier, 'ready', at, 'Reviewed readiness')
    return out.transition(state, identifier, 'dispatching', at, 'Durable handoff claim; no actual send', permission_id='permission-a', raw=payload(recipient=state['outbound_actions'][0]['inspection']['recipient']))


def report(**extra):
    return {'status': 'completed', 'outcome': 'pass', 'at': AT, 'evidence': 'Synthetic receiver report',
            'receiver_evidence': 'Synthetic receiving-side authentication and SpamAssassin observation',
            'authentication': {'spf': 'pass', 'dkim': 'pass', 'dmarc': 'pass'}, 'spamassassin_score': 0.7,
            'score_interpretation': 'heuristic_only', 'rules': ['SYNTHETIC_RULE'], 'threshold': 5.0, 'recipient':'receiver@example.net', 'tested_payload_sha256':out.inspect_payload(payload(),variant())['payload_sha256'], 'source_locator':'Synthetic private receiver report', **extra}


class ContactEvidenceTests(unittest.TestCase):
    def test_published_contact_is_usable_but_not_verified_mailbox(self):
        state = state_with_contact(); check = out.contact_guard(state, 'person-route', 'role-a', AT)
        self.assertTrue(check['usable']); self.assertEqual(check['confidence']['delivery'], 'unknown')
        row = contact(); row['confidence']['delivery'] = 'high'
        with self.assertRaisesRegex(cs.Invalid, 'Publication/DNS'): out.save_contact(base(), row, AT, 'Bad promotion')

    def test_missing_wrong_url_and_unobserved_provenance_rejected(self):
        for change in ('missing', 'url', 'date'):
            with self.subTest(change=change):
                row = contact()
                if change == 'missing': row['provenance'] = row['provenance'][1:]
                elif change == 'url': row['provenance'][0]['url'] = 'https://other.example/team'
                else: row['provenance'][0]['checked_at'] = '2025-12-31T12:00:00Z'
                with self.assertRaises(cs.Invalid): out.save_contact(base(), row, AT, 'Invalid source')

    def test_stale_affiliation_former_employee_and_inferred_addresses_not_usable(self):
        for row, at in [(contact(), EXPIRY), (contact(affiliation='former'), AT),
                        (contact(kind='inferred_address', address_provenance='inferred'), AT)]:
            state = out.save_contact(base(), row, AT, 'Retain uncertain historical evidence')
            self.assertFalse(out.contact_guard(state, row['id'], 'role-a', at)['usable'])

    def test_role_and_generic_inboxes_remain_explicit(self):
        for kind in ('role_inbox', 'company_inbox'):
            row = contact(kind=kind, affiliation='not_applicable'); state = out.save_contact(base(), row, AT, 'Published inbox')
            self.assertTrue(out.contact_guard(state, row['id'], 'role-a', AT)['usable']); self.assertEqual(state['employee_contacts'][0]['kind'], kind)

    def test_shared_channel_reused_across_roles_and_namesakes_not_merged(self):
        state = state_with_contact()
        with self.assertRaisesRegex(cs.Invalid, 'shared channel'): out.save_contact(state, contact(identifier='duplicate'), AT, 'Duplicate')
        other = contact(identifier='namesake-route', endpoint='other@northstar-demo.example', person='different-person')
        state = out.save_contact(state, other, AT, 'Distinct identity evidence despite same name')
        self.assertEqual(len(state['employee_contacts']), 2)
        self.assertEqual({c['person_key'] for c in state['employee_contacts']}, {'owner-a', 'different-person'})

    def test_refresh_cannot_replace_identity_and_preserves_provenance(self):
        state = state_with_contact(); wrong = contact(person='namesake')
        with self.assertRaises(cs.Invalid): out.save_contact(state, wrong, AT, 'Wrong alias merge')
        refreshed = contact(valid_until='2026-03-01T12:00:00Z')
        result = out.save_contact(state, refreshed, AT, 'Rechecked same route')
        self.assertEqual(len(result['employee_contacts']), 1); self.assertEqual(len(result['change_history']), 2)

    def test_opt_out_scope_does_not_become_company_ban(self):
        state = state_with_contact(); row = {'id': 'opt-out', 'company_id': 'company-a', 'scope': 'endpoint',
            'value': contact()['endpoint'], 'reason': 'opt_out', 'at': AT, 'evidence': 'Synthetic recipient declined this endpoint', 'source_ids': ['source-a']}
        state = out._append(state, 'contact_suppressions', row)
        self.assertFalse(out.contact_guard(state, 'person-route', 'role-a', AT)['usable'])
        state = out.save_contact(state, contact(identifier='other', endpoint='other@northstar-demo.example', person='other'), AT, 'Different evidenced employee')
        self.assertTrue(out.contact_guard(state, 'other', 'role-a', AT)['usable'])


class PayloadAndCadenceTests(unittest.TestCase):
    def test_exact_payload_changes_but_text_tailoring_preserves_variant(self):
        a = out.inspect_payload(payload(), variant()); b = out.inspect_payload(payload('Different truthful vacancy-specific text'), variant())
        self.assertNotEqual(a['payload_sha256'], b['payload_sha256']); self.assertEqual(a['variant_sha256'], b['variant_sha256'])
        for field in ('delivery_revision', 'template_revision', 'attachment_revision', 'provider'):
            self.assertNotEqual(a['variant_sha256'], out.inspect_payload(payload(), variant(**{field: '2'}))['variant_sha256'])
        self.assertNotEqual(a['variant_sha256'], out.inspect_payload(payload('See https://portfolio.example/work'), variant(stable_links=['https://portfolio.example/work']))['variant_sha256'])

    def test_real_mime_parity_attachment_hidden_and_destinations_inspected_without_rewriting(self):
        text = 'Crypto infrastructure; team saved USD 57000.'
        raw = payload(text, html='<p>'+text+'</p><span style="display:none">hidden</span><a href="https://track.example/click">https://portfolio.example</a>', attachment=True)
        before = bytes(raw); check = out.inspect_payload(raw, variant())
        self.assertEqual(raw, before); self.assertEqual(check['parity'], 'different')
        self.assertEqual(check['attachments'][0]['name'], 'Resume.pdf'); self.assertEqual(check['attachments'][0]['bytes'], len(b'Synthetic resume bytes'))
        self.assertTrue(check['hidden_tags']); self.assertIn('Review visible/destination URL mismatch', check['flags'])
        self.assertEqual(check['links'][0]['check'], 'unfetched'); self.assertEqual(check['receiver_authentication'], 'unknown')
        self.assertNotIn('crypto', str(check['flags']).lower())

    def test_multi_person_payload_and_sender_mismatch_rejected(self):
        with self.assertRaises(cs.Invalid): out.inspect_payload(payload(recipient='one@example.org, two@example.org'), variant())
        with self.assertRaises(cs.Invalid): out.inspect_payload(payload(), variant(sender='different@example.org'))

    def test_inactive_initial_week_boundary_and_material_change(self):
        state = prepared(); fingerprint = state['outbound_actions'][0]['inspection']['variant_sha256']
        self.assertFalse(out.diagnostic_due(state, fingerprint, AT)['due'])
        state['report_preferences']['deliverability'] = {'active_outbound': True, 'interval_days': 7}
        self.assertTrue(out.diagnostic_due(state, fingerprint, AT)['due'])
        state = out.transition(dispatch(authorized(state)), 'diagnostic-a', 'sent', AT, 'Synthetic accepted send')
        state = out.record_report(state, 'diagnostic-a', report())
        self.assertFalse(out.diagnostic_due(state, fingerprint, BEFORE_WEEK)['due'])
        self.assertTrue(out.diagnostic_due(state, fingerprint, WEEK)['due'])
        self.assertTrue(out.diagnostic_due(state, 'f'*64, AT)['due'])
        state['report_preferences']['deliverability']['interval_days'] = 8
        self.assertFalse(out.diagnostic_due(state, fingerprint, WEEK)['due'])
        self.assertFalse(out.diagnostic_due(state, fingerprint, WEEK)['autonomous_while_closed'])

    def test_score_is_not_probability_and_sent_copy_cannot_pass(self):
        state = out.transition(dispatch(), 'diagnostic-a', 'sent', AT, 'Synthetic provider receipt')
        for r in (report(score_interpretation='probability'), report(receiver_evidence=''), report(authentication={'spf':'unknown','dkim':'pass','dmarc':'pass'}), report(spamassassin_score=None)):
            with self.assertRaises(cs.Invalid): out.record_report(state, 'diagnostic-a', r)
        self.assertEqual(out.record_report(state, 'diagnostic-a', report())['outbound_actions'][0]['receiver_report']['spamassassin_score'], 0.7)

    def test_local_only_warns_and_does_not_send_or_require_mail_scheduler(self):
        state = authorized(); state['report_preferences']['deliverability'] = {'mode': 'local_only', 'active_outbound': True}
        self.assertFalse(out.action_check(state, state['outbound_actions'][0], AT)['allowed'])
        self.assertTrue(out.diagnostic_due(state, out.digest(variant()), AT)['independent_preparation_allowed'])
        with self.assertRaises(cs.Invalid): out.transition(state, 'diagnostic-a', 'ready', AT, 'Forbidden disclosure')
        self.assertEqual(out.summary(state, AT)['sends_performed'], 0)


class PermissionAndActionTests(unittest.TestCase):
    def test_permission_reuse_same_scope_and_revoke_expiry_changed_recipient(self):
        state = authorized(); action = state['outbound_actions'][0]
        for _ in range(3): self.assertEqual(out.permission_match(state, action, AT), ['permission-a'])
        self.assertEqual(out.permission_match(state, action, EXPIRY), [])
        changed = copy.deepcopy(action); changed['inspection']['recipient'] = 'other@example.net'
        self.assertEqual(out.permission_match(state, changed, AT), [])
        changed = copy.deepcopy(action); changed['service'] = 'different-service'
        self.assertEqual(out.permission_match(state, changed, AT), [])
        state['delivery_permissions'][0].update(revoked_at=AT,revocation_evidence='Synthetic withdrawal')
        self.assertEqual(out.permission_match(state, action, AT), [])

    def test_one_time_not_standing_and_explicit_standing_data_variant_scope(self):
        state = prepared(); action = state['outbound_actions'][0]
        with self.assertRaises(cs.Invalid): out.grant_permission(state, grant(action), False)
        one = out.grant_permission(state, grant(action), True)
        changed = copy.deepcopy(action); changed['inspection'] = out.inspect_payload(payload('Tailored text'), variant())
        self.assertEqual(out.permission_match(one, changed, AT), [])
        standing = grant(action, mode='standing'); standing['scope'].pop('payload_sha256')
        standing['scope'].update(variant_sha256=action['inspection']['variant_sha256'], allows_tailored_text=True)
        state = out.grant_permission(state, standing, True)
        self.assertEqual(out.permission_match(state, changed, AT), ['permission-a'])
        changed['data_classes'].append('resume_attachment')
        self.assertEqual(out.permission_match(state, changed, AT), [])
        self.assertEqual(cs.lookup_answer(state, {'meaning':'diagnostic','scope':{},'units':{}}, AT), [])

    def test_durable_intent_and_uncertain_acceptance_never_timer_retry(self):
        state = dispatch(); self.assertEqual(out.status(state['outbound_actions'][0]), 'dispatching')
        self.assertEqual(out.transition(state, 'diagnostic-a', 'dispatching', AT, 'Repeated claim'), state)
        state = out.transition(state, 'diagnostic-a', 'uncertain', AT, 'API response lost after possible acceptance')
        for target in ('ready', 'dispatching', 'failed', 'sent'):
            with self.assertRaises(cs.Invalid): out.transition(state, 'diagnostic-a', target, LATER, 'Timer expired', known_not_sent=True)
        state = out.transition(state, 'diagnostic-a', 'sent', LATER, 'Provider located message', reconciliation='Synthetic provider message identity and exact payload matched')
        self.assertEqual(out.status(state['outbound_actions'][0]), 'sent')

    def test_unknown_api_denial_is_uncertain_and_quota_has_retry_window(self):
        state = dispatch()
        with self.assertRaises(cs.Invalid): out.transition(state, 'diagnostic-a', 'failed', AT, 'Blocked API; unknown acceptance')
        state = out.transition(state, 'diagnostic-a', 'failed', AT, 'Provider proves quota refused before acceptance', known_not_sent=True, retry_after=LATER)
        state = prepared(state, request('retry'), payload('Another synthetic test'))
        self.assertFalse(out.action_check(state, state['outbound_actions'][-1], AT)['allowed'])
        self.assertTrue(out.action_check(state, state['outbound_actions'][-1], LATER)['allowed'])

    def test_concurrent_runners_only_one_claim_commits(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'state.json'; path.write_text(cs.canonical_json(out.transition(authorized(), 'diagnostic-a', 'ready', AT, 'Review')))
            def claim():
                try:
                    cs.transact(path, lambda s: out.transition(s, 'diagnostic-a', 'dispatching', AT, 'Claim', permission_id='permission-a', raw=payload()), 0)
                    return 'claimed'
                except cs.Invalid: return 'blocked'
            with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(lambda _: claim(), range(2)))
            self.assertEqual(sorted(results), ['blocked', 'claimed'])
            self.assertEqual(len([e for e in cs.read_state(path)['outbound_actions'][0]['events'] if e['state']=='dispatching']), 1)

    def test_duplicate_diagnostics_idempotency_and_usage_limit(self):
        state = authorized(); same = prepared(state)
        self.assertEqual(state, same)
        with self.assertRaises(cs.Invalid): prepared(state, raw=payload('Changed bytes under same key'))
        state = dispatch(state); state = prepared(state, request('diagnostic-b'))
        self.assertFalse(out.action_check(state, state['outbound_actions'][-1], AT)['allowed'])
        self.assertEqual(out.permission_match(state, state['outbound_actions'][-1], AT), [])

    def test_generic_mutations_cannot_bypass_owner_or_count_diagnostic_as_application(self):
        state = authorized()
        for collection in out.OWNED:
            with self.assertRaisesRegex(cs.Invalid, 'owner commands'): cs.add_record(state, collection, {'id':'bypass'})
        with self.assertRaises(cs.Invalid): cs.add_record(state, 'attempts', attempt(channel='email'))
        with self.assertRaises(cs.Invalid): cs.add_record(state, 'attempts', attempt(purpose='diagnostic'))
        with self.assertRaises(cs.Invalid): cs.add_record(state, 'attempts', attempt(outbound_action_id='diagnostic-a'))
        sent = out.transition(dispatch(state), 'diagnostic-a', 'sent', AT, 'Synthetic diagnostic accepted')
        counts = cs.stats(sent, LATER)['counts']
        self.assertEqual(counts['sent_roles'], 0); self.assertEqual(counts['attempt_records'], 0)


class OutreachHistoryTests(unittest.TestCase):
    def prepared_outreach(self, state=None, **changes):
        return prepared(state or state_with_contact(), request('application-a', 'outreach', **changes), payload(recipient=contact()['endpoint']))

    def test_prior_form_blocks_duplicate_application_but_allows_justified_follow_up(self):
        state = cs.add_record(state_with_contact(), 'attempts', attempt())
        state = self.prepared_outreach(state)
        self.assertFalse(out.action_check(state, state['outbound_actions'][0], AT)['allowed'])
        action = request('follow-a', 'outreach', purpose='follow_up', prior_application_acknowledgment='Applied through the role form; this is a question about the documented team problem')
        state = prepared(state, action, payload(recipient=contact()['endpoint']))
        follow = state['outbound_actions'][-1]; follow['inbound_check'] = {'checked_at':AT, 'coverage':'complete', 'obsolete':False, 'evidence':'Synthetic user checked scoped inbox'}
        self.assertTrue(out.action_check(state, follow, AT)['allowed'])
        follow.pop('prior_application_acknowledgment'); self.assertFalse(out.action_check(state, follow, AT)['allowed'])

    def test_manual_send_import_blocks_repeat_without_inflating_confirmed_counts(self):
        rows = [{'employer':'Northstar Demo','role':'API Engineer','role_url':'https://northstar-demo.example/jobs/api-1', 'status':'sent','date_text':'2026-01-01','channel':'email','source_locator':'Synthetic list','source_kind':'user_list'}]
        state=state_with_contact(); plan=cs.preview_history(state,rows); state=cs.apply_history(state,plan,'Reviewed synthetic manual history')
        state=self.prepared_outreach(state)
        self.assertFalse(out.action_check(state,state['outbound_actions'][0],AT)['allowed']); self.assertEqual(cs.stats(state,LATER)['counts']['sent_roles'],0)

    def test_no_simultaneous_company_role_blast_and_uncertain_cross_role_contact(self):
        state=self.prepared_outreach(); state=out.transition(state,'application-a','ready',AT,'Review')
        state=out.save_contact(state,contact(identifier='other-route',endpoint='other@northstar-demo.example',person='other'),AT,'Different owner')
        state=prepared(state, request('application-b','outreach',contact_id='other-route'),payload(recipient='other@northstar-demo.example'))
        self.assertFalse(out.action_check(state,state['outbound_actions'][-1],AT)['allowed'])

    def test_hard_bounce_suppresses_endpoint_temporary_bounce_does_not(self):
        for outcome in ('hard_bounce','temporary_bounce'):
            with self.subTest(outcome=outcome):
                state=authorized(self.prepared_outreach()); state=dispatch(state,'application-a')
                state=out.transition(state,'application-a','sent',AT,'Synthetic provider acceptance')
                state=out.record_report(state,'application-a',report(outcome=outcome,recipient=contact()['endpoint'],tested_payload_sha256=state['outbound_actions'][0]['inspection']['payload_sha256']))
                self.assertEqual(out.contact_guard(state,'person-route','role-a',AT)['usable'],outcome=='temporary_bounce')
                self.assertEqual(len(state.get('contact_suppressions',[])),int(outcome=='hard_bounce'))

    def test_late_reply_makes_followup_obsolete_and_missing_inbound_access_blocks_dispatch(self):
        state=self.prepared_outreach(purpose='follow_up'); action=state['outbound_actions'][0]
        self.assertFalse(out.action_check(state,action,AT)['allowed'])
        action['inbound_check']={'checked_at':AT,'coverage':'complete','obsolete':True,'evidence':'Synthetic new inbound reply'}
        self.assertFalse(out.action_check(state,action,AT)['allowed'])
        self.assertEqual(out.status(action),'draft'); self.assertEqual(len(state['outbound_actions']),1)

    def test_soft_due_warning_and_cold_message_default_do_not_delete_attachments(self):
        state=self.prepared_outreach(purpose='cold_introduction'); state['report_preferences']['deliverability']={'active_outbound':True}
        check=out.action_check(state,state['outbound_actions'][0],AT)
        self.assertTrue(check['allowed']);self.assertTrue(any('diagnostic is due' in w for w in check['warnings']))
        raw=payload(recipient=contact()['endpoint'],attachment=True)
        state=prepared(state,request('cold-b','outreach',purpose='cold_introduction',data_classes=['message_headers','message_body','attachments']),raw)
        check=out.action_check(state,state['outbound_actions'][-1],AT)
        self.assertTrue(check['allowed']);self.assertTrue(any('intentional exception' in w for w in check['warnings']))
        self.assertEqual(len(state['outbound_actions'][-1]['inspection']['attachments']),1)

    def test_email_application_record_requires_matching_action_and_does_not_allow_followup_counts(self):
        state=authorized(self.prepared_outreach());state=dispatch(state,'application-a');state=out.transition(state,'application-a','sent',AT,'Synthetic provider confirmation')
        state=cs.add_record(state,'attempts',attempt(channel='email',outbound_action_id='application-a'))
        self.assertEqual(cs.stats(state,LATER)['counts']['sent_roles'],1)
        with self.assertRaises(cs.Invalid):cs.add_record(state,'attempts',attempt('duplicate',channel='email',outbound_action_id='application-a'))


class AdditionalBoundaryTests(unittest.TestCase):
    def test_actual_structure_changes_variant_and_stable_link_cannot_be_fabricated(self):
        plain=out.inspect_payload(payload(),variant())
        self.assertNotEqual(plain['variant_sha256'],out.inspect_payload(payload(attachment=True),variant())['variant_sha256'])
        self.assertNotEqual(plain['variant_sha256'],out.inspect_payload(payload(html='<p>Same content</p>'),variant())['variant_sha256'])
        with self.assertRaises(cs.Invalid): out.inspect_payload(payload(),variant(stable_links=['https://portfolio.example/absent']))
        self.assertEqual(out.url_observation(999),'inconclusive');self.assertEqual(out.url_observation(403),'inconclusive')
        self.assertEqual(out.url_observation(404),'broken');self.assertEqual(out.url_observation(200),'reachable')

    def test_dispatch_verifies_exact_bytes_and_missing_attachment_data_scope_is_rejected(self):
        state=out.transition(authorized(),'diagnostic-a','ready',AT,'Review')
        for raw in (None,payload('Changed after approval')):
            with self.assertRaises(cs.Invalid):out.transition(state,'diagnostic-a','dispatching',AT,'Claim',permission_id='permission-a',raw=raw)
        with self.assertRaises(cs.Invalid):prepared(raw=payload(attachment=True))

    def test_proved_non_send_reuses_exact_one_time_scope_after_quota_window(self):
        state=out.transition(dispatch(),'diagnostic-a','failed',AT,'Provider proves no acceptance',known_not_sent=True,retry_after=LATER)
        state=prepared(state,request('retry'),payload())
        self.assertEqual(out.permission_match(state,state['outbound_actions'][-1],LATER),['permission-a'])
        self.assertFalse(out.action_check(state,state['outbound_actions'][-1],AT)['allowed'])
        self.assertTrue(out.action_check(state,state['outbound_actions'][-1],LATER)['allowed'])

    def test_auth_rejection_pauses_only_variant_and_quota_never_suppresses_contact(self):
        state=out.transition(dispatch(),'diagnostic-a','sent',AT,'Synthetic provider receipt')
        state=out.record_report(state,'diagnostic-a',report(outcome='auth_failure',authentication={'spf':'fail','dkim':'pass','dmarc':'pass'}))
        due=out.diagnostic_due(state,state['outbound_actions'][0]['inspection']['variant_sha256'],AT)
        self.assertTrue(due['affected_delivery_paused']);self.assertTrue(due['independent_preparation_allowed'])
        self.assertFalse(out.diagnostic_due(state,'f'*64,AT)['affected_delivery_paused']);self.assertEqual(state.get('contact_suppressions',[]),[])

    def test_receiver_report_cannot_be_swapped_between_payloads_or_called_probability(self):
        state=out.transition(dispatch(),'diagnostic-a','sent',AT,'Synthetic provider receipt')
        for change in ({'tested_payload_sha256':'f'*64},{'recipient':'other@example.net'},{'score_interpretation':'inbox_probability'},{'spamassassin_score':6}):
            with self.assertRaises(cs.Invalid):out.record_report(state,'diagnostic-a',report(**change))
        for outcome in ('quota','missing_mailbox','missing_domain','spam_rejection','unknown'):
            result=out.record_report(state,'diagnostic-a',report(status='unknown' if outcome=='unknown' else 'blocked',outcome=outcome))
            self.assertEqual(result['outbound_actions'][0]['receiver_report']['outcome'],outcome)

    def test_late_recorded_human_response_cancels_followup_and_projection_shows_contact_reason(self):
        from test_state import response
        import career_snapshot as snapshot
        state=cs.add_record(state_with_contact(),'attempts',attempt())
        state=prepared(state,request('follow','outreach',purpose='follow_up',prior_application_acknowledgment='Acknowledges earlier form'),payload(recipient=contact()['endpoint']))
        state=cs.add_record(state,'responses',response('reply','human_reply'))
        action=state['outbound_actions'][0];action['inbound_check']={'checked_at':LATER,'coverage':'complete','obsolete':False,'evidence':'Synthetic mailbox read'}
        check=out.action_check(state,action,LATER)
        self.assertFalse(check['allowed']);self.assertTrue(any('obsolete' in r for r in check['reasons']))
        state=out.transition(state,'follow','cancelled',LATER,'New reply supersedes follow-up')
        with tempfile.TemporaryDirectory() as directory:
            _,rows,metadata=snapshot.view_data(state,Path(directory),LATER)
            self.assertIn('Morgan Example',rows[0]['values'][7]);self.assertIn('cancelled',rows[0]['values'][7])
            self.assertTrue(any('Supported source' in str(row) for row in metadata))
        self.assertEqual(len(state['outbound_actions']),1)

    def test_schema_tampering_and_generic_cli_cannot_insert_send_or_permission(self):
        state=dispatch();bad=copy.deepcopy(state);bad['outbound_actions'][0]['inspection']['variant_sha256']='f'*64
        with self.assertRaises(cs.Invalid):cs.validate(bad)
        bad=copy.deepcopy(state);bad['delivery_permissions'][0]['scope']['service']='wrong-service'
        with self.assertRaises(cs.Invalid):cs.validate(bad)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'state.json';path.write_text(cs.canonical_json(base()));row=Path(directory)/'bypass.json';row.write_text(cs.canonical_json(grant(state['outbound_actions'][0])))
            before=path.read_bytes()
            process=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/career_state.py'),'put',str(path),'delivery_permissions',str(row)],capture_output=True,text=True)
            self.assertEqual(process.returncode,2);self.assertIn('owner commands',process.stderr);self.assertEqual(path.read_bytes(),before)


class IntegrationAcceptanceTests(unittest.TestCase):
    def test_three_modes_are_distinct_and_must_match_opportunity_identity(self):
        for kind,mode in [('vacancy','vacancy'),('company_outreach','company_problem'),('contract_project','paid_project')]:
            state=state_with_contact();state['opportunities'][0]['kind']=kind
            if kind=='company_outreach':
                state['opportunities'][0].update(outreach_need='Synthetic API reliability problem',contact_route={'url':'https://northstar-demo.example/jobs/api-1','source_id':'source-a','checked_at':AT})
                state['opportunities'][0]['status_observations'][0]['status']='unknown'
            state=prepared(state,request('mode-test','outreach',mode=mode),payload(recipient=contact()['endpoint']))
            self.assertEqual(state['outbound_actions'][0]['mode'],mode)
            bad=copy.deepcopy(state);bad['outbound_actions'][0]['mode']='paid_project' if mode!='paid_project' else 'vacancy'
            with self.assertRaises(cs.Invalid):cs.validate(bad)

    def test_company_only_history_needs_review_but_does_not_mark_all_roles_sent(self):
        state=state_with_contact();rows=[{'employer':'Northstar Demo','status':'sent','source_locator':'Synthetic company-only note','source_kind':'user_list','channel':'email','date_text':'unknown'}]
        plan=cs.preview_history(state,rows);state=cs.apply_history(state,plan,'Retain unscoped manual contact')
        state=prepared(state,request('company-history','outreach'),payload(recipient=contact()['endpoint']))
        self.assertFalse(out.action_check(state,state['outbound_actions'][0],AT)['allowed'])
        self.assertEqual(cs.stats(state,LATER)['counts']['sent_roles'],0)

    def test_fresh_built_bundle_executable_acceptance_outside_checkout(self):
        import build_skill_bundle as builder
        with tempfile.TemporaryDirectory() as directory:
            bundle=Path(directory)/'.agents/skills/career-agent';legacy_bundle(bundle)
            process=subprocess.run([sys.executable,'-B',str(ROOT/'tests/outreach_acceptance.py'),'--bundle',str(bundle)],cwd='/tmp',capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stderr)
            evidence=cs.strict_json_loads(process.stdout)
            self.assertEqual(evidence['status'],'passed');self.assertEqual(evidence['external_sends'],0);self.assertEqual(evidence['application_count'],0)


class PersonalContactReconciliationTests(unittest.TestCase):
    def state(self):
        state=state_with_contact()
        return cs.add_record(state,'referrals',{'id':'legacy-person','opportunity_id':'role-a','public_name':'Morgan Example','company_id':'company-a',
              'observed_role':'Engineering manager','relevance':'Owns API hiring','relationship':'cold','affiliation':'unknown','verified_at':AT,
              'source_ids':['source-a'],'employee_contact_id':'person-route'})

    def event(self,identifier='uncertain-contact',status='uncertain',**extra):
        return {'id':identifier,'opportunity_id':'role-a','referral_id':'legacy-person','status':status,'at':AT,'evidence':'Synthetic external personal-contact observation',**extra}

    def test_uncertain_personal_contact_blocks_blind_contact_and_application_retry(self):
        state=cs.add_record(self.state(),'contact_events',self.event())
        self.assertTrue(cs.reapplication_guard(state,'role-a')['requires_review'])
        self.assertEqual(cs.reapplication_guard(state,'role-a')['contact_event_ids'],['uncertain-contact'])
        with self.assertRaisesRegex(cs.Invalid,'Reconcile uncertain personal'):cs.add_record(state,'contact_events',self.event('blind','user_reported_sent',at=LATER))
        with self.assertRaisesRegex(cs.Invalid,'Reconcile uncertain personal'):cs.add_record(state,'attempts',attempt())
        corrupted=copy.deepcopy(state);corrupted['contact_events'].append(self.event('raw-bypass','user_reported_sent',at=LATER))
        with self.assertRaises(cs.Invalid):cs.validate(corrupted)

    def test_explicit_reconciliation_preserves_time_and_not_sent_clears_uncertainty(self):
        state=cs.add_record(self.state(),'contact_events',self.event())
        resolved=self.event('resolution','not_sent',at=LATER,resolves_contact_event_id='uncertain-contact',occurred_at=AT,reconciliation_evidence='Synthetic provider proves no message accepted')
        bad=copy.deepcopy(resolved);bad.pop('reconciliation_evidence')
        with self.assertRaises(cs.Invalid):cs.add_record(state,'contact_events',bad)
        bad=copy.deepcopy(resolved);bad['occurred_at']=LATER
        with self.assertRaises(cs.Invalid):cs.add_record(state,'contact_events',bad)
        result=cs.add_record(state,'contact_events',resolved)
        self.assertFalse(cs.reapplication_guard(result,'role-a')['requires_review'])
        self.assertEqual(len(result['contact_events']),2)
        sent=copy.deepcopy(resolved);sent['status']='user_reported_sent'
        result=cs.add_record(state,'contact_events',sent)
        self.assertTrue(cs.reapplication_guard(result,'role-a')['requires_review']);self.assertEqual(cs.stats(result,LATER)['counts']['sent_roles'],0)

    def test_shared_person_uncertainty_is_not_bypassed_by_another_role_referral(self):
        state=cs.add_record(self.state(),'contact_events',self.event())
        referral=copy.deepcopy(state['referrals'][0]);referral.update(id='second-role-person',opportunity_id='role-b')
        state=cs.add_record(state,'referrals',referral)
        with self.assertRaises(cs.Invalid):cs.add_record(state,'contact_events',self.event('other-role','user_reported_sent',opportunity_id='role-b',referral_id='second-role-person',at=LATER))


class LocalStatusAndAliasTests(unittest.TestCase):
    def test_skipped_and_blocked_local_diagnostics_remain_unknown_without_sending(self):
        for diagnostic_status in ('skipped','blocked','unknown'):
            state=prepared();state['report_preferences']['deliverability']={'active_outbound':True,'mode':'local_only'}
            local=report(status=diagnostic_status,outcome='unknown',receiver_evidence='',spamassassin_score=None,threshold=None,authentication={'spf':'unknown','dkim':'unknown','dmarc':'unknown'})
            state=out.record_report(state,'diagnostic-a',local)
            self.assertEqual(out.status(state['outbound_actions'][0]),'cancelled')
            self.assertEqual(state['outbound_actions'][0]['receiver_report']['status'],diagnostic_status)
            self.assertTrue(out.diagnostic_due(state,state['outbound_actions'][0]['inspection']['variant_sha256'],AT)['due'])
            self.assertEqual(cs.stats(state,LATER)['counts']['sent_roles'],0)
            with self.assertRaises(cs.Invalid):out.transition(state,'diagnostic-a','dispatching',AT,'Cannot dispatch skipped test',permission_id='none',raw=payload())

    def test_supported_email_aliases_cannot_evade_generic_write_guard(self):
        for channel in ('SMTP','Gmail','Outlook','Amazon SES','manual email'):
            with self.assertRaises(cs.Invalid):cs.add_record(base(),'attempts',attempt(channel=channel))

    def test_all_actual_headers_are_inspected_and_blocked_receiver_auth_still_pauses_variant(self):
        raw=payload().replace(b'Subject:',b'X-Synthetic-Header: inspect-this-value\nSubject:')
        inspection=out.inspect_payload(raw,variant());self.assertIn('X-Synthetic-Header',inspection['headers'])
        state=out.transition(dispatch(),'diagnostic-a','sent',AT,'Synthetic receipt')
        state=out.record_report(state,'diagnostic-a',report(status='blocked',outcome='auth_failure',authentication={'spf':'fail','dkim':'pass','dmarc':'pass'}))
        self.assertTrue(out.diagnostic_due(state,state['outbound_actions'][0]['inspection']['variant_sha256'],AT)['affected_delivery_paused'])


class SenderAuthenticationBoundaryTests(unittest.TestCase):
    def test_first_active_batch_is_due_and_template_change_cannot_bypass_sender_auth_failure(self):
        initial=base();initial['report_preferences']['deliverability']={'active_outbound':True}
        self.assertTrue(out.summary(initial,AT)['initial_diagnostic_due'])
        state=out.transition(dispatch(),'diagnostic-a','sent',AT,'Synthetic acceptance')
        state=out.record_report(state,'diagnostic-a',report(outcome='auth_failure',authentication={'spf':'fail','dkim':'pass','dmarc':'pass'}))
        state=out.save_contact(state,contact(),AT,'Fictional route')
        state=prepared(state,request('application-new-template','outreach'),payload(recipient=contact()['endpoint']),variant(template_revision='2'))
        self.assertFalse(out.action_check(state,state['outbound_actions'][-1],AT)['allowed'])
        state=prepared(state,request('application-other-provider','outreach'),payload(recipient=contact()['endpoint']),variant(provider='other-provider'))
        self.assertTrue(out.action_check(state,state['outbound_actions'][-1],AT)['allowed'])


class OutreachCLITests(unittest.TestCase):
    def test_cli_private_ledger_claim_replay_inspect_summary_and_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); path=root/'state.json'; path.write_text(cs.canonical_json(authorized()))
            def run(*args):
                process=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/career_outreach.py'),*map(str,args)],capture_output=True,text=True)
                self.assertEqual(process.returncode,0,process.stderr);return cs.strict_json_loads(process.stdout)
            transition=root/'transition.json'
            transition.write_text(cs.canonical_json({'action_id':'diagnostic-a','target':'ready','evidence':'Synthetic review'}))
            run('transition',path,transition,'--at',AT,'--expected-revision',0)
            transition.write_text(cs.canonical_json({'action_id':'diagnostic-a','target':'dispatching','evidence':'Synthetic claim','permission_id':'permission-a'}))
            mime=root/'payload.eml'; mime.write_bytes(payload())
            first=run('transition',path,transition,'--at',AT,'--expected-revision',1,'--payload',mime)
            second=run('transition',path,transition,'--at',AT,'--expected-revision',2,'--payload',mime)
            self.assertTrue(first['dispatch_claimed']);self.assertFalse(second['dispatch_claimed']);self.assertEqual(first['sends_performed'],0)
            self.assertEqual(run('summary',path,'--at',AT)['actions'][0]['state'],'dispatching')
            self.assertTrue(run('audit',path,'--at',AT)['audit_complete'])
            self.assertTrue(run('due',path,'--at',AT,'--variant-sha256',out.digest(variant()))['independent_preparation_allowed'])
            mime=root/'payload.eml'; mime.write_bytes(payload()); config=root/'variant.json';config.write_text(cs.canonical_json(variant()))
            self.assertEqual(run('inspect',mime,config)['payload_sha256'],out.inspect_payload(payload(),variant())['payload_sha256'])


if __name__=='__main__': unittest.main()
