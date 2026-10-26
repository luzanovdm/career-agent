"""Installed contact-policy upgrade using a caller-supplied private document.

No document bytes, applicant facts or local document paths belong in source fixtures.
All operations use installed CLI commands; no SQL, sending or live workspace access.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile
from installed_numeric_policy_upgrade import verify_archive


def run(previous,previous_sha,candidate,candidate_sha,document,document_sha,output):
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assert digest(document)==document_sha
    old=verify_archive(previous,previous_sha);new=verify_archive(candidate,candidate_sha)
    assert old['version']=='1.0.5' and new['version']=='1.0.6'
    extractor=shutil.which('pdftotext');assert extractor,'Host Poppler is required by the existing PDF contract'
    extracted=subprocess.check_output([extractor,'-enc','UTF-8',str(document),'-']).decode('utf-8')
    with tempfile.TemporaryDirectory(prefix='career-contact-upgrade-',dir='/tmp') as temporary:
        parent=Path(temporary);stage=parent/'previous';stage.mkdir();workspace=parent/'workspace'
        subprocess.run(['/usr/bin/unzip','-q',str(previous),'-d',str(stage)],check=True)
        env=dict(os.environ,PATH=str(Path(extractor).parent)+':/usr/bin:/bin',PYTHONPATH='/nonexistent');env.pop('CAREER_AGENT_DEVELOPMENT',None)
        boot=subprocess.run([str(stage/old['python_executable']),'-I','-B',str(stage/'bin/bootstrap.py'),str(previous),'--workspace',str(workspace),'--sha256',previous_sha,'--name','Private artifact verification','--ui-locale','en'],env=env,capture_output=True,text=True,timeout=60)
        assert boot.returncode==0,boot.stderr
        launcher=workspace/'.career-agent/career';serial=0
        def cli(*args,data=None,allowed=(0,3)):
            r=subprocess.run([str(launcher),*args],input=json.dumps(data) if data is not None else None,env=env,cwd=parent,capture_output=True,text=True,timeout=90)
            assert r.returncode in allowed,(args,r.returncode,r.stderr[:1000])
            return json.loads(r.stdout or r.stderr)
        def command(intent,allowed=(0,3),**data):
            nonlocal serial
            serial+=1
            return cli('command',data=dict(request_id='contact_fixture_'+str(serial),expected_revision=cli('context')['revision'],intent=intent,input=data),allowed=allowed)
        command('source.capture',id='source_one',locator='https://northstar.example/project',excerpt='A fictional project for private artifact verification, not applicant fact confirmation.',observed_at='2026-10-26T00:00:00Z',readable=True)
        command('track.save',id='track_one',name='Artifact check',positioning='No applicant claims adopted.',selected=True,language='en',policies={})
        command('company.capture',id='company_one',name='Northstar Demo',domain='northstar.example')
        command('case.capture',id='case_one',company_id='company_one',title='Private artifact check',kind='project',route='unknown',canonical_url='https://northstar.example/project',tracks=[dict(id='track_one',rationale='Verify attachment mechanics only.')],source_ids=['source_one'])
        command('packet.create',id='packet_one',case_id='case_one',purpose='contact')
        command('answer.save',meaning='contact.phone.preference',scope={},units={},disposition='answered',value=dict(disposition='omit',value=None),evidence='Explicit omission in the isolated regression.')
        saved=command('packet.save',packet_id='packet_one',documents=[dict(slot='resume',text=extracted)],used_claim_ids=[],review=dict(findings='Attachment mechanism only; no applicant claims adopted.',limitations='Actual numerical facts remain unresolved, never approved by this fixture.',tone_findings='No text rewritten.',claim_spans=[],coverage=[]))
        assert 'CONTACT_DISCLOSURE_BLOCKED' in {i['code'] for i in saved['issues']}
        selected=cli('deliver','packet_one');staged=cli('stage',str(document));assert staged['sha256']==document_sha
        attach=dict(packet_id='packet_one',slot='resume',input_id=staged['input_id'],source_artifact_id=selected['slots'][0]['artifact_id'],extension='pdf')
        before=cli('context');versions=cli('query','versions','--id','packet_one');history=cli('query','case-history','--id','case_one')
        old_failure=command('artifact.attach',allowed=(2,),**attach);assert old_failure['error']['code']=='CONTACT_DISCLOSURE_BLOCKED'
        assert cli('context')['revision']==before['revision'] and cli('deliver','packet_one')['version_id']==selected['version_id']
        assert cli('app','update','--archive',str(candidate),'--sha256',candidate_sha)['release_id']==new['release_id']
        current=cli('deliver','packet_one');assert cli('context')['revision']==before['revision']
        assert current['slots']==selected['slots'] and current['version_id']==selected['version_id'] and current['review']==selected['review']
        assert 'CONTACT_DISCLOSURE_BLOCKED' not in {i['code'] for i in current['assessment']['issues']}
        assert not current['assessment']['prepared'] and 'UNMATCHED_NUMBER' in {i['code'] for i in current['assessment']['issues']}
        assert cli('query','versions','--id','packet_one')==versions and cli('query','case-history','--id','case_one')==history
        assert 'CONTACT_DISCLOSURE_BLOCKED' not in {i['code'] for i in cli('query','cases')['items'][0]['blockers']}
        command('artifact.attach',**attach);attached=cli('deliver','packet_one');assert attached['slots'][0]['sha256']==document_sha
        assert not attached['assessment']['prepared'] and 'CONTACT_DISCLOSURE_BLOCKED' not in {i['code'] for i in attached['assessment']['issues']}
        phone='Phone: +1 202 555 0142';command('packet.save',packet_id='packet_one',documents=[dict(slot='resume',text=phone)],used_claim_ids=[])
        source=cli('deliver','packet_one');stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>'+phone+'</w:t></w:r></w:p></w:document>')
        path=parent/'fictional-phone.docx';path.write_bytes(stream.getvalue());phone_input=cli('stage',str(path));revision=cli('context')['revision']
        failure=command('artifact.attach',allowed=(2,),packet_id='packet_one',slot='resume',input_id=phone_input['input_id'],source_artifact_id=source['slots'][0]['artifact_id'],extension='docx')
        assert failure['error']['code']=='CONTACT_DISCLOSURE_BLOCKED' and failure['error']['issues'][0]['slot']=='resume'
        assert cli('context')['revision']==revision and cli('deliver','packet_one')['version_id']==source['version_id'] and cli('doctor')['healthy']
        assert digest(document)==document_sha
        result=dict(status='passed',release_id=new['release_id'],previous_archive_sha256=previous_sha,candidate_archive_sha256=candidate_sha,private_document_sha256=document_sha,private_document_bytes=document.stat().st_size,original_document_unchanged=True,old_false_positive_reproduced=True,old_versions_and_source_bytes_preserved_on_update=True,old_contact_finding_rechecked_without_rewriting_review=True,exact_approved_pdf_attached=True,other_review_blocks_preserved=True,true_phone_rejected_atomically_with_structured_location=True,no_direct_sql=True,live_workspace_touched=False,external_actions=0,browser_opened=False)
    output.write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('previous_archive',type=Path);p.add_argument('candidate_archive',type=Path);p.add_argument('--previous-sha256',required=True);p.add_argument('--candidate-sha256',required=True);p.add_argument('--document',type=Path,required=True);p.add_argument('--document-sha256',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(run(a.previous_archive,a.previous_sha256,a.candidate_archive,a.candidate_sha256,a.document,a.document_sha256,a.output),indent=2))
