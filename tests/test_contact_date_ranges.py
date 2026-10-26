"""Fictional contact-disclosure regressions; no applicant documents in source."""
import json
from itertools import product
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from career.binary import contact_checks
from career.contracts import CareerError
from test_runtime_1 import Fixture
from test_runtime_extended_1 import docx


def preference(disposition='omit',value=None):
    return dict(id='answer_phone',meaning='contact.phone.preference',disposition='answered',value=dict(disposition=disposition,value=value))


class ContactDateTests(unittest.TestCase):
    def check(self,text,answer=None):
        return contact_checks([dict(slot='resume',text=text)],[answer or preference()])

    def test_valid_education_period_is_not_an_omitted_phone(self):
        for text in ('Example College · 2008 - 2012','Experience: 2014-2019','Observed: 2026-10-26'):
            with self.subTest(text=text):self.assertEqual([],self.check(text))

    def test_real_phones_including_ambiguous_year_shaped_labels_still_block(self):
        for text in ('Phone: +1 202 555 0142','+44 (0)20 7946 0123','1234-5678','20122016','Phone: 2012 - 2016','Phone number: 2012 - 2016','Contact: 2012 - 2016','tel:2012-2016','Телефон: 2012 - 2016','+2012 - 2016','Invalid date: 2016-2012'):
            with self.subTest(text=text):self.assertIn('CONTACT_DISCLOSURE_BLOCKED',{i['code'] for i in self.check(text)})

    def test_explicit_phone_fields_keep_priority_through_wrappers_and_qualifiers(self):
        fields=[label+index+qualifier+': '+mark for label,index,qualifier,mark in product(('Phone','Telephone','Tel','Mobile','Fax','Contact','Телефон'),('',' 1',' #2'),('',' (office 2)',' [desk 3]',' (work) (optional)',' [office 2] (direct)',' (office (work))',' \"work\" [optional]'),('','\u200e','\u200f','\u202a','\u2066','\u2069','\u200b'))]
        fields.extend(('Phone (office 2) #1:', 'Phone: (office 2):', 'Ph\u200fone: \u2066'))
        for field in fields:
            for opening,closing in (('', ''), ('(', ')'), ('[', ']'), ('"', '"'), ('“', '”'), ('«(', ')»')):
                for value in ('2012 - 2016', '2026-10-26'):
                    text=f'{field} {opening}{value}{closing}'
                    with self.subTest(text=text):
                        self.assertIn('CONTACT_DISCLOSURE_BLOCKED',{i['code'] for i in self.check(text)})
                        unknown=contact_checks([dict(slot='resume',text=text)],[])
                        self.assertIn('CONTACT_PREFERENCE_UNKNOWN',{i['code'] for i in unknown})
        for text in ('Education: (2012 - 2016)', 'Dates: [2026-10-26]', 'Contact history: Example College (2012 - 2016)'):
            with self.subTest(text=text):self.assertEqual([],self.check(text))

    def test_explicit_current_phone_is_not_reinterpreted_as_a_period(self):
        issues=self.check('Phone: 2012 - 2016',preference('use','20122015'))
        self.assertIn('CONTACT_MISMATCH',{i['code'] for i in issues})

    def test_phone_error_exposes_location_without_leaking_omitted_number(self):
        body='Private note. Phone: +1 202 555 0142'
        issue=self.check(body)[0]
        self.assertEqual('resume',issue['slot']);self.assertEqual('+1 202 555 0142',body[issue['start']:issue['end']])
        self.assertEqual('unicode_code_points',issue['offset_unit']);self.assertNotIn('+1 202 555 0142',json.dumps(issue))

    def test_omission_is_checked_independently_in_every_external_slot(self):
        issues=contact_checks([dict(slot='resume',text='Example College · 2008 - 2012'),dict(slot='message',text='Phone: +1 202 555 0142'),dict(slot='notes',text='Phone: +1 202 555 0100')],[preference()])
        self.assertEqual(1,len(issues));self.assertEqual('message',issues[0]['slot'])


class ContactBinaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='career-contact-date-');self.addCleanup(self.temp.cleanup);self.f=Fixture(self.temp.name).seed()
        self.f.command('answer.save',meaning='contact.phone.preference',scope={},units={},disposition='answered',value=dict(disposition='omit',value=None),evidence='Explicit fictional omission choice.')

    def save(self,text):
        self.f.command('packet.save',packet_id='packet_one',documents=[dict(slot='resume',text=text)],used_claim_ids=[])
        return self.f.tasks.query('selection',record_id='packet_one')

    def test_attach_dated_document_preserves_exact_bytes_and_other_review_blocks(self):
        text='Example College · 2008 - 2012';selected=self.save(text);body=docx(text);path=self.f.root/'.career-agent/staging/input_period';path.write_bytes(body)
        self.f.command('artifact.attach',packet_id='packet_one',slot='resume',input_id='input_period',source_artifact_id=selected['slots'][0]['artifact_id'],extension='docx')
        after=self.f.tasks.query('selection',record_id='packet_one');self.assertFalse(after['assessment']['prepared'])
        with self.f.tasks.repository.open() as snapshot:
            _,actual=snapshot.object(after['slots'][0]['artifact_id']);self.assertEqual(body,actual.read_bytes())

    def test_rejected_binary_returns_exact_contact_issue_and_no_partial_commit(self):
        text='Phone: +1 202 555 0142';selected=self.save(text);revision=self.f.tasks.context()['revision'];(self.f.root/'.career-agent/staging/input_phone').write_bytes(docx(text))
        with self.assertRaises(CareerError) as caught:self.f.command('artifact.attach',packet_id='packet_one',slot='resume',input_id='input_phone',source_artifact_id=selected['slots'][0]['artifact_id'],extension='docx')
        self.assertEqual('CONTACT_DISCLOSURE_BLOCKED',caught.exception.code);self.assertEqual('resume',caught.exception.issues[0]['slot']);self.assertEqual(revision,self.f.tasks.context()['revision'])
        self.assertEqual(selected['version_id'],self.f.tasks.query('selection',record_id='packet_one')['version_id'])

    def test_current_projection_rechecks_saved_legacy_contact_finding(self):
        review=dict(findings='Compared fictional education dates.',limitations='Other numeric evidence still needs review.',tone_findings='Fixture only.',claim_spans=[],coverage=[])
        with patch('career.binary.calendar_period',lambda *args:False):
            receipt=self.f.command('packet.save',packet_id='packet_one',documents=[dict(slot='resume',text='Example College · 2008 - 2012')],used_claim_ids=[],review=review)
            old=self.f.tasks.query('selection',record_id='packet_one')
        self.assertIn('CONTACT_DISCLOSURE_BLOCKED',{i['code'] for i in receipt['issues']})
        revision=self.f.tasks.context()['revision'];current=self.f.tasks.query('selection',record_id='packet_one')
        self.assertNotIn('CONTACT_DISCLOSURE_BLOCKED',{i['code'] for i in current['assessment']['issues']})
        self.assertIn('UNMATCHED_NUMBER',{i['code'] for i in current['assessment']['issues']})
        self.assertEqual(old['version_id'],current['version_id']);self.assertEqual(old['review'],current['review']);self.assertEqual(revision,self.f.tasks.context()['revision'])
        cached=self.f.tasks.query('cases')['items'][0]
        self.assertNotIn('CONTACT_DISCLOSURE_BLOCKED',{i['code'] for i in cached['blockers']});self.assertFalse(cached['prepared'])

    def save_phone_review(self,f,text):
        f.command('source.capture',id='source_phone',locator='https://northstar.example/fixture',excerpt=text,observed_at='2026-10-24T00:00:00Z',readable=True)
        f.command('claim.save',id='claim_one',assertion=text,meaning=text,source_ids=['source_phone'],confirmation='confirmed',disclosure='allowed')
        return f.command('packet.save',packet_id='packet_one',used_claim_ids=['claim_one'],documents=[dict(slot='resume',text=text),dict(slot='message',text='An evidenced contribution.'),dict(slot='dossier',text='Private context.'),dict(slot='interview',text='Private preparation.')],review=dict(findings='Compared exact synthetic evidence.',limitations='Mechanical fixture only.',tone_findings='No invented familiarity.',claim_spans=[dict(claim_id='claim_one',text=text)],coverage=[dict(claim_id='claim_one',disposition='included')]))

    def test_wrapped_phone_blocks_facade_handoff_and_exact_binary_atomically(self):
        for index,text in enumerate(('Phone: (2012 - 2016)', 'Phone: [2012 - 2016]', 'Phone: "2012 - 2016"', 'Phone (work): 2012 - 2016', 'Phone: \u200e2012 - 2016', 'Phone (office 2): 2012 - 2016', 'Phone 1: 2012 - 2016', 'Phone (work) (optional): 2012 - 2016', 'Phone 1 [office 2] (direct): 2012 - 2016')):
            with self.subTest(text=text):
                receipt=self.save_phone_review(self.f,text)
                self.assertIn('CONTACT_DISCLOSURE_BLOCKED',{i['code'] for i in receipt['issues']})
                selected=self.f.tasks.query('selection',record_id='packet_one')
                self.assertFalse(selected['assessment']['prepared'])
                self.assertFalse(self.f.tasks.query('cases')['items'][0]['prepared'])
                self.assertFalse(self.f.tasks.query('handoff-check',input=dict(packet_id='packet_one',version_id=selected['version_id'],documents=[dict(slot=s['name'],text=s['text']) for s in selected['slots'] if s['name'] in ('resume','message','answers')],recipient=dict(kind='profile',value='https://northstar.example/team/morgan')))['ready'])
                input_id='input_wrapped_'+str(index);(self.f.root/'.career-agent/staging'/input_id).write_bytes(docx(text));revision=self.f.tasks.context()['revision']
                with self.assertRaises(CareerError) as caught:self.f.command('artifact.attach',packet_id='packet_one',slot='resume',input_id=input_id,source_artifact_id=next(s['artifact_id'] for s in selected['slots'] if s['name']=='resume'),extension='docx')
                self.assertEqual('CONTACT_DISCLOSURE_BLOCKED',caught.exception.code);self.assertEqual(revision,self.f.tasks.context()['revision'])

    def test_cached_readiness_rechecks_legacy_iso_phone_without_any_answer(self):
        with tempfile.TemporaryDirectory(prefix='career-legacy-phone-') as root:
            f=Fixture(root).seed();text='Phone: 2026-10-26'
            with patch('career.binary.calendar_period',lambda *args:True):
                self.save_phone_review(f,text)
                f.command('batch.save',id='batch_phone',task='packets',requested_count=1,count_unit='cases',track_ids=['track_one'],criterion='One prepared synthetic packet',selected_ids=['case_one'],required_outputs=[])
                self.assertTrue(f.tasks.query('selection',record_id='packet_one')['assessment']['prepared'])
                self.assertTrue(f.tasks.query('cases')['items'][0]['prepared'])
                self.assertEqual(1,f.tasks.query('board')['counts']['columns']['ready']);self.assertTrue(f.tasks.query('assess',record_id='batch_phone')['task_complete'])
            revision=f.tasks.context()['revision'];selected=f.tasks.query('selection',record_id='packet_one')
            self.assertIn('CONTACT_PREFERENCE_UNKNOWN',{i['code'] for i in selected['assessment']['issues']})
            cached=f.tasks.query('cases')['items'][0]
            self.assertFalse(cached['prepared']);self.assertNotEqual('ready',cached['column'])
            self.assertEqual(0,f.tasks.query('board')['counts']['columns']['ready']);assessed=f.tasks.query('assess',record_id='batch_phone');self.assertFalse(assessed['task_complete']);self.assertEqual(0,assessed['prepared'])
            self.assertIn('CONTACT_PREFERENCE_UNKNOWN',{i['code'] for i in cached['blockers']})
            self.assertFalse(f.tasks.query('case',record_id='case_one')['selection']['assessment']['prepared'])
            self.assertFalse(f.tasks.query('handoff-check',input=dict(packet_id='packet_one',version_id=selected['version_id'],documents=[dict(slot=s['name'],text=s['text']) for s in selected['slots'] if s['name'] in ('resume','message','answers')],recipient=dict(kind='profile',value='https://northstar.example/team/morgan')))['ready'])
            self.assertEqual(revision,f.tasks.context()['revision'])

    def test_phone_in_docx_header_remains_disclosed_and_blocked(self):
        from career.binary import extract_docx
        body=docx('Example College · 2008 - 2012','Phone: +1 202 555 0142');text,_=extract_docx(body);selected=self.save(text)
        (self.f.root/'.career-agent/staging/input_header').write_bytes(body)
        with self.assertRaises(CareerError) as caught:self.f.command('artifact.attach',packet_id='packet_one',slot='resume',input_id='input_header',source_artifact_id=selected['slots'][0]['artifact_id'],extension='docx')
        self.assertTrue(caught.exception.issues)


if __name__=='__main__':unittest.main()
