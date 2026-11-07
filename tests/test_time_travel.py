import pytest
from fastapi.testclient import TestClient

from coach import agents, rules_engine as r
from tests.test_coach import FakeClient, text, tool_use

S = {"monthly_income": 1100, "monthly_expenses_estimate": 940, "monthly_discretionary_spend": 180,
     "savings": 350, "notes": []}


def test_baseline_projection():
    p = r.project_future(S)
    assert p["baseline_balance"] == {"1_months": 510, "12_months": 2270, "60_months": 9950}
    assert p["what_if_balance"] == p["baseline_balance"]
    assert len(p["monthly_balances"]["baseline"]) == 61
    assert p["months_of_essentials_covered_now"] == 0.5


def test_one_off_shock_runs_out_immediately():
    p = r.project_future(S, "laptop_breaks")
    assert p["what_if_balance"]["1_months"] == 10 and p["what_if_runs_out_in_month"] == 0
    assert p["amount_is_default_estimate"] is True and any("typical amount" in n for n in p["notes"])


def test_income_drop_runs_out():
    p = r.project_future(S, "income_drops_20")
    assert p["monthly_net_with_what_if"] == -60 and p["what_if_runs_out_in_month"] == 6
    assert p["difference_after"]["60_months"] == -13200


def test_user_amounts():
    assert r.project_future(S, "rent_rises", 80)["what_if_balance"]["60_months"] == 5150
    shift = r.project_future(S, "lose_a_shift", 50)
    assert shift["monthly_net_with_what_if"] == round(160 - 50 * r.WEEKS_PER_MONTH, 2)


@pytest.mark.parametrize("kwargs", [{"scenario": "alien_invasion"}, {"scenario": "income_drops_20", "amount": 150},
                                    {"amount": -5}, {"amount": float("nan")}, {"months": 0}, {"months": 61}])
def test_validation(kwargs):
    with pytest.raises(ValueError):
        r.project_future(S, **kwargs)


def test_coach_uses_time_travel_tool():
    client = FakeClient({"You are the Coach": [
        ([tool_use("1", "project_future", {"scenario": "rent_rises", "amount": 80})], "tool_use"),
        ([text("You'd still save.")], "end_turn"),
    ]})
    out = agents.coach_chat(S | {"disposable_left_this_month": 0, "days_left_in_month": 1, "safe_to_spend_daily": 0,
                                 "rent_buffer": 0, "purchases_per_category_last_7_days": {}},
                            "what if rent goes up £80?", client=client)
    assert out["time_travel"]["what_if_balance"]["60_months"] == 5150
    assert "monthly_balances" not in out["time_travel"]  # agent gets the summary only


def test_endpoint():
    import main
    res = TestClient(main.app).post("/api/time-travel", json={"scenario": "phone_breaks", "amount": 300,
                                                              "profile": {"monthly_income": 1000, "monthly_expenses": 900, "savings": 100}})
    body = res.json()
    assert res.status_code == 200 and body["what_if_balance"]["1_months"] == -100
    assert len(body["monthly_balances"]["what_if"]) == 61
    assert TestClient(main.app).post("/api/time-travel", json={"scenario": "zombies"}).status_code == 422


def test_website_data_replaces_server_database():
    """The website sends its own transactions; the snapshot must use those, not finance.db."""
    import main
    from datetime import date
    today = date.today().replace(day=1).isoformat()
    body = {"scenario": "none", "data": {
        "transactions": [{"amount": 400, "type": "income", "category": "Salary", "name": "Pay", "date": today},
                         {"amount": 390, "type": "expense", "category": "Rent", "name": "Rent", "date": today}],
        "goals": [{"name": "Laptop", "target": 500, "saved": 25}]}}
    res = TestClient(main.app).post("/api/time-travel", json=body)
    assert res.status_code == 200
    out = res.json()
    assert out["starting_savings"] == 25
    assert out["monthly_net_now"] == 10  # £400 in, £390 out: the "running on £10" case
