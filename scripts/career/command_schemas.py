"""Bounded discoverable command schemas/examples, sharing the facade intent inventory."""
from .contracts import SCHEMAS,PROTOCOL,VERSION,require

TEXT=dict(type='string',maxLength=65536)
ID=dict(type='string',pattern='^[A-Za-z0-9_-]+$',minLength=1,maxLength=128)
IDS=dict(type='array',items=ID,maxItems=100,uniqueItems=True)
TIME=dict(type=['string','null'],description='ISO-8601 timestamp, or null when no expiry is asserted')


def obj(properties,required=None):return dict(type='object',properties=properties,required=list(properties) if required is None else required,additionalProperties=False)
def array(items,maximum=100):return dict(type='array',items=items,maxItems=maximum)
def enum(*values):return dict(enum=list(values))

def shapes():
    scope=dict(type='object',properties=dict(track_id=ID,track_ids=IDS,company_id=ID,case_id=ID,opportunity_id=ID,purpose=TEXT),additionalProperties=True,description='Known scope axes must match exactly. Unknown axes are retained as unresolved and cannot authorize reuse.')
    policy=obj(dict(state=enum('inherit','known','no_preference','unknown'),value={}),['state'])
    route=obj(dict(kind=enum('profile','email','form','website'),value=dict(type='string',maxLength=4096),source_id=ID))
    coverage=obj(dict(claim_id=ID,disposition=enum('included','condensed','private','excluded','pending'),reason=TEXT),['claim_id','disposition'])
    entity_span=dict(description='Exact Unicode offsets: an evidenced alphanumeric name, or a complete HTTP(S) URL equal to a scoped readable source locator. Unit-shaped names require independent mapped claim support; use an exact span, never a global entity_refs exception. URL digits grant no quantity authority outside that span.',oneOf=[obj(dict(slot=enum('resume','message','answers'),start=dict(type='integer',minimum=0),end=dict(type='integer',minimum=1),text=TEXT,source_id=ID)),obj(dict(slot=enum('resume','message','answers'),start=dict(type='integer',minimum=0),end=dict(type='integer',minimum=1),text=TEXT,company_id=ID))])
    editorial=obj(dict(argument=dict(type='string',minLength=1,maxLength=8192),decision=enum('approved','revise','pending'),findings=dict(type='string',minLength=1,maxLength=8192),binding=dict(type='string',pattern='^[a-f0-9]{64}$')))
    review=obj(dict(editorial=editorial,entity_refs=array(obj(dict(text=dict(type='string',minLength=2,maxLength=128),source_id=ID))),entity_spans=array(entity_span),answer_spans=array(obj(dict(answer_id=ID,text=TEXT))),findings=TEXT,limitations=TEXT,tone_findings=TEXT,claim_spans=array(obj(dict(claim_id=ID,text=TEXT))),coverage=array(coverage),base_coverage_version_id=ID),['findings','limitations','tone_findings','claim_spans','coverage'])
    unknown=obj(dict(code=TEXT,subject=TEXT,message=TEXT,source_ids=IDS))
    return dict(scope=scope,policy=policy,route=route,coverage=coverage,review=review,unknown=unknown)


def descriptions():
    return {
        'source.capture':'Save an actual readable observation or explicit unreadable-source state.',
        'claim.save':'Save verbatim assertion, interpreted meaning and source/disclosure evidence.',
        'track.save':'Save a career track and scoped policy overrides; explicit unknown does not inherit.',
        'answer.save':'Save a pending question or an actual scoped user response; they are distinct states.',
        'case.capture':'Capture exact opportunity identity and track rationale. Company mailbox route requires a personless case, canonical company domain and exact scoped public email evidence.',
        'contact.suppress':'Suppress one known exact endpoint with actual evidence. Specify exactly one person_id or company_id; scope is not sending permission.',
        'packet.create':'Create an alternative or first primary packet without replacing a later primary implicitly.',
        'packet.save':'Save all selected text slots as immutable bytes; review fields describe actual source/span checks.',
        'batch.save':'Persist original job_search goal or a linked preliminary quota, never replace the original goal.',
        'research.control':'Record an explicit scoped start, pause or revocation. There is no research.start command.',
        'activity.record':'Record actual externally observed activity; never send or infer an uncertain outcome.'}


