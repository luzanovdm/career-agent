"""Evidence/byte bindings for model editorial judgments; no text scoring or sender."""
import json
import re
from .contracts import require,text,digest,issue,identifier,canonical

POLICY='career-agent.editorial/1'
EXTERNAL=frozenset(('resume','message','answers'))


def bank(snapshot,linked=()):
    """Small discovery projection of the existing claim bank, never another fact store."""
    if not hasattr(snapshot,'_editorial_bank'):
        claims=snapshot.rows("SELECT id,version FROM claims WHERE confirmation='confirmed' AND disclosure='allowed' AND contradicted=0 ORDER BY id")
        sources=snapshot.rows("SELECT cs.claim_id,s.id,s.version FROM claim_sources cs JOIN sources s ON s.id=cs.source_id JOIN claims c ON c.id=cs.claim_id WHERE c.confirmation='confirmed' AND c.disclosure='allowed' AND c.contradicted=0 ORDER BY cs.claim_id,s.id")
        token=digest(dict(claims=[[c['id'],c['version']] for c in claims],sources=[[s['claim_id'],s['id'],s['version']] for s in sources]))
        snapshot._editorial_bank=(claims,token)
    claims,token=snapshot._editorial_bank;linked=set(linked);outside=[c for c in claims if c['id'] not in linked]
    preview=snapshot.rows("SELECT id,version,substr(assertion,1,240) AS assertion_excerpt FROM claims WHERE id IN(SELECT value FROM json_each(?)) ORDER BY id",(json.dumps([c['id'] for c in outside[:5]]),))
    return dict(token=token,total=len(claims),outside_linked_context=len(outside),preview=preview,read_more='context --task profile --claim-scope bank; follow next_cursor, then exact --claim-id/--source-id',meaning='Candidate evidence, not automatically relevant or approved prose. A bank change requires reconsideration, not automatic inclusion.')


def document_hashes(documents):
    require(isinstance(documents,list) and 1<=len(documents)<=6,'INVALID_INPUT','Review context needs 1..6 actual documents')
    hashes={}
    for document in documents:
        require(isinstance(document,dict) and set(document)=={'slot','text'} and isinstance(document['slot'],str) and document['slot'] in EXTERNAL|{'dossier','interview','notes'},'INVALID_INPUT','Document requires declared slot/text')
        require(document['slot'] not in hashes,'INVALID_INPUT','Duplicate document slot');text(document['text'],'document text',262144)
        hashes[document['slot']]=digest(document['text'].encode())
    return {name:value for name,value in hashes.items() if name in EXTERNAL}


def selected_hashes(snapshot,version_id):
    """Verified conversion receipts preserve reviewed source text; payload hashes stay separate."""
    hashes={}
    for slot in snapshot.rows('SELECT * FROM slots WHERE version_id=?',(version_id,)):
        if slot['name'] not in EXTERNAL:continue
        artifact=snapshot.get('object',slot['artifact_id'])
        receipt=snapshot.one('SELECT source_artifact_id FROM extraction_receipts WHERE artifact_id=? AND binary_hash=?',(artifact['id'],artifact['sha256']))
        hashes[slot['name']]=snapshot.get('object',receipt['source_artifact_id'])['sha256'] if receipt else artifact['sha256']
    return hashes


def binding(snapshot,packet_id,hashes,claim_ids,answer_ids=()):
    packet=snapshot.get('packet',packet_id);case=snapshot.get('case',packet['case_id']);company=snapshot.get('company',case['company_id']);person=snapshot.get('person',packet['person_id']) if packet['person_id'] else None
    detail=json.loads(case['detail']);claims=[snapshot.get('claim',cid) for cid in sorted(set(claim_ids))]
    source_ids=set(detail.get('source_ids',[]))
    if person:source_ids.update(o['source_id'] for o in json.loads(person['detail']).get('sources',[]))
    for claim in claims:source_ids.update(row['source_id'] for row in snapshot.rows('SELECT source_id FROM claim_sources WHERE claim_id=?',(claim['id'],)))
    answers={a['id']:a for a in [*[snapshot.get('answer',aid) for aid in answer_ids],*snapshot.applicable_answers(case['id'])]}
    tracks=snapshot.rows('SELECT t.id,t.version FROM tracks t JOIN case_tracks ct ON ct.track_id=t.id WHERE ct.case_id=? ORDER BY t.id',(case['id'],))
    writing=[]
    for answer in snapshot.rows("SELECT * FROM answers WHERE meaning LIKE 'writing.%' ORDER BY id"):
        public=snapshot.public_answer(answer,[t['id'] for t in tracks],case)
        if public['reusable_here']:writing.append([answer['id'],answer['version']])
    scope=dict(writing_answers=writing,policy=POLICY,packet_id=packet_id,case_id=case['id'],case_semantic_version=detail.get('semantic_version',1),person=[person['id'],person['version']] if person else None,company=[company['id'],company['version']],purpose=packet['purpose'],tracks=[[t['id'],t['version']] for t in tracks],claims=[[c['id'],c['version']] for c in claims],answers=sorted([a['id'],a['version']] for a in answers.values()),sources=[[sid,snapshot.get('source',sid)['version']] for sid in sorted(source_ids)],candidate_bank_token=bank(snapshot)['token'],external_hashes=hashes)
    return dict(policy=POLICY,binding=digest(scope),scope=scope,approval=False,meaning='Binds exact content and evidence scope only; does not perform factual/editorial review or grant sending permission.')


