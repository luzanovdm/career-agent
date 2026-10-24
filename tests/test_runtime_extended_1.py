"""Extended 1.0 regressions for current answers, binaries, intents and cached projections."""
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from career.contracts import CareerError,digest
from career.localization import validate_catalog
from career.binary import extract_docx,extract_binary,check_conversion
from career.repository import Repository
from test_runtime_1 import Fixture


def docx(body,header=None):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as archive:
        for name,text in [('document',body)]+([('header1',header)] if header else []):
            archive.writestr('word/'+name+'.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>'+text+'</w:t></w:r></w:p></w:document>')
    return stream.getvalue()


class ExtendedRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='career-extended-fictional-');self.addCleanup(self.temp.cleanup);self.fx=Fixture(self.temp.name).seed()

    def answer(self,**extra):
        data=dict(meaning='contact.phone.preference',scope=dict(purpose='application'),units={},disposition='answered',value=dict(disposition='omit',value=None),evidence='Explicit fictional user phone choice.')
        data.update(extra);return self.fx.command('answer.save',**data)

    def test_answer_persists_exact_scope_and_units_without_competing_choice(self):
        receipt=self.answer();answer_id=receipt['saved_ids'][0]
        self.assertEqual(answer_id,self.answer(value=dict(disposition='unknown',value=None))['saved_ids'][0])
        with self.assertRaises(CareerError):self.answer(id='different')
        with self.fx.tasks.repository.open() as snapshot:
            self.assertEqual(2,snapshot.get('answer',answer_id)['version'])
        self.assertEqual(1,self.answer(scope=dict(purpose='interview'))['revision']-self.fx.tasks.context()['revision']+1)

    def test_current_phone_omission_blocks_new_and_previous_selected_bytes(self):
        self.fx.save('Improved processing by 25%. Phone: +1 202 555 0142',review=False)
        self.answer()
        selection=self.fx.tasks.query('selection',record_id='packet_one')
        self.assertIn('CONTACT_DISCLOSURE_BLOCKED',{i['code'] for i in selection['assessment']['issues']})
        page=self.fx.tasks.query('cases')
        self.assertNotEqual('ready',page['items'][0]['column'])

    def test_docx_header_phone_and_actual_conversion_hash_receipt(self):
        selection=self.fx.tasks.query('selection',record_id='packet_one');source=next(slot for slot in selection['slots'] if slot['name']=='resume')
        binary=docx(source['text']);staged=self.fx.root/'.career-agent/staging/input_good';staged.write_bytes(binary)
        self.fx.command('artifact.attach',packet_id='packet_one',slot='resume',input_id='input_good',source_artifact_id=source['artifact_id'],extension='docx')
        newer=self.fx.tasks.query('selection',record_id='packet_one');slot=next(s for s in newer['slots'] if s['name']=='resume')
        self.assertNotEqual(selection['version_id'],newer['version_id']);self.assertEqual(digest(binary),slot['sha256']);self.assertTrue(newer['assessment']['prepared'])
        with self.fx.tasks.repository.open() as snapshot:
            row=snapshot.one('SELECT * FROM extraction_receipts WHERE artifact_id=?',(slot['artifact_id'],))
        self.assertEqual(source['artifact_id'],row['source_artifact_id'])
        text,_=extract_docx(docx(source['text'],'Phone: +1 202 555 0142'))
        self.assertIn('+1 202 555 0142',text)
        with self.assertRaises(CareerError):check_conversion(source['text'],text)

    def test_unsupported_pdf_extraction_never_accepts_declared_text(self):
        path=self.fx.root/'fake.pdf';path.write_bytes(b'%PDF-1.4\nNot a valid PDF')
        with self.assertRaises(CareerError):extract_binary(path,'pdf')

    def test_alternative_packet_cannot_change_primary_projection(self):
        first=self.fx.tasks.query('case',record_id='case_one')['selection']
        self.fx.command('packet.create',id='aaa_alternative',case_id='case_one',purpose='contact')
        self.fx.command('packet.save',packet_id='aaa_alternative',documents=[dict(slot='message',text='An unreviewed alternative.')],used_claim_ids=[])
        detail=self.fx.tasks.query('case',record_id='case_one')
        self.assertEqual(first['packet_id'],detail['selection']['packet_id'])
        self.fx.command('packet.primary',packet_id='aaa_alternative')
        self.assertEqual('aaa_alternative',self.fx.tasks.query('case',record_id='case_one')['selection']['packet_id'])

    def test_track_optional_claims_and_browser_lineage_preserved(self):
        self.fx.command('track.save',id='track_one',name='Changed name',positioning='Same supported track.',selected=True,language='en',policies={})
        with self.fx.tasks.repository.open() as snapshot:self.assertEqual(['claim_one'],json.loads(snapshot.get('track','track_one')['detail'])['claim_ids'])
        before=self.fx.tasks.query('selection',record_id='packet_one')
        self.fx.command('packet.save',packet_id='packet_one',documents=[dict(slot=s['name'],text=s['text']) for s in before['slots']],used_claim_ids=[],source_version_id=before['version_id'])
        after=self.fx.tasks.query('selection',record_id='packet_one');self.assertEqual(['claim_one'],after['used_claim_ids']);self.assertFalse(after['assessment']['prepared'])

    def test_intent_survives_unrelated_revision_but_conflicts_on_selected_change(self):
        bound=self.fx.tasks.query('agent-intent',intent='agent.prepare',case_id='case_one')['descriptor']
        self.fx.command('case.note',case_id='case_one',text='Unrelated private note')
        resumed=self.fx.tasks.query('resolve-intent',descriptor=bound)
        self.assertTrue(resumed['context_refreshed']);self.assertFalse(resumed['executed'])
        self.fx.save(review=False)
        with self.assertRaises(CareerError) as caught:self.fx.tasks.query('resolve-intent',descriptor=bound)
        self.assertEqual('SELECTION_CONFLICT',caught.exception.code)
        with self.assertRaises(CareerError):self.fx.tasks.query('resolve-intent',descriptor=dict(bound,workspace_id='other'))

    def test_research_intent_respects_revocation(self):
        scope=dict(track_ids=['track_one'],purpose='Professional contact discovery')
        self.fx.command('research.control',status='active',scope=scope,evidence='Explicit fictional user start.')
        bound=self.fx.tasks.query('agent-intent',intent='agent.research',case_id='case_one')['descriptor']
        self.assertFalse(self.fx.tasks.query('resolve-intent',descriptor=bound)['executed'])
        self.fx.command('research.control',status='revoked',scope=scope,evidence='Explicit fictional user revoke.')
        with self.assertRaises(CareerError) as caught:self.fx.tasks.query('resolve-intent',descriptor=bound)
        self.assertEqual('RESEARCH_NOT_AUTHORIZED',caught.exception.code)

    def test_board_table_counts_and_rebuild_missing_derived_cache(self):
        board=self.fx.tasks.query('board');table=self.fx.tasks.query('cases')
        self.assertEqual(board['revision'],table['revision']);self.assertEqual(board['counts'],table['counts'])
        self.assertEqual(table['items'],board['columns']['ready']['items'])
        db=self.fx.tasks.repository.connect();db.execute('DELETE FROM case_projection_cache');db.close()
        recovered=self.fx.tasks.query('cases');self.assertEqual(table,recovered)
        self.fx.command('claim.save',id='claim_one',assertion='Improved processing by 25%.',meaning='Meaning changed.',source_ids=['source_one'],confirmation='confirmed',disclosure='allowed')
        self.assertEqual('prepare',self.fx.tasks.query('cases')['items'][0]['column'])

    def test_track_filtered_intent_is_exact_and_unrelated_case_track_rejected(self):
        self.fx.command('track.save',id='track_other',name='Other work',positioning='Other supported track.',selected=True,language='en',policies={})
        bound=self.fx.tasks.query('agent-intent',intent='agent.prepare',track_id='track_one')['descriptor']
        self.assertEqual(['track_one'],bound['scope']['track_ids'])
        self.assertFalse(self.fx.tasks.query('resolve-intent',descriptor=bound)['executed'])
        with self.assertRaises(CareerError) as caught:self.fx.tasks.query('agent-intent',intent='agent.prepare',case_id='case_one',track_id='track_other')
        self.assertEqual('SCOPE_CONFLICT',caught.exception.code)

    def test_failed_endpoint_survives_contact_recapture_and_alternative_selection(self):
        with self.fx.tasks.repository.open() as snapshot:person=snapshot.contact('person_one')
        data={key:person[key] for key in ('id','name','company_id','affiliation','relevance','sources','route')}
        old_route=data['route']
        self.fx.command('contact.suppress',person_id='person_one',kind=old_route['kind'],value=old_route['value'],reason='Known delivery failure.',evidence='Fictional observed failure.')
        self.fx.command('contact.capture',**data)
        self.assertFalse(self.fx.tasks.query('contacts')['items'][0]['qualified'])
        alternate=dict(old_route,value='https://northstar.example/team/alternate')
        self.fx.command('contact.capture',**dict(data,route=alternate))
        self.assertEqual(alternate['value'],self.fx.tasks.query('contacts')['items'][0]['route']['value'])
        self.fx.command('contact.capture',**data)
        self.assertFalse(self.fx.tasks.query('contacts')['items'][0]['qualified'])

    def test_required_view_freshness_is_separate_from_saved_prepared_counts(self):
        from career.views import render
        self.fx.command('batch.save',id='batch_outputs',task='search',requested_count=1,count_unit='cases',track_ids=['track_one'],criterion='Prepared current case.',selected_ids=['case_one'],required_outputs=['xlsx'])
        before=self.fx.tasks.query('assess',record_id='batch_outputs');self.assertEqual(1,before['prepared']);self.assertFalse(before['task_complete'])
        render(self.fx.tasks.repository,'xlsx')
        self.assertTrue(self.fx.tasks.query('assess',record_id='batch_outputs')['task_complete'])
        self.fx.command('case.note',case_id='case_one',text='Private note leaves content ready but view becomes stale.')
        after=self.fx.tasks.query('assess',record_id='batch_outputs');self.assertEqual(1,after['prepared']);self.assertFalse(after['task_complete'])

    def test_csv_formula_like_data_is_text_without_changing_canonical_record(self):
        from career.views import render
        self.fx.command('company.capture',id='company_one',name='=WEBSERVICE("https://northstar.example")',domain='northstar.example')
        result=render(self.fx.tasks.repository,'csv')
        body=Path(result['destination'],'Cases.csv').read_text();self.assertIn("'=WEBSERVICE",body)
        self.assertEqual('=WEBSERVICE("https://northstar.example")',self.fx.tasks.query('cases')['items'][0]['company'])

    def test_bounded_change_replay_gap_requires_resync(self):
        db=self.fx.tasks.repository.connect();base=self.fx.tasks.context()['revision']
        try:
            db.execute('BEGIN IMMEDIATE')
            for revision in range(base+1,base+1102):db.execute('INSERT INTO change_log VALUES (?,?,?,?,?)',(revision,revision,'[]','[]','[]'))
            db.execute('UPDATE workspace SET revision=?',(base+1101,));db.commit()
        finally:db.close()
        changes=self.fx.tasks.query('changes',after=base)
        self.assertEqual(1000,len(changes['changes']));self.assertTrue(changes['resync_required'])

    def test_locale_key_type_placeholder_and_plural_validation(self):
        en=dict(locale='en',plural_categories=['one','other'],messages={'greeting':'Hello {name}','count':dict(one='{count} item',other='{count} items')})
        ru=dict(locale='ru',plural_categories=['one','few','many','other'],messages={'greeting':'Привет, {name}','count':{key:'{count} единиц' for key in ['one','few','many','other']}})
        validate_catalog(ru,en)
        for wrong in [dict(ru,messages={'greeting':'Missing key'}),dict(ru,messages=dict(ru['messages'],greeting='Missing placeholder')),dict(ru,plural_categories=['other'])]:
            with self.assertRaises(CareerError):validate_catalog(wrong,en)
        self.fx.command('preferences.set',theme='dark');self.fx.command('preferences.set',ui_locale='ru')
        self.assertEqual(dict(theme='dark',ui_locale='ru',introduction_shown=False),self.fx.tasks.context()['preferences'])


if __name__=='__main__':unittest.main()
