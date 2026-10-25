"""Fictional retained observation projection; no private workspace or sent mutation."""
from contextlib import contextmanager, redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'maintenance'))
import project_history as history


def original(**changes):
    result=dict(id='original-example', source_locator='user-supplied list', source_kind='user_list',
                employer='Northstar Example',role='Analyst',role_url='https://northstar.example/roles/42',
                date_text='around March 2020',date_precision='approximate',occurred_at=None,channel='email',
                status='uncertain',event_kind='initial_application',opportunity_id='old-role-reference',
                evidence_level='user_reported',provider_message_id=None,provider_thread_id=None)
    result.update(changes);return result


class FakeRepository:
    workspace_id='fictional-workspace'
    revision=22
    def __init__(self,records):
        self.records=records;self.applied=[]
    @contextmanager
    def open(self):yield self
    def retained_history_sources(self):return self.records
    def cache_historical_observations(self,bundle):
        self.applied.append(bundle);return dict(cached=len(bundle['items']),business_revision=self.revision)


class HistoryProjectionTests(unittest.TestCase):
    def test_normalization_preserves_status_precision_and_source_without_new_activity(self):
        raw=original(evidence='Fictional user report; transmission unverified.')
        item=history.normalize_history_record(raw,17)
        self.assertEqual('uncertain',item['original_status'])
        self.assertEqual('approximate',item['date']['precision'])
        self.assertEqual('around March 2020',item['date']['text'])
        self.assertIsNone(item['date']['occurred_at'])
        self.assertEqual('old-role-reference',item['historical_opportunity_reference'])
        self.assertIsNone(item['case_id']);self.assertEqual('unlinked',item['scope'])
        self.assertIs(item['canonical_activity_created'],False)
        self.assertEqual(raw['evidence'],item['evidence'])
        self.assertEqual(history.digest(raw),item['source']['sha256'])
        self.assertEqual(17,item['source']['record_history_id'])
        self.assertEqual(raw,original(evidence='Fictional user report; transmission unverified.'))

    def test_physical_occurrences_have_distinct_stable_ids_and_exact_fingerprint(self):
        raw=original();repo=FakeRepository([dict(id=7,body=history.canonical(raw)),dict(id=4,body=history.canonical(raw))])
        bundle=history.prepare_projection(repo)
        self.assertEqual(2,len(bundle['items']));self.assertNotEqual(bundle['items'][0]['id'],bundle['items'][1]['id'])
        self.assertEqual(history.digest([dict(record_history_id=4,sha256=history.digest(raw)),dict(record_history_id=7,sha256=history.digest(raw))]),bundle['source_fingerprint'])
        self.assertEqual(22,bundle['revision']);self.assertFalse(repo.applied)
        self.assertEqual(bundle,history.prepare_projection(repo))

    def test_missing_history_and_unknown_precisions_never_become_exact_dates(self):
        item=history.normalize_history_record({},1)
        self.assertEqual('unknown',item['original_status']);self.assertEqual('unknown',item['date']['precision'])
        self.assertIsNone(item['date']['occurred_at']);self.assertEqual('',item['employer'])
        with self.assertRaises(ValueError):history.normalize_history_record(original(date_precision='guessed'),2)
        with self.assertRaises(ValueError):history.normalize_history_record(original(employer='x'*(history.MAX_TEXT+1)),2)
        with self.assertRaises(ValueError):history.normalize_history_record([],2)
        with self.assertRaises(ValueError):history.normalize_history_record(original(),True)

    def test_resource_bounds_abort_without_apply_or_truncation(self):
        repo=FakeRepository([dict(id=1,body=history.canonical(original()))])
        with patch.object(history,'MAX_RECORDS',0):
            with self.assertRaises(ValueError):history.prepare_projection(repo)
        with patch.object(history,'MAX_BUNDLE_BYTES',1):
            with self.assertRaises(ValueError):history.prepare_projection(repo)
        self.assertFalse(repo.applied)

    def test_apply_requires_exact_reviewed_fingerprint_and_delegates_to_owner(self):
        repo=FakeRepository([dict(id=1,body=history.canonical(original()))]);bundle=history.prepare_projection(repo)
        with self.assertRaises(ValueError):history.apply_projection(repo,bundle,'0'*64)
        with self.assertRaises(ValueError):history.apply_projection(repo,bundle,None)
        self.assertFalse(repo.applied)
        result=history.apply_projection(repo,bundle,bundle['source_fingerprint'])
        self.assertEqual(1,result['cached']);self.assertEqual([bundle],repo.applied)

    def test_cli_prepare_is_private_non_overwriting_and_does_not_apply(self):
        repo=FakeRepository([dict(id=1,body=history.canonical(original()))])
        with tempfile.TemporaryDirectory(prefix='career-history-fictional-') as folder:
            target=Path(folder)/'projection.json';output=io.StringIO();error=io.StringIO()
            with patch.object(history,'installed_repository',return_value=repo),redirect_stdout(output),redirect_stderr(error):
                self.assertEqual(0,history.main(['--workspace',folder,'--output',str(target)]))
                self.assertEqual(2,history.main(['--workspace',folder,'--output',str(target)]))
            self.assertEqual(0o600,target.stat().st_mode & 0o777)
            self.assertFalse(repo.applied);self.assertNotIn('Northstar',output.getvalue())
            bundle=json.loads(target.read_text());self.assertEqual('Northstar Example',bundle['items'][0]['employer'])
            with patch.object(history,'installed_repository',return_value=repo),redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
                self.assertEqual(2,history.main(['--workspace',folder,'--input',str(target),'--apply','--expected-source-fingerprint','0'*64]))
            self.assertFalse(repo.applied)

    def test_cli_refuses_uninstalled_workspace_without_source_runtime_fallback(self):
        with tempfile.TemporaryDirectory(prefix='career-history-uninstalled-') as folder:
            with redirect_stderr(io.StringIO()):
                self.assertEqual(2,history.main(['--workspace',folder,'--output',str(Path(folder)/'projection.json')]))
            self.assertFalse((Path(folder)/'projection.json').exists())


