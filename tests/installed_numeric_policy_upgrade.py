"""Exact previous/candidate archive upgrade regression. Fictional workspaces only."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import tempfile
import zipfile


def verify_archive(path,expected):
    assert hashlib.sha256(path.read_bytes()).hexdigest()==expected
    with zipfile.ZipFile(path) as archive:
        manifest=json.loads(archive.read('RELEASE.json'));names=archive.namelist()
        assert len(names)==len(set(names)) and set(names)==set(manifest['files'])|{'RELEASE.json'}
        for name,record in manifest['files'].items():
            assert not Path(name).is_absolute() and '..' not in Path(name).parts
            body=archive.read(name);assert len(body)==record['size'] and hashlib.sha256(body).hexdigest()==record['sha256']
    return manifest


def state(workspace):
    db=sqlite3.connect((workspace/'Data/career.sqlite3').as_uri()+'?mode=ro',uri=True);db.execute('PRAGMA query_only=ON');db.execute('BEGIN');tables={}
    for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN('case_projection_cache','view_exports') ORDER BY name"):
        assert name.replace('_','').isalnum();rows=list(db.execute('SELECT * FROM '+name+' ORDER BY rowid'))
        tables[name]=dict(count=len(rows),sha256=hashlib.sha256(json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode()).hexdigest())
    revision=db.execute('SELECT revision FROM workspace').fetchone()[0];db.close()
    return dict(revision=revision,tables=tables,objects={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((workspace/'Objects').iterdir()) if p.is_file()})


def run(previous,previous_sha,candidate,candidate_sha,output):
    old=verify_archive(previous,previous_sha);new=verify_archive(candidate,candidate_sha)
    assert old['version']=='1.0.3' and new['version']=='1.0.4'
    with tempfile.TemporaryDirectory(prefix='career-policy-upgrade-fictional-',dir='/tmp') as temporary:
        parent=Path(temporary);stage=parent/'previous';stage.mkdir();workspace=parent/'workspace'
        subprocess.run(['/usr/bin/unzip','-q',str(previous),'-d',str(stage)],check=True)
        env=dict(os.environ,PATH='/nonexistent',PYTHONPATH='/nonexistent');env.pop('CAREER_AGENT_DEVELOPMENT',None)
        boot=subprocess.run([str(stage/old['python_executable']),'-I','-B',str(stage/'bin/bootstrap.py'),str(previous),'--workspace',str(workspace),'--sha256',previous_sha,'--name','Alex Example','--ui-locale','en'],env=env,capture_output=True,text=True,timeout=60)
        assert boot.returncode==0,boot.stdout+boot.stderr
        launcher=workspace/'.career-agent/career';serial=0
        def cli(*args,data=None,allowed=(0,3)):
            result=subprocess.run([str(launcher),*args],input=json.dumps(data) if data is not None else None,env=env,cwd=parent,capture_output=True,text=True,timeout=60)
            assert result.returncode in allowed,(args,result.returncode,result.stdout,result.stderr)
            return json.loads(result.stdout or result.stderr),result.returncode
        def command(intent,**data):
            nonlocal serial
            serial+=1
            return cli('command',data=dict(request_id='policy_fixture_'+str(serial),expected_revision=cli('context')[0]['revision'],intent=intent,input=data))[0]
        command('source.capture',id='source_one',locator='https://named.example/team',excerpt='Company named 7inch. Morgan Example coordinates its interfaces. Alex Example worked at 7inch.',observed_at='2026-10-26T00:00:00Z',readable=True)
        command('claim.save',id='claim_one',assertion='At 7inch.',meaning='At 7inch.',source_ids=['source_one'],confirmation='confirmed',disclosure='allowed')
        command('track.save',id='track_one',name='Interface work',positioning='Supported work.',selected=True,language='en',policies={},claim_ids=['claim_one'])
        command('company.capture',id='company_one',name='7inch',domain='named.example',source_ids=['source_one'])
        command('contact.capture',id='person_one',name='Morgan Example',company_id='company_one',affiliation='current',relevance='Coordinates the documented interfaces.',sources=[dict(source_id='source_one',axes=['identity','affiliation','relevance'],assessment='supports')],route=dict(kind='profile',value='https://named.example/team/morgan',source_id='source_one'))
        def create(case,packet,requisition):
            command('case.capture',id=case,company_id='company_one',title='Fictional interface role',kind='vacancy',route='person',tracks=[dict(id='track_one',rationale='Fictional supported work.')],source_ids=['source_one'],person_id='person_one',requisition=requisition,essential_policy='passed')
            command('packet.create',id=packet,case_id=case,purpose='contact')
        def packet_data(packet,text):return dict(packet_id=packet,documents=[dict(slot='message',text=text)],used_claim_ids=['claim_one'])
        def review(data):
            bound=cli('review-context',data=data)[0]
            return dict(findings='Synthetic actual old/new policy comparison.',limitations='Mechanical fixture, not semantic proof.',tone_findings='Fixture only.',claim_spans=[dict(claim_id='claim_one',text=data['documents'][0]['text'])],coverage=[dict(claim_id='claim_one',disposition='included')],entity_spans=[dict(slot='message',start=3,end=8,text='7inch',company_id='company_one')],editorial=dict(argument='Fictional source-backed interface history.',findings='Structural fixture; independent judgment is separate.',decision='approved',binding=bound['binding']))
        create('case_bad','packet_bad','DEMO-BAD')
        bad_data=packet_data('packet_bad','At 7inch%.');command('packet.save',**bad_data,review=review(bad_data))
        bad=cli('deliver','packet_bad')[0]
        create('case_history','packet_history','DEMO-HISTORY')
        good_data=packet_data('packet_history','At 7inch.');command('packet.save',**good_data,review=review(good_data));good=cli('deliver','packet_history')[0]
        command('activity.record',case_id='case_history',kind='sent',occurred_at='2026-10-26T00:00:00Z',evidence='Synthetic historical receipt; no actual transmission performed.',packet_id='packet_history',version_id=good['version_id'],message_sha256=good['slots'][0]['sha256'])
        command('batch.save',id='batch_one',task='packets',requested_count=1,count_unit='cases',track_ids=['track_one'],criterion='One prepared fixture',selected_ids=['case_bad'],required_outputs=[])
        def handoff(data,version):return cli('handoff-check',data=dict(packet_id=data['packet_id'],version_id=version,documents=data['documents'],recipient=dict(kind='profile',value='https://named.example/team/morgan')))[0]
        assert bad['assessment']['prepared'] and handoff(bad_data,bad['version_id'])['ready']
        assert bad['review']['numeric_audit']['policy']=='career-agent.numeric-occurrences/3'
        assert cli('query','board')[0]['counts']['columns']['ready']==1
        assert cli('query','assess','--id','batch_one')[0]['task_complete']
        before=state(workspace);history_before=cli('query','case-history','--id','case_history')[0]['items']
        update=cli('app','update','--archive',str(candidate),'--sha256',candidate_sha)[0];assert update['release_id']==new['release_id']
        selected=cli('deliver','packet_bad')[0];handoff_after=handoff(bad_data,bad['version_id'])
        assert not selected['assessment']['prepared'] and not selected['assessment']['factual_pass'] and not handoff_after['ready']
        assert any(i.get('reason')=='numeric_policy_changed' and i.get('saved_policy')=='career-agent.numeric-occurrences/3' and i.get('required_policy')=='career-agent.numeric-occurrences/4' for i in handoff_after['issues'])
        assert selected['version_id']==bad['version_id'] and selected['slots']==bad['slots'] and selected['review']==bad['review']
        cases=cli('query','cases')[0]['items'];assert not next(c for c in cases if c['id']=='case_bad')['prepared']
        assert cli('query','board')[0]['counts']['columns']['ready']==0
        assert not cli('query','case','--id','case_bad')[0]['case']['prepared']
        batch=cli('query','assess','--id','batch_one')[0];assert batch['prepared']==0 and not batch['task_complete']
        assert cli('query','case-history','--id','case_history')[0]['items']==history_before
        historical=cli('deliver','packet_history')[0];assert historical['reported_sent'] and not historical['assessment']['prepared'] and historical['version_id']==good['version_id']
        assert state(workspace)==before
        serial+=1;refused,code=cli('command',data=dict(request_id='policy_fixture_'+str(serial),expected_revision=before['revision'],intent='packet.save',input=dict(bad_data,review=review(bad_data))),allowed=(2,))
        assert code==2 and refused['error']['code']=='INVALID_REVIEW' and state(workspace)==before
        command('packet.save',**good_data,review=review(good_data));current=cli('deliver','packet_history')[0]
        assert current['assessment']['prepared'] and current['review']['numeric_audit']['policy']=='career-agent.numeric-occurrences/4' and handoff(good_data,current['version_id'])['ready']
        assert current['version_id']!=good['version_id'] and current['slots']==good['slots']
        prior=cli('query','selection','--id','packet_history','--version-id',good['version_id'])[0]
        assert prior['reported_sent'] and prior['review']==good['review'] and prior['slots']==good['slots'] and not prior['assessment']['prepared']
        assert cli('query','case-history','--id','case_history')[0]['items']==history_before
        result=dict(status='passed',previous_archive_sha256=previous_sha,candidate_archive_sha256=candidate_sha,release_id=new['release_id'],old_policy='career-agent.numeric-occurrences/3',required_policy='career-agent.numeric-occurrences/4',old_unsafe_ready=True,upgraded_selection_ready=False,upgraded_handoff_ready=False,cached_board_table_detail_batch_consistent=True,canonical_tables_preserved_on_code_update=len(before['tables']),all_object_bytes_preserved_on_code_update=True,old_reviews_versions_sent_history_immutable=True,fresh_same_unsafe_payload_refused=True,actual_current_review_restores_valid_payload=True,revision_preserved_on_code_update=before['revision'],external_actions_performed=0,browser_opened=False,scope='Exact installed old/new archives; disposable fictional workspace only. No real data or global/release changes.')
    output.write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('previous_archive',type=Path);p.add_argument('candidate_archive',type=Path);p.add_argument('--previous-sha256',required=True);p.add_argument('--candidate-sha256',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(run(a.previous_archive,a.previous_sha256,a.candidate_archive,a.candidate_sha256,a.output),indent=2))
