#!/usr/bin/env python3
"""Actual offline archive acceptance with bundled Python and empty PATH. Fictional only."""
import argparse
import hashlib
import http.client as http_client
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit,parse_qs
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def update_fixture(archive,destination,version=None,fail_context=False):
    """Compatible local test updates only; never publication assets."""
    with zipfile.ZipFile(archive) as source:
        manifest=json.loads(source.read('RELEASE.json'));replacements={}
        if version:
            body=source.read('runtime/career/contracts.py')
            replacement=body.replace(("VERSION = '"+manifest['version']+"'").encode(),("VERSION = '"+version+"'").encode())
            assert replacement!=body;replacements['runtime/career/contracts.py']=replacement;manifest['version']=version
        if fail_context:
            body=source.read('runtime/career/cli.py')
            replacement=body.replace(b'    args=parser().parse_args(argv)',b'    args=parser().parse_args(argv)\n    if args.operation=="context":return 2  # Fictional startup-failure fixture.')
            assert replacement!=body;replacements['runtime/career/cli.py']=replacement
        for name,body in replacements.items():
            manifest['files'][name]['sha256']=hashlib.sha256(body).hexdigest();manifest['files'][name]['size']=len(body)
        file_digest=hashlib.sha256(json.dumps(manifest['files'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:16]
        manifest['release_id']=manifest['version']+'-'+manifest['platform']['target']+'-'+file_digest
        replacements['RELEASE.json']=json.dumps(manifest,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
        with zipfile.ZipFile(destination,'x',zipfile.ZIP_DEFLATED) as output:
            for item in source.infolist():output.writestr(item,replacements.get(item.filename,source.read(item.filename)))
    return hashlib.sha256(Path(destination).read_bytes()).hexdigest(),manifest['release_id']


def run(archive,expected,output):
    archive=Path(archive).absolute();assert hashlib.sha256(archive.read_bytes()).hexdigest()==expected
    with tempfile.TemporaryDirectory(prefix='career-installed-proof-',dir='/tmp') as temporary:
        parent=Path(temporary);stage=parent/'verified-offline-archive';stage.mkdir()
        # Trusted complete archive was hashed above. No Python/Node on PATH is used below.
        with zipfile.ZipFile(archive) as zipped:
            names=zipped.namelist();assert len(names)==len(set(names))
            assert all(not Path(name).is_absolute() and '..' not in Path(name).parts for name in names)
        subprocess.run(['/usr/bin/unzip','-q',str(archive),'-d',str(stage)],check=True)
        manifest=json.loads((stage/'RELEASE.json').read_text())
        python=stage/manifest['python_executable'];workspace=parent/'Installed fictional workspace'
        environment=dict(os.environ,PATH='/nonexistent',PYTHONPATH='/nonexistent');environment.pop('CAREER_AGENT_DEVELOPMENT',None)
        bootstrap=[str(python),'-I','-B',str(stage/'bin/bootstrap.py'),str(archive),'--workspace',str(workspace),'--sha256',expected,'--name','Alex Installed Example','--ui-locale','ru']
        installed=subprocess.run(bootstrap,env=environment,cwd=parent,capture_output=True,text=True,timeout=60)
        assert installed.returncode==0,installed.stderr+installed.stdout
        install_result=json.loads(installed.stdout);launcher=workspace/'.career-agent/career'
        checks=[];timings={}
        def cli(*args,input=None,allowed=(0,)):
            started=time.perf_counter();result=subprocess.run([str(launcher),*args],input=json.dumps(input) if input else None,env=environment,cwd=parent,capture_output=True,text=True,timeout=30)
            assert result.returncode in allowed,(args,result.returncode,result.stdout,result.stderr)
            return json.loads(result.stdout),round((time.perf_counter()-started)*1000,2)
        try:
            context,timings['context_ms']=cli('context');assert context['preferences']['ui_locale']=='ru'
            catalog,_=cli('schema');assert 'research.control' in {entry['intent'] for entry in catalog['intents']}
            nested,_=cli('schema','packet.save');assert 'claim_spans' in nested['input_schema']['properties']['review']['properties']
            assert context['preferences']['introduction_shown'] is False and context['runtime']['ui_available'] is True
            checks.append('Bundled bootstrap, schema catalog/nested examples and CLI work with empty PATH outside repository')
            revision=context['revision'];serial=0
            def command(intent,**data):
                nonlocal revision,serial
                serial+=1;request=dict(request_id='installed_'+str(serial),expected_revision=revision,intent=intent,input=data)
                receipt,elapsed=cli('command',input=request,allowed=(0,3));revision=receipt['revision'];return receipt,elapsed
            command('source.capture',id='source_installed',locator='https://northstar.example/team',excerpt='Morgan Example works on the workflow. Improved processing by 25%.',observed_at='2026-10-24T00:00:00Z',readable=True)
            command('claim.save',id='claim_installed',assertion='Improved processing by 25%.',meaning='Personally improved processing by 25%.',source_ids=['source_installed'],confirmation='confirmed',disclosure='allowed')
            command('track.save',id='track_installed',name='Product work',positioning='Supported contribution.',selected=True,language='en',policies={},claim_ids=['claim_installed'])
            command('company.capture',id='company_installed',name='Northstar Demo',domain='northstar.example')
            command('contact.capture',id='person_installed',name='Morgan Example',company_id='company_installed',affiliation='current',relevance='Relevant workflow colleague.',sources=[dict(source_id='source_installed',axes=['identity','affiliation','relevance'],assessment='supports')],route=dict(kind='profile',value='https://northstar.example/team/morgan',source_id='source_installed'))
            command('case.capture',id='case_installed',company_id='company_installed',title='Product specialist',kind='vacancy',route='person',tracks=[dict(id='track_installed',rationale='Supported contribution.')],source_ids=['source_installed'],requisition='REQ-42',person_id='person_installed',essential_policy='passed')
            command('packet.create',id='packet_installed',case_id='case_installed',purpose='application')
            command('packet.save',packet_id='packet_installed',used_claim_ids=['claim_installed'],documents=[dict(slot='resume',text='Improved processing by 25%.'),dict(slot='message',text='A specific supported professional contribution.'),dict(slot='dossier',text='Private evidence and unknowns.'),dict(slot='interview',text='Supported outline and employer questions.')],review=dict(findings='Fictional source and actual wording compared.',limitations='Deterministic fixture, not independent semantic validation.',claim_spans=[dict(claim_id='claim_installed',text='Improved processing by 25%.')],tone_findings='Concrete professional wording, no invented relationship.',coverage=[dict(claim_id='claim_installed',disposition='included')]))
            selection,_=cli('deliver','packet_installed');assert selection['assessment']['prepared']
            # CP2 defects are exercised through this installed launcher, not imported source helpers.
            base_version=selection['version_id']
            def save_review(body,used,coverage,base=None):
                review=dict(findings='Compared exact installed fictional bytes.',limitations='Mechanical evidence only; no semantic truth certification.',tone_findings='Specific fictional contribution.',claim_spans=[dict(claim_id='claim_installed',text=body)] if used else [],coverage=coverage)
                if base:review['base_coverage_version_id']=base
                return command('packet.save',packet_id='packet_installed',documents=[dict(slot=name,text=body if name=='resume' else 'Fictional supporting content.') for name in ('resume','message','dossier','interview')],used_claim_ids=used,review=review)
            omitted,_=save_review('Prepared synthetic content',[],[dict(claim_id='claim_installed',disposition='included')]);assert omitted['outcome']=='partial'
            omitted,_=save_review('Improved processing.',['claim_installed'],[],base_version);assert 'METRIC_MISSING' in {i['code'] for i in omitted['issues']}
            command('track.save',id='track_other',name='Fictional hospitality',positioning='Training',selected=True,language='en',policies={})
            command('batch.save',id='batch_other',task='research',requested_count=1,count_unit='cases',track_ids=['track_other'],criterion='Hospitality only',selected_ids=['case_installed'],required_outputs=[])
            assessed,_=cli('query','assess','--id','batch_other',allowed=(0,3));assert not assessed['task_complete'] and assessed['qualifying']==0
            request=dict(request_id='identity_refusal',expected_revision=revision,intent='case.capture',input=dict(id='case_installed',company_id='company_installed',title='Different Role',kind='vacancy',route='person',tracks=[dict(id='track_installed',rationale='Supported contribution.')],source_ids=['source_installed'],requisition='REQ-42',canonical_url='https://northstar.example/different-role',person_id='person_installed'))
            refused=subprocess.run([str(launcher),'command'],input=json.dumps(request),env=environment,cwd=parent,capture_output=True,text=True,timeout=30)
            assert refused.returncode==2 and 'IDENTITY_CONFLICT' in refused.stderr
            assert cli('context')[0]['revision']==revision
            command('source.capture',id='source_installed',locator='https://northstar.example/unavailable',excerpt='',readable=False,observed_at='2026-10-24T00:00:00Z')
            unreadable,_=save_review('Improved processing by 25%.',['claim_installed'],[dict(claim_id='claim_installed',disposition='included')]);assert 'SOURCE_UNREADABLE' in {i['code'] for i in unreadable['issues']}
            command('source.capture',id='source_installed',locator='https://northstar.example/team',excerpt='Morgan Example leads product. Improved processing by 25%.',readable=True,observed_at='2026-10-24T00:00:00Z')
            save_review('Improved processing by 25%.',['claim_installed'],[dict(claim_id='claim_installed',disposition='included')])
            command('answer.save',id='answer_other',meaning='location.preference',scope=dict(track_id='track_other'),units={},disposition='answered',value='Other track only',evidence='Synthetic supplied answer')
            for n in range(27):command('claim.save',id='claim_extra_'+str(n).zfill(2),assertion='Synthetic achievement '+chr(65+n%26),meaning='Synthetic private statement',source_ids=['source_installed'],confirmation='unknown',disclosure='private')
            scoped,_=cli('context','--task','packets','--case-id','case_installed','--track-id','track_installed');assert not scoped['evidence']['answers'] and scoped['pagination']['claims']['omitted_by_scope']==27
            page,_=cli('context','--task','profile');assert page['partial'] and page['pagination']['claims']['total']==28
            ids={r['id'] for r in page['evidence']['claims']}
            while page['next_cursor']:
                page,_=cli('context','--task','profile','--cursor',page['next_cursor']);ids.update(r['id'] for r in page['evidence']['claims'])
            assert len(ids)==28
            selection,_=cli('deliver','packet_installed');slot=next(row for row in selection['slots'] if row['name']=='resume')
            material=workspace/'Objects'/(slot['sha256']+'.md');original=material.read_bytes();material.unlink()
            board,_=cli('query','board');assert board['counts']['columns']['ready']==0
            missing=subprocess.run([str(launcher),'deliver','packet_installed'],env=environment,cwd=parent,capture_output=True,text=True,timeout=30);assert missing.returncode==2 and 'MATERIAL_CHANGED' in missing.stderr
            material.write_bytes(original);board,_=cli('query','board');assert board['counts']['columns']['ready']==1
            selection,_=cli('deliver','packet_installed');assert selection['assessment']['prepared']
            checks.append('Installed CP2 regressions: coverage/base metric, batch scope, atomic identity, unreadable evidence, scoped paginated context and missing-object recovery')
            command('packet.create',id='aaa_alternative',case_id='case_installed',purpose='contact')
            detail,_=cli('query','case','--id','case_installed');assert detail['selection']['version_id']==selection['version_id']
            checks.append('Installed domain commands retain explicit primary/selected bytes and readback')
            view,_=cli('render','--format','xlsx');assert Path(view['destination'],'Career.xlsx').is_file()
            saved_manifest=json.loads(Path(view['destination'],'manifest.json').read_text());assert saved_manifest['selection'][0]['version_id']==selection['version_id']
            checks.append('Installed spreadsheet manifest consumes the same selected version')
            backup,_=cli('backup');assert Path(backup['destination'],'Data/career.sqlite3').is_file()
            checks.append('Revision-bound portable DB/object backup uses installed repository')
            source_attempt=subprocess.run([sys.executable,str(ROOT/'scripts/career.py'),'--workspace',str(workspace),'context'],capture_output=True,text=True,cwd=parent,env=environment)
            assert source_attempt.returncode==2 and 'INSTALLED_COPY_REQUIRED' in source_attempt.stderr
            checks.append('Source/global application execution refused for installed workspace')
            status,_=cli('app','status');assert status['release_id']==manifest['release_id']
            release=Path(status['release_path'])
            runtime_info=subprocess.run([str(release/manifest['python_executable']),'-I','-B','-c','import sys,sqlite3,ssl,json;print(json.dumps({"python":sys.version,"executable":sys.executable,"sqlite":sqlite3.sqlite_version,"ssl":ssl.OPENSSL_VERSION,"sys_path":sys.path}))'],capture_output=True,text=True,env=environment,check=True)
            runtime_info=json.loads(runtime_info.stdout);assert all(str(ROOT) not in path for path in runtime_info['sys_path'])
            opened,timings['open_ms']=cli('ui','open','--no-browser');url=urlsplit(opened['url']);origin='http://'+url.netloc
            cookie=None;csrf=None
            def http(path,method='GET',body=None,csrf_override=None,cookie_override=None):
                client=http_client.HTTPConnection('127.0.0.1',url.port,timeout=5);headers={'Origin':origin}
                if cookie_override or cookie:headers['Cookie']=cookie_override or cookie
                if csrf_override or csrf:headers['X-CSRF-Token']=csrf_override or csrf
                if body is not None:body=json.dumps(body);headers['Content-Type']='application/json'
                client.request(method,path,body,headers);response=client.getresponse();content=response.read();value=(response.status,dict(response.getheaders()),content);client.close();return value
            capability=parse_qs(url.fragment)['launch'][0]
            code,headers,body=http('/api/v1/session','POST',dict(capability=capability));assert code==200
            cookie=headers['Set-Cookie'].split(';')[0];csrf=json.loads(body)['csrf_token']
            assert http('/locales/ru.json')[0]==200
            assert b'lang="ru"' in http('/')[2]
            assert json.loads(http('/api/v1/localization')[2])['locale']=='ru'
            board=json.loads(http('/api/v1/board')[2]);assert board['counts']['total']==1 and len(board['columns']['ready']['items'])==1
            request=dict(request_id='http_installed',expected_revision=revision,intent='preferences.set',input=dict(theme='dark'))
            code,_,body=http('/api/v1/commands','POST',request);assert code==200;revision=json.loads(body)['revision']
            read,_=cli('context');assert read['preferences']==dict(theme='dark',ui_locale='ru',introduction_shown=False)
            assert http('/api/v1/commands','POST',dict(request,request_id='stale_installed'))[0]==409
            checks.append('Installed UI API shares SQLite writes, board counts, locale, CSRF and revision conflicts')
            stream=http_client.HTTPConnection('127.0.0.1',url.port,timeout=10)
            stream.request('GET','/api/v1/events?after='+str(revision),headers={'Origin':origin,'Cookie':cookie});response=stream.getresponse();assert response.status==200
            started=time.perf_counter();command('case.note',case_id='case_installed',text='Actual installed CLI update.')
            while True:
                line=response.readline().decode()
                if line.startswith('data: '):
                    event=json.loads(line[6:])
                    if event.get('cursor')==revision:break
            timings['cli_to_stream_ms']=round((time.perf_counter()-started)*1000,2);stream.close()
            assert json.loads(http('/api/v1/cases/case_installed')[2])['notes']=='Actual installed CLI update.'
            assert http('/api/v1/session','POST',{})[0]==200
            checks.append('Installed CLI commits reach durable SSE and authenticated reload')
            old_cookie=cookie
            restarted,timings['restart_ms']=cli('ui','restart','--no-browser');url=urlsplit(restarted['url']);origin='http://'+url.netloc
            assert http('/api/v1/context',cookie_override=old_cookie)[0]==401
            cli('ui','stop');assert cli('ui','status')[0]['status']=='stopped'
            checks.append('Restart invalidates sessions; graceful stop confirmed without PID killing')
            verify,_=cli('app','verify');assert verify['verified']
            doctor,_=cli('doctor');assert doctor['healthy']
            repeated=subprocess.run(bootstrap,env=environment,cwd=parent,capture_output=True,text=True,timeout=60);assert repeated.returncode==0,repeated.stdout+repeated.stderr
            repeated=json.loads(repeated.stdout);assert repeated['reused'] and repeated['revision']==revision and repeated['workspace_id']==context['workspace_id']
            checks.append('Repeated offline initialization preserves workspace identity/revision/data')
            # Verified fresh-chat mechanics are tested here without editing the independent evaluator workspace.
            before_research=cli('context')[0]['research']
            command('preferences.set',introduction_shown=True)
            current,_=cli('context');assert current['preferences']==dict(theme='dark',ui_locale='ru',introduction_shown=True) and current['research']==before_research
            pending=dict(meaning='location.preference',scope=dict(track_id='track_installed'),units={},disposition='pending',value=None,evidence='Open location question; no user response exists.',response_state='pending')
            receipt,_=command('answer.save',**pending);answer_id=receipt['saved_ids'][0]
            current,_=cli('context','--track-id','track_installed','--answer-id',answer_id);assert current['answer']['response_state']=='pending' and not current['answer']['reusable_here']
            receipt,_=command('answer.save',**dict(pending,disposition='unknown',response_state='provided',evidence='Fictional user explicitly answered that they do not know.'));assert receipt['saved_ids'][0]==answer_id
            current,_=cli('context','--track-id','track_installed','--answer-id',answer_id);assert current['answer']['reusable_here'] and not current['answer']['value_reusable_here']
            command('batch.save',id='job_original',task='job_search',requested_count=2,count_unit='cases',track_ids=['track_installed'],criterion='Original two-case job search',selected_ids=['case_installed'],required_outputs=[])
            command('batch.save',id='packet_child',parent_id='job_original',task='packets',requested_count=1,count_unit='cases',track_ids=['track_installed'],criterion='One preliminary packet',selected_ids=['case_installed'],required_outputs=[])
            child,_=cli('query','assess','--id','packet_child',allowed=(0,3));assert child['scope_complete'] and not child['task_complete'] and child['task']['requested_count']==2
            selected,_=cli('deliver','packet_installed');assert selected['task_progress'][0]['remaining_work']
            number_check=subprocess.run([str(release/manifest['python_executable']),'-I','-B','-c','import sys,json;sys.path.insert(0,sys.argv[1]);from career.policy import number_tokens;print(json.dumps(number_tokens("\\u04413,2% \\u0434\\u043e1,8%")))',str(release/'runtime')],env=environment,capture_output=True,text=True,timeout=10)
            assert number_check.returncode==0 and json.loads(number_check.stdout)==['3,2','1,8'],number_check.stdout+number_check.stderr
            checks.append('Installed pending/provided answers, one-time display preference, original-task remaining and non-Latin decimal tokens')
            command('source.capture',id='source_taylor',locator='https://northstar.example/team/taylor',excerpt='Taylor Example leads relevant training at Northstar Demo.',readable=True,observed_at='2026-10-24T00:00:00Z')
            command('contact.capture',id='person_taylor',name='Taylor Example',company_id='company_installed',affiliation='current',relevance='Relevant training colleague.',sources=[dict(source_id='source_taylor',axes=['identity','affiliation','relevance'],assessment='supports')],route=dict(kind='profile',value='https://northstar.example/team/taylor',source_id='source_taylor'))
            command('packet.create',id='packet_taylor',case_id='case_installed',purpose='application',person_id='person_taylor')
            documents=[dict(slot=name,text='Improved processing by 25%.' if name=='resume' else 'Specific supported Taylor contribution.') for name in ('resume','message','dossier','interview')]
            review=dict(findings='Compared actual fictional spans and recipient evidence.',limitations='No independent truth guarantee.',tone_findings='Specific professional wording.',claim_spans=[dict(claim_id='claim_installed',text='Improved processing by 25%.')],coverage=[dict(claim_id='claim_installed',disposition='included')])
            command('packet.save',packet_id='packet_taylor',documents=documents,used_claim_ids=['claim_installed'],review=review)
            command('packet.primary',packet_id='packet_taylor')
            command('contact.capture',id='person_installed',name='Morgan Example',company_id='company_installed',affiliation='unknown',relevance='Relevant workflow colleague.',sources=[dict(source_id='source_installed',axes=['identity','affiliation','relevance'],assessment='supports')],route=dict(kind='profile',value='https://northstar.example/team/morgan',source_id='source_installed'))
            detail,_=cli('query','case','--id','case_installed');assert detail['case']['contact']['id']==detail['selection']['person_id']=='person_taylor'
            board,_=cli('query','board');assert board['columns']['ready']['items'][0]['contact']['id']=='person_taylor'
            command('case.capture',id='case_installed',company_id='company_installed',title='Product specialist',kind='vacancy',route='person',tracks=[dict(id='track_installed',rationale='Supported contribution.')],source_ids=['source_installed'],requisition='REQ-42',person_id='person_installed',essential_policy='unknown',essential_unknowns=[dict(code='REQUIRED_CERTIFICATE_UNKNOWN',subject='Required certificate',message='The required certificate is not established.',source_ids=['source_installed'])])
            command('packet.save',packet_id='packet_taylor',documents=documents,used_claim_ids=['claim_installed'],review=review)
            selected,_=cli('deliver','packet_taylor',allowed=(0,3));assert selected['assessment']['prepared'] and selected['assessment']['conditional'] and selected['assessment']['unknown_details']
            assessed,_=cli('query','assess','--id','packet_child',allowed=(0,3));assert assessed['qualified']==0 and assessed['prepared']==1 and not assessed['task_complete']
            checks.append('Installed selected-recipient projections and useful conditional draft without unconditional qualification')
            # The actual installed runtime owns the retention files; no source/global helper is loaded.
            automatic=workspace/'Backups/Automatic'
            checkpoints=list(automatic.glob('r*.sqlite3'));assert 1<=len(checkpoints)<=17
            metadata=[json.loads(path.with_suffix('.json').read_text()) for path in checkpoints]
            assert max(item['revision'] for item in metadata)==revision-1
            for path in checkpoints:
                record=json.loads(path.with_suffix('.json').read_text())
                assert hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256']
            latest=max(checkpoints,key=lambda path:json.loads(path.with_suffix('.json').read_text())['revision'])
            probe_code="""import sys,json,sqlite3,shutil
from unittest.mock import patch
sys.path.insert(0,sys.argv[1])
from career.facade import Tasks
from career.contracts import CareerError
from career.policy import number_tokens
tasks=Tasks(sys.argv[2]);revision=tasks.context()['revision']
with patch('career.repository.shutil.disk_usage',return_value=shutil._ntuple_diskusage(100,99,1)):
 try:tasks.command(dict(request_id='installed_low_disk_probe',expected_revision=revision,intent='preferences.set',input=dict(theme='dark')))
 except CareerError as error:assert error.code=='DISK_SPACE_LOW' and error.status==507
 else:raise AssertionError('Low disk was not rejected')
assert tasks.context()['revision']==revision
assert number_tokens('n8n B2B 25%')==['8','2','25']  # Raw scanner; scoped review resolves reference roles.
source=sqlite3.connect('file:'+sys.argv[3]+'?mode=ro&immutable=1',uri=True);restored=sqlite3.connect(':memory:')
source.backup(restored)
assert restored.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
assert not list(restored.execute('PRAGMA foreign_key_check'))
assert restored.execute('SELECT revision FROM workspace').fetchone()[0]==revision-1
restored.close();source.close()
print(json.dumps(dict(status='passed',revision=revision)))
"""
            before_hash=hashlib.sha256((workspace/'Data/career.sqlite3').read_bytes()).hexdigest()
            probe=subprocess.run([str(release/manifest['python_executable']),'-I','-B','-c',probe_code,str(release/'runtime'),str(workspace),str(latest)],env=environment,cwd=parent,capture_output=True,text=True,timeout=20)
            assert probe.returncode==0,probe.stdout+probe.stderr
            assert hashlib.sha256((workspace/'Data/career.sqlite3').read_bytes()).hexdigest()==before_hash
            checks.append('Installed bounded checkpoint retention, verified restore, typed low-disk refusal without mutation, and identifier-number distinction')
            command('company.capture',id='company_numeric',name='Icons8',domain='icons.example')
            command('source.capture',id='source_numeric',locator='https://tools.example/reference',excerpt='Fictional reference: Icons8 uses named D3, n8n and B2B concepts.',observed_at='2026-10-25T00:00:00Z',readable=True)
            command('case.capture',id='case_numeric',company_id='company_numeric',title='Fictional tooling need',kind='speculative',route='unknown',tracks=[dict(id='track_installed',rationale='Synthetic numeric reference check')],source_ids=['source_numeric'],essential_policy='passed')
            command('packet.create',id='packet_numeric',case_id='case_numeric',purpose='contact')
            numeric_review=dict(findings='Compared exact canonical name and scoped source identifiers.',limitations='Does not certify semantic truth.',tone_findings='Concrete.',claim_spans=[],coverage=[],entity_refs=[dict(text=value,source_id='source_numeric') for value in ('D3','n8n','B2B')])
            good,_=command('packet.save',packet_id='packet_numeric',documents=[dict(slot='message',text='Icons8: D3 n8n B2B.')],used_claim_ids=[],review=numeric_review);assert good['outcome']=='satisfied'
            current,_=cli('deliver','packet_numeric');assert current['assessment']['prepared'] and all(entry['role']=='reference' for entry in current['review']['numeric_audit']['occurrences'])
            good_version=current['version_id'];good_hash=current['slots'][0]['sha256']
            bad,_=command('packet.save',packet_id='packet_numeric',documents=[dict(slot='message',text='Icons8: D3 n8n B2B. Managed 8 engineers for 3 years; improved by 999%.')],used_claim_ids=[],review=numeric_review)
            assert bad['outcome']=='partial' and {'8','3','999'}=={entry['token'] for entry in bad['issues'] if entry['code']=='UNMATCHED_NUMBER'}
            historical,_=cli('query','selection','--id','packet_numeric','--version-id',good_version);assert historical['assessment']['prepared'] and historical['slots'][0]['sha256']==good_hash
            command('packet.select',packet_id='packet_numeric',version_id=good_version)
            checks.append('Installed canonical/source entity occurrences do not authorize independent counts, durations or percent claims; historical exact bytes stay unchanged')
            failed_archive=parent/'fictional-failed-update.zip';failed_sha,failed_id=update_fixture(archive,failed_archive,fail_context=True)
            before_pointer=json.loads((workspace/'.career-agent/active.json').read_text())
            failed=subprocess.run([str(launcher),'app','update','--archive',str(failed_archive),'--sha256',failed_sha],capture_output=True,text=True,env=environment,cwd=parent,timeout=60)
            assert failed.returncode==2 and 'WORKSPACE_CHECK_FAILED' in failed.stderr
            assert json.loads((workspace/'.career-agent/active.json').read_text())==before_pointer
            assert not (workspace/'.career-agent/previous.json').exists()
            assert (workspace/'.career-agent/releases'/failed_id).is_dir()
            checks.append('Failed new-code startup restores pointer, preserves failed release and prior rollback state')
            pending=dict(request_id='pending_before_update',expected_revision=revision,intent='case.note',input=dict(case_id='case_installed',text='Pending bounded plan before code update.'))
            planned,_=cli('plan',input=pending)
            db_hash=hashlib.sha256((workspace/'Data/career.sqlite3').read_bytes()).hexdigest()
            next_archive=parent/'fictional-compatible-update.zip';major,minor,patch=map(int,manifest['version'].split('.'));next_sha,next_id=update_fixture(archive,next_archive,version=str(major)+'.'+str(minor)+'.'+str(patch+1))
            updated=subprocess.run([str(launcher),'app','update','--archive',str(next_archive),'--sha256',next_sha],capture_output=True,text=True,env=environment,cwd=parent,timeout=60)
            assert updated.returncode==0,updated.stdout+updated.stderr
            assert cli('app','status')[0]['release_id']==next_id
            stale=subprocess.run([str(launcher),'apply',planned['plan_id']],capture_output=True,text=True,env=environment,cwd=parent,timeout=30)
            assert stale.returncode==2 and 'PLAN_CODE_CHANGED' in stale.stderr
            assert hashlib.sha256((workspace/'Data/career.sqlite3').read_bytes()).hexdigest()==db_hash
            rolled,_=cli('app','rollback');assert rolled['release_id']==manifest['release_id']
            assert cli('context')[0]['revision']==revision
            assert hashlib.sha256((workspace/'Data/career.sqlite3').read_bytes()).hexdigest()==db_hash
            checks.append('Compatible code update/rollback preserve database; old sealed plans require replan')

            result=dict(status='passed',archive=str(archive),archive_sha256=expected,release_id=manifest['release_id'],ui_build=manifest['ui_build'],checks=checks,timings_ms=timings,runtime=runtime_info,
                        scope='Fictional macOS arm64 installed-runtime proof only. UI independent review remains a separate gate. No real-data migration, external research/send, global installation or publication.',external_actions_performed=0)
        finally:
            subprocess.run([str(launcher),'ui','stop'],env=environment,cwd=parent,capture_output=True,text=True,timeout=30)
        Path(output).write_text(json.dumps(result,indent=2)+'\n');return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('archive');parser.add_argument('--sha256',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    result=run(args.archive,args.sha256,args.output);print(json.dumps({key:result[key] for key in ('status','release_id','checks','timings_ms')},indent=2))
