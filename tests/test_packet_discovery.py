"""Fictional read-only packet navigation and export freshness regressions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from test_runtime_1 import Fixture
import test_http_1
from career.contracts import CareerError
from career.views import render


def alternatives(fx):
    fx.command('contact.capture',id='person_two',name='Taylor Example',company_id='company_one',affiliation='unknown',relevance='Fictional colleague',sources=[dict(source_id='source_one',axes=['identity'],assessment='supports')],route=None)
    for key,person in [('contact_a','person_one'),('contact_b','person_two')]:
        fx.command('packet.create',id=key,case_id='case_one',person_id=person,purpose='contact')
        fx.command('packet.save',packet_id=key,used_claim_ids=[],documents=[dict(slot='message',text='Message '+key),dict(slot='interview',text='Preparation '+key)])
    fx.command('packet.create',id='contact_empty',case_id='case_one',purpose='contact',person_id='person_one')


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='career-packets-fictional-');self.addCleanup(self.temp.cleanup)
        self.fx=Fixture(self.temp.name).seed();alternatives(self.fx)

    def test_all_case_and_person_packets_have_labels_without_changing_primary_or_history(self):
        fx=self.fx
        selected=fx.tasks.query('selection',record_id='packet_one')
        fx.command('activity.record',case_id='case_one',kind='sent',occurred_at='2026-10-24T12:00:00Z',evidence='Fictional manual send scenario',packet_id='packet_one',version_id=selected['version_id'])
        before=fx.tasks.context()['revision']
        case=fx.tasks.query('case',record_id='case_one')
        self.assertEqual(4,len(case['packets']));self.assertEqual('packet_one',case['selection']['packet_id'])
        self.assertEqual(['packet_one'],[p['id'] for p in case['packets'] if p['is_primary']])
        self.assertEqual({'Morgan Example','Taylor Example'},{p['person_name'] for p in case['packets']})
        page=fx.tasks.query('contact-packets',record_id='person_one',limit=1)
        ids=[]
        while True:
            ids.extend(p['id'] for p in page['items'])
            if not page['next_cursor']:break
            page=fx.tasks.query('contact-packets',record_id='person_one',limit=1,cursor=page['next_cursor'])
        self.assertEqual({'packet_one','contact_a','contact_empty'},set(ids))
        self.assertEqual(['contact_b'],[p['id'] for p in fx.tasks.query('contact-packets',record_id='person_two')['items']])
        for packet in ('contact_a','contact_b','packet_one'):
            self.assertEqual(packet,fx.tasks.query('selection',record_id=packet)['packet_id'])
        self.assertEqual(before,fx.tasks.context()['revision'])
        self.assertEqual(case,fx.tasks.query('case',record_id='case_one'))
        fx.command('case.close',case_id='case_one',reason='Fictional closure',evidence='Fictional user decision')
        self.assertEqual(4,len(fx.tasks.query('case',record_id='case_one')['packets']))
        fx.command('case.reopen',case_id='case_one',reason='Fictional reopen')
        final=fx.tasks.query('case',record_id='case_one')
        self.assertEqual(case['history'],final['history']);self.assertEqual('packet_one',final['selection']['packet_id'])
        self.assertEqual('paused',fx.tasks.context()['research']['status'])

    def test_contact_pagination_scope_and_revision_conflicts(self):
        page=self.fx.tasks.query('contact-packets',record_id='person_one',limit=1)
        with self.assertRaises(CareerError):self.fx.tasks.query('contact-packets',record_id='person_two',cursor=page['next_cursor'])
        self.fx.command('case.note',case_id='case_one',text='Fictional change')
        with self.assertRaises(CareerError):self.fx.tasks.query('contact-packets',record_id='person_one',cursor=page['next_cursor'])

    def test_explicit_packet_agent_handoff_never_silently_targets_primary(self):
        tasks=self.fx.tasks
        intent=tasks.query('agent-intent',intent='agent.review',case_id='case_one',packet_id='contact_b')['descriptor']
        self.assertEqual(['contact_b'],intent['scope']['packet_ids']);self.assertEqual('packet',intent['selection_mode'])
        self.fx.command('case.note',case_id='case_one',text='Unrelated private note')
        self.assertTrue(tasks.query('resolve-intent',descriptor=intent)['context_refreshed'])
        self.fx.command('packet.save',packet_id='contact_b',documents=[dict(slot='message',text='New exact draft')],used_claim_ids=[])
        with self.assertRaises(CareerError) as error:tasks.query('resolve-intent',descriptor=intent)
        self.assertEqual('SELECTION_CONFLICT',error.exception.code)
        self.assertEqual('packet_one',tasks.query('case',record_id='case_one')['selection']['packet_id'])
        old=tasks.query('agent-intent',intent='agent.review',case_id='case_one')['descriptor']
        self.assertNotIn('selection_mode',old);tasks.query('resolve-intent',descriptor=old)
        with self.assertRaises(CareerError):tasks.query('agent-intent',intent='agent.review',packet_id='contact_b')

    def test_exports_report_exact_revision_missing_stale_current_without_business_writes(self):
        fx=self.fx;before=fx.tasks.context()['revision']
        self.assertTrue(all(row['status']=='missing' for row in fx.tasks.context()['exports']))
        exports={}
        for kind in ('csv','xlsx','profile','snapshot'):
            exports[kind]=render(fx.tasks.repository,kind)
        self.assertEqual(before,fx.tasks.context()['revision'])
        self.assertTrue(all(row['status']=='current' for row in fx.tasks.context()['exports']))
        self.assertIn('Revision '+str(before), (Path(exports['profile']['destination'])/'Profile.md').read_text())
        fx.command('case.note',case_id='case_one',text='New fictional state')
        self.assertTrue(all(row['status']=='stale' and row['revision']==before for row in fx.tasks.context()['exports']))
        render(fx.tasks.repository,'csv')
        status={row['kind']:row['status'] for row in fx.tasks.context()['exports']}
        self.assertEqual('current',status['csv']);self.assertEqual('stale',status['profile'])
        self.assertEqual(before+1,fx.tasks.context()['revision'])

    def test_new_interface_keys_do_not_break_or_overwrite_an_installed_custom_locale(self):
        from unittest.mock import patch
        with self.fx.tasks.repository.open() as snapshot:english=snapshot.builtin_catalog('en')
        categories=['one','few','many','other']
        messages={key:value if isinstance(value,str) else {category:value.get(category,value['other']) for category in categories} for key,value in english['messages'].items()}
        messages['app.title']='Synthetic translated title'
        self.fx.command('locale.install',locale='pl',plural_categories=categories,messages=messages)
        revision=self.fx.tasks.context()['revision']
        with self.fx.tasks.repository.open() as snapshot:
            record=snapshot.one('SELECT artifact_id FROM locale_catalogs WHERE locale="pl"')
            _,path=snapshot.object(record['artifact_id']);original=path.read_bytes()
            future=dict(english,messages=dict(english['messages'],new_key='New interface text'))
            with patch.object(snapshot,'builtin_catalog',return_value=future):localized=snapshot.localization('pl')
            self.assertEqual('Synthetic translated title',localized['catalog']['app.title'])
            self.assertEqual('New interface text',localized['catalog']['new_key'])
            self.assertEqual(['new_key'],localized['issues'][0]['missing_keys'])
            self.assertEqual(original,path.read_bytes())
        self.assertEqual(revision,self.fx.tasks.context()['revision'])


class DiscoveryHttpTests(unittest.TestCase):
    setUp = test_http_1.HttpTests.setUp
    cleanup_server = test_http_1.HttpTests.cleanup_server
    request = test_http_1.HttpTests.request
    authenticate = test_http_1.HttpTests.authenticate
    def test_contact_packet_route_is_authenticated_bounded_and_scoped(self):
        alternatives(self.fx)
        self.assertEqual(401,self.request('/api/v1/contacts/person_one/packets')[0])
        self.authenticate()
        status,_,body=self.request('/api/v1/contacts/person_one/packets?limit=1')
        self.assertEqual(200,status);page=json.loads(body)
        self.assertEqual(3,page['total']);self.assertEqual(1,len(page['items']));self.assertTrue(page['next_cursor'])
        self.assertEqual(422,self.request('/api/v1/contacts/person_one/packets?sql=x')[0])
        self.assertEqual(422,self.request('/api/v1/contacts/person_one/packets?limit=101')[0])
        self.assertEqual(422,self.request('/api/v1/contacts/person_one/packets?cursor=e30=')[0])
        status,_,body=self.request('/api/v1/agent-intent?intent=agent.review&case_id=case_one&packet_id=contact_b')
        self.assertEqual(200,status);self.assertEqual(['contact_b'],json.loads(body)['descriptor']['scope']['packet_ids'])

class HistoricalVersionTests(unittest.TestCase):
    setUp = DiscoveryTests.setUp
    def test_exact_old_version_reads_never_select_or_repin_sent_materials(self):
        tasks=self.fx.tasks;old=tasks.query('selection',record_id='packet_one')
        self.fx.command('activity.record',case_id='case_one',kind='sent',occurred_at='2026-10-24T12:00:00Z',evidence='Fictional pinned send',packet_id='packet_one',version_id=old['version_id'])
        self.fx.save('Improved processing by 25%. New fictional draft.',review=False)
        selected=tasks.query('selection',record_id='packet_one');before=tasks.context()['revision']
        historical=tasks.query('selection',record_id='packet_one',version_id=old['version_id'])
        self.assertFalse(historical['is_selected']);self.assertEqual(old['slots'],historical['slots'])
        page=tasks.query('versions',record_id='packet_one',limit=1)
        self.assertEqual(2,page['total']);self.assertEqual(selected['version_id'],page['items'][0]['id'])
        earlier=tasks.query('versions',record_id='packet_one',limit=1,cursor=page['next_cursor'])
        self.assertEqual(old['version_id'],earlier['items'][0]['id'])
        self.assertEqual(before,tasks.context()['revision']);self.assertEqual(selected,tasks.query('selection',record_id='packet_one'))
        history=tasks.query('case-history',record_id='case_one')['items']
        self.assertEqual(old['version_id'],history[0]['version_id']);self.assertFalse(history[0]['payload_unknown'])
        intent=tasks.query('agent-intent',intent='agent.review',case_id='case_one',packet_id='packet_one',version_id=old['version_id'])['descriptor']
        self.assertEqual('version',intent['selection_mode']);self.assertEqual(old['version_id'],tasks.query('resolve-intent',descriptor=intent)['viewed_selection']['version_id'])
        with self.assertRaises(CareerError):tasks.query('selection',record_id='contact_a',version_id=old['version_id'])

    def test_unknown_sent_pin_stays_unknown_and_role_identity_is_readable(self):
        # Imported historical uncertainty is not a new-send command with missing pins.
        db=self.fx.tasks.repository.connect()
        try:db.execute('INSERT INTO activities VALUES (?,?,?,?,?,?,?,?,?,?)',('legacy_unknown','case_one','sent','2026-10-24T12:00:00Z','2026-10-24T12:00:00Z','Fictional historical send with no known attachment',None,None,None,'{}'))
        finally:db.close()
        case=self.fx.tasks.query('case',record_id='case_one')
        self.assertTrue(case['history'][0]['payload_unknown']);self.assertIsNone(case['history'][0]['version_id'])
        self.assertEqual('REQ-42',case['role']['reference'])

class ExportDownloadTests(unittest.TestCase):
    setUp = DiscoveryHttpTests.setUp
    cleanup_server = DiscoveryHttpTests.cleanup_server
    request = DiscoveryHttpTests.request
    authenticate = DiscoveryHttpTests.authenticate
    def test_manifest_bound_static_downloads_and_changed_or_missing_exports(self):
        self.authenticate();render(self.fx.tasks.repository,'csv')
        context=json.loads(self.request('/api/v1/context')[2]);export=next(item for item in context['exports'] if item['kind']=='csv')
        self.assertTrue(export['generated_at']);self.assertEqual('current',export['status'])
        url=export['files'][0]['download_url'];status,headers,content=self.request(url)
        self.assertEqual(200,status);self.assertIn('attachment;',headers['Content-Disposition'])
        with self.fx.tasks.repository.open() as snapshot:
            row=snapshot.one("SELECT path FROM view_exports WHERE kind='csv'")
        file=Path(row['path'])/export['files'][0]['name'];self.assertEqual(file.read_bytes(),content)
        file.write_text('Changed fictional file')
        self.assertEqual(422,self.request(url)[0])
        self.assertEqual(404,self.request('/api/v1/exports/unknown/files/0')[0])
        self.assertEqual(422,self.request(url+'?path=/etc/passwd')[0])
        manifest=Path(row['path'])/'manifest.json';manifest.unlink()
        context=json.loads(self.request('/api/v1/context')[2]);export=next(item for item in context['exports'] if item['kind']=='csv')
        self.assertEqual('VIEW_UNAVAILABLE',export['issue']);self.assertEqual([],export['files'])