def properties(intent):
    d=shapes();base={key:TEXT for key in SCHEMAS[intent][0]+SCHEMAS[intent][1]}
    for key in ('id','packet_id','person_id','company_id','case_id','version_id','source_version_id','parent_id','input_id','source_artifact_id','resolves_activity_id','related_activity_id'):
        if key in base:base[key]=ID
    for key in ('claim_ids','source_ids','used_claim_ids','answer_ids','track_ids','selected_ids'):
        if key in base:base[key]=IDS
    for key in ('valid_from','valid_until','expires_at','published_at'):
        if key in base:base[key]=TIME
    specific={
        'preferences.set':dict(theme=enum('system','light','dark'),ui_locale=dict(type='string',maxLength=64),introduction_shown=dict(type='boolean')),
        'locale.install':dict(locale=TEXT,plural_categories=array(TEXT,6),messages=dict(type='object',additionalProperties=dict(oneOf=[TEXT,dict(type='object',additionalProperties=TEXT)]))),
        'source.capture':dict(readable=dict(type='boolean'),excerpt=dict(type='string',maxLength=32768),supports={}),
        'claim.save':dict(confirmation=enum('confirmed','unconfirmed','unknown','disputed'),disclosure=enum('allowed','private','unknown','withdrawn'),contradicted=dict(type='boolean'),metrics=array({}),coverage_disposition=enum('included','condensed','private','excluded','pending')),
        'track.save':dict(selected=dict(type='boolean'),policies=dict(type='object',additionalProperties=d['policy'])),
        'answer.save':dict(scope=d['scope'],units=dict(type='object'),value={},disposition=enum('answered','pending','unknown','confidential','declined','no_preference','omit'),response_state=enum('pending','provided'),evidence=dict(type='string',minLength=1,maxLength=8192)),
        'contact.capture':dict(affiliation=enum('current','unknown','conflicting','former'),sources=array(obj(dict(source_id=ID,axes=array(enum('identity','affiliation','relevance'),3),assessment=enum('supports','conflicts','unknown')))),route=dict(oneOf=[dict(type='null'),d['route']]),track_rationales=array(obj(dict(track_id=ID,rationale=TEXT,source_ids=IDS)))),
        'case.capture':dict(kind=enum('vacancy','project','speculative'),route=enum('person','company','form','unknown'),company_route=obj(dict(kind=enum('email'),value=dict(type='string',maxLength=320),source_id=ID)),tracks=array(obj(dict(id=ID,rationale=TEXT))),essential_policy=enum('unknown','passed','failed'),essential_unknowns=array(d['unknown'],25)),
        'packet.create':dict(purpose=enum('application','referral','contact','interview')),
        'packet.save':dict(documents=array(obj(dict(slot=enum('resume','message','dossier','answers','interview','notes'),text=dict(type='string',minLength=1,maxLength=262144))),6),review=d['review']),
        'artifact.attach':dict(slot=enum('resume','message','dossier','answers','interview','notes'),extension=enum('docx','pdf')),
        'batch.save':dict(task=enum('job_search','research','search','contacts','packets','interview'),requested_count=dict(type='integer',minimum=1,maximum=100),count_unit=enum('cases','people'),required_outputs=array(enum('csv','xlsx','profile','snapshot'),4),budget={},predicate=obj(dict(kind=enum('qualified_people','evidenced_cases','prepared_cases'),essential_policy=enum('no_confirmed_failure','verified_pass')))),
        'activity.record':dict(message_sha256=dict(type='string',pattern='^[a-f0-9]{64}$'),kind=enum('sent','uncertain','not_sent','receipt','human_reply','interview','offer','rejection','bounce','withdrawal','referral_agreed','referral_performed','coverage'),coverage=dict(type='object'),channel=obj(dict(kind=enum('profile','email','form','website'),value=TEXT))),
        'permission.record':dict(scope=d['scope'],status=enum('active','revoked','declined'),one_time=dict(type='boolean')),
        'research.control':dict(status=enum('active','paused','revoked'),scope=obj(dict(track_ids=IDS,purpose=TEXT)))
    }
    base.update(specific.get(intent,{}));return base


