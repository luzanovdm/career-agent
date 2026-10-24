"""CP4 selection/scope correctness and measured recovery regressions. Fictional only."""
import io
import json
import tempfile
import tarfile
from pathlib import Path
import sys
import unittest
from test_runtime_1 import Fixture
from career.contracts import CareerError,canonical,digest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'maintenance'))
from import_legacy import migrate
from import_archive import ImportLimits


class CP4Regressions(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='career-cp4-fictional-',dir='/tmp');self.addCleanup(self.temp.cleanup)
        self.fx=Fixture(Path(self.temp.name)/'workspace')

    def test_selected_primary_recipient_owns_board_table_batch_and_invalidation(self):
        f=self.fx.seed()
        f.command('source.capture',id='source_two',locator='https://northstar.example/team/taylor',excerpt='Taylor Example works on the product workflow at Northstar Demo.',readable=True,observed_at='2026-10-24T00:00:00Z')
        f.command('contact.capture',id='person_two',name='Taylor Example',company_id='company_one',affiliation='current',relevance='Product workflow colleague',sources=[dict(source_id='source_two',axes=['identity','affiliation','relevance'],assessment='supports')],route=dict(kind='profile',value='https://northstar.example/team/taylor',source_id='source_two'))
        f.command('packet.create',id='packet_two',case_id='case_one',purpose='application',person_id='person_two')
        f.command('packet.save',packet_id='packet_two',used_claim_ids=['claim_one'],documents=[dict(slot=slot,text='Improved processing by 25%.' if slot=='resume' else 'Taylor, a specific supported contribution.') for slot in ('resume','message','dossier','interview')],review=dict(findings='Compared actual supported synthetic sources.',limitations='No independent truth guarantee.',tone_findings='Specific wording.',claim_spans=[dict(claim_id='claim_one',text='Improved processing by 25%.')],coverage=[dict(claim_id='claim_one',disposition='included')]))
        f.command('packet.primary',packet_id='packet_two')
        f.command('contact.capture',id='person_one',name='Morgan Example',company_id='company_one',affiliation='unknown',relevance='Workflow colleague',sources=[dict(source_id='source_one',axes=['identity','affiliation','relevance'],assessment='supports')],route=dict(kind='profile',value='https://northstar.example/team/morgan',source_id='source_one'))
        for task,unit,selected in [('packets','cases','case_one'),('contacts','people','person_two')]:
            f.command('batch.save',id='batch_'+task,task=task,requested_count=1,count_unit=unit,track_ids=['track_one'],criterion='Selected useful person/packet',selected_ids=[selected],required_outputs=[])
            assessed=f.tasks.query('assess',record_id='batch_'+task);self.assertTrue(assessed['task_complete']);self.assertEqual(1,assessed['qualified'])
        detail=f.tasks.query('case',record_id='case_one');self.assertEqual('person_two',detail['case']['contact']['id']);self.assertEqual('person_two',detail['selection']['person_id'])
        table=f.tasks.query('cases');self.assertEqual('person_two',table['items'][0]['contact']['id']);self.assertEqual(1,table['qualified_people'])
        board=f.tasks.query('board');self.assertEqual('person_two',board['columns']['ready']['items'][0]['contact']['id']);self.assertEqual(1,board['qualified_people'])
        with f.tasks.repository.open() as s:self.assertEqual('person_one',s.get('case','case_one')['person_id'])
        f.command('source.capture',id='source_two',locator='https://northstar.example/team/taylor',excerpt='',readable=False,observed_at='2026-10-24T00:00:00Z')
        board=f.tasks.query('board');self.assertEqual(0,board['counts']['columns']['ready']);self.assertEqual(0,board['qualified_people'])
        self.assertFalse(f.tasks.query('assess',record_id='batch_packets')['task_complete'])

    def test_explicit_empty_intent_scope_does_not_pick_up_later_tracks_or_answers(self):
        f=self.fx;descriptor=f.tasks.query('agent-intent',intent='agent.prepare')['descriptor'];self.assertEqual([],descriptor['scope']['track_ids'])
        f.command('track.save',id='track_later',name='Later fictional career',positioning='Later',selected=True,language='en',policies={})
        f.command('answer.save',id='answer_later',meaning='location.preference',scope=dict(track_id='track_later'),units={},disposition='answered',value='Later track only',evidence='Fictional supplied answer')
        resumed=f.tasks.query('resolve-intent',descriptor=descriptor);context=resumed['context']
        self.assertTrue(resumed['context_refreshed']);self.assertEqual([],context['tracks']);self.assertEqual([],context['evidence']['answers']);self.assertEqual(0,context['pagination']['tracks']['total']);self.assertEqual(1,context['pagination']['tracks']['omitted_by_scope'])
        self.assertEqual('empty_intent_scope',context['coverage']['claim_scope'])

    def test_indexed_delivery_query_preserves_same_person_uncertainty_across_cases(self):
        f=self.fx.seed();selected=f.tasks.query('selection',record_id='packet_one')
        f.command('activity.record',case_id='case_one',kind='uncertain',occurred_at='2026-10-24T10:00:00Z',evidence='Fictional lost provider response.',packet_id='packet_one',version_id=selected['version_id'])
        f.command('case.capture',id='case_two',company_id='company_one',title='Other exact role',kind='vacancy',route='person',tracks=[dict(id='track_one',rationale='Supported workflow')],source_ids=['source_one'],requisition='REQ-43',person_id='person_one')
        f.command('packet.create',id='packet_two',case_id='case_two',purpose='application')
        f.command('packet.save',packet_id='packet_two',documents=[dict(slot='message',text='Fictional draft')],used_claim_ids=[])
        self.assertTrue(f.tasks.query('selection',record_id='packet_two')['delivery']['retry_blocked'])
        with f.tasks.repository.open() as s:
            statements=[];s._db.set_trace_callback(statements.append);s.selection('packet_two');s._db.set_trace_callback(None)
            query=next(q for q in statements if q.startswith('SELECT a.id FROM activities a WHERE'))
            plan=[r['detail'] for r in s.rows('EXPLAIN QUERY PLAN '+query)]
            self.assertFalse(any(x=='SCAN a' for x in plan),plan)
        with f.tasks.repository.open() as s:uncertain=s.one('SELECT id FROM activities WHERE kind="uncertain"')['id']
        f.command('activity.record',case_id='case_one',kind='not_sent',occurred_at='2026-10-24T10:00:00Z',evidence='Fictional explicit provider history.',resolves_activity_id=uncertain)
        self.assertFalse(f.tasks.query('selection',record_id='packet_two')['delivery']['retry_blocked'])

    def source(self,extra=''):
        root=Path(self.temp.name)/'source';(root/'Data').mkdir(parents=True)
        value=dict(schema_version=1,revision=804,sources=[],facts=[],companies=[],opportunities=[],materials=[],extra_original=extra)
        raw=canonical(value).encode();(root/'Data/state.json').write_bytes(raw);return root,raw

    def test_large_original_is_stream_archived_verified_and_runtime_caps_remain(self):
        root,raw=self.source('F'*(27*1024*1024));destination=Path(self.temp.name)/'import'
        result=migrate(root,destination,digest(raw),allow_partial=True,limits=ImportLimits(chunk_bytes=65536))
        report=json.loads((destination/'Data/import-report.json').read_text());self.assertTrue(result['accepted']);self.assertFalse(result['activation_allowed'])
        archive=report['originals_archive'];self.assertTrue(archive['verification']['verified']);self.assertEqual(len(raw),archive['verification']['original_bytes'])
        self.assertTrue(all(chunk['size']<=65536 for chunk in archive['chunks']))
        compressed=b''.join((destination/'Objects'/(chunk['sha256']+'.bin')).read_bytes() for chunk in archive['chunks'])
        with tarfile.open(fileobj=io.BytesIO(compressed),mode='r:gz') as tar:self.assertEqual(raw,tar.extractfile('Data/state.json').read())
        self.assertEqual(digest(raw),digest((root/'Data/state.json').read_bytes()))
        from import_repository import ImportRepository
        with self.assertRaises(CareerError):ImportRepository(destination).publish(b'B'*(26*1024*1024))

    def test_resource_limits_fail_before_copy_or_retain_explicit_unactivated_failure(self):
        root,raw=self.source('Bounded fictional input')
        destination=Path(self.temp.name)/'too_big'
        with self.assertRaises(CareerError) as error:migrate(root,destination,digest(raw),limits=ImportLimits(state_bytes=10))
        self.assertEqual('IMPORT_RESOURCE_LIMIT',error.exception.code);self.assertFalse(destination.exists())
        with self.assertRaises(CareerError):ImportLimits(state_bytes=512*1024*1024).validate()
        failed=Path(self.temp.name)/'failed_archive'
        with self.assertRaises(CareerError):migrate(root,failed,digest(raw),limits=ImportLimits(archive_bytes=1))
        report=json.loads((failed/'Data/import-report.json').read_text());self.assertEqual('failed',report['status']);self.assertFalse(report['activation_allowed']);self.assertFalse((failed/'.career-agent/active.json').exists())

    def test_snapshot_metadata_reuse_never_promotes_unsaved_caller_mutations(self):
        f=self.fx.seed()
        with f.tasks.repository.open() as snapshot:
            company=snapshot.get('company','company_one');company['name']='Unsaved caller mutation'
            source=snapshot.get('source','source_one');source['readable']=False;source['detail']={}
            self.assertEqual('Northstar Demo',snapshot.get('company','company_one')['name'])
            self.assertTrue(snapshot.contact('person_one')['qualified'])
        self.assertEqual('Northstar Demo',f.tasks.query('case',record_id='case_one')['case']['company'])

    def test_structural_indexes_never_touch_an_unrecognized_sqlite_database(self):
        import sqlite3
        from career.repository import Repository
        root=Path(self.temp.name)/'unrecognized';(root/'Data').mkdir(parents=True);path=root/'Data/career.sqlite3'
        db=sqlite3.connect(path);db.execute('CREATE TABLE unrelated(value TEXT)');db.execute("INSERT INTO unrelated VALUES ('Fictional retained bytes')");db.commit();db.close();before=path.read_bytes()
        with self.assertRaises(CareerError) as error:Repository(root).connect()
        self.assertEqual('UNSUPPORTED_FORMAT',error.exception.code);self.assertEqual(before,path.read_bytes())

    def test_supervised_cli_records_budget_and_refuses_existing_destination(self):
        import subprocess
        root,raw=self.source();target=Path(self.temp.name)/'supervised'
        script=Path(__file__).resolve().parents[1]/'maintenance/import_legacy.py'
        result=subprocess.run([sys.executable,'-B',str(script),'--source',str(root),'--destination',str(target),'--state-sha256',digest(raw)],capture_output=True,text=True,timeout=20)
        self.assertEqual(0,result.returncode,result.stdout+result.stderr)
        observation=json.loads((target/'Data/import-supervision.json').read_text())
        self.assertEqual('completed',observation['status']);self.assertGreater(observation['peak_observed_rss_bytes'],0);self.assertLess(observation['peak_observed_rss_bytes'],observation['memory_budget_bytes'])
        before=(target/'Data/import-supervision.json').read_bytes()
        repeated=subprocess.run([sys.executable,'-B',str(script),'--source',str(root),'--destination',str(target),'--state-sha256',digest(raw)],capture_output=True,text=True,timeout=20)
        self.assertEqual(2,repeated.returncode);self.assertEqual(before,(target/'Data/import-supervision.json').read_bytes())

    def test_resource_abort_waits_owned_worker_and_blocks_previously_ready_report(self):
        from import_supervision import supervise
        script=Path(self.temp.name)/'fictional_worker.py';target=Path(self.temp.name)/'resource_failure'
        script.write_text("import sys,json,time\nfrom pathlib import Path\np=Path(sys.argv[1]);(p/'Data').mkdir(parents=True)\n(p/'Data/import-report.json').write_text(json.dumps(dict(format='career-agent.import/1',status='complete',strict_pass=True,activation_allowed=True)))\npayload=bytearray(128*1024*1024)\ntime.sleep(10)\n")
        with self.assertRaises(CareerError) as error:supervise(script,[str(target)],target,ImportLimits(memory_bytes=32*1024*1024))
        self.assertEqual('IMPORT_RESOURCE_LIMIT',error.exception.code)
        report=json.loads((target/'Data/import-report.json').read_text());self.assertEqual('failed',report['status']);self.assertFalse(report['activation_allowed']);self.assertFalse(report['strict_pass'])
        self.assertTrue((target/'Data/import-report-before-resource-failure.json').is_file())

if __name__=='__main__':unittest.main()
