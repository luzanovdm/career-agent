"""Mechanical scope/attestation tests. Synthetic prose here is not a quality benchmark."""
import json
import unittest
from datetime import datetime,timezone
from unittest.mock import patch
from test_runtime_1 import Fixture
from tempfile import TemporaryDirectory
from career.contracts import CareerError,digest

class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='career-editorial-fictional-');self.addCleanup(self.temp.cleanup);self.fx=Fixture(self.temp.name,editorial=False).seed()
    def payload(self,message='A relevant workflow contribution.'):
        return dict(packet_id='packet_one',documents=[dict(slot='resume',text='Improved processing by 25%.'),dict(slot='message',text=message),dict(slot='dossier',text='Private synthetic evidence.'),dict(slot='interview',text='Private synthetic preparation.')],used_claim_ids=['claim_one'])
    def review(self,data,decision='approved'):
        context=self.fx.tasks.query('review-context',input=data)
        return dict(findings='Compared the confirmed synthetic claim with the exact wording.',limitations='Mechanical fixture; does not establish literary quality.',claim_spans=[dict(claim_id='claim_one',text='Improved processing by 25%.')],coverage=[dict(claim_id='claim_one',disposition='included')],tone_findings='Plain factual fixture language.',editorial=dict(argument='The workflow owner can use a demonstrated process contribution.',decision=decision,findings='Fixture attestation only. Independent behavioral evaluation tests actual arguments.',binding=context['binding']))
    def test_factual_approval_is_not_editorial_approval(self):
        selection=self.fx.tasks.query('selection',record_id='packet_one');self.assertTrue(selection['assessment']['factual_pass']);self.assertFalse(selection['assessment']['prepared']);self.assertEqual('not_recorded',selection['assessment']['editorial_status'])
    def test_bound_approved_and_revise_have_different_readiness(self):
        data=self.payload();review=self.review(data,'revise');self.fx.command('packet.save',**data,review=review);s=self.fx.tasks.query('selection',record_id='packet_one');self.assertTrue(s['assessment']['factual_pass']);self.assertFalse(s['assessment']['prepared'])
        self.fx.command('packet.save',**data,review=self.review(data));self.assertTrue(self.fx.tasks.query('selection',record_id='packet_one')['assessment']['prepared'])
    def test_text_mutation_cannot_rebind_old_approval(self):
        data=self.payload();review=self.review(data);data['documents'][1]['text']='A different qualitative promise.';r=self.fx.command('packet.save',**data,review=review);self.assertIn('EDITORIAL_BINDING_CHANGED',{i['code'] for i in r['issues']})
    def test_new_unlinked_confirmed_claim_is_discoverable_and_invalidates_binding(self):
        data=self.payload();self.fx.command('packet.save',**data,review=self.review(data));self.assertEqual(1,self.fx.tasks.query('board')['counts']['columns']['ready']);self.fx.command('claim.save',id='claim_new',assertion='Coordinated a documented repair handover.',meaning='Personal coordination, team delivery; no claimed measured effect.',source_ids=['source_one'],confirmation='confirmed',disclosure='allowed')
        c=self.fx.tasks.context(task='packets',case_id='case_one');self.assertEqual(1,c['claim_frontier']['outside_linked_context']);self.assertEqual('claim_new',c['claim_frontier']['preview'][0]['id']);self.assertNotIn('claim_new',{x['id'] for x in c['evidence']['claims']})
        bank=self.fx.tasks.context(task='profile',claim_scope='bank');self.assertIn('claim_new',{x['id'] for x in bank['evidence']['claims']});s=self.fx.tasks.query('selection',record_id='packet_one');self.assertEqual('stale',s['assessment']['editorial_status']);self.assertEqual(0,self.fx.tasks.query('board')['counts']['columns']['ready'])
    def test_unrelated_note_does_not_expire_review_but_fact_correction_does(self):
        data=self.payload();self.fx.command('packet.save',**data,review=self.review(data));self.fx.command('case.note',case_id='case_one',text='An unrelated private checkpoint.');self.assertTrue(self.fx.tasks.query('selection',record_id='packet_one')['assessment']['prepared'])
        self.fx.command('claim.save',id='claim_one',assertion='Improved processing by 25%.',meaning='A team result; personal role was coordinating one handover.',source_ids=['source_one'],confirmation='confirmed',disclosure='allowed');self.assertFalse(self.fx.tasks.query('selection',record_id='packet_one')['assessment']['prepared'])
    def test_handoff_requires_exact_payload_recipient_and_selection(self):
        data=self.payload();self.fx.command('packet.save',**data,review=self.review(data));s=self.fx.tasks.query('selection',record_id='packet_one');handoff=dict(packet_id='packet_one',version_id=s['version_id'],documents=[d for d in data['documents'] if d['slot'] in ('resume','message','answers')],recipient=dict(kind='profile',value='https://northstar.example/team/morgan'));r=self.fx.tasks.query('handoff-check',input=handoff);self.assertTrue(r['ready']);self.assertFalse(r['permission_granted']);self.assertEqual(0,r['external_actions']['performed'])
        handoff['documents']=[dict(slot='message',text='Unreviewed final edit.')];self.assertFalse(self.fx.tasks.query('handoff-check',input=handoff)['ready'])
        handoff['documents']=data['documents']+[dict(slot='dossier',text='Private facts')]
        with self.assertRaises(CareerError):self.fx.tasks.query('handoff-check',input=handoff)
    def test_actual_send_mismatch_is_retained_without_becoming_ready(self):
        self.fx.command('activity.record',case_id='case_one',kind='sent',occurred_at='2026-10-26T00:00:00Z',evidence='Synthetic manual observed receipt.',packet_id='packet_one',version_id=self.fx.tasks.query('selection',record_id='packet_one')['version_id'],message_sha256=digest(b'Actual different text'))
        with self.fx.tasks.repository.open() as snap:
            row=snap.one("SELECT kind,detail FROM activities WHERE case_id='case_one'");self.assertEqual('sent',row['kind']);self.assertEqual(digest(b'Actual different text'),json.loads(row['detail'])['message_sha256'])
        self.assertFalse(self.fx.tasks.query('selection',record_id='packet_one')['assessment']['prepared'])

    def test_context_and_handoff_are_read_only_and_missing_recipient_is_blocked(self):
        data=self.payload();self.fx.command('packet.save',**data,review=self.review(data));s=self.fx.tasks.query('selection',record_id='packet_one');revision=s['version_id']
        with self.fx.tasks.repository.open() as snap:counts={table:snap.one('SELECT count(*) AS n FROM '+table)['n'] for table in ('plans','commands','packet_versions','reviews')};before=snap.revision
        self.fx.tasks.query('review-context',input=data);r=self.fx.tasks.query('handoff-check',input=dict(packet_id='packet_one',version_id=revision,documents=[d for d in data['documents'] if d['slot'] in ('resume','message')]))
        self.assertFalse(r['ready']);self.assertIn('HANDOFF_RECIPIENT_MISMATCH',{i['code'] for i in r['issues']})
        with self.fx.tasks.repository.open() as snap:self.assertEqual(before,snap.revision);self.assertEqual(counts,{table:snap.one('SELECT count(*) AS n FROM '+table)['n'] for table in counts})
    def test_bank_discovery_is_bounded_and_fully_pageable(self):
        for n in range(12):self.fx.command('claim.save',id='outside_'+str(n),assertion='A fictional qualitative contribution '+chr(65+n),meaning='Specific supplied contribution without a metric.',source_ids=['source_one'],confirmation='confirmed',disclosure='allowed')
        c=self.fx.tasks.context(task='packets',case_id='case_one');self.assertEqual(12,c['claim_frontier']['outside_linked_context']);self.assertEqual(5,len(c['claim_frontier']['preview']));page=self.fx.tasks.context(task='profile',claim_scope='bank',limit=4);ids=set()
        while True:
            ids.update(x['id'] for x in page['evidence']['claims'])
            if not page['next_cursor']:break
            page=self.fx.tasks.context(task='profile',claim_scope='bank',limit=4,cursor=page['next_cursor'])
        self.assertEqual(13,len(ids))
    def test_wrong_target_cannot_reuse_same_text_approval(self):
        data=self.payload();review=self.review(data);self.fx.command('packet.create',id='packet_alternative',case_id='case_one',purpose='contact');data['packet_id']='packet_alternative';r=self.fx.command('packet.save',**data,review=review);self.assertIn('EDITORIAL_BINDING_CHANGED',{i['code'] for i in r['issues']})
    def test_scoped_new_writing_preference_invalidates_editorial_and_board(self):
        data=self.payload();self.fx.command('packet.save',**data,review=self.review(data));self.fx.command('answer.save',meaning='writing.preference',scope=dict(case_id='case_one',purpose='external'),units={},disposition='answered',value='Use a short direct request.',evidence='Synthetic user preference.')
        self.assertFalse(self.fx.tasks.query('selection',record_id='packet_one')['assessment']['prepared']);self.assertEqual(0,self.fx.tasks.query('board')['counts']['columns']['ready'])

    def test_uncertain_observation_blocks_exact_handoff_until_reconciled(self):
        data=self.payload();self.fx.command('packet.save',**data,review=self.review(data));selected=self.fx.tasks.query('selection',record_id='packet_one');version=selected['version_id']
        receipt=self.fx.command('activity.record',case_id='case_one',kind='uncertain',occurred_at='2026-10-26T00:00:00Z',evidence='Synthetic interrupted provider response.',packet_id='packet_one',version_id=version);activity=receipt['saved_ids'][0]
        request=dict(packet_id='packet_one',version_id=version,documents=[d for d in data['documents'] if d['slot'] in ('resume','message')],recipient=dict(kind='profile',value='https://northstar.example/team/morgan'))
        check=self.fx.tasks.query('handoff-check',input=request);self.assertFalse(check['ready']);warning=next(i for i in check['issues'] if i['code']=='HANDOFF_OUTCOME_UNCERTAIN');self.assertIn(activity,warning['unresolved_activity_ids'])
        self.fx.command('activity.record',case_id='case_one',kind='not_sent',occurred_at='2026-10-26T00:00:00Z',evidence='Synthetic provider evidence confirms no acceptance.',packet_id='packet_one',version_id=version,resolves_activity_id=activity);self.assertTrue(self.fx.tasks.query('handoff-check',input=request)['ready'])
    def test_history_preserves_observed_hash_and_mismatch_warning(self):
        version=self.fx.tasks.query('selection',record_id='packet_one')['version_id'];observed=digest(b'Different actually observed synthetic payload')
        receipt=self.fx.command('activity.record',case_id='case_one',kind='sent',occurred_at='2026-10-26T00:00:00Z',evidence='Synthetic observed send receipt, no external action.',packet_id='packet_one',version_id=version,message_sha256=observed);self.assertIn('SENT_PAYLOAD_MISMATCH',{i['code'] for i in receipt['issues']})
        history=self.fx.tasks.query('case-history',record_id='case_one')['items'][0];self.assertEqual(observed,history['message_sha256']);self.assertIn('SENT_PAYLOAD_MISMATCH',{i['code'] for i in history['warnings']});self.assertEqual(version,history['version_id']);self.assertEqual('sent',history['kind'])

    def test_malformed_read_only_payloads_are_typed_refusals(self):
        for documents in ({'slot':'message'},['not an object'],[dict(slot=['message'],text='x')]):
            with self.subTest(documents=documents),self.assertRaises(CareerError):self.fx.tasks.query('handoff-check',input=dict(packet_id='packet_one',version_id='version_wrong',documents=documents))
        with self.assertRaises(CareerError):self.fx.tasks.query('review-context',input=dict(packet_id='packet_one',documents=self.payload()['documents'],used_claim_ids=[['not an id']]))

    def test_explicit_empty_intent_scope_never_exposes_bank_candidates(self):
        c=self.fx.tasks.context(task='packets',case_id='case_one',_track_ids=[],claim_scope='bank')
        self.assertEqual([],c['evidence']['claims']);self.assertEqual(0,c['claim_frontier']['total']);self.assertEqual([],c['claim_frontier']['preview'])

    def assert_writing_boundary(self,boundary):
        clock=[datetime(2030,1,1,tzinfo=timezone.utc)]
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return clock[0].astimezone(tz) if tz else clock[0].replace(tzinfo=None)
        with patch('career.repository.datetime',Clock):
            self.fx.command('answer.save',meaning='writing.preference',scope=dict(case_id='case_one',purpose='external'),units={},disposition='answered',value='Use a short direct request.',evidence='Synthetic time-scoped user preference.',**{boundary:'2030-01-02T00:00:00Z'})
            data=self.payload();self.fx.command('packet.save',**data,review=self.review(data))
            self.assertTrue(self.fx.tasks.query('selection',record_id='packet_one')['assessment']['prepared'])
            self.assertEqual(1,self.fx.tasks.query('board')['counts']['columns']['ready'])
            with self.fx.tasks.repository.open() as snap:self.assertEqual(datetime(2030,1,2,tzinfo=timezone.utc),datetime.fromisoformat(snap.one("SELECT expires_at FROM case_projection_cache WHERE case_id='case_one'")['expires_at'].replace('Z','+00:00')))
            clock[0]=datetime(2030,1,2,tzinfo=timezone.utc)
            selected=self.fx.tasks.query('selection',record_id='packet_one')
            self.assertFalse(selected['assessment']['prepared']);self.assertEqual('stale',selected['assessment']['editorial_status'])
            self.assertEqual(0,self.fx.tasks.query('board')['counts']['columns']['ready'])
            self.assertFalse(self.fx.tasks.query('cases')['items'][0]['prepared'])

    def test_writing_preference_expiry_invalidates_cached_readiness(self):
        self.assert_writing_boundary('valid_until')

    def test_future_writing_preference_start_invalidates_cached_readiness(self):
        self.assert_writing_boundary('valid_from')
