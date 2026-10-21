"""Scoped optional context enrichment and private interview growth regressions."""
import copy
import unittest
from test_state import cs, base, AT, answer


def access(state, decision="opted_in", scope=None, purposes=None):
    return cs.reviewed_update(state, {"operation": "set_context_access", "access": {
        "decision": decision, "source_scope": scope or ["selected-demo-thread"],
        "purposes": purposes or list(cs.CONTEXT_PURPOSE.values()), "at": AT,
        "evidence": "Synthetic user's explicit scoped choice"}}, "Synthetic context preference")


def insight(kind="strength", **extra):
    return {"id": "insight-a", "kind": kind, "statement": "Synthetic career-relevant observation",
            "source_ids": ["source-user"], "source_scope": ["selected-demo-thread"],
            "basis": "inference", "confidence": "medium", "status": "suggested", **extra}


def confirmed(state, kind="strength"):
    state = cs.add_record(access(state), "context_insights", insight(kind))
    return cs.reviewed_update(state, {"operation": "confirm_context_insight", "insight_id": "insight-a",
        "confirmation": {"at": AT, "source_id": "source-user", "evidence": "Synthetic exact user confirmation"}},
        "Confirm synthetic insight")


class ContextTests(unittest.TestCase):
    def test_legacy_state_is_valid_and_no_access_is_implied(self):
        state = base()
        state.pop("context_access", None); state.pop("context_insights", None)
        cs.validate(state)
        for candidate in (state, access(state, "declined"), access(state, "withdrawn")):
            with self.assertRaises(cs.Invalid):
                cs.add_record(candidate, "context_insights", insight())
        self.assertFalse(cs.research_allowed(access(state)))

    def test_exact_source_and_purpose_opt_in_and_clean_shape_errors(self):
        state = access(base(), purposes=["strengths"])
        cs.add_record(state, "context_insights", insight())
        for row in (insight(source_scope=["another-thread"]), insight("growth_area"), insight(source_scope={})):
            with self.assertRaises(cs.Invalid):
                cs.add_record(state, "context_insights", row)
        invalid = {"operation": "set_context_access", "access": {"decision": "opted_in"}}
        with self.assertRaises(cs.Invalid): cs.reviewed_update(state, invalid, "Missing scope")

    def test_suggestion_is_not_a_confirmed_fact_or_external_claim(self):
        state = cs.add_record(access(base()), "context_insights", insight())
        fact = copy.deepcopy(state["facts"][0]); fact.update(id="context-fact", context_insight_ids=["insight-a"])
        with self.assertRaises(cs.Invalid): cs.add_record(state, "facts", fact)
        packet = copy.deepcopy(state["artifacts"][0]); packet.update(id="bad", version=2, context_insight_ids=["insight-a"])
        with self.assertRaises(cs.Invalid): cs.add_record(state, "artifacts", packet)
        state = confirmed(base())
        state = cs.add_record(state, "facts", fact)
        packet.pop("context_insight_ids"); packet["fact_ids"] = ["context-fact"]
        cs.add_record(state, "artifacts", packet)

    def test_growth_never_leaks_into_external_artifact_or_form_answer(self):
        state = confirmed(base(), "growth_area")
        fact = copy.deepcopy(state["facts"][0]); fact.update(id="growth-fact", context_insight_ids=["insight-a"])
        with self.assertRaises(cs.Invalid): cs.add_record(state, "facts", fact)
        fact.update(disclosure="private", private_interview_only=True)
        state = cs.add_record(state, "facts", fact)
        packet = copy.deepcopy(state["artifacts"][0]); packet.update(id="growth-note", version=2,
            kind="private_interview_preparation", visibility="private", fact_ids=["growth-fact"], context_insight_ids=["insight-a"])
        cs.add_record(state, "artifacts", packet)
        for kind in ("resume", "cover_letter", "public_post", "application_answers", "referral_request"):
            external = {**packet, "visibility": "external", "kind": kind}
            with self.assertRaises(cs.Invalid): cs.add_record(state, "artifacts", external)
        for row in (answer(context_insight_ids=["insight-a"]), answer(fact_ids=["growth-fact"])):
            with self.assertRaises(cs.Invalid): cs.add_record(state, "answers", row)
        raw_form = {"id": "form", "opportunity_id": "role-a", "status": "provisional", "at": AT,
                    "source_ids": [], "fields": [], "context_insight_ids": ["insight-a"]}
        with self.assertRaises(cs.Invalid): cs.add_record(state, "forms", raw_form)
        raw_form.pop("context_insight_ids")
        for refs in ({"context_insight_ids": ["insight-a"]}, {"fact_ids": ["growth-fact"]}):
            raw_form["fields"] = [{"id": "answer", "label": "Experience", "control": "text", "help_text": "", "choices": [], **refs}]
            with self.assertRaises(cs.Invalid): cs.add_record(state, "forms", raw_form)

    def test_withdrawal_preserves_history_flags_claims_and_blocks_new_use(self):
        state = confirmed(base())
        fact = copy.deepcopy(state["facts"][0]); fact.update(id="context-fact", context_insight_ids=["insight-a"])
        state = cs.add_record(state, "facts", fact)
        packet = copy.deepcopy(state["artifacts"][0]); packet.update(id="context-cv", version=2, fact_ids=["context-fact"])
        state = cs.add_record(state, "artifacts", packet)
        withdrawn = access(state, "withdrawn")
        self.assertTrue(withdrawn["facts"][-1]["context_reuse_blocked"])
        self.assertTrue(withdrawn["artifacts"][-1]["review_required"])
        self.assertEqual(withdrawn["context_insights"], state["context_insights"])
        self.assertEqual(withdrawn["change_history"][-1]["operation"], "set_context_access")
        with self.assertRaises(cs.Invalid): cs.add_record(withdrawn, "artifacts", {**packet, "id": "new", "version": 3})
        with self.assertRaises(cs.Invalid): cs.add_record(withdrawn, "context_insights", insight(id="new"))
        self.assertFalse(cs.research_allowed(withdrawn))


if __name__ == "__main__":
    unittest.main()