def examples(intent):
    sample={
        'preferences.set':dict(theme='system',ui_locale='en'),
        'profile.update':dict(display_name='Alex Example',conversation_language='en'),
        'source.capture':dict(id='source_demo',locator='https://northstar.example/team',excerpt='Published team and role observation.',observed_at='2026-10-24T00:00:00Z',readable=True),
        'claim.save':dict(id='claim_demo',assertion='Improved processing by 25%.',meaning='Personally improved processing by 25%.',source_ids=['source_demo'],confirmation='confirmed',disclosure='allowed'),
        'track.save':dict(id='track_demo',name='Hospitality operations',positioning='Supported operations and training.',selected=True,language='en',policies=dict(location=dict(state='unknown')),claim_ids=['claim_demo']),
        'answer.save':dict(meaning='location.preference',scope=dict(track_id='track_demo',purpose='application'),units={},disposition='pending',value=None,evidence='Open question: what location is acceptable?',response_state='pending'),
        'company.capture':dict(id='company_demo',name='Northstar Demo',domain='northstar.example',source_ids=['source_demo']),
        'contact.capture':dict(id='person_demo',name='Morgan Example',company_id='company_demo',affiliation='current',relevance='Published relevant training role.',sources=[dict(source_id='source_demo',axes=['identity','affiliation','relevance'],assessment='supports')],route=dict(kind='profile',value='https://northstar.example/team/morgan',source_id='source_demo')),
        'contact.suppress':dict(person_id='person_demo',kind='email',value='morgan@northstar.example',reason='Known failed exact endpoint.',evidence='Actual fictional bounce observation.'),
        'case.capture':dict(id='case_demo',company_id='company_demo',title='Operations trainer',kind='vacancy',route='person',person_id='person_demo',requisition='REQ-42',tracks=[dict(id='track_demo',rationale='Supported operations training.')],source_ids=['source_demo'],essential_policy='unknown',essential_unknowns=[dict(code='REQUIRED_CERTIFICATE_UNKNOWN',subject='Required certificate',message='Certificate requirement needs confirmation.',source_ids=['source_demo'])]),
        'case.note':dict(case_id='case_demo',text='Private task note.'),
        'case.close':dict(case_id='case_demo',reason='User closed this case.',evidence='Actual user instruction.'),
        'case.reopen':dict(case_id='case_demo',reason='User reopened this case.'),
        'packet.create':dict(id='packet_demo',case_id='case_demo',purpose='application'),
        'packet.primary':dict(packet_id='packet_demo'),
        'packet.select':dict(packet_id='packet_demo',version_id='version_demo'),
        'packet.save':dict(packet_id='packet_demo',used_claim_ids=['claim_demo'],documents=[dict(slot=slot,text='Improved processing by 25%.' if slot=='resume' else 'Specific supported contribution and private preparation.') for slot in ('resume','message','dossier','interview')],review=dict(findings='Compared source meaning and actual selected wording.',limitations='Does not independently verify source truth.',tone_findings='Concrete professional wording.',claim_spans=[dict(claim_id='claim_demo',text='Improved processing by 25%.')],coverage=[dict(claim_id='claim_demo',disposition='included')])),
        'artifact.attach':dict(packet_id='packet_demo',slot='resume',input_id='input_demo',source_artifact_id='artifact_demo',extension='docx'),
        'batch.save':dict(id='job_demo',task='job_search',requested_count=4,count_unit='cases',track_ids=['track_demo'],criterion='Original ordinary job search with selected packets.',selected_ids=[],required_outputs=['xlsx']),
        'activity.record':dict(case_id='case_demo',kind='receipt',occurred_at='2026-10-24T00:00:00Z',evidence='Actual automatic provider receipt; no hiring progress inferred.'),
        'permission.record':dict(purpose='Exact employer agreement',scope=dict(company_id='company_demo',case_id='case_demo'),status='active',evidence='Actual exact user agreement instruction.',one_time=True),
        'research.control':dict(status='active',scope=dict(track_ids=['track_demo'],purpose='Find useful people and roles'),evidence='Explicit user start for this exact scope.')}
    if intent=='locale.install':return [] # Catalog must use this workspace's complete current English keyset.
    value=sample[intent];result=[value]
    if intent=='answer.save':result.append(dict(value,disposition='unknown',response_state='provided',evidence='User explicitly answered that they do not know.'))
    if intent=='batch.save':result.append(dict(value,id='research_demo',task='research',parent_id='job_demo',selected_ids=['case_demo'],criterion='Preliminary research within the original task.'))
    return result


