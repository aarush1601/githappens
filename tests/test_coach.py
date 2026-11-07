import json
import sqlite3
from datetime import date
from types import SimpleNamespace

import pytest

from coach import agents, rules_engine

TODAY = date(2026, 11, 10)  # 21 days left in November


def make_db(transactions, goals=()):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE transactions (id INTEGER PRIMARY KEY, amount REAL, transaction_type TEXT,"
                 " category TEXT, description TEXT, transaction_date TEXT)")
    conn.execute("CREATE TABLE savings_goals (id INTEGER PRIMARY KEY, goal_name TEXT, target_amount REAL,"
                 " current_amount REAL, target_date TEXT)")
    conn.executemany("INSERT INTO transactions (amount, transaction_type, category, description, transaction_date)"
                     " VALUES (?, ?, ?, '', ?)", transactions)
    conn.executemany("INSERT INTO savings_goals (goal_name, target_amount, current_amount, target_date)"
                     " VALUES (?, ?, ?, '2027-06-01')", goals)
    return conn


@pytest.fixture
def snapshot():
    conn = make_db(
        [
            (1200, "income", "Salary", "2026-11-01"),
            (800, "expense", "Rent", "2026-10-15"),     # rent not yet paid this month -> protected
            (100, "expense", "Food", "2026-11-03"),
            (12, "expense", "Takeaway", "2026-11-05"),
            (11, "expense", "Takeaway", "2026-11-07"),
            (13, "expense", "Takeaway", "2026-11-09"),
            (64, "expense", "Shopping", "2026-10-20"),  # last 30 days, not this month
        ],
        goals=[("Trip", 1000, 500)],
    )
    return rules_engine.build_snapshot(conn, today=TODAY)


def test_snapshot_figures(snapshot):
    assert snapshot["spent_this_month"] == 136
    assert snapshot["spent_last_30_days"] == 1000
    assert snapshot["rent_buffer"] == 800
    # 1200 income - 136 spent - 800 rent still due
    assert snapshot["disposable_left_this_month"] == 264
    assert snapshot["days_left_in_month"] == 21
    assert snapshot["safe_to_spend_daily"] == round(264 / 21, 2)
    assert snapshot["monthly_discretionary_spend"] == 100  # takeaways + shopping
    assert snapshot["savings"] == 500
    assert snapshot["purchases_per_category_last_7_days"]["takeaway"] == 3


def test_profile_overrides(snapshot):
    conn = make_db([])
    snap = rules_engine.build_snapshot(conn, today=TODAY, profile={"monthly_income": 1500, "rent_buffer": 0})
    assert snap["disposable_left_this_month"] == 1500
    assert snap["has_data"] is True


@pytest.mark.parametrize(
    "price,category,verdict",
    [
        (20, "Shopping", "GO"),
        (150, "Shopping", "THINK_TWICE"),     # over half of £264
        (10, "Takeaway", "THINK_TWICE"),      # 4th takeaway this week
        (300, "Shopping", "SKIP"),            # would dip into rent buffer
        (200, "Bills", "GO"),                 # essential and affordable
    ],
)
def test_purchase_verdicts(snapshot, price, category, verdict):
    assert rules_engine.evaluate_purchase(snapshot, "thing", price, category)["verdict"] == verdict


def test_purchase_shortfall(snapshot):
    result = rules_engine.evaluate_purchase(snapshot, "laptop", 300, "Shopping")
    assert result["short_by"] == 36
    assert result["would_use_rent_or_bill_money"] is True
    assert result["money_left_this_month_after"] == 0


def test_espresso_machine_affordable_but_flagged_as_low_value(snapshot):
    # Affordability is about money only...
    assert rules_engine.evaluate_purchase(snapshot, "espresso machine", 123, "Shopping")["verdict"] == "GO"
    # ...and the value check carries the student warning separately.
    value = rules_engine.assess_value(snapshot, "espresso machine", 123, "kitchen_gadget")
    assert value["student_rule_of_thumb"] == "usually_not_worth_it"
    assert value["percent_of_money_left_this_month"] == 46.6


def test_buy_check_has_rules_only_fallback_without_provider(snapshot, monkeypatch):
    monkeypatch.setattr(agents, "get_client", lambda: (_ for _ in ()).throw(agents.CoachUnavailable("offline")))
    result = agents.buy_check(snapshot, "espresso machine", 123, "Shopping")
    assert result["provider"] == "rules_only"
    assert result["purchase_check"]["verdict"] == "GO"
    assert result["value_check"]["item_type"] == "kitchen_gadget"
    assert result["worth_check"] is None
    assert "rarely worth it" in result["explanation"]


def test_trip_cost_breakdown(snapshot):
    trip = rules_engine.simulate_trip(snapshot, "Barcelona", 2, "months", "travel", 3)
    # upfront: 120 flights + 0 visa + 750 deposit + 60 insurance = 930
    assert trip["one_time_upfront_total"] == 930
    assert trip["monthly_living"]["total"] == 1055
    assert trip["living_total_for_stay"] == 2110
    assert trip["inflation_multiplier"] == 1.0
    assert trip["currency_buffer_10_percent"] == 304
    assert trip["total_cost"] == 3344