class HistoryCacheOwnerTests(unittest.TestCase):
    """The real shared SQL owner may change derived rows, never career history."""
    def setUp(self):
        from test_runtime_1 import Fixture
        self.temp=tempfile.TemporaryDirectory(prefix='career-history-owner-fictional-');self.addCleanup(self.temp.cleanup)
        self.fx=Fixture(self.temp.name).seed()
        db=self.fx.tasks.repository.connect()
        try:
            for index,row in enumerate([original(),original(status='bounced',role='',opportunity_id=None)]):
                db.execute('INSERT INTO record_history(kind,record_id,version,body,revision) VALUES (?,?,?,?,?)',('legacy:history_imports','legacy-'+str(index),1,history.canonical(row),0))
        finally:db.close()

    def business_hash(self):
        db=self.fx.tasks.repository.connect()
        try:
            tables=[row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('view_exports','case_projection_cache') ORDER BY name")]
            data=[]
            for table in tables:data.append([table,[list(row) for row in db.execute('SELECT * FROM '+table+' ORDER BY rowid')]])
            return history.digest(data)
        finally:db.close()

    def test_cache_roundtrip_is_paged_derived_only_and_survives_unrelated_revision(self):
        repository=self.fx.tasks.repository;before=self.business_hash();revision=self.fx.tasks.context()['revision']
        with repository.open() as snapshot:
            absent=snapshot.historical_observations();self.assertEqual(2,absent['pending_projection']);self.assertFalse(absent['projection_current'])
        bundle=history.prepare_projection(repository)
        history.apply_projection(repository,bundle,bundle['source_fingerprint'])
        self.assertEqual(before,self.business_hash());self.assertEqual(revision,self.fx.tasks.context()['revision'])
        with repository.open() as snapshot:
            first=snapshot.historical_observations(limit=1)
            second=snapshot.historical_observations(limit=1,cursor=first['next_cursor'])
            self.assertTrue(first['projection_current']);self.assertEqual(0,first['pending_projection'])
            self.assertEqual(2,first['total']);self.assertIsNone(second['next_cursor'])
            self.assertNotEqual(first['items'][0]['id'],second['items'][0]['id'])
            self.assertTrue(all(row['case_id'] is None and row['canonical_activity_created'] is False for row in first['items']+second['items']))
        self.fx.command('case.note',case_id='case_one',text='Unrelated fictional note')
        with repository.open() as snapshot:self.assertTrue(snapshot.historical_observations()['projection_current'])
        with repository.open() as snapshot:self.assertEqual(0,snapshot.one('SELECT count(*) AS n FROM activities')['n'])

    def test_cache_refuses_stale_revision_and_changed_source_without_replacing_previous_view(self):
        from career.contracts import CareerError
        repository=self.fx.tasks.repository;bundle=history.prepare_projection(repository)
        history.apply_projection(repository,bundle,bundle['source_fingerprint'])
        self.fx.command('case.note',case_id='case_one',text='Fictional newer state')
        with self.assertRaises(CareerError) as error:history.apply_projection(repository,bundle,bundle['source_fingerprint'])
        self.assertEqual('REVISION_CONFLICT',error.exception.code)
        current=history.prepare_projection(repository)
        db=repository.connect()
        try:db.execute("UPDATE record_history SET body=? WHERE id=(SELECT min(id) FROM record_history WHERE kind='legacy:history_imports')",(history.canonical(original(employer='Changed synthetic original')),))
        finally:db.close()
        with self.assertRaises(CareerError) as error:history.apply_projection(repository,current,current['source_fingerprint'])
        self.assertEqual('SOURCE_CHANGED',error.exception.code)
        with repository.open() as snapshot:self.assertEqual(2,snapshot.historical_observations()['total'])
