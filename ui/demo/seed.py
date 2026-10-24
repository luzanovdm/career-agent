#!/usr/bin/env python3
"""Seed a separate fictional product-design workspace through the supported facade.

Usage: python3 ui/demo/seed.py REPOSITORY_ROOT NEW_DEMO_WORKSPACE
No research, messaging, networking, or real applicant data is used.
"""
import json
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(sys.argv[1]).resolve() / 'scripts'))
from career.repository import Repository
from career.facade import Tasks

root = Path(sys.argv[2]).absolute()
if root.exists():
    raise SystemExit('Choose a new dedicated fictional demo directory.')
Repository.initialize(root, 'Casey Example · Fictional demo', 'en')
tasks = Tasks(root)

def command(intent, **data):
    return tasks.command(dict(request_id=uuid4().hex, expected_revision=tasks.context()['revision'], intent=intent, input=data))

command('source.capture', id='career_source', locator='https://portfolio.example/casey',
        excerpt='Fictional demo career evidence: Casey Example led booking-flow research and redesigned a service onboarding journey. Casey facilitated cross-functional research workshops.',
        observed_at='2026-10-24T10:00:00Z', readable=True)
claims = [('claim_design', 'Led booking-flow research and redesigned a service onboarding journey.'),
          ('claim_research', 'Facilitated cross-functional research workshops.')]
for cid, assertion in claims:
    command('claim.save', id=cid, assertion=assertion, meaning=assertion, source_ids=['career_source'], confirmation='confirmed', disclosure='allowed')
for tid, name, positioning in [('track_design','Product design','Turn complex service journeys into clear, accessible experiences.'), ('track_research','UX research','Connect evidence from customer research to practical product decisions.')]:
    command('track.save', id=tid, name=name, positioning=positioning, selected=True, language='en', policies={'geography':{'state':'unknown'},'compensation':{'state':'unknown'}}, claim_ids=[c[0] for c in claims])
command('answer.save', id='answer_availability', meaning='availability.notice_period', scope={'track_id':'track_design'}, units={'period':'days'}, disposition='answered', value=30, evidence='Fictional demo applicant explicitly confirmed a 30-day notice period.')

companies = [
 ('Cedar Example Travel','Product designer','qualify'), ('Fern Example Care','Service designer','qualify'),
 ('Harbor Example Studio','Senior product designer','prepare'), ('Juniper Example Systems','UX researcher','prepare'),
 ('Lighthouse Example Health','Product designer','ready'), ('Meadow Example Learning','Design researcher','ready'),
 ('North Example Mobility','Service design lead','waiting'), ('Orchard Example Studio','Product design partner','waiting'),
 ('River Example Services','UX research consultant','response'), ('Solace Example Products','Product designer','response'),
 ('Tandem Example Collective','Experience designer','closed'), ('Willow Example Learning','Research facilitator','closed')]