def context(snapshot,data):
    require(isinstance(data,dict) and {'packet_id','documents','used_claim_ids'}<=set(data)<= {'packet_id','documents','used_claim_ids','answer_ids'},'INVALID_INPUT','Review context requires packet_id/documents/used_claim_ids and optional answer_ids')
    require(len(canonical(data).encode())<=1024*1024,'LIMIT_EXCEEDED','Review context exceeds 1 MiB');identifier(data['packet_id'])
    for key in ('used_claim_ids','answer_ids'):
        require(isinstance(data.get(key,[]),list) and len(data.get(key,[]))<=100,'INVALID_INPUT','Bounded reference IDs required')
        for value in data.get(key,[]):identifier(value)
    result=binding(snapshot,data['packet_id'],document_hashes(data['documents']),data['used_claim_ids'],data.get('answer_ids',[]))
    return snapshot.envelope(**result,claim_frontier=bank(snapshot,data['used_claim_ids']))


def assess(review,expected,has_message):
    if not has_message:return dict(status='not_applicable',issues=[])
    value=review.get('editorial') if review else None
    if value is None:return dict(status='not_recorded',issues=[issue('EDITORIAL_REVIEW_REQUIRED','Message needs a separate argument/meaning review of its exact content')])
    require(isinstance(value,dict) and set(value)=={'argument','decision','findings','binding'},'INVALID_REVIEW','Editorial review needs argument/decision/findings/binding')
    for key in ('argument','findings'):text(value[key],'editorial '+key,8192)
    require(value['decision'] in ('approved','revise','pending'),'INVALID_REVIEW','Unknown editorial decision')
    require(isinstance(value['binding'],str) and re.fullmatch('[a-f0-9]{64}',value['binding']),'INVALID_REVIEW','Editorial binding must be the actual review-context fingerprint')
    if value['binding']!=expected['binding']:return dict(status='stale',issues=[issue('EDITORIAL_BINDING_CHANGED','Text, recipient, selected evidence or candidate bank changed; do not rehash an old approval')])
    if value['decision']!='approved':return dict(status=value['decision'],issues=[issue('EDITORIAL_REVISION_REQUIRED','Actual editorial review is pending or requests revision')])
    return dict(status='approved',issues=[])


def handoff(snapshot,data):
    require(isinstance(data,dict) and {'packet_id','version_id','documents'}<=set(data)<= {'packet_id','version_id','documents','recipient','artifacts'},'INVALID_INPUT','Handoff check requires exact packet/version and actual final external documents')
    require(len(canonical(data).encode())<=1024*1024,'LIMIT_EXCEEDED','Handoff exceeds 1 MiB');identifier(data['packet_id']);identifier(data['version_id'])
    require(isinstance(data['documents'],list) and len(data['documents'])<=6,'INVALID_INPUT','Actual external documents must be a bounded list')
    require(all(isinstance(d,dict) and isinstance(d.get('slot'),str) and d['slot'] in EXTERNAL for d in data['documents']),'PRIVATE_PAYLOAD','Only declared external documents may enter an outgoing payload')
    selection=snapshot.selection(data['packet_id']);hashes=document_hashes(data['documents']) if data['documents'] else {};expected={s['name']:s['sha256'] for s in selection['slots'] if s['name'] in EXTERNAL};issues=list(selection['assessment']['issues'])
    if selection['delivery']['retry_blocked']:issues.append(dict(code='HANDOFF_OUTCOME_UNCERTAIN',message='Resolve the actual uncertain outcome before another external transmission',unresolved_activity_ids=selection['delivery']['unresolved_activity_ids']))
    artifacts=data.get('artifacts',[]);require(isinstance(artifacts,list) and len(artifacts)<=6,'INVALID_INPUT','Bounded selected artifact references required')
    selected_slots={s['name']:s for s in selection['slots']}
    for artifact in artifacts:
        require(isinstance(artifact,dict) and set(artifact)=={'slot','artifact_id'} and isinstance(artifact['slot'],str) and artifact['slot'] in EXTERNAL and artifact['slot'] not in hashes,'INVALID_INPUT','Selected external artifact requires unique slot/artifact_id')
        identifier(artifact['artifact_id']);record,_=snapshot.object(artifact['artifact_id']);slot=selected_slots.get(artifact['slot'])
        if not slot or slot['artifact_id']!=artifact['artifact_id']:issues.append(issue('HANDOFF_PAYLOAD_MISMATCH','Actual attachment differs from the selected artifact'))
        hashes[artifact['slot']]=record['sha256']
    if selection['version_id']!=data['version_id']:issues.append(issue('HANDOFF_SELECTION_CHANGED','Selected version changed before handoff'))
    if 'message' in expected and 'message' not in hashes:issues.append(issue('HANDOFF_PAYLOAD_MISMATCH','Final message payload is missing'))
    if not expected or not hashes or hashes!=expected:issues.append(issue('HANDOFF_PAYLOAD_MISMATCH','Actual final payload differs from the reviewed selected bytes'))
    if data.get('recipient') is None:issues.append(issue('HANDOFF_RECIPIENT_MISMATCH','Actual intended recipient is required before handoff'))
    if data.get('recipient') is not None:
        recipient=data['recipient'];require(isinstance(recipient,dict) and set(recipient)=={'kind','value'},'INVALID_INPUT','Recipient needs exact kind/value')
        route=selection['selected_route']
        matches=route and route['qualified'] and recipient=={k:route.get(k) for k in ('kind','value')}
        if not matches:issues.append(issue('HANDOFF_RECIPIENT_MISMATCH','Final recipient differs from the evidenced selected route'))
    return snapshot.envelope(outcome='partial' if issues else 'satisfied',ready=not issues,packet_id=data['packet_id'],version_id=data['version_id'],payload_sha256=digest(dict(packet_id=data['packet_id'],version_id=data['version_id'],recipient=data.get('recipient'),external_hashes=hashes)),recipient=data.get('recipient'),message_sha256=hashes.get('message'),external_hashes=hashes,issues=issues,permission_granted=False,external_actions={'performed':0})