def describe(intent=None):
    if intent in ('review-context','handoff-check'):
        document=obj(dict(slot=enum(*(('resume','message','answers') if intent=='handoff-check' else ('resume','message','answers','dossier','interview','notes'))),text=dict(type='string',minLength=1,maxLength=262144)))
        props=dict(packet_id=ID,documents=array(document,6))
        if intent=='review-context':props.update(used_claim_ids=IDS,answer_ids=IDS);required=['packet_id','documents','used_claim_ids']
        else:props.update(version_id=ID,recipient=obj(dict(kind=enum('profile','email','form','website'),value=TEXT)),artifacts=array(obj(dict(slot=enum('resume','message','answers'),artifact_id=ID)),6));required=['packet_id','version_id','documents']
        return dict(operation=intent,read_only=True,input_schema=obj(props,required),approval=False,description='Bound actual content/scope only; no prose scoring, permission or send. Actual handoff requires matching selected external payload and recipient.')
    if intent is None:
        return dict(protocol=PROTOCOL,version=VERSION,intents=[dict(intent=name,description=descriptions().get(name,'Bounded local domain operation; inspect schema '+name),required=required,optional=optional) for name,(required,optional) in SCHEMAS.items()],read_operations=['review-context','handoff-check'],workflow=dict(writing='Read claim_frontier; use context --claim-scope bank for evidence outside old links. Obtain review-context from actual final bytes, review facts and argument separately, then save editorial binding. handoff-check checks actual payload, never grants permission.',job_search='Create batch.save task=job_search, link preliminary batches with parent_id, assess the original root; child scope_complete is not original task_complete.',research='Use research.control only after an explicit scoped start.',questions='Use answer.save pending for unanswered questions; explicit unknown requires response_state provided.',readback='Use context cursors/exact IDs, selected deliver, and query assess for remaining_work.'),examples_note='Examples use fictional reference IDs; resolve actual IDs through context before applying.')
    require(intent in SCHEMAS,'UNKNOWN_INTENT','Unknown command intent; use schema without an intent for the catalog')
    required,optional=SCHEMAS[intent]
    result=dict(intent=intent,required=required,optional=optional,additional_properties=False,envelope=['request_id','expected_revision','intent','input'],input_schema=dict(**obj(properties(intent),required),**{'$schema':'https://json-schema.org/draft/2020-12/schema'}),examples=examples(intent),readback='Use the committed receipt, selected deliver and original query assess; examples grant no research/send permission.')

    if intent=='packet.save':
        from .interview import dialogue_schema
        result['document_formats']=dict(interview=dict(encoding='JSON serialized in documents[].text with slot interview; ordinary text remains a document',schema=dialogue_schema(),references='Only existing readable source observations; exact observed URLs, no automatic browsing'))
    return result
