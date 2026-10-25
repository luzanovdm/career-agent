"""Saved interview dialogue contract; fictional materials and no generation or practice."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from test_runtime_1 import Fixture
from career.contracts import CareerError
from career.interview import DIALOGUE_FORMAT, validate_interview_text, project_interview_slot


def dialogue():
    return dict(format=DIALOGUE_FORMAT,turns=[
        dict(kind='question',text='How would you explain the workflow?',status='hypothesis',source_ids=[],terms=[]),
        dict(kind='answer',text='I would use the documented example term.',status='outline',source_ids=['source_term'],
             terms=[dict(label='example term',url='https://workflow.example/concept',source_id='source_term')]),
        dict(kind='question',text='What would you ask the team?',status='hypothesis',source_ids=[],terms=[]),
        dict(kind='answer',text='I would ask about the supported workflow.',status='unknown',source_ids=[],terms=[]),
    ])


class DialogueTests(unittest.TestCase):
    def source(self,source_id):
        self.assertEqual('source_term',source_id)
        return dict(id=source_id,locator='https://workflow.example/concept',excerpt='A readable fictional explanation.',
                    observed_at='2026-10-24T00:00:00Z',readable=True)

    def test_actual_explicit_turns_and_sources_project_without_inferred_roles(self):
        value=dialogue();raw=json.dumps(value)
        self.assertEqual(value,validate_interview_text(raw,self.source))
        projected=project_interview_slot(dict(name='interview',artifact_id='artifact_demo',text=raw),self.source)
        self.assertEqual(['question','answer','question','answer'],[item['kind'] for item in projected])
        self.assertTrue(projected[1]['terms'][0]['available'])
        self.assertEqual('2026-10-24T00:00:00Z',projected[1]['sources'][0]['observed_at'])
        self.assertEqual(raw,json.dumps(value))
        document='INTERVIEWER\nExample question\n\nAPPLICANT OUTLINE\nSaved answer outline.'
        self.assertIsNone(validate_interview_text(document,self.source))
        plain=project_interview_slot(dict(name='interview',artifact_id='artifact_doc',text=document),self.source)
        self.assertEqual(1,len(plain));self.assertEqual('document',plain[0]['kind']);self.assertEqual(document,plain[0]['text'])
        self.assertEqual('file',project_interview_slot(dict(name='interview',artifact_id='artifact_file',text=None),self.source)[0]['kind'])

    def test_source_or_link_changes_are_unavailable_on_read_never_fabricated(self):
        source=lambda key:dict(self.source(key),readable=False)
        projected=project_interview_slot(dict(name='interview',artifact_id='artifact_demo',text=json.dumps(dialogue())),source)
        self.assertFalse(projected[1]['sources'][0]['available']);self.assertFalse(projected[1]['terms'][0]['available'])
        changed=lambda key:dict(self.source(key),locator='https://workflow.example/different')
        projected=project_interview_slot(dict(name='interview',artifact_id='artifact_demo',text=json.dumps(dialogue())),changed)
        self.assertFalse(projected[1]['terms'][0]['available'])
        def missing(key):raise CareerError('NOT_FOUND','Fictional source missing',404)
        projected=project_interview_slot(dict(name='interview',artifact_id='artifact_demo',text=json.dumps(dialogue())),missing)
        self.assertEqual('source_term',projected[1]['sources'][0]['id']);self.assertFalse(projected[1]['terms'][0]['available'])

    def test_save_rejects_unreadable_or_unobserved_links_and_false_confirmation(self):
        value=dialogue()
        for url in ('javascript:alert(1)','https://invented.example/term','https://user:password@workflow.example/concept'):
            invalid=copy.deepcopy(value);invalid['turns'][1]['terms'][0]['url']=url
            with self.assertRaises(CareerError):validate_interview_text(json.dumps(invalid),self.source)
        with self.assertRaises(CareerError):validate_interview_text(json.dumps(value),lambda key:dict(self.source(key),readable=False))
        invalid=copy.deepcopy(value);invalid['turns'][0]['status']='confirmed'
        with self.assertRaises(CareerError) as error:validate_interview_text(json.dumps(invalid),self.source)
        self.assertEqual('INTERVIEW_EVIDENCE_REQUIRED',error.exception.code)
        invalid=copy.deepcopy(value);invalid['turns'][1]['source_ids']=[]
        with self.assertRaises(CareerError):validate_interview_text(json.dumps(invalid),self.source)

    def test_shapes_roles_statuses_byte_and_turn_bounds_are_mechanical(self):
        invalids=[dict(format=DIALOGUE_FORMAT,turns=[]),dict(format=DIALOGUE_FORMAT,turns=dialogue()['turns']*26),
                  dict(format=DIALOGUE_FORMAT,turns=[dict(dialogue()['turns'][0],kind='assistant')]),
                  dict(format=DIALOGUE_FORMAT,turns=[dict(dialogue()['turns'][0],kind=[])]),
                  dict(format=DIALOGUE_FORMAT,turns=[dict(dialogue()['turns'][0],source_ids=[[]])]),
                  dict(format=DIALOGUE_FORMAT,turns=[dict(dialogue()['turns'][0],status='passed')]),
                  dict(format=DIALOGUE_FORMAT,turns=[dict(dialogue()['turns'][0],invented='extra')]),
                  dict(format='career-agent.interview/2',turns=dialogue()['turns'])]
        for value in invalids:
            with self.subTest(value=value),self.assertRaises(CareerError):validate_interview_text(json.dumps(value),self.source)
        with self.assertRaises(CareerError):validate_interview_text('{"format":"career-agent.interview/1",',self.source)
        with self.assertRaises(CareerError):validate_interview_text('x'*262145,self.source)
        with self.assertRaises(CareerError):validate_interview_text('я'*140000,self.source)


class SavedDialogueTests(unittest.TestCase):
    def test_real_packet_save_has_one_object_and_projects_four_explicit_turns(self):
        with tempfile.TemporaryDirectory(prefix='career-dialogue-fictional-') as folder:
            fx=Fixture(folder).seed()
            fx.command('source.capture',id='source_term',locator='https://workflow.example/concept',excerpt='A documented fictional explanation.',observed_at='2026-10-24T00:00:00Z',readable=True)
            fx.command('packet.create',id='packet_interview',case_id='case_one',purpose='interview')
            original=fx.tasks.query('case',record_id='case_one')
            raw=json.dumps(dialogue())
            fx.command('packet.save',packet_id='packet_interview',used_claim_ids=[],documents=[dict(slot='interview',text=raw)])
            selection=fx.tasks.query('selection',record_id='packet_interview')
            self.assertEqual(1,len(selection['slots']));self.assertEqual(raw,selection['slots'][0]['text'])
            self.assertEqual(['question','answer','question','answer'],[turn['kind'] for turn in selection['interview']])
            self.assertTrue(selection['interview'][1]['terms'][0]['available'])
            current=fx.tasks.query('case',record_id='case_one')
            self.assertEqual(original['selection']['packet_id'],current['selection']['packet_id'])
            self.assertEqual(original['history'],current['history'])
            revision=fx.tasks.context()['revision']
            invalid=dialogue();invalid['turns'][1]['terms'][0]['url']='https://unobserved.example/concept'
            with self.assertRaises(CareerError):fx.command('packet.save',packet_id='packet_interview',used_claim_ids=[],documents=[dict(slot='interview',text=json.dumps(invalid))])
            self.assertEqual(revision,fx.tasks.context()['revision'])
            fx.command('source.capture',id='source_term',locator='https://workflow.example/concept',excerpt='A later fictional source observation at the same URL.',observed_at='2026-10-24T12:00:00Z',readable=True)
            changed=fx.tasks.query('selection',record_id='packet_interview')
            self.assertFalse(changed['interview'][1]['terms'][0]['available'])
            self.assertEqual(raw,changed['slots'][0]['text'])
            self.assertEqual(original['selection']['packet_id'],fx.tasks.query('case',record_id='case_one')['selection']['packet_id'])
            self.assertEqual('paused',fx.tasks.context()['research']['status'])
