"""Synthetic regressions for draft readiness versus applicability and sending permission."""
import copy
import json
import unittest
from test_search_cases import configured, request, pay, search, cs


def condition(meaning, outcome="pass", **extra):
    return {"meaning": meaning, "outcome": outcome, "source_ids": ["source-new"],
            "evidence": "Synthetic observed employer requirement", "evidence_kind": "explicit_requirement", **extra}


def setting(meaning, value="Synthetic preference", **extra):
    return {"meaning": meaning, "value": value, "priority": "hard", "status": "known", **extra}


def evaluate(settings=(), conditions=(), role_changes=None, config_changes=None, form_change=None):
    state, item = configured(), request()
    state["search_config"]["constraints"] = list(settings)
    if config_changes: state["search_config"].update(config_changes)
    item["opportunity"].update(role_changes or {})
    if form_change: form_change(item["form"])
    for source in item["sources"]: state = cs.add_record(state, "sources", source)
    state = cs.add_record(state, "opportunities", item["opportunity"])
    state = cs.add_record(state, "forms", item["form"])
    case = {"id": "case-a", "batch_id": "search-a", "requested_new": 1, "opportunity_id": item["opportunity"]["id"], "at": item["at"],
            "request_sha256": "0" * 64, "novelty": {"status": "new", "matches": [], "coverage": [], "errors": []},
            "phase": "preparing", "form_id": item["form"]["id"], "compensation": item["compensation"], "conditions": list(conditions),
            "registry_paths": [], "attempt_id": None, "reference_resume_id": None}
    state = cs.add_record(state, "search_cases", case)
    return state, case, search.readiness(state, case)


