"""Worth-it check and purchase tracker (no real AI calls)."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from coach import agents, rules_engine
from tests.test_coach import FakeClient, text, tool_use

SNAP = {"monthly_income": 1100, "disposable_left_this_month": 400, "days_left_in_month": 20,
        "safe_to_spend_daily": 20, "rent_buffer": 0, "purchases_per_category_last_7_days": {},
        "spending_by_category_last_30_days": {"Coffee": 64.29, "Transport": 0}}


def test_cost_per_use_and_payback():
    v = rules_engine.assess_value(SNAP, "espresso machine", 123, "kitchen_gadget",
                                  uses_per_week=7, replaces_category="coffee")
    assert v["cost_per_use"] == 0.11 and v["uses_over_lifespan"] == 1095
    assert v["replaces_spending"]["weekly_spend_replaced"] == 15.0
    assert v["replaces_spending"]["pays_for_itself_in_weeks"] == 8.2
    assert v["replaces_spending"]["pays_back_quickly"] is False


def test_user_stated_spend_beats_history():
    v = rules_engine.assess_value(SNAP, "espresso machine", 123, "kitchen_gadget", replaces_weekly_spend=25)
    assert v["replaces_spending"]["pays_back_quickly"] is True
    assert v["replaces_spending"]["source"] == "what you told me"


def test_no_habit_no_payback():
    v = rules_engine.assess_value(SNAP, "bike", 200, "hobby_or_sport", replaces_category="Transport")
    assert v["replaces_spending"] is None
    assert any("doesn't replace" in n for n in v["notes"])


def test_walking_shoes_are_essential_type():
    v = rules_engine.assess_value(SNAP, "walking shoes", 90, "everyday_essential", uses_per_week=6)
    assert v["student_rule_of_thumb"] == "usually_worth_it"
    assert v["cost_per_use"] == 0.19


@pytest.mark.parametrize("kwargs", [{"item_type": "spaceship"}, {"uses_per_week": 0}, {"uses_per_week": float("nan")},
                                    {"replaces_weekly_spend": -1}, {"price": 0}])
def test_value_input_validation(kwargs):
    args = {"item": "x", "price": 10, "item_type": "other", **kwargs}
    with pytest.raises(ValueError):
        rules_engine.assess_value(SNAP, **args)


@pytest.mark.parametrize("item,expected", [("Espresso machine", "kitchen_gadget"), ("good walking shoes", "everyday_essential"),
                                           ("Textbook for module", "study_or_work_tool"), ("PS5", "tech_gadget"),
                                           ("mystery box", "other")])
def test_offline_item_type_guess(item, expected):
    assert rules_engine.guess_item_type(item) == expected


@pytest.mark.parametrize("bad", [{"worth_verdict": "MAYBE"}, {"need_level": "vital"}, {"reasons": []},
                                 {"reasons": ["a", "b", "c", "d"]}])
def test_worth_verdict_is_validated(bad):
    args = {"item": "x", "worth_verdict": "DEPENDS", "need_level": "useful", "reasons": ["ok"], "better_option": "y", **bad}
    with pytest.raises(ValueError):
        agents._record_worth_handler(args, agents.AgentContext(snapshot=SNAP))


def advisor_script():
    return {"You are the Buy Advisor": [
        ([tool_use("1", "evaluate_purchase", {"item": "espresso machine", "price": 123, "category": "Shopping"}),
          tool_use("2", "assess_value", {"item": "espresso machine", "price": 123, "item_type": "kitchen_gadget",
                                         "replaces_category": "Coffee"}),
          tool_use("3", "record_worth_verdict", {"item": "espresso machine", "worth_verdict": "NOT_WORTH_IT",
                                                 "need_level": "nice_to_have", "reasons": ["Running costs"],
                                                 "better_option": "A cafetière"})], "tool_use"),
        ([text("You can afford it, but it's probably not worth it. How often do you buy coffee out?")], "end_turn"),
    ]}


def test_purchase_review_returns_both_verdicts_and_history():
    out = agents.purchase_review(SNAP, "espresso machine", 123, "Shopping", "bought", client=FakeClient(advisor_script()))
    assert out["purchase_check"]["verdict"] == "GO"
    assert out["worth_check"]["worth_verdict"] == "NOT_WORTH_IT"
    assert out["value_check"]["replaces_spending"]["pays_for_itself_in_weeks"] == 8.2
    assert [m["role"] for m in out["history"]] == ["user", "assistant"]
    assert "How often" in out["history"][1]["content"]


def test_endpoint_logs_purchase_after_snapshot(tmp_path, monkeypatch):
    import database
    import main

    db = tmp_path / "t.db"
    monkeypatch.setattr(database, "DATABASE_NAME", str(db))
    database.create_tables()
    seen = {}

    def fake_review(snapshot, item, price, category, status):
        seen["spent"] = snapshot["spent_this_month"]
        return {"explanation": "hi", "history": [], "purchase_check": None, "value_check": None, "worth_check": None}

    monkeypatch.setattr(agents, "purchase_review", fake_review)
    client = TestClient(main.app)
    r = client.post("/api/purchase-review", json={"item": "espresso machine", "price": 123})
    assert r.status_code == 200 and r.json()["transaction_id"] == 1
    assert seen["spent"] == 0  # the new purchase wasn't in the snapshot the coach judged
    row = sqlite3.connect(db).execute("SELECT amount, description FROM transactions").fetchone()
    assert row == (123.0, "espresso machine")

    r = client.post("/api/purchase-review", json={"item": "x", "price": 5, "status": "planning"})
    assert r.json()["transaction_id"] is None


def test_price_each_times_per_week_is_multiplied_by_code():
    v = rules_engine.assess_value(SNAP, "espresso machine", 123, "kitchen_gadget",
                                  replaces_cost_each=3.20, replaces_times_per_week=5)
    assert v["replaces_spending"]["weekly_spend_replaced"] == 16.0
    assert v["replaces_spending"]["pays_for_itself_in_weeks"] == 7.7
    assert v["replaces_spending"]["pays_back_quickly"] is True
    with pytest.raises(ValueError, match="both"):
        rules_engine.assess_value(SNAP, "x", 10, "other", replaces_cost_each=3)
