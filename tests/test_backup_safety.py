"""Small fictional recovery regressions; never operate on a personal workspace."""
import errno
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
os.environ['CAREER_AGENT_DEVELOPMENT']='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from career.contracts import CareerError
from career.repository import Repository
from career.policy import number_tokens,mechanical_review
from test_runtime_1 import Fixture

class BackupSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='career-backup-fictional-');self.addCleanup(self.temp.cleanup)
        self.fx=Fixture(self.temp.name);self.repo=self.fx.tasks.repository

    def test_low_disk_rejects_before_plan_objects_or_business_write(self):
        with patch('career.repository.shutil.disk_usage',return_value=shutil._ntuple_diskusage(100,99,1)):
            with self.assertRaises(CareerError) as caught:self.fx.command('source.capture',id='source_test',locator='https://demo.example',excerpt='Fictional source',observed_at='2026-10-25T00:00:00Z',readable=True)
        self.assertEqual('DISK_SPACE_LOW',caught.exception.code);self.assertEqual(507,caught.exception.status)
        self.assertEqual(1,caught.exception.issues[0]['free_bytes']);self.assertEqual('DISK_SPACE_LOW',caught.exception.issues[0]['code'])
        self.assertEqual(0,self.fx.tasks.context()['revision'])
        with self.repo.open() as snap:
            self.assertEqual(0,snap.one('SELECT count(*) n FROM plans')['n']);self.assertEqual(0,snap.one('SELECT count(*) n FROM sources')['n'])
        self.assertFalse(list((self.fx.root/'Objects').iterdir()))

    def test_low_disk_after_plan_rejects_apply_and_receipt(self):
        value=dict(request_id='one',expected_revision=0,intent='preferences.set',input=dict(theme='dark'))
        plan=self.fx.tasks.plan(value)
        with patch.object(self.repo,'check_disk_space',side_effect=CareerError('DISK_SPACE_LOW','Fictional exhausted disk',507)):
            with self.assertRaises(CareerError):self.fx.tasks.apply(plan['plan_id'])
        self.assertEqual(0,self.fx.tasks.context()['revision'])
        with self.assertRaises(CareerError):self.repo.status('one')
        self.assertEqual(1,self.fx.tasks.apply(plan['plan_id'])['revision'])

    def test_interrupted_backup_never_publishes_target_and_retry_restores(self):
        value=dict(request_id='retry',expected_revision=0,intent='preferences.set',input=dict(theme='dark'))
        plan=self.fx.tasks.plan(value)
        with patch('career.repository.os.link',side_effect=OSError(errno.ENOSPC,'Fictional storage exhausted')):
            with self.assertRaises(CareerError) as caught:self.fx.tasks.apply(plan['plan_id'])
        self.assertEqual('DISK_SPACE_LOW',caught.exception.code)
        self.assertEqual([],list((self.fx.root/'Backups/Automatic').iterdir()))
        self.assertEqual(0,self.fx.tasks.context()['revision'])
        result=self.fx.tasks.apply(plan['plan_id']);self.assertEqual(1,result['revision'])
        backup=next((self.fx.root/'Backups/Automatic').glob('*.sqlite3'))
        db=sqlite3.connect(backup.as_uri()+'?mode=ro',uri=True);restored=sqlite3.connect(':memory:')
        try:
            db.backup(restored);self.assertEqual('ok',restored.execute('PRAGMA integrity_check').fetchone()[0]);self.assertEqual(0,restored.execute('SELECT revision FROM workspace').fetchone()[0]);self.assertEqual('system',restored.execute('SELECT theme FROM app_preferences').fetchone()[0])
        finally:db.close();restored.close()
        self.assertEqual(result,self.fx.tasks.command(value))

    def test_existing_partial_or_changed_checkpoint_is_not_trusted(self):
        directory=self.fx.root/'Backups/Automatic';directory.mkdir()
        path=directory/'r0-partial.sqlite3';path.write_bytes(b'not a database')
        value=dict(request_id='partial',expected_revision=0,intent='preferences.set',input=dict(theme='dark'))
        receipt=self.fx.tasks.command(value)
        self.assertEqual(1,receipt['revision'])
        preserved=next((directory/'Quarantine').glob('r0-partial.sqlite3.*'))
        self.assertEqual(b'not a database',preserved.read_bytes())
        self.assertEqual(0,sqlite3.connect(path).execute('SELECT revision FROM workspace').fetchone()[0])

    def test_checkpoint_metadata_symlink_cannot_escape_workspace(self):
        directory=self.fx.root/'Backups/Automatic';directory.mkdir()
        outside=self.fx.root/'private-unrelated.json';outside.write_text('{}')
        (directory/'r0-link.json').symlink_to(outside)
        value=dict(request_id='link',expected_revision=0,intent='preferences.set',input=dict(theme='dark'))
        with self.assertRaises(CareerError) as caught:self.fx.tasks.command(value)
        self.assertEqual('UNSAFE_PATH',caught.exception.code);self.assertEqual('{}',outside.read_text())
        self.assertEqual(0,self.fx.tasks.context()['revision'])

    def test_valid_checkpoint_retry_checks_content_and_metadata(self):
        value=dict(request_id='verified',expected_revision=0,intent='preferences.set',input=dict(theme='dark'))
        plan=self.fx.tasks.plan(value)
        with self.repo.open() as snap:workspace_id=snap.workspace_id
        self.repo.automatic_backup(0,'verified',workspace_id)
        path=self.fx.root/'Backups/Automatic/r0-verified.sqlite3';raw=path.read_bytes();path.write_bytes(b'X'+raw[1:])
        self.assertEqual(1,self.fx.tasks.apply(plan['plan_id'])['revision'])
        preserved=next((path.parent/'Quarantine').glob('r0-verified.sqlite3.*'))
        self.assertEqual(b'X'+raw[1:],preserved.read_bytes())
        restored=sqlite3.connect(path)
        try:self.assertEqual('ok',restored.execute('PRAGMA integrity_check').fetchone()[0])
        finally:restored.close()

    def test_retention_bounds_owned_files_and_preserves_exports_manual_history(self):
        manual=self.fx.root/'Backups/r0-preserved.sqlite3';manual.write_bytes(b'Historical manual recovery point')
        exported=self.fx.root/'Backups/export-fictional';exported.mkdir();(exported/'keep').write_bytes(b'keep')
        for i in range(35):
            day=1+min(i//4,8)
            with patch('career.repository.now',return_value='2026-10-'+str(day).zfill(2)+'T12:00:'+str(i%60).zfill(2)+'Z'):
                self.fx.command('preferences.set',theme='light' if i%2 else 'dark')
        files=list((self.fx.root/'Backups/Automatic').glob('*.sqlite3'));self.assertLessEqual(len(files),17)
        self.assertEqual(b'Historical manual recovery point',manual.read_bytes());self.assertEqual(b'keep',(exported/'keep').read_bytes())
        with self.repo.open() as snap:
            self.assertEqual(35,snap.one('SELECT count(*) n FROM commands')['n']);self.assertEqual(35,snap.one('SELECT count(*) n FROM change_log')['n']);self.assertEqual(35,snap.revision)
        self.assertTrue(all(p.with_suffix('.json').exists() for p in files))

    def test_reads_and_idempotent_receipt_do_not_create_checkpoints_on_low_disk(self):
        value=dict(request_id='saved',expected_revision=0,intent='preferences.set',input=dict(theme='dark'))
        receipt=self.fx.tasks.command(value);before={p.name for p in (self.fx.root/'Backups/Automatic').iterdir()}
        with patch.object(self.repo,'check_disk_space',side_effect=AssertionError('Read must not preflight a write')):
            self.fx.tasks.context();self.repo.doctor();self.repo.status('saved');self.fx.tasks.query('changes',after=0)
            self.assertEqual(receipt,self.fx.tasks.command(value))
        self.assertEqual(before,{p.name for p in (self.fx.root/'Backups/Automatic').iterdir()})

    def test_rotation_keeps_canonical_history_and_exact_materials(self):
        self.fx.seed()
        with self.repo.open() as snap:
            materials=[tuple(x) for x in snap._db.execute('SELECT * FROM slots ORDER BY version_id,name')]
            activities=[tuple(x) for x in snap._db.execute('SELECT * FROM activities ORDER BY id')]
            old_history=[tuple(x) for x in snap._db.execute('SELECT * FROM record_history ORDER BY id')]
        for i in range(24):self.fx.command('claim.save',id='claim_one',assertion='Improved processing by 25%.',meaning='Personally improved processing by 25%.',source_ids=['source_one'],confirmation='confirmed',disclosure='allowed')
        with self.repo.open() as snap:
            self.assertEqual(materials,[tuple(x) for x in snap._db.execute('SELECT * FROM slots ORDER BY version_id,name')])
            self.assertEqual(activities,[tuple(x) for x in snap._db.execute('SELECT * FROM activities ORDER BY id')])
            history=[tuple(x) for x in snap._db.execute('SELECT * FROM record_history ORDER BY id')]
            self.assertEqual(old_history,history[:len(old_history)])
            self.assertGreater(len(history),len(old_history))
        self.assertLessEqual(len(list((self.fx.root/'Backups/Automatic').glob('*.sqlite3'))),17)

    def test_crash_after_database_publish_before_metadata_recovers_same_request(self):
        value=dict(request_id='crash_window',expected_revision=0,intent='preferences.set',input=dict(theme='dark'))
        plan=self.fx.tasks.plan(value)
        actual_link=os.link
        def interrupt(source,target,*args,**kwargs):
            if Path(target).suffix=='.json':raise SystemExit('Fictional process crash after database promotion')
            return actual_link(source,target,*args,**kwargs)
        with patch('career.repository.os.link',side_effect=interrupt):
            with self.assertRaises(SystemExit):self.fx.tasks.apply(plan['plan_id'])
        path=self.fx.root/'Backups/Automatic/r0-crash_window.sqlite3'
        self.assertTrue(path.is_file());self.assertFalse(path.with_suffix('.json').exists())
        self.assertEqual(0,self.fx.tasks.context()['revision'])
        orphan_bytes=path.read_bytes()
        with patch.object(self.repo,'backup',wraps=self.repo.backup) as rebuild:
            receipt=self.fx.tasks.apply(plan['plan_id'])
        self.assertEqual(1,rebuild.call_count)
        preserved=next((path.parent/'Quarantine').glob('r0-crash_window.sqlite3.*'))
        self.assertEqual(orphan_bytes,preserved.read_bytes())
        self.assertEqual(1,receipt['revision']);self.assertTrue(path.with_suffix('.json').is_file())
        self.assertEqual(receipt,self.fx.tasks.command(value))

    def test_valid_sqlite_orphan_content_tamper_is_preserved_and_rebuilt(self):
        value=dict(request_id='crash_corrupt',expected_revision=0,intent='preferences.set',input=dict(theme='dark'))
        plan=self.fx.tasks.plan(value);actual_link=os.link
        def interrupt(source,target,*args,**kwargs):
            if Path(target).suffix=='.json':raise SystemExit('Fictional crash between database and metadata')
            return actual_link(source,target,*args,**kwargs)
        with patch('career.repository.os.link',side_effect=interrupt):
            with self.assertRaises(SystemExit):self.fx.tasks.apply(plan['plan_id'])
        path=self.fx.root/'Backups/Automatic/r0-crash_corrupt.sqlite3';raw=path.read_bytes()
        self.assertEqual(1,raw.count(b'Alex Example'))
        altered=raw.replace(b'Alex Example',b'Olex Example');path.write_bytes(altered)
        orphan=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)
        try:self.assertEqual('ok',orphan.execute('PRAGMA integrity_check').fetchone()[0])
        finally:orphan.close()
        self.assertFalse(path.with_suffix('.json').exists())
        receipt=self.fx.tasks.apply(plan['plan_id']);self.assertEqual(1,receipt['revision'])
        preserved=next((path.parent/'Quarantine').glob('r0-crash_corrupt.sqlite3.*'))
        self.assertEqual(altered,preserved.read_bytes())
        rebuilt=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)
        try:
            self.assertEqual('Alex Example',rebuilt.execute('SELECT display_name FROM workspace').fetchone()[0])
            self.assertEqual(0,rebuilt.execute('SELECT revision FROM workspace').fetchone()[0])
        finally:rebuilt.close()
        with self.repo.open() as snapshot:self.assertEqual('Alex Example',snapshot.one('SELECT display_name FROM workspace')['display_name'])
        metadata=json.loads(path.with_suffix('.json').read_text());self.assertEqual(self.repo.file_digest(path),metadata['sha256'])
        self.assertEqual(receipt,self.fx.tasks.command(value))

    def test_clock_rollback_cannot_prune_current_pre_command_checkpoint(self):
        for i in range(22):
            with patch('career.repository.now',return_value='2026-10-'+str(1+i%15).zfill(2)+'T12:00:00Z'):
                self.fx.command('preferences.set',theme='dark' if i%2 else 'light')
        revision=self.fx.tasks.context()['revision']
        with patch('career.repository.now',return_value='1970-01-01T00:00:00Z'):
            self.fx.command('preferences.set',theme='system')
        checkpoint=self.fx.root/'Backups/Automatic'/('r'+str(revision)+'-fictional_'+str(self.fx.serial)+'.sqlite3')
        self.assertTrue(checkpoint.is_file());self.assertTrue(checkpoint.with_suffix('.json').is_file())
        restored=sqlite3.connect(checkpoint)
        try:self.assertEqual(revision,restored.execute('SELECT revision FROM workspace').fetchone()[0])
        finally:restored.close()
        self.assertLessEqual(len(list(checkpoint.parent.glob('*.sqlite3'))),17)

    def test_brand_digits_are_not_metrics_but_real_signed_decimals_still_are(self):
        self.assertEqual(['8','2','25','3,2','1,8','-3.2','+1.8'],number_tokens('n8n B2B 25% с3,2% до1,8% from-3.2 to+1.8'))
        self.assertEqual(['825','2','2'],number_tokens('825 B2B2'))
        claim=dict(id='claim_test',assertion='Improved by 25%.',meaning='Personal measured improvement.',confirmation='confirmed',disclosure='allowed',contradicted=False)
        review=dict(findings='Checked actual words.',limitations='Mechanical check only.',tone_findings='Concrete.',claim_spans=[dict(claim_id='claim_test',text='Improved by 25%.')],coverage=[dict(claim_id='claim_test',disposition='included')])
        docs=[dict(slot='resume',text='Improved by 25%. Used n8n for B2B workflows.')]
        source=dict(id='source_numeric',version=1,locator='https://example.org',excerpt='Public tool n8n and contract term B2B.',readable=True)
        review['entity_refs']=[dict(text=term,source_id=source['id']) for term in ('n8n','B2B')]
        self.assertFalse(mechanical_review(docs,[claim],review,sources=[source]))
        docs[0]['text']+=' Unsupported 999% improvement.'
        self.assertIn('UNMATCHED_NUMBER',{x['code'] for x in mechanical_review(docs,[claim],review,sources=[source])})

if __name__=='__main__':unittest.main()