for index, (company,title,column) in enumerate(companies):
    company_id,source_id,person_id,case_id,packet_id=[f'{kind}_{index:02d}' for kind in ('company','source','person','case','packet')]
    domain=f'{company.split()[0].lower()}.example'
    person=['Morgan','Riley','Taylor','Avery','Jordan','Quinn'][index%6]+' Example'
    command('source.capture', id=source_id, locator=f'https://{domain}/team', excerpt=f'Fictional demo company page: {person} leads the design or research team at {company}. The team works on service journeys.', observed_at='2026-10-24T10:00:00Z', readable=True)
    command('company.capture', id=company_id, name=company, domain=domain, source_ids=[source_id])
    command('contact.capture', id=person_id, name=person, company_id=company_id, affiliation='unknown' if column=='qualify' else 'current', relevance='Relevant design or research leader for the recorded opportunity.', sources=[dict(source_id=source_id,axes=['identity','affiliation','relevance'],assessment='unknown' if column=='qualify' else 'supports')], route=dict(kind='profile',value=f'https://{domain}/team/{person.split()[0].lower()}',source_id=source_id))
    tracks=[dict(id='track_design',rationale='The recorded service-design work connects to this product need.')]
    if index%2: tracks.append(dict(id='track_research',rationale='Research facilitation supports this team need.'))
    command('case.capture', id=case_id, company_id=company_id, title=title, kind='project' if index in (7,8) else 'vacancy', route='person', tracks=tracks, source_ids=[source_id], requisition=f'DEMO-{index:02d}', person_id=person_id)
    command('packet.create', id=packet_id, case_id=case_id, purpose='referral')
    resume='# Casey Example\nProduct designer · UX researcher\n\n## Selected experience\nLed booking-flow research and redesigned a service onboarding journey.\nFacilitated cross-functional research workshops.\n\n## Approach\nAccessible service journeys, research synthesis, and clear cross-functional decisions.\n\nFictional demonstration material.'
    message=f'Hello {person.split()[0]},\n\nYour team at {company} is a useful match for the service journeys I enjoy working on. I led booking-flow research and redesigned a service onboarding journey, and facilitated cross-functional research workshops.\n\nI am exploring the {title.lower()} opportunity. If this connects to your team’s current needs, would you be open to a short conversation about the work and the best route to an introduction?\n\nThank you,\nCasey Example\n\nFictional demonstration draft — no message has been sent.'
    interview='## Question\nHow do you turn an ambiguous customer problem into a design decision?\n\n## Answer outline\nUse the booking-flow research example. Explain the research question, what you personally did, and how findings shaped the onboarding journey. Keep outcomes limited to the source evidence.\n\n## Follow-up question\nHow did you work with engineering and operations?\n\n## Answer outline\nDescribe the cross-functional workshop and the decisions it supported. Do not invent conversion metrics.\n\n## Questions to ask the team\nWhich service journey needs attention first? How do research findings reach product planning?'
    documents=[dict(slot='resume',text=resume),dict(slot='message',text=message),dict(slot='dossier',text=f'Private: compare service-design evidence with {company} needs. Current role scope and working arrangement remain questions. This is fictional data.'),dict(slot='answers',text='## Confirmed fictional answer\nNotice period: 30 days, scoped to the product-design track.\n\n## Still unknown\nCompensation and geography have no confirmed answer. Employer consent is never reused.'),dict(slot='interview',text=interview)]
    inputs=dict(packet_id=packet_id,documents=documents,used_claim_ids=[c[0] for c in claims],answer_ids=['answer_availability'])
    if column not in ('qualify','prepare'):
        inputs['review']=dict(findings='Reviewed exact fictional claims, wording, and achievement coverage.',limitations='Demonstration evidence only; no real employer facts or actions.',claim_spans=[dict(claim_id=c[0],text=c[1]) for c in claims],tone_findings='Specific, professional request without invented familiarity.',coverage=[dict(claim_id=c[0],disposition='included') for c in claims])
    command('packet.save',**inputs)
    command('case.note',case_id=case_id,text='Private next step: confirm the team’s current scope before requesting an introduction. Keep evidence and applicant questions separate. Fictional demo only.')
    if column in ('waiting','response'):
        selection=tasks.query('selection',record_id=packet_id)
        command('activity.record',case_id=case_id,kind='sent',occurred_at='2026-10-22T11:00:00Z',evidence='Fictional scenario: the demo applicant reports a past manual message. No message was sent by this software.',packet_id=packet_id,version_id=selection['version_id'])
    if column=='response':
        command('activity.record',case_id=case_id,kind='human_reply',occurred_at='2026-10-23T14:00:00Z',evidence='Fictional scenario: the contact asked which service journey the applicant wants to work on. No real correspondence exists.')
    if column=='closed':
        command('case.close',case_id=case_id,reason='Fictional applicant chose a different focus.',evidence='Explicit fictional demo closure; this does not imply an employer rejection.')
print(json.dumps(dict(workspace=str(root),context=tasks.context(),fictional=True),indent=2))