def test_long_stay_applies_inflation(snapshot):
    trip = rules_engine.simulate_trip(snapshot, "Berlin", 1, "years", "study", 6)
    assert trip["inflation_multiplier"] == 1.0125  # average rise over 12 months at 2.5%/yr


def test_trip_verdicts():
    base = {"monthly_income": 2000, "monthly_expenses_estimate": 1500, "monthly_discretionary_spend": 400,
            "savings": 0, "safe_to_spend_daily": 20}
    # Lisbon 1 week: small trip, surplus covers it
    assert rules_engine.simulate_trip(base, "Lisbon", 1, "weeks", "travel", 3)["affordability"]["verdict"] == "GO"
    # New York 1 year with no time to save: unaffordable
    nyc = rules_engine.simulate_trip(base, "New York", 1, "years", "study", 0)
    assert nyc["affordability"]["verdict"] == "SKIP"
    assert nyc["suggestions"]["budget_housing_saves"] > 0


def test_trip_think_twice_band():
    base = {"monthly_income": 2000, "monthly_expenses_estimate": 1800, "monthly_discretionary_spend": 300,
            "savings": 0, "safe_to_spend_daily": 10}
    trip = rules_engine.simulate_trip(base, "Barcelona", 2, "months", "travel", 7)
    # total 3344, projected 1400, gap 1944, cut capacity 2100 -> 92.6% cut
    assert trip["affordability"]["verdict"] == "THINK_TWICE"
    assert trip["affordability"]["discretionary_cut_needed_percent"] == 92.6


def test_unknown_city_raises(snapshot):
    with pytest.raises(ValueError, match="Known destinations"):
        rules_engine.simulate_trip(snapshot, "Atlantis", 1, "weeks")


# ---------------------------------------------------------------------------
# Agent loop with a fake Claude client
# ---------------------------------------------------------------------------

def text(t):
    return SimpleNamespace(type="text", text=t)


def tool_use(id_, name, input_):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_)


class FakeClient:
    """Returns scripted responses per agent (picked by system prompt)."""

    def __init__(self, scripts):
        self.scripts = scripts
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        assert kwargs["model"] == "claude-opus-5-5"
        assert kwargs["fallbacks"] == "default"
        role = next(k for k in self.scripts if k in kwargs["system"])
        content, stop = self.scripts[role].pop(0)
        return SimpleNamespace(content=content, stop_reason=stop)


def test_coach_delegates_to_buy_advisor(snapshot):
    client = FakeClient({
        "You are the Coach": [
            ([tool_use("c1", "ask_buy_advisor", {"question": "trainers £60?"})], "tool_use"),
            ([text("Think twice on the trainers.")], "end_turn"),
        ],
        "You are the Buy Advisor": [
            ([tool_use("b1", "evaluate_purchase", {"item": "trainers", "price": 60, "category": "Shopping"})], "tool_use"),
            ([text("Go - it fits.")], "end_turn"),
        ],
    })
    out = agents.coach_chat(snapshot, "Can I buy trainers for £60?", client=client)
    assert out["reply"] == "Think twice on the trainers."
    assert out["purchase_check"]["verdict"] == "GO"
    assert out["trip_plan"] is None

    # The coach received the specialist's reply plus the exact figures from code.
    coach_followup = client.calls[-1]["messages"][-2]["content"][0]
    payload = json.loads(coach_followup["content"])
    assert payload["specialist_reply"] == "Go - it fits."
    assert payload["figures_used"][0]["price"] == 60


def test_tool_error_is_reported_not_raised(snapshot):
    client = FakeClient({
        "You are the Trip Planner": [
            ([tool_use("t1", "simulate_trip", {"destination": "Atlantis", "duration_value": 1, "duration_unit": "weeks",
                                               "purpose": "travel", "months_until_departure": 1,
                                               "housing_tier": "standard"})], "tool_use"),
            ([text("I don't have Atlantis yet.")], "end_turn"),
        ],
    })
    ctx = agents.AgentContext(snapshot=snapshot)
    reply = agents.run_agent(client, agents.TRIP_PLANNER, [{"role": "user", "content": "Atlantis"}], ctx)
    assert reply == "I don't have Atlantis yet."
    result = client.calls[-1]["messages"][-2]["content"][0]
    assert result["is_error"] is True and "Known destinations" in result["content"]


def test_buy_check_falls_back_to_code_verdict(snapshot):
    client = FakeClient({"You are the Buy Advisor": [([text("Skip for now.")], "end_turn")]})
    out = agents.buy_check(snapshot, "laptop", 300, "Shopping", client=client)
    assert out["purchase_check"]["verdict"] == "SKIP"
    assert out["explanation"] == "Skip for now."


def test_refusal_returns_safe_reply(snapshot):
    client = FakeClient({"You are the Coach": [([], "refusal")]})
    assert agents.coach_chat(snapshot, "hi", client=client)["reply"] == agents.REFUSAL_REPLY


def test_history_cleaned():
    hist = [{"role": "assistant", "content": "hi"}, {"role": "user", "content": "a"},
            {"role": "system", "content": "x"}, {"role": "assistant", "content": "b"}]
    assert agents._clean_history(hist) == [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