class ReadinessBoundaryTests(unittest.TestCase):
    def test_residence_context_matches_geographic_evidence_under_another_key(self):
        state, case, result = evaluate([setting("work.residence", "Demo Country")], [condition("geography.eligibility")])
        self.assertTrue(result["draft_ready"]); self.assertFalse(result["unknowns"])
        self.assertEqual(state["search_config"]["constraints"][0]["meaning"], "work.residence")
        self.assertEqual(case["conditions"][0]["meaning"], "geography.eligibility")

    def test_real_geographic_restriction_still_blocks(self):
        _, _, result = evaluate([setting("work.residence", "Demo Country")], [condition("geography.eligibility", "fail")])
        self.assertEqual(result["status"], "blocked"); self.assertFalse(result["draft_ready"])

    def test_contract_process_input_is_distinct_from_a_real_hard_requirement(self):
        geo = condition("geography.eligibility")
        ordinary = condition("contract.ie_eor", "unknown", priority="negotiable", dimension="contract_arrangement")
        state, case, result = evaluate(conditions=[geo, ordinary])
        self.assertTrue(result["draft_ready"]); self.assertTrue(result["clarifications"])
        self.assertEqual(case["conditions"][1]["outcome"], "unknown")
        # The evaluator must not silently reclassify a user's hard setting.
        hard = condition("contract.ie_eor", "unknown", priority="hard", dimension="contract_arrangement")
        self.assertFalse(evaluate([setting("contract.ie_eor")], [geo, hard])[2]["draft_ready"])
        self.assertFalse(evaluate([setting("contract.legal_eligibility")], [geo, condition("contract.legal_eligibility", "unknown")])[2]["draft_ready"])
        self.assertEqual(evaluate([setting("contract.ie_eor")], [geo, condition("contract.ie_eor", "fail")])[2]["status"], "blocked")

    def test_management_language_applies_to_management_cases_only(self):
        criteria = [setting("management.team_language")]
        self.assertTrue(evaluate(criteria, role_changes={"role_track": "individual_contributor"})[2]["draft_ready"])
        unknown_track = evaluate(criteria)[2]
        self.assertFalse(unknown_track["draft_ready"]); self.assertTrue(unknown_track["unknowns"])
        self.assertFalse(evaluate(criteria, role_changes={"role_track": "management"})[2]["draft_ready"])
        management_fail = evaluate(criteria, [condition("management.team_language", "fail")], {"role_track": "management"})[2]
        self.assertEqual(management_fail["status"], "blocked")
        conflict = evaluate(criteria, role_changes={"role_track": "individual_contributor", "management_scope": "management"})[2]
        self.assertFalse(conflict["draft_ready"])

    def test_no_send_is_operational_and_unknown_arbitrary_hard_settings_remain_unresolved(self):
        state, _, result = evaluate([setting("submission.no_sends", True)])
        self.assertTrue(result["draft_ready"]); self.assertFalse(result["submission_authorized"])
        self.assertFalse(cs.research_allowed(state))
        self.assertFalse(evaluate([setting("security.clearance")])[2]["draft_ready"])
        # A case annotation must not silently narrow an arbitrary user-essential setting.
        custom = evaluate([setting("security.clearance")], [condition("security.clearance", "unknown", dimension="management_language")], {"role_track": "individual_contributor"})[2]
        self.assertFalse(custom["draft_ready"])

    def test_missing_case_type_metadata_is_not_an_explicit_exclusion(self):
        cfg = configured()["search_config"]; cfg["income_policy"].pop("case_types"); cfg["income_policy"].pop("weekly_hours")
        cfg["constraints"] = [setting("search.case_types", ["vacancy"])]
        result = evaluate(config_changes=cfg)[2]
        self.assertTrue(result["draft_ready"]); self.assertEqual(result["scope"]["status"], "allowed")
        cfg["income_policy"]["case_types"] = ["contract_project"]
        self.assertEqual(evaluate(config_changes=cfg)[2]["status"], "blocked")
        cfg["income_policy"].pop("case_types"); cfg["constraints"] = []
        result = evaluate(config_changes=cfg)[2]
        self.assertTrue(result["draft_ready"]); self.assertEqual(result["scope"]["status"], "not_normalized")

    def test_monthly_comparison_uses_real_units_without_inventing_weekly_hours(self):
        cfg = configured()["search_config"]
        for key, amount in (("salary_floor", 4100), ("salary_goal", 5800)):
            cfg[key].update(amount=amount, period="month")
        cfg["income_policy"].pop("weekly_hours"); cfg["income_policy"].pop("case_types")
        quote = pay(minimum=5000, maximum=7000, period="month"); quote.pop("weekly_hours")
        original = copy.deepcopy(cfg)
        self.assertEqual(search.income_assessment(cfg, quote)["status"], "pass")
        cfg["income_policy"]["weekly_hours"] = 18  # A separately recorded hourly-work scenario.
        self.assertEqual(search.income_assessment(cfg, {**quote, "weekly_hours": 40})["status"], "pass")
        self.assertNotIn("weekly_hours", original["income_policy"])
        low_cap = {**quote, "minimum": 2100, "maximum": 3000}
        self.assertEqual(search.income_assessment(cfg, low_cap)["status"], "fail")
        self.assertEqual(search.income_assessment(cfg, {**quote, "period": "hour"})["status"], "unknown")

    def test_missing_policy_reuses_existing_salary_records_without_fake_confirmation(self):
        cfg = configured()["search_config"]; cfg.pop("income_policy"); original = json.dumps(cfg, sort_keys=True)
        result = search.income_assessment(cfg, pay())
        self.assertEqual(result["status"], "pass"); self.assertEqual(result["policy_status"], "absent")
        self.assertEqual(json.dumps(cfg, sort_keys=True), original)
        self.assertEqual(search.income_assessment({}, pay())["status"], "intake_missing")
        cfg["income_policy"] = None
        self.assertEqual(search.income_assessment(cfg, pay())["status"], "pass")
        self.assertTrue(evaluate(config_changes=cfg)[2]["draft_ready"])

    def test_explicit_hours_or_essential_stack_failures_still_block(self):
        for meaning in ("work.weekly_hours", "role.requirement.framework"):
            result = evaluate([setting(meaning)], [condition(meaning, "fail")])[2]
            self.assertEqual(result["status"], "blocked")
        preference = condition("role.requirement.framework", "unknown", priority="preference")
        self.assertTrue(evaluate(conditions=[preference])[2]["draft_ready"])

    def test_pending_consent_does_not_complete_factual_answers_or_authorize_submit(self):
        def pending(form):
            form["fields"].append({"id": "privacy", "label": "Privacy terms", "control": "checkbox", "help_text": "", "choices": [], "required": True,
                                   "is_consent": True, "consent_text_version": "Synthetic current version", "answer_state": "consent_pending"})
        state, case, result = evaluate(form_change=pending)
        self.assertTrue(result["draft_ready"]); self.assertEqual(result["pending_consents"], ["privacy"])
        self.assertFalse(result["submission_authorized"])
        state["forms"][0]["fields"][0]["answer_state"] = "unknown"
        self.assertFalse(search.readiness(state, case)["draft_ready"])

    def test_unread_employer_degree_claim_is_unverified_not_a_categorical_failure(self):
        state, case, _ = evaluate(conditions=[condition("role.requirement.degree", "fail", priority="hard", verification="unverified")])
        result = search.readiness(state, case)
        self.assertEqual(result["status"], "conditional"); self.assertFalse(result["blockers"])
        self.assertEqual(case["conditions"][0]["outcome"], "fail")  # Historical claim retained, not silently rewritten.
        case["conditions"][0]["verification"] = "primary_verified"
        self.assertEqual(search.readiness(state, case)["status"], "blocked")

    def test_unconfigured_and_invalid_policy_are_not_explicit_scope_exclusions(self):
        state, case, result = evaluate(config_changes={"salary_floor": None, "salary_goal": None, "income_policy": None})
        self.assertEqual(result["status"], "conditional"); self.assertEqual(result["income"]["status"], "intake_missing")
        self.assertEqual(result["scope"]["status"], "not_normalized")
        self.assertFalse(any("outside" in reason for reason in result["blockers"]))
        state["search_config"]["income_policy"] = {}
        with self.assertRaises(cs.Invalid): cs.validate(state)

    def calendar_case(self, floor_period, floor_amount, observed_period, cap):
        state, case, _ = evaluate()
        state["search_config"]["salary_floor"].update(period=floor_period, amount=floor_amount)
        state["search_config"]["salary_goal"] = None
        state["search_config"]["income_policy"].update(goal_disposition="no_goal")
        state["search_config"]["income_policy"].pop("weekly_hours")
        case["compensation"].update(kind="range", period=observed_period, minimum=cap, maximum=cap)
        case["compensation"].pop("weekly_hours")
        state["search_cases"][0] = case
        cs.validate(state)
        return state, case

    def test_monthly_floor_annual_cap_below_floor_is_not_pay_uncertain_ready(self):
        state, case = self.calendar_case("month", 5000, "year", 36000)
        before = copy.deepcopy(state)
        result = search.readiness(state, case)
        self.assertEqual(result["income"]["status"], "fail"); self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["draft_ready"]); self.assertEqual(state, before)
        self.assertEqual(case["compensation"]["period"], "year")

    def test_annual_floor_monthly_cap_below_floor_is_not_pay_uncertain_ready(self):
        state, case = self.calendar_case("year", 60000, "month", 3000)
        before = copy.deepcopy(state)
        result = search.readiness(state, case)
        self.assertEqual(result["income"]["status"], "fail"); self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["draft_ready"]); self.assertEqual(state, before)
        self.assertEqual(case["compensation"]["period"], "month")

    def test_fixed_calendar_controls_and_goal_comparison_in_both_directions(self):
        for floor_period, floor_amount, observed_period, value in (("month", 5000, "year", 72000), ("year", 60000, "month", 6000),
                                                                  ("month", 5000, "year", 60000), ("year", 60000, "month", 5000)):
            state, case = self.calendar_case(floor_period, floor_amount, observed_period, value)
            state["search_config"]["salary_goal"] = {"amount": value / 12 if observed_period == "year" else value * 12,
                "currency": "USD", "basis": "gross", "period": "month" if observed_period == "year" else "year"}
            state["search_config"]["income_policy"]["goal_disposition"] = "stated"
            before = copy.deepcopy(state)
            result = search.readiness(state, case)
            self.assertEqual(result["income"]["status"], "pass"); self.assertTrue(result["draft_ready"])
            self.assertEqual(result["income"]["goal"], "meets"); self.assertEqual(state, before)

    def test_calendar_normalization_does_not_cross_currency_gross_net_or_hourly_basis(self):
        for change in ({"currency": "EUR"}, {"basis": "net"}, {"period": "hour"}):
            state, case = self.calendar_case("month", 5000, "year", 36000)
            case["compensation"].update(change)
            before = copy.deepcopy(state)
            self.assertEqual(search.readiness(state, case)["income"]["status"], "unknown")
            self.assertEqual(state, before)


if __name__ == "__main__":
    unittest.main()
