#!/usr/bin/env python3
"""Create one clearly fictional, reproducible screenshot workspace via Tasks.

Usage: python3 seed_stories.py REPOSITORY_ROOT NEW_WORKSPACE PERSONA
PERSONA: designer, makeup, analyst, hospitality. Never modifies an existing path.
All source assertions, past-action reports, replies, and interviews are invented
scenario fixtures, explicitly labeled as such. No networking or sending occurs.
"""
import json
from pathlib import Path
import sys
from uuid import uuid4

repository_root, destination, persona = sys.argv[1:]
sys.path.insert(0, str(Path(repository_root).resolve() / "scripts"))
from career.repository import Repository
from career.facade import Tasks

story = json.loads(Path(__file__).with_name("stories.json").read_text())[persona]
root = Path(destination).absolute()
if root.exists():
    raise SystemExit("Choose a new, dedicated fictional demo workspace.")
Repository.initialize(root, story["name"] + " · Fictional demo", "en")
tasks = Tasks(root)
receipts = []


def command(intent, **data):
    receipt = tasks.command(dict(request_id=uuid4().hex,
                                expected_revision=tasks.context()["revision"],
                                intent=intent, input=data))
    assert receipt["external_actions"]["performed"] == 0
    receipts.append(receipt)
    return receipt


claim_ids = ["claim_" + str(index) for index in range(len(story["claims"]))]
command("source.capture", id="career_source",
        locator=f"https://portfolio.example/{persona}",
        excerpt="Fictional demonstration career evidence. " + story["experience"]
        + " " + " ".join(story["claims"]) + " " + story["skills"],
        observed_at="2026-10-24T09:00:00Z", readable=True)
for claim_id, assertion in zip(claim_ids, story["claims"]):
    command("claim.save", id=claim_id, assertion=assertion, meaning=assertion,
            source_ids=["career_source"], confirmation="confirmed", disclosure="allowed")
for track in story["tracks"]:
    command("track.save", id="track_" + track["id"], name=track["name"],
            positioning=track["positioning"], selected=True, language="en",
            claim_ids=claim_ids, policies={"geography": {"state": "unknown"},
                                         "compensation": {"state": "unknown"}})
command("answer.save", id="answer_notice", meaning="availability.notice_period",
        scope={"track_id": "track_" + story["tracks"][0]["id"]},
        units={"period": "days"}, disposition="answered", value=30,
        evidence="Fictional applicant explicitly confirmed 30 days; not employer consent.")
command("answer.save", id="answer_portfolio", meaning="portfolio.disclosure",
        scope={"track_id": "track_" + story["tracks"][1]["id"]}, units={},
        disposition="answered", value="Share only the approved fictional portfolio excerpt.",
        evidence="Fictional applicant choice; no private client material or reusable employer consent.")

stages = ["qualify", "qualify", "prepare", "prepare", "ready", "ready",
          "waiting", "waiting", "response", "response", "closed", "closed"]
