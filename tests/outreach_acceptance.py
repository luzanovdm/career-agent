#!/usr/bin/env python3
"""Exercise a staged bundle with fictional local inputs; never research or send."""
import argparse
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(bundle, *args):
    result = subprocess.run([sys.executable, '-B', str(bundle/'scripts/career_outreach.py'), *map(str,args)], cwd='/tmp', capture_output=True, text=True)
    if result.returncode: raise RuntimeError(result.stderr)
    return json.loads(result.stdout)


def write(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n');return path


def inputs(bundle, root):
    sys.path.insert(0,str(bundle/'scripts'))
    import career_state as cs
    cs.initialize_workspace(root/'Private')
    path=root/'Private/Data/state.json'; state=json.loads((ROOT/'tests/fixtures/synthetic-state.json').read_text())
    at=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    expires=(datetime.fromisoformat(at)+timedelta(days=14)).isoformat()
    state['sources'][0]['observations'].append({'at':at,'status':'not_applicable','primary':True,'evidence':'Fictional company page identifies Morgan Example as current API hiring owner and publishes owner@northstar-demo.example.'})
    state=cs.transact(path,lambda _:state,0)
    row={'id':'demo-contact','company_id':'company-a','person_key':'morgan-example','public_name':'Morgan Example','observed_role':'API Engineering Manager',
         'relevance':'Fictional current owner of the documented API role','opportunity_ids':['role-a'],'kind':'named_employee','endpoint':'owner@northstar-demo.example',
         'address_provenance':'published_professional','affiliation':'current','checked_at':at,'valid_until':expires,
         'confidence':{k:'unknown' if k=='delivery' else 'high' for k in ('identity','affiliation','relevance','address','delivery')},
         'provenance':[{'source_id':'source-a','url':state['sources'][0]['locator'],'checked_at':at,'evidence':'Fictional supplied professional page observation','purpose':p} for p in ('identity','affiliation','relevance','address')]}
    run(bundle,'contact',path,write(root/'contact.json',row),'--at',at,'--expected-revision',state['revision'],'--reason','Reviewed fictional supplied evidence')
    v={'sender':'applicant@example.org','provider':'synthetic-mail','delivery_revision':'1','template_revision':'1','stable_links':[],'attachment_revision':'1'}
    write(root/'variant.json',v)
    msg=EmailMessage();msg['From']='Alex Example <applicant@example.org>';msg['To']='receiver@example.net';msg['Subject']='Fictional representative diagnostic'
    msg.set_content('Implemented retry handling; the team reported USD 57000 annual savings. This is fictional test content.')
    (root/'outgoing.eml').write_bytes(msg.as_bytes())
    write(root/'action.json',{'id':'demo-diagnostic','idempotency_key':'demo-diagnostic','kind':'diagnostic','purpose':'diagnostic','mode':'diagnostic',
         'company_id':None,'opportunity_id':None,'contact_id':None,'reason':'Fictional representative receiving test, local ledger simulation only','source_ids':['source-a'],
         'service':'synthetic-receiver','data_classes':['message_headers','message_body']})
    (root/'Source.md').write_text('# Fictional supplied company evidence\n\nNorthstar Demo advertises the API Engineer role at https://northstar-demo.example/jobs/api-1. Morgan Example currently manages that team. The professional page publishes owner@northstar-demo.example. Source checked: '+at+'. All people, companies and addresses are fictional. No mailbox has been tested.\n')
    return path,at


def acceptance(bundle, root):
    path,at=inputs(bundle,root); state=json.loads(path.read_text());revision=state['revision']
    contact=run(bundle,'contact-check',path,'--id','demo-contact','--opportunity-id','role-a','--at',at)
    assert contact['usable'] and contact['confidence']['delivery']=='unknown'
    inspection=run(bundle,'inspect',root/'outgoing.eml',root/'variant.json')
    run(bundle,'prepare',path,root/'action.json','--payload',root/'outgoing.eml','--variant',root/'variant.json','--at',at,'--expected-revision',revision);revision+=1
    check=run(bundle,'check',path,'--id','demo-diagnostic','--at',at);assert check['permission_ids']==[]
    grant={'id':'demo-grant','mode':'one_time','max_uses':1,'valid_from':at,'valid_until':(datetime.fromisoformat(at)+timedelta(days=1)).isoformat(),
           'evidence':'Fictional user permission for this simulated test only; no external service call authorized',
           'scope':{'kind':'diagnostic','purpose':'diagnostic','sender':'applicant@example.org','provider':'synthetic-mail','service':'synthetic-receiver','recipient':'receiver@example.net',
                    'data_classes':['message_headers','message_body'],'payload_sha256':inspection['payload_sha256']}}
    run(bundle,'grant',path,write(root/'grant.json',grant),'--at',at,'--expected-revision',revision,'--user-confirmed');revision+=1
    for target in ('ready','dispatching','uncertain','sent'):
        row={'action_id':'demo-diagnostic','target':target,'evidence':'Fictional local transition; no actual send'}
        if target=='dispatching':row['permission_id']='demo-grant'
        if target=='sent':row['reconciliation']='Fictional provider message identity reconciled in isolated test'
        args=['transition',path,write(root/'transition.json',row),'--at',at,'--expected-revision',revision]
        if target=='dispatching':args+=['--payload',root/'outgoing.eml']
        result=run(bundle,*args);assert result['sends_performed']==0;revision+=1
        if target=='dispatching':
            assert result['dispatch_claimed']
            args[args.index('--expected-revision')+1]=revision
            replay=run(bundle,*args);assert not replay['dispatch_claimed']
    state=json.loads(path.read_text());sys.path.insert(0,str(bundle/'scripts'));import career_state as cs
    assert cs.stats(state,at)['counts']['sent_roles']==0
    assert run(bundle,'audit',path,'--at',at)['audit_complete']
    return {'status':'passed','contact_usable':True,'mailbox_status':'unknown','claim_replay_authorized':False,'uncertain_reconciled':True,'application_count':0,'external_sends':0,'bundle_files':len(json.loads((bundle/'BUNDLE.json').read_text())['files'])}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--stage-inputs',type=Path)
    args=parser.parse_args();bundle=args.bundle.resolve();manifest=json.loads((bundle/'BUNDLE.json').read_text())
    assert all(hashlib.sha256((bundle/name).read_bytes()).hexdigest()==sha for name,sha in manifest['files'].items()),'Staged bundle hash mismatch'
    with tempfile.TemporaryDirectory(prefix='career-outreach-acceptance-') as directory:
        result=acceptance(bundle,Path(directory))
    if args.stage_inputs:
        root=args.stage_inputs.resolve();root.mkdir(parents=True,exist_ok=False);path,at=inputs(bundle,root)
        write(root/'expected-evidence.json',{'contact':'demo-contact','mailbox_delivery':'unknown','external_sends':0,'no_permission_ids':True,'require_scripts':True,'no_campaign_count_change':True})
        (root/'fresh-chat-prompt.txt').write_text('Use career-agent from '+str(bundle)+'. This is a fictional learning example. My private workspace is '+str(path.parent.parent)+'. Supplied source: '+str(root/'Source.md')+'. I want to approach the API Engineer vacancy: assess a suitable contact, prepare a short first message, and inspect the representative email '+str(root/'outgoing.eml')+' with configuration '+str(root/'variant.json')+'. Work locally only: no sending, external services or internet research.\n')
        result['fresh_chat_inputs']=str(root);result['at']=at
    print(json.dumps(result,indent=2));return 0


if __name__=='__main__':sys.exit(main())
