"""Synthetic current-contact selection, historical evidence and one-time clarification."""
import copy
from pathlib import Path
import tempfile
import unittest
from test_state import AT, LATER, answer
from test_search_cases import configured, request
from workflow_fixtures import baseline_audit
import career_state as cs
import career_search as search
import career_materials as materials

OLD="+1 202 555 0100"
CURRENT="+1 202 555 0199"


def preference(value=OLD,disposition="use",identifier="phone-old",at=AT):
    row=answer(identifier=identifier,meaning="contact.phone.preference",scope={"purpose":"application"},value={"disposition":disposition,"value":value},confirmed_at=at,valid_from=at)
    row["units"]={}
    return row


class ContactPreferenceTests(unittest.TestCase):
    def test_historical_phone_does_not_establish_preference_or_invent_replacement(self):
        state=configured();check=materials.review_phone(state,["# Alex Demo\n"+OLD],at=AT)
        self.assertFalse(check["ready"]);self.assertTrue(check["question_needed"])
        self.assertTrue(materials.review_phone(state,["# Alex Demo\nNo phone supplied"],at=AT)["ready"])
        state=cs.add_record(state,"answers",preference(None,"unknown"))
        check=materials.review_phone(state,[OLD],at=AT);self.assertFalse(check["ready"]);self.assertFalse(check["question_needed"])

    def test_newer_choice_supersedes_old_cv_contact_and_valid_phone_is_preserved(self):
        state=cs.add_record(configured(),"answers",preference())
        self.assertTrue(materials.review_phone(state,[OLD],at=AT)["ready"])
        replacement=preference(CURRENT,identifier="phone-current",at=LATER)
        state=cs.reviewed_update(state,{"operation":"supersede_answer","answer_id":"phone-old","replacement":replacement},"User selected a different application contact")
        self.assertFalse(materials.review_phone(state,[OLD],at=LATER)["ready"])
        self.assertTrue(materials.review_phone(state,[CURRENT],at=LATER)["ready"])
        self.assertTrue(materials.review_phone(state,[OLD],at=AT)["ready"])
        self.assertEqual(state["answers"][0]["value"]["value"],OLD)

    def test_explicit_omit_rejects_visible_old_number_and_cached_unknown_does_not_reask(self):
        state=cs.add_record(configured(),"answers",preference(None,"omit"))
        check=materials.review_phone(state,[OLD],at=AT);self.assertFalse(check["ready"]);self.assertFalse(check["question_needed"])
        self.assertTrue(materials.review_phone(state,["# Alex Demo"],at=AT)["ready"])
        check=materials.review_phone(state,[],[{"label":"Phone", "answer":OLD}],at=AT)
        self.assertFalse(check["ready"])
        malformed=preference();malformed["value"]={"disposition":"use","value":"not-a-phone"}
        with self.assertRaises(cs.Invalid):cs.add_record(state,"answers",malformed)

    def test_packet_cannot_present_old_phone_as_current_after_contact_choice_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/"Private";cs.initialize_workspace(root);path=root/"Data/state.json"
            state=cs.add_record(configured(),"answers",preference());path.write_text(cs.canonical_json(state))
            item=request();doc=item["documents"]["resume"];doc["text"]="# Resume\n"+OLD+"\n\n"+state["facts"][0]["statement"];doc["adaptation_audit"]=baseline_audit(state,doc["text"])
            self.assertTrue(search.prepare_case(path,root,item,0)["completed"])
            state=cs.read_state(path)
            state=cs.transact(path,lambda s:cs.reviewed_update(s,{"operation":"supersede_answer","answer_id":"phone-old","replacement":preference(None,"omit","phone-omit",LATER)},"User withdrew application phone choice"),state["revision"])
            receipt=search.deliver_packets(path,root,[item["id"]]);self.assertFalse(receipt["all_updated"]);self.assertFalse(receipt["completed"])
            self.assertFalse(receipt["packets"][0]["assessment"]["contacts"]["ready"])
            dest=root/"old-phone.zip"
            with self.assertRaises(cs.Invalid):materials.package_attempt(state,root,receipt["packets"][0]["attempt_id"],["resume"],dest,LATER)
            self.assertFalse(dest.exists())


if __name__ == "__main__":unittest.main()
