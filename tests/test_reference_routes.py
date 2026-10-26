"""Fictional URL identity and company-owned mailbox boundary regressions."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from career.contracts import CareerError
from career.numeric import numeric_review
from test_runtime_1 import Fixture


class SourceURLTests(unittest.TestCase):
    def check_url(self,text=None,url='https://market.example/jobs/offer,654321/',locator=None,readable=True):
        text=text or 'Listing: '+url
        start=text.index(url)
        review=dict(findings='Compared exact published locator.',limitations='URL identity is not claim truth.',tone_findings='Fictional reference.',claim_spans=[],coverage=[],entity_spans=[dict(slot='message',start=start,end=start+len(url),text=url,source_id='source_url')])
        source=dict(id='source_url',version=2,readable=readable,locator=locator or url,excerpt='A published fictional opportunity.')
        return numeric_review([dict(slot='message',text=text)],[],review,sources=[source])

    def test_exact_source_bound_url_ids_are_references(self):
        for url in ('https://market.example/jobs/offer,654321/','https://market.example/jobs?id=654321#details','https://market.example/v2/jobs/654321?lang=en%20US'):
            with self.subTest(url=url):
                issues,audit=self.check_url(url=url)
                self.assertEqual([],issues)
                self.assertTrue(audit['occurrences'])
                self.assertTrue(all(row['role']=='reference' and row['reference']['record_version']==2 for row in audit['occurrences']))

    def test_url_digits_do_not_authorize_identical_quantities_outside(self):
        url='https://market.example/jobs/offer,654321/'
        issues,audit=self.check_url('Listing: '+url+' Managed 654321 engineers; improved by 999%.')
        self.assertEqual(['654321','999'],[row['token'] for row in issues])
        self.assertEqual('reference',audit['occurrences'][0]['role'])

    def test_exact_source_and_valid_safe_url_required(self):
        for values in (dict(locator='https://other.example/jobs/offer,654321/'),dict(locator='https://market.example/jobs/offer,654322/'),dict(readable=False),dict(url='https://user:secret@market.example/jobs/654321'),dict(url='https://market.example:invalid/654321'),dict(url='https://market.example/jobs/%ZZ654321')):
            with self.subTest(values=values),self.assertRaises(CareerError):self.check_url(**values)

    def test_markers_outside_url_are_never_hidden(self):
        url='https://market.example/jobs/offer,654321/'
        for text in (url+'%', '$'+url, '('+url+')%'):
            with self.subTest(text=text),self.assertRaises(CareerError):self.check_url(text)

    def test_partial_url_continuations_are_not_hidden(self):
        url='https://market.example/jobs/offer,654321/'
        for ending in ('more','?rate=999','#other',',654322'):
            with self.subTest(ending=ending),self.assertRaises(CareerError):self.check_url(url+ending)

    def test_url_wrapper_must_close_without_hiding_a_continuation(self):
        url='https://market.example/jobs/123'
        for text in ('<'+url+')evil>','('+url+')evil','<'+url+'>evil','['+url+']evil'):
            with self.subTest(text=text),self.assertRaises(CareerError):self.check_url(text,url=url)
        for text in ('<'+url+'>','('+url+').','[listing]('+url+')','(<'+url+'>).'):
            with self.subTest(text=text):self.assertEqual([],self.check_url(text,url=url)[0])


class CompanyMailboxTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='career-company-route-');self.addCleanup(self.temp.cleanup)
        self.f=Fixture(self.temp.name).seed()
        self.f.command('source.capture',id='source_mail',locator='https://northstar.example/contact',excerpt='Northstar Demo project enquiries: projects@northstar.example. Alternative: team@northstar.example.',observed_at='2026-10-26T00:00:00Z',readable=True)
        self.data=dict(id='case_mail',company_id='company_one',title='Published project',kind='project',route='company',company_route=dict(kind='email',value='projects@northstar.example',source_id='source_mail'),tracks=[dict(id='track_one',rationale='Documented product work.')],source_ids=['source_mail'],canonical_url='https://market.example/jobs/654321',essential_policy='passed')

    def seed(self):
        self.f.command('case.capture',**self.data)
        self.f.command('packet.create',id='packet_mail',case_id='case_mail',purpose='contact')
        self.save()

    def save(self):
        return self.f.command('packet.save',packet_id='packet_mail',documents=[dict(slot='message',text='A relevant workflow contribution.')],used_claim_ids=[],review=dict(findings='Compared exact scoped company evidence.',limitations='Not permission to send.',tone_findings='Fictional project introduction.',claim_spans=[],coverage=[]))

    def handoff(self,recipient=None):
        s=self.f.tasks.query('selection',record_id='packet_mail')
        return self.f.tasks.query('handoff-check',input=dict(packet_id='packet_mail',version_id=s['version_id'],documents=[dict(slot='message',text='A relevant workflow contribution.')],recipient=recipient or dict(kind='email',value='projects@northstar.example')))

    def test_company_route_consistent_without_fake_person(self):
        self.seed();s=self.f.tasks.query('selection',record_id='packet_mail')
        self.assertIsNone(s['person_id']);self.assertTrue(s['assessment']['prepared']);self.assertTrue(self.handoff()['ready'])
        for row in (s,self.f.tasks.query('case',record_id='case_mail')['case'],next(r for r in self.f.tasks.query('cases')['items'] if r['id']=='case_mail')):
            self.assertEqual('projects@northstar.example',row['selected_route']['value'])
        self.assertFalse(self.handoff(dict(kind='email',value='arbitrary@northstar.example'))['ready'])

    def test_company_route_requires_scoped_readable_official_literal(self):
        for patch in (dict(company_route=dict(kind='email',value='absent@northstar.example',source_id='source_mail')),dict(source_ids=['source_one']),dict(person_id='person_one')):
            with self.subTest(patch=patch),self.assertRaises(CareerError):self.f.command('case.capture',**dict(self.data,**patch))
        self.f.command('source.capture',id='source_mail',locator='https://other.example/contact',excerpt='projects@northstar.example',observed_at='2026-10-26T00:00:00Z',readable=True)
        with self.assertRaises(CareerError):self.f.command('case.capture',**self.data)

    def test_route_change_stales_review_but_private_note_does_not(self):
        self.seed();old=self.f.tasks.query('selection',record_id='packet_mail')
        self.f.command('case.note',case_id='case_mail',text='Unrelated private note')
        self.assertTrue(self.handoff()['ready'])
        self.f.command('case.capture',**dict(self.data,company_route=dict(kind='email',value='team@northstar.example',source_id='source_mail')))
        self.assertFalse(self.handoff()['ready']);self.assertFalse(self.f.tasks.query('selection',record_id='packet_mail')['assessment']['prepared'])
        self.save();self.assertTrue(self.handoff(dict(kind='email',value='team@northstar.example'))['ready'])
        historical=self.f.tasks.query('selection',record_id='packet_mail',version_id=old['version_id'])
        self.assertEqual(old['slots'],historical['slots'])

    def test_suppression_and_bounce_survive_recapture(self):
        self.seed();self.f.command('contact.suppress',company_id='company_one',kind='email',value='projects@northstar.example',reason='Actual scoped opt-out.',evidence='Fictional recorded opt-out.')
        self.assertFalse(self.handoff()['ready'])
        self.f.command('company.capture',id='company_one',name='Northstar Demo',domain='northstar.example')
        self.assertFalse(self.handoff()['ready'])
        with self.assertRaises(CareerError):self.f.command('case.capture',**self.data)

    def test_bounce_and_uncertain_outcome_are_shared_with_company_endpoint(self):
        self.seed();s=self.f.tasks.query('selection',record_id='packet_mail')
        receipt=self.f.command('activity.record',case_id='case_mail',packet_id='packet_mail',version_id=s['version_id'],kind='uncertain',occurred_at='2026-10-26T00:00:00Z',evidence='Fictional provider outcome unknown.')
        self.assertFalse(self.handoff()['ready'])
        self.assertIn('HANDOFF_OUTCOME_UNCERTAIN',{i['code'] for i in self.handoff()['issues']})
        with self.f.tasks.repository.open() as snap:
            event=snap.one("SELECT id FROM activities WHERE case_id='case_mail' AND kind='uncertain'")['id']
        self.f.command('activity.record',case_id='case_mail',kind='not_sent',occurred_at='2026-10-26T00:00:00Z',resolves_activity_id=event,evidence='Fictional provider confirmed no transmission.')
        self.assertTrue(self.handoff()['ready'])
        self.f.command('activity.record',case_id='case_mail',kind='bounce',occurred_at='2026-10-26T00:02:00Z',channel=dict(kind='email',value='projects@northstar.example'),evidence='Fictional endpoint hard bounce.')
        self.assertFalse(self.handoff()['ready'])
        self.assertFalse(next(r for r in self.f.tasks.query('cases')['items'] if r['id']=='case_mail')['qualified'])

    def test_source_evidence_change_invalidates_cached_route(self):
        self.seed();self.f.tasks.query('board')
        self.f.command('source.capture',id='source_mail',locator='https://northstar.example/contact',excerpt='No readable contact evidence.',observed_at='2026-10-26T00:00:00Z',readable=False)
        self.assertFalse(self.handoff()['ready'])
        row=next(r for r in self.f.tasks.query('cases')['items'] if r['id']=='case_mail')
        self.assertFalse(row['qualified']);self.assertFalse(row['prepared']);self.assertEqual('qualify',row['column'])

    def test_old_policy_requires_current_review_after_upgrade(self):
        self.seed()
        with self.f.tasks.repository.open() as s:
            version=s.get('packet','packet_mail')['selected_version_id'];r=s.one('SELECT detail FROM reviews WHERE version_id=?',(version,));detail=json.loads(r['detail']);detail['numeric_audit']['policy']='career-agent.numeric-occurrences/5'
            s._db.execute('UPDATE reviews SET detail=? WHERE version_id=?',(json.dumps(detail),version));s._db.execute('DELETE FROM case_projection_cache');s._db.commit()
        self.assertFalse(self.handoff()['ready'])
        self.assertFalse(self.f.tasks.query('selection',record_id='packet_mail')['assessment']['prepared'])
        self.save();self.assertTrue(self.handoff()['ready'])

    def test_url_reference_source_dependency_and_outside_metric_at_facade(self):
        url='https://market.example/jobs/654321'
        self.f.command('source.capture',id='source_url',locator=url,excerpt='Published project.',observed_at='2026-10-26T00:00:00Z',readable=True)
        self.data['source_ids'].append('source_url');self.seed()
        body='Listing: '+url;start=body.index(url)
        review=dict(findings='Compared exact locator.',limitations='URL is not an achievement.',tone_findings='Fictional.',claim_spans=[],coverage=[],entity_spans=[dict(slot='message',start=start,end=start+len(url),text=url,source_id='source_url')])
        self.f.command('packet.save',packet_id='packet_mail',documents=[dict(slot='message',text=body)],used_claim_ids=[],review=review)
        self.assertTrue(self.f.tasks.query('selection',record_id='packet_mail')['assessment']['prepared'])
        self.f.command('packet.save',packet_id='packet_mail',documents=[dict(slot='message',text=body+' Managed 654321 engineers.')],used_claim_ids=[],review=review)
        selected=self.f.tasks.query('selection',record_id='packet_mail')
        self.assertFalse(selected['assessment']['prepared']);self.assertIn('UNMATCHED_NUMBER',{r['code'] for r in selected['assessment']['issues']})
        self.f.command('packet.save',packet_id='packet_mail',documents=[dict(slot='message',text=body)],used_claim_ids=[],review=review)
        self.f.command('source.capture',id='source_url',locator=url,excerpt='Evidence unavailable.',observed_at='2026-10-26T00:00:00Z',readable=False)
        self.assertFalse(self.f.tasks.query('selection',record_id='packet_mail')['assessment']['prepared'])

    def test_company_suppression_cannot_be_bypassed_by_real_person_alias(self):
        self.seed();self.f.command('contact.suppress',company_id='company_one',kind='email',value='projects@northstar.example',reason='Actual scoped opt-out.',evidence='Fictional endpoint statement.')
        self.f.command('contact.capture',id='person_one',name='Morgan Example',company_id='company_one',affiliation='current',relevance='Published project owner.',sources=[dict(source_id='source_mail',axes=['identity','affiliation','relevance'],assessment='supports')],route=dict(kind='email',value='PROJECTS@northstar.example',source_id='source_mail'))
        with self.f.tasks.repository.open() as snap:self.assertFalse(snap.contact('person_one')['qualified'])

    def test_person_suppression_cannot_be_bypassed_by_company_route(self):
        self.seed()
        self.f.command('contact.capture',id='person_one',name='Morgan Example',company_id='company_one',affiliation='current',relevance='Published project owner.',sources=[dict(source_id='source_mail',axes=['identity','affiliation','relevance'],assessment='supports')],route=dict(kind='email',value='projects@northstar.example',source_id='source_mail'))
        self.f.command('contact.suppress',person_id='person_one',kind='email',value='projects@northstar.example',reason='Actual endpoint opt-out.',evidence='Fictional recipient statement.')
        self.assertFalse(self.handoff()['ready'])
        self.assertFalse(next(r for r in self.f.tasks.query('cases')['items'] if r['id']=='case_mail')['qualified'])

    def test_lowercase_company_bounce_invalidates_uppercase_person_cache_and_counts(self):
        self.assert_bounce_alias('PROJECTS@northstar.example','projects@northstar.example')

    def test_unicode_email_alias_uses_same_comparison_in_projection_and_suppression(self):
        self.f.command('source.capture',id='source_mail',locator='https://northstar.example/contact',excerpt='Northstar Demo: проекты@northstar.example. Morgan Example coordinates projects.',observed_at='2026-10-26T00:00:00Z',readable=True)
        self.data['company_route']['value']='проекты@northstar.example'
        self.assert_bounce_alias('ПРОЕКТЫ@northstar.example','проекты@northstar.example')

    def assert_bounce_alias(self,person_email,company_email):
        self.seed()
        self.f.command('contact.capture',id='person_one',name='Morgan Example',company_id='company_one',affiliation='current',relevance='Published project owner.',sources=[dict(source_id='source_mail',axes=['identity','affiliation','relevance'],assessment='supports')],route=dict(kind='email',value=person_email,source_id='source_mail'))
        self.f.save();before=self.f.tasks.query('cases');self.assertTrue(next(r for r in before['items'] if r['id']=='case_one')['prepared'])
        self.f.command('activity.record',case_id='case_mail',kind='bounce',occurred_at='2026-10-26T00:02:00Z',channel=dict(kind='email',value=company_email),evidence='Fictional endpoint hard bounce.')
        self.assertFalse(self.f.tasks.query('selection',record_id='packet_one')['assessment']['prepared'])
        after=self.f.tasks.query('cases');person=next(r for r in after['items'] if r['id']=='case_one')
        self.assertFalse(person['prepared']);self.assertFalse(person['qualified']);self.assertEqual('qualify',person['column'])
        self.assertEqual(0,after['counts']['columns']['ready']);self.assertEqual(0,after['qualified_people'])
        self.assertEqual(0,self.f.tasks.query('board')['counts']['columns']['ready'])

if __name__=='__main__':unittest.main()
