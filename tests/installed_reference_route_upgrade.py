"""Exact 1.0.4-to-candidate archive acceptance; fictional private workspace only."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
from installed_numeric_policy_upgrade import verify_archive,state


def run(previous,previous_sha,candidate,candidate_sha,output):
    old=verify_archive(previous,previous_sha);new=verify_archive(candidate,candidate_sha)
    assert old['version'] in ('1.0.4','1.0.5') and new['version']=='1.0.5'
    with tempfile.TemporaryDirectory(prefix='career-reference-upgrade-',dir='/tmp') as temporary:
        parent=Path(temporary);stage=parent/'previous';stage.mkdir();workspace=parent/'workspace'
        subprocess.run(['/usr/bin/unzip','-q',str(previous),'-d',str(stage)],check=True)
        env=dict(os.environ,PATH='/nonexistent',PYTHONPATH='/nonexistent');env.pop('CAREER_AGENT_DEVELOPMENT',None)
        boot=subprocess.run([str(stage/old['python_executable']),'-I','-B',str(stage/'bin/bootstrap.py'),str(previous),'--workspace',str(workspace),'--sha256',previous_sha,'--name','Alex Example','--ui-locale','en'],env=env,capture_output=True,text=True,timeout=60)
        assert boot.returncode==0,boot.stdout+boot.stderr
        launcher=workspace/'.career-agent/career';serial=0
        def cli(*args,data=None,allowed=(0,3)):
            r=subprocess.run([str(launcher),*args],input=json.dumps(data) if data is not None else None,env=env,cwd=parent,capture_output=True,text=True,timeout=60)
            assert r.returncode in allowed,(args,r.returncode,r.stdout,r.stderr)
            return json.loads(r.stdout or r.stderr)
        def command(intent,**data):
            nonlocal serial
            serial+=1
            return cli('command',data=dict(request_id='reference_upgrade_'+str(serial),expected_revision=cli('context')['revision'],intent=intent,input=data))
        def review(data,spans=None):
            bound=cli('review-context',data=data)
            return dict(findings='Compared the exact fictional locator and supported contribution.',limitations='Mechanics do not certify source truth or literary quality.',tone_findings='Fictional introduction.',claim_spans=[],coverage=[],entity_spans=spans or [],editorial=dict(argument='Relevant project inquiry.',decision='approved',findings='Structural fixture attestation only.',binding=bound['binding']))
        command('source.capture',id='source_mail',locator='https://northstar.example/contact',excerpt='Northstar Demo project enquiries: projects@northstar.example. Morgan Example coordinates projects.',observed_at='2026-10-26T00:00:00Z',readable=True)
        url='https://market.example/jobs/offer,654321/'
        command('source.capture',id='source_job',locator=url,excerpt='A published fictional interface project.',observed_at='2026-10-26T00:00:00Z',readable=True)
        command('track.save',id='track_one',name='Product work',positioning='Documented workflow contribution.',selected=True,language='en',policies={})
        command('company.capture',id='company_one',name='Northstar Demo',domain='northstar.example',source_ids=['source_mail'])
        command('contact.capture',id='person_one',name='Morgan Example',company_id='company_one',affiliation='current',relevance='Coordinates relevant projects.',sources=[dict(source_id='source_mail',axes=['identity','affiliation','relevance'],assessment='supports')],route=dict(kind='email',value='projects@northstar.example',source_id='source_mail'))
        case=dict(id='case_one',company_id='company_one',title='Published project',kind='project',route='person',person_id='person_one',tracks=[dict(id='track_one',rationale='Relevant supported work.')],source_ids=['source_mail','source_job'],canonical_url=url,essential_policy='passed')
        command('case.capture',**case);command('packet.create',id='packet_history',case_id='case_one',purpose='contact')
        data=dict(packet_id='packet_history',documents=[dict(slot='message',text='A relevant professional contribution.')],used_claim_ids=[])
        command('packet.save',**data,review=review(data));prior=cli('deliver','packet_history');assert prior['assessment']['prepared']
        command('activity.record',case_id='case_one',packet_id='packet_history',version_id=prior['version_id'],kind='sent',occurred_at='2026-10-26T00:00:00Z',evidence='Fictional historical provider receipt; no external transmission.',message_sha256=prior['slots'][0]['sha256'])
        command('packet.create',id='packet_draft',case_id='case_one',purpose='contact')
        message='Relevant listing: '+url
        draft=dict(packet_id='packet_draft',documents=[dict(slot='message',text=message)],used_claim_ids=[])
        command('packet.save',**draft,review=review(draft));before_draft=cli('deliver','packet_draft');assert not before_draft['assessment']['prepared']
        assert any(i['code']=='UNMATCHED_NUMBER' for i in before_draft['assessment']['issues'])
        unsafe_prefix=None
        if old['version']=='1.0.5':
            command('packet.create',id='packet_bad_prefix',case_id='case_one',purpose='contact')
            unsafe_prefix=dict(packet_id='packet_bad_prefix',documents=[dict(slot='message',text='<'+url+')evil>')],used_claim_ids=[])
            prefix_spans=[dict(slot='message',start=1,end=1+len(url),text=url,source_id='source_job')]
            command('packet.save',**unsafe_prefix,review=review(unsafe_prefix,prefix_spans))
            bad_prior=cli('deliver','packet_bad_prefix');assert bad_prior['assessment']['prepared'] and bad_prior['review']['numeric_audit']['policy']=='career-agent.numeric-occurrences/5'
            command('packet.primary',packet_id='packet_bad_prefix')
            command('batch.save',id='batch_prefix',task='packets',requested_count=1,count_unit='cases',track_ids=['track_one'],criterion='One actually prepared case.',selected_ids=['case_one'],required_outputs=[])
            assert cli('query','assess','--id','batch_prefix')['task_complete']
            assert next(r for r in cli('query','cases')['items'] if r['id']=='case_one')['prepared']
        before=state(workspace);history=cli('query','case-history','--id','case_one')['items']
        assert cli('app','update','--archive',str(candidate),'--sha256',candidate_sha)['release_id']==new['release_id']
        assert state(workspace)==before
        after=cli('deliver','packet_history');assert after['reported_sent'] and after['slots']==prior['slots'] and after['review']==prior['review'] and not after['assessment']['prepared']
        assert any(i.get('reason')=='numeric_policy_changed' for i in after['assessment']['issues'])
        assert not cli('handoff-check',data=dict(packet_id='packet_history',version_id=after['version_id'],documents=data['documents'],recipient=dict(kind='email',value='projects@northstar.example')))['ready']
        if unsafe_prefix:
            bad_after=cli('deliver','packet_bad_prefix');assert not bad_after['assessment']['prepared'] and bad_after['slots']==bad_prior['slots'] and bad_after['review']==bad_prior['review']
            assert not cli('handoff-check',data=dict(packet_id='packet_bad_prefix',version_id=bad_after['version_id'],documents=unsafe_prefix['documents'],recipient=dict(kind='email',value='projects@northstar.example')))['ready']
            assert not cli('query','case','--id','case_one')['case']['prepared']
            assert not next(r for r in cli('query','cases')['items'] if r['id']=='case_one')['prepared']
            assert not next(r for r in cli('query','board')['columns']['waiting']['items'] if r['id']=='case_one')['prepared']
            assert not cli('query','assess','--id','batch_prefix')['task_complete']
            serial+=1
            failure=cli('command',data=dict(request_id='reference_upgrade_'+str(serial),expected_revision=cli('context')['revision'],intent='packet.save',input=dict(unsafe_prefix,review=review(unsafe_prefix,prefix_spans))),allowed=(2,))
            assert failure['error']['code']=='INVALID_REVIEW' and state(workspace)==before
        company_case=dict(case,route='company',company_route=dict(kind='email',value='projects@northstar.example',source_id='source_mail'));company_case.pop('person_id')
        command('case.capture',**company_case);command('packet.create',id='packet_company',case_id='case_one',purpose='contact');command('packet.primary',packet_id='packet_company')
        current_data=dict(draft,packet_id='packet_company');start=message.index(url);spans=[dict(slot='message',start=start,end=start+len(url),text=url,source_id='source_job')]
        command('packet.save',**current_data,review=review(current_data,spans));current=cli('deliver','packet_company');assert current['assessment']['prepared'] and current['person_id'] is None
        handoff=dict(packet_id='packet_company',version_id=current['version_id'],documents=current_data['documents'],recipient=dict(kind='email',value='projects@northstar.example'))
        assert cli('handoff-check',data=handoff)['ready']
        assert cli('query','case','--id','case_one')['case']['selected_route']['value']=='projects@northstar.example'
        assert next(r for r in cli('query','cases')['items'] if r['id']=='case_one')['prepared']
        assert any(r['id']=='case_one' for r in cli('query','board')['columns']['waiting']['items'])
        unsafe=dict(current_data,documents=[dict(slot='message',text=message+' Managed 654321 engineers.')])
        command('packet.save',**unsafe,review=review(unsafe,spans));bad=cli('deliver','packet_company')
        assert not bad['assessment']['prepared'] and any(i.get('token')=='654321' for i in bad['assessment']['issues'])
        command('packet.save',**current_data,review=review(current_data,spans));current=cli('deliver','packet_company');handoff['version_id']=current['version_id'];assert cli('handoff-check',data=handoff)['ready']
        command('contact.suppress',company_id='company_one',kind='email',value='projects@northstar.example',reason='Actual fictional endpoint opt-out.',evidence='Fictional recipient statement.')
        assert not cli('handoff-check',data=handoff)['ready']
        assert not next(r for r in cli('query','cases')['items'] if r['id']=='case_one')['qualified']
        assert cli('query','case-history','--id','case_one')['items']==history
        historical=cli('query','selection','--id','packet_history','--version-id',prior['version_id']);assert historical['slots']==prior['slots'] and historical['review']==prior['review']
        assert cli('doctor')['healthy']
        result=dict(status='passed',release_id=new['release_id'],previous_archive_sha256=previous_sha,candidate_archive_sha256=candidate_sha,canonical_tables_unchanged_on_upgrade=len(before['tables']),revision_preserved_on_code_update=before['revision'],objects_and_historical_reviews_preserved=True,old_policy_stale=True,legacy_prefix_bug_stale_and_rejected=bool(unsafe_prefix),company_mailbox_positive=True,url_span_positive=True,equal_digit_outside_url_blocked=True,suppression_handoff_and_projection_consistent=True,history_pins_unchanged=True,no_host_helpers=True,external_actions=0,browser_opened=False)
    output.write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('previous_archive',type=Path);p.add_argument('candidate_archive',type=Path);p.add_argument('--previous-sha256',required=True);p.add_argument('--candidate-sha256',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(run(a.previous_archive,a.previous_sha256,a.candidate_archive,a.candidate_sha256,a.output),indent=2))
