"""Offline fictional import inventory/reference/quarantine preservation regressions."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'maintenance'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from import_legacy import migrate,inventory
from career.contracts import CareerError,canonical,digest
from career.repository import Repository


class ImportTests(unittest.TestCase):
    def setUp(self):
        import os
        from unittest.mock import patch
        development=patch.dict(os.environ,CAREER_AGENT_DEVELOPMENT='1');development.start();self.addCleanup(development.stop)
        self.temp=tempfile.TemporaryDirectory(prefix='career-import-fictional-');self.addCleanup(self.temp.cleanup)
        self.source=Path(self.temp.name)/'restored';(self.source/'Data').mkdir(parents=True);(self.source/'Materials').mkdir();(self.source/'Applications').mkdir()
        self.material=self.source/'Materials/resume.md';self.material.write_text('Fictional original contribution, retained exactly.')
        self.state=dict(schema_version=1,revision=804,sources=[],facts=[],companies=[],opportunities=[],materials=[dict(id='material_demo',path='Materials/resume.md',sha256=digest(self.material.read_bytes()),version=1)])

    def save(self):
        raw=canonical(self.state).encode();(self.source/'Data/state.json').write_bytes(raw);return digest(raw)

    def test_twenty_six_historical_references_normalize_individually_without_loss(self):
        for i in range(26):
            value=dict(material_id='material_demo',path='Materials/resume.md',sha256=digest(self.material.read_bytes()),version=1) if i%2 else dict(material_id='material_demo',link_mode='reference',relative_target='../Materials/resume.md',sha256=digest(self.material.read_bytes()),version=1)
            (self.source/'Applications'/('reference-'+str(i)+'.json')).write_text(canonical(value))
        fingerprint=self.save();before=digest(inventory(self.source));destination=Path(self.temp.name)/'candidate'
        result=migrate(self.source,destination,fingerprint,allow_partial=True)
        report=json.loads((destination/'Data/import-report.json').read_text())
        self.assertEqual(26,result['references']);self.assertEqual(26,sum(r['status']=='resolved' for r in report['references']))
        self.assertEqual(before,digest(inventory(self.source)));self.assertTrue(Repository(destination).doctor()['healthy'])
        self.assertEqual(digest(self.material.read_bytes()),report['artifact_by_path']['Materials/resume.md']['sha256'])
        self.assertTrue(report['activation_allowed'])  # Every known material pin and reference has an explicit normalized mapping.

    def test_unknown_reference_and_semantics_block_strict_acceptance_preserving_originals(self):
        (self.source/'Applications/unknown.json').write_text(canonical(dict(material_id='material_demo',mystery_shape=True)))
        self.state['attempts']=[dict(id='attempt_unknown',outcome='uncertain',evidence='Fictional lost response.')]
        destination=Path(self.temp.name)/'strict';result=migrate(self.source,destination,self.save())
        self.assertFalse(result['accepted']);self.assertEqual('IMPORT_QUARANTINED',result['code'])
        report=json.loads((destination/'Data/import-report.json').read_text())
        self.assertTrue(any(q.get('reason')=='UNKNOWN_REFERENCE' for q in report['quarantine']))
        with Repository(destination).open() as snapshot:
            retained=snapshot.one('SELECT body FROM record_history WHERE kind=? AND record_id=?',('legacy:attempts','attempt_unknown'))
        self.assertEqual('uncertain',json.loads(retained['body'])['outcome'])

    def test_historical_selection_and_sent_pins_are_canonical_without_review_promotion(self):
        self.state['companies']=[dict(id='company_a',name='Northstar Demo')]
        self.state['opportunities']=[dict(id='role_a',company_id='company_a',title='Fictional role',kind='vacancy',identity='REQ-42',role_url='https://northstar.example/jobs/42',source_ids=[])]
        sha=digest(self.material.read_bytes())
        self.state['application_attempts']=[dict(id='application_a',opportunity_id='role_a',at='2026-10-01T00:00:00Z',materials=[dict(slot='resume',material_id='material_demo',version=1,sha256=sha)])]
        self.state['search_cases']=[dict(id='selected_case',opportunity_id='role_a',attempt_id='application_a')]
        self.state['attempts']=[dict(id='sent_a',opportunity_id='role_a',outcome='sent',at='2026-10-01T00:00:00Z',evidence='Fictional explicit actual send report.',application_attempt_id='application_a')]
        destination=Path(self.temp.name)/'history';result=migrate(self.source,destination,self.save())
        self.assertTrue(result['accepted'])
        with Repository(destination).open() as snapshot:
            case=snapshot.one('SELECT id FROM cases');detail=snapshot.case_detail(case['id'])
            self.assertEqual(sha,detail['selection']['slots'][0]['sha256'])
            self.assertFalse(detail['selection']['assessment']['prepared'])
            self.assertEqual('sent',detail['history'][0]['kind'])
            self.assertEqual(detail['selection']['version_id'],detail['history'][0]['version_id'])

    def test_bootstrap_cannot_activate_quarantined_import_even_when_partial_retained(self):
        from career.installation import install_archive
        self.state['unknown_group']=[dict(id='unresolved_semantics',meaning='Fictional unresolved original')]
        destination=Path(self.temp.name)/'quarantined'
        result=migrate(self.source,destination,self.save(),allow_partial=True)
        self.assertTrue(result['accepted']) # Retaining partial work never implies activation.
        archive=Path(self.temp.name)/'irrelevant.zip';archive.write_bytes(b'Fictional placeholder not executed')
        with self.assertRaises(CareerError) as error:install_archive(archive,destination,digest(archive.read_bytes()))
        self.assertEqual('IMPORT_QUARANTINED',error.exception.code)
        self.assertFalse((destination/'.career-agent/active.json').exists())

    def test_claim_original_metrics_and_structured_interpretation_are_mapped_without_approval(self):
        self.state['sources']=[dict(id='source_a',locator='https://northstar.example/source',observations=[dict(evidence='Fictional personally improved processing by 25%.',at='2026-10-24T00:00:00Z')])]
        self.state['facts']=[dict(id='fact_a',statement='Personally improved processing by 25%.',status='confirmed',confirmation=dict(evidence='Explicit fictional source confirmation'),disclosure='allowed',source_ids=['source_a'])]
        self.state['achievement_evidence']=[dict(id='achievement_a',fact_id='fact_a',source_id='source_a',source_locator='https://northstar.example/source',original_text='Improved processing by 25%.',numeric_anchors=['25%'],metrics=[dict(raw='25%')])]
        self.state['achievement_interpretations']=[dict(id='interpretation_a',achievement_id='achievement_a',version=1,at='2026-10-24T00:00:00Z',fields=dict(contribution=dict(status='supported',text='Personally improved processing.',fact_ids=['fact_a']),decisions=dict(status='hypothesis',text='Unconfirmed leadership interpretation.',fact_ids=[])))]
        self.state['change_history']=[dict(operation='Fictional audit without an ID'),dict(operation='Second retained audit without an ID')]
        self.state['profile']=dict(name='Alex Example')
        destination=Path(self.temp.name)/'meaning';migrate(self.source,destination,self.save(),allow_partial=True)
        report=json.loads((destination/'Data/import-report.json').read_text());self.assertEqual(2,len(report['normalized_records']));self.assertEqual(2,len(report['archived_records']));self.assertEqual(2,len({x['record_history_id'] for x in report['archived_records']}))
        self.assertEqual(['profile'],[x['group'] for x in report['quarantine']]) # Remaining profile scope is not waved through.
        from import_repository import ImportRepository
        with ImportRepository(destination).open() as snapshot:
            claim=snapshot.public_claim(snapshot.get('claim',report['mappings']['claim:fact_a']))
            self.assertEqual('Improved processing by 25%.',claim['assertion']);self.assertEqual([dict(raw='25%')],claim['detail']['metrics'])
            self.assertEqual('hypothesis',claim['detail']['interpretation']['fields']['decisions']['status']);self.assertNotIn('Unconfirmed leadership',claim['meaning'])
            self.assertEqual([claim['id']],claim['detail']['interpretation']['fields']['contribution']['fact_ids']);self.assertEqual('Alex Example',snapshot.context()['profile']['display_name'])
        self.assertFalse(report['activation_allowed'])

    def test_wrong_fingerprint_and_unsafe_destination_do_not_modify_source(self):
        fingerprint=self.save();before=digest(inventory(self.source))
        with self.assertRaises(CareerError):migrate(self.source,Path(self.temp.name)/'bad','0'*64)
        with self.assertRaises(CareerError):migrate(self.source,self.source/'nested',fingerprint)
        self.assertEqual(before,digest(inventory(self.source)))


if __name__=='__main__':unittest.main()