for index, (company, title, stage) in enumerate(zip(story["companies"], story["roles"], stages)):
    company_id, source_id, person_id, case_id, packet_id = [
        f"{kind}_{index:02d}" for kind in ("company", "source", "person", "case", "packet")]
    domain = f"{persona}-{company.split()[0].lower()}.example"
    first_name = ["Morgan", "Riley", "Avery", "Jordan", "Quinn", "Drew",
                  "Alex", "Rowan", "Ellis", "Skyler", "Parker", "Reese"][index]
    person = first_name + " " + company.split()[0] + " Example"
    track = story["tracks"][index % 2]
    relevance = f"Published team lead for {track['name'].lower()}; relevant to {story['need']}."
    provisional = stage == "qualify"
    excerpt = (f"Fictional company page: {person} is listed for {company}. "
               + ("The date and current affiliation remain unconfirmed. " if provisional else
                  f"The current team directory identifies this person as the {track['name'].lower()} team lead. ")
               + f"The fictional opportunity is {title}; the team is exploring {story['need']}. "
               "No real vacancy, personal relationship, or willingness to refer is asserted.")
    command("source.capture", id=source_id, locator=f"https://{domain}/team",
            excerpt=excerpt, observed_at="2026-10-24T10:00:00Z", readable=True)
    command("company.capture", id=company_id, name=company, domain=domain, source_ids=[source_id])
    command("contact.capture", id=person_id, name=person, company_id=company_id,
            affiliation="unknown" if provisional else "current", relevance=relevance,
            relationship="No personal relationship established; fictional directory evidence only.",
            sources=[dict(source_id=source_id, axes=["identity", "affiliation", "relevance"],
                          assessment="unknown" if provisional else "supports")],
            route=dict(kind="profile", value=f"https://{domain}/team/{first_name.lower()}", source_id=source_id))
    tracks = [dict(id="track_" + track["id"], rationale=track["positioning"])]
    if index in (4, 8):
        other = story["tracks"][(index + 1) % 2]
        tracks.append(dict(id="track_" + other["id"], rationale="The same opportunity also uses this supported contribution; one shared case."))
    command("case.capture", id=case_id, company_id=company_id, title=title,
            kind="project" if index in (3, 8) else "speculative" if index == 1 else "vacancy",
            route="person", tracks=tracks, source_ids=[source_id],
            requisition=f"FICTIONAL-{persona.upper()}-{index:02d}", person_id=person_id)
    command("packet.create", id=packet_id, case_id=case_id, purpose="referral")
    resume = (f"# {story['name']}\n{story['headline']}\n\n## Experience\n{story['experience']}\n\n"
              + "## Selected contributions\n" + "\n".join("- " + claim for claim in story["claims"])
              + f"\n\n## Working strengths\n{story['skills']}\n\n## This opportunity\n{track['positioning']}\n\n"
                "Fictional demonstration resume. No real employment or credential is represented.")
    message = (f"Hello {first_name},\n\nThe {title.lower()} work at {company} caught my attention because your fictional team page describes {story['need']}.\n\n"
               + " ".join(story["claims"][:2])
               + f" This is the experience I would bring to the {track['name'].lower()} work.\n\n"
                 "If that experience connects to your team's current priorities, would you be open to a short conversation about the work and the appropriate route to an introduction? I would first like to understand the scope and the team's expectations.\n\n"
               + f"Thank you,\n{story['name']}\n\nFictional demonstration draft. This application has no sending function.")
    dossier = (f"# Private working dossier\n\n## Why this person\n{relevance}\n\n## Evidence\n{excerpt}\n\n"
               "## Unknowns\nCurrent budget, working arrangements, decision owner, and willingness to introduce are unknown. Published relevance is not a personal referral.\n\n"
               "## Next conversation\n" + story["team_question"]
               + "\n\n## Disclosure\nUse only approved fictional career claims. Do not expose private availability or client details. All records in this workspace are fictional.")
    answers = ("# Saved applicant answers\n\nNotice period: thirty days, explicitly confirmed for the first career track.\n"
               "Portfolio: share only the approved fictional excerpt, scoped to the second track.\n"
               "Compensation and geography: unknown. Ask only when consequential.\n"
               "Consent: no employer-specific agreement is recorded or reusable.\n\nFictional demonstration answers.")
    interview = ("Fictional interview preparation — saved material, not an active practice session.\n\n"
                 + "INTERVIEWER\n" + story["story_question"] + "\n\nAPPLICANT OUTLINE\n" + story["story_answer"]
                 + "\n\nFOLLOW-UP\nWhat was your personal responsibility, and what remains uncertain?\n\n"
                   "APPLICANT OUTLINE\nSeparate my recorded contribution from the team's work. Preserve the original numbers and explain their scope. Say when a result was not measured.\n\n"
                   "QUESTIONS FOR THE TEAM\n" + story["team_question"]
                 + "\n\nLOGISTICS\n" + ("Simulated interview: 27 October, 14:00 UTC, 30 minutes. Fictional scenario only; no real invitation or calendar event exists." if index == 9 else "No actual interview is scheduled. No practice session has started."))
    documents = [dict(slot=slot, text=text) for slot, text in (
        ("resume", resume), ("message", message), ("dossier", dossier), ("answers", answers), ("interview", interview))]
    save_input = dict(packet_id=packet_id, documents=documents, used_claim_ids=claim_ids,
                      answer_ids=["answer_notice", "answer_portfolio"])
    if stage not in ("qualify", "prepare"):
        save_input["review"] = dict(
            findings="Reviewed these exact fictional document bytes against the fictional source, attribution, numbers, disclosure, contact evidence, and retained achievement coverage.",
            limitations="Scenario fixture only, not verification of a real candidate or employer. No conversion, revenue, satisfaction, or hiring outcome is asserted.",
            claim_spans=[dict(claim_id=cid, text=claim) for cid, claim in zip(claim_ids, story["claims"])],
            tone_findings="Specific, calm professional request; no invented familiarity, guaranteed referral, or unsupported outcome.",
            coverage=[dict(claim_id=cid, disposition="included") for cid in claim_ids])
    command("packet.save", **save_input)
    command("case.note", case_id=case_id,
            text=f"Private next step: {story['team_question']}\nKeep the two career tracks connected through this exact opportunity, while preserving distinct positioning. Do not treat a published contact as an agreed referral. Fictional demo only.")
    if stage in ("waiting", "response"):
        selection = tasks.query("selection", record_id=packet_id)
        command("activity.record", case_id=case_id, kind="sent", occurred_at="2026-10-21T11:00:00Z",
                evidence="FICTIONAL SCENARIO: applicant reports a past manual introduction request using the pinned demo material. No transmission occurred; this software sent nothing.",
                packet_id=packet_id, version_id=selection["version_id"])
    if stage == "waiting" and index == 7:
        command("activity.record", case_id=case_id, kind="receipt", occurred_at="2026-10-21T11:01:00Z",
                evidence="FICTIONAL SCENARIO: receipt-only acknowledgment. It is not human engagement or hiring progress. No real delivery or correspondence exists.")
    if stage == "response":
        command("activity.record", case_id=case_id, kind="human_reply", occurred_at="2026-10-23T14:00:00Z",
                evidence=f"FICTIONAL EMPLOYER REPLY from {person}: 'Thank you for the specific introduction. Could you describe your personal contribution and which part of our {track['name'].lower()} work you would like to explore?' This is authored scenario text, not real correspondence.")
        if index == 9:
            command("activity.record", case_id=case_id, kind="interview", occurred_at="2026-10-23T15:00:00Z",
                    evidence="FICTIONAL INTERVIEW INVITATION: 27 October, 14:00 UTC, 30 minutes with the team lead; discuss the saved evidence story and questions. No real invitation, calendar event, or employer communication exists.")
    if stage == "closed":
        command("case.close", case_id=case_id, reason="Fictional applicant chose a different focus." if index == 10 else "Fictional project timing does not match the applicant's current plan.",
                evidence="Explicit fictional applicant decision. It does not imply employer rejection or transmission.")

board = tasks.query("board", limit=50, closed=True)
expected = {stage: 2 for stage in set(stages)}
assert board["counts"]["columns"] == expected, board["counts"]
assert tasks.context()["research"]["status"] != "active"
for index in range(12):
    detail = tasks.query("case", record_id=f"case_{index:02d}")
    assert len(detail["selection"]["slots"]) == 5
    assert len(detail["selection"]["used_claim_ids"]) == 3
    assert len(detail["selection"]["answer_ids"]) == 2
manifest = dict(format="career-agent.fictional-story/1", persona=persona, fictional=True,
                workspace=str(root), profile=story["name"], tracks=2, companies=12, contacts=12,
                cases=12, columns=board["counts"]["columns"], claims=3, answers=2,
                document_slots=5, command_count=len(receipts), external_actions=0,
                research=tasks.context()["research"]["status"], revision=tasks.context()["revision"])
(root / "fictional-demo-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps(manifest, indent=2))
