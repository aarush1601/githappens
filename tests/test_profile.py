"""Welcome-page profile: real balances, bills still due, and the bots' memory."""
import sqlite3
from datetime import date

from coach import agents, rules_engine
from tests.test_coach import FakeClient, make_db, text, tool_use

TODAY = date(2026, 11, 10)


def test_running_on_ten_pounds():
    """Income says plenty is left, but they only have £10 right now: never suggest more."""
    snap = rules_engine.build_snapshot(make_db([]), today=TODAY, profile={
        "monthly_income": 900, "monthly_rent": 500, "monthly_bills": 60, "current_balance": 10})
    assert snap["disposable_left_this_month"] == 0  # £10 doesn't even cover rent + bills still due
    assert snap["rent_buffer"] == 500 and snap["bills_still_due_this_month"] == 60
    assert rules_engine.evaluate_purchase(snap, "trainers", 20, "Shopping")["verdict"] == "SKIP"


def test_rent_already_paid_frees_the_balance():
    db = make_db([(500, "expense", "Rent", "2026-11-01"), (60, "expense", "Bills", "2026-11-02")])
    snap = rules_engine.build_snapshot(db, today=TODAY, profile={
        "monthly_income": 900, "monthly_rent": 500, "monthly_bills": 60, "current_balance": 10})
    assert snap["rent_buffer"] == 0 and snap["bills_still_due_this_month"] == 0
    assert snap["disposable_left_this_month"] == 10
    assert any("£10.00 you have right now" in n for n in snap["notes"])


def test_planned_costs_used_until_history_builds_up():
    snap = rules_engine.build_snapshot(make_db([]), today=TODAY, profile={
        "monthly_income": 1100, "monthly_rent": 600, "monthly_bills": 80, "monthly_everyday": 250})
    assert snap["monthly_expenses_estimate"] == 930
    assert not any("rough estimate" in n for n in snap["notes"])


def test_about_user_reaches_every_agent_prompt():
    snap = {"about_user": {"persona": "international_student", "income_type": "fixed", "home_country": "India",
                           "goal": "Trip home in June", "facts": ["On a Student visa"]}}
    block = agents.about_user_block(snap)
    assert "international student" in block and "India" in block and "On a Student visa" in block
    assert agents.about_user_block({}) == ""


def test_bots_save_new_facts_without_duplicates():
    snap = {"about_user": {"persona": "student", "facts": ["Gets paid on the 28th"]}, "notes": []}
    client = FakeClient({"You are the Coach": [
        ([tool_use("1", "remember_about_user", {"fact": "Works 15 hours a week at a café"}),
          tool_use("2", "remember_about_user", {"fact": "gets paid on the 28th"})], "tool_use"),
        ([text("Got it, thanks!")], "end_turn"),
    ]})
    out = agents.coach_chat(snap, "I work 15 hours a week at a café", client=client)
    assert out["new_facts"] == ["Works 15 hours a week at a café"]
    system = client.calls[0]["system"]
    assert "Gets paid on the 28th" in system


def test_api_accepts_profile_with_about():
    from fastapi.testclient import TestClient
    import main
    res = TestClient(main.app).post("/api/time-travel", json={"profile": {
        "monthly_income": 900, "monthly_rent": 500, "savings": 40, "current_balance": 10,
        "about": {"persona": "international_student", "facts": ["x" * 301]}}})
    assert res.status_code == 422  # facts are length-limited
    res = TestClient(main.app).post("/api/time-travel", json={"profile": {
        "monthly_income": 900, "savings": 40, "about": {"persona": "gig_worker", "income_type": "irregular"}}})
    assert res.status_code == 200 and res.json()["starting_savings"] == 40


def test_rent_and_bills_marked_paid():
    snap = rules_engine.build_snapshot(make_db([]), today=TODAY, profile={
        "monthly_income": 900, "monthly_rent": 500, "monthly_bills": 60, "current_balance": 10,
        "essentials_paid_this_month": True})
    assert snap["rent_buffer"] == 0 and snap["disposable_left_this_month"] == 10


def test_similar_facts_merged():
    ctx = agents.AgentContext(snapshot={"about_user": {"facts": ["On a Student visa and works 10 hours a week at Tesco"]}})
    out = agents._remember_handler({"fact": "On a Student visa; works 10 hours a week at Tesco"}, ctx)
    assert out["saved"] is False and ctx.new_facts == []
    assert agents._remember_handler({"fact": "Gets paid on the 15th"}, ctx)["saved"] is True


def test_delegated_specialists_cannot_save_facts():
    coach = agents.make_coach(client=None)
    specialist = agents._without_memory(agents.BUY_ADVISOR)
    assert "remember_about_user" not in [t["name"] for t in specialist.tools]
    assert "remember_about_user" in [t["name"] for t in coach.tools]
    assert "remember_about_user" in agents.BUY_ADVISOR.handlers  # still saves when used directly


def test_shortfall_not_called_rent_money_when_rent_is_paid():
    snap = rules_engine.build_snapshot(make_db([]), today=TODAY, profile={
        "monthly_income": 900, "monthly_rent": 500, "current_balance": 10, "essentials_paid_this_month": True})
    r = rules_engine.evaluate_purchase(snap, "espresso machine", 123, "Shopping")
    assert r["short_by"] == 113 and r["would_use_rent_or_bill_money"] is False
    assert r["reason_code"] == "more_than_money_left_this_month"
