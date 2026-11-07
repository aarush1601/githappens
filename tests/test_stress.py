"""Edge cases and randomised checks for the rules engine (no AI calls)."""
import math
import random
from datetime import date

import pytest

from coach import rules_engine as re_
from tests.test_coach import make_db

VERDICT_ORDER = {"GO": 0, "THINK_TWICE": 1, "SKIP": 2}


def snap(**over):
    base = {"monthly_income": 1500, "monthly_expenses_estimate": 1200, "monthly_discretionary_spend": 300,
            "savings": 500, "safe_to_spend_daily": 15, "disposable_left_this_month": 300,
            "days_left_in_month": 20, "rent_buffer": 0, "purchases_per_category_last_7_days": {}}
    base.update(over)
    return base


# --- snapshot edge cases ---------------------------------------------------

def test_empty_database():
    s = re_.build_snapshot(make_db([]), today=date(2026, 11, 10))
    assert s["safe_to_spend_daily"] == 0 and s["history_days"] == 0
    assert any("No income" in n for n in s["notes"])


def test_rent_paid_this_month_is_not_reserved_twice():
    s = re_.build_snapshot(make_db([(2000, "income", "Salary", "2026-11-01"),
                                    (800, "expense", "Rent", "2026-11-01")]), today=date(2026, 11, 10))
    assert s["rent_buffer"] == 0
    assert s["disposable_left_this_month"] == 1200


def test_payday_not_yet_this_month_uses_last_30_days():
    s = re_.build_snapshot(make_db([(1500, "income", "Salary", "2026-10-28"),
                                    (200, "expense", "Food", "2026-11-03")]), today=date(2026, 11, 10))
    assert s["monthly_income"] == 1500
    assert s["disposable_left_this_month"] == 1300
    assert any("last 30 days" in n for n in s["notes"])


def test_future_and_bad_rows_ignored():
    s = re_.build_snapshot(make_db([(1000, "income", "Salary", "2026-11-01"),
                                    (999, "expense", "Shopping", "2026-12-25"),     # future
                                    (-50, "expense", "Food", "2026-11-02")]),        # negative
                           today=date(2026, 11, 10))
    assert s["spent_this_month"] == 0


@pytest.mark.parametrize("today,days_left", [(date(2026, 2, 28), 1), (date(2028, 2, 1), 29), (date(2026, 12, 31), 1)])
def test_month_boundaries(today, days_left):
    assert re_.build_snapshot(make_db([]), today=today)["days_left_in_month"] == days_left


def test_category_case_insensitive():
    s = snap(purchases_per_category_last_7_days={"takeaway": 3})
    assert re_.evaluate_purchase(s, "pizza", 10, "Takeaway")["verdict"] == "THINK_TWICE"


def test_essential_never_skip():
    r = re_.evaluate_purchase(snap(disposable_left_this_month=50), "electric bill", 120, "Bills")
    assert r["verdict"] == "THINK_TWICE" and r["reason_code"] == "essential_but_over_budget"


@pytest.mark.parametrize("bad", [0, -1, math.nan, math.inf, 10_000_000])
def test_bad_prices_rejected(bad):
    with pytest.raises(ValueError):
        re_.evaluate_purchase(snap(), "x", bad)


# --- trip simulator edge cases -------------------------------------------

@pytest.mark.parametrize("value,unit", [(0, "weeks"), (math.nan, "weeks"), (math.inf, "months"),
                                        (11, "years"), (2, "fortnights")])
def test_bad_durations_rejected(value, unit):
    with pytest.raises(ValueError):
        re_.simulate_trip(snap(), "Paris", value, unit)


@pytest.mark.parametrize("name", ["  PARIS ", "Paris, France", "nyc", "New York City", "Bombay"])
def test_destination_spellings(name):
    assert re_.simulate_trip(snap(), name, 1, "weeks")["total_cost"] > 0


def test_leaving_now_has_no_daily_saving():
    t = re_.simulate_trip(snap(savings=100), "Paris", 1, "weeks", months_until_departure=0)
    assert t["budget_sync"]["leaving_now"] is True
    assert t["affordability"]["verdict"] in ("THINK_TWICE", "SKIP")


def test_overspending_reduces_projected_savings():
    t = re_.simulate_trip(snap(monthly_income=1000, monthly_expenses_estimate=1200, savings=1000),
                          "Lisbon", 1, "weeks", months_until_departure=3)
    assert t["affordability"]["projected_savings_by_departure"] == 400


def test_no_income_no_savings_is_skip():
    t = re_.simulate_trip(snap(monthly_income=0, monthly_expenses_estimate=0, monthly_discretionary_spend=0,
                               savings=0), "Lisbon", 1, "weeks")
    assert t["affordability"]["verdict"] == "SKIP"
    assert t["suggestions"]["months_to_delay_departure_to"] is None


# --- randomised invariants -----------------------------------------------

def _finite(obj):
    if isinstance(obj, dict):
        return all(_finite(v) for v in obj.values())
    if isinstance(obj, list):
        return all(_finite(v) for v in obj)
    return not isinstance(obj, float) or math.isfinite(obj)


def random_snapshot(rng):
    income = rng.choice([0, rng.uniform(0, 5000)])
    return snap(monthly_income=round(income, 2), monthly_expenses_estimate=round(rng.uniform(0, 5000), 2),
                monthly_discretionary_spend=round(rng.uniform(0, 1500), 2), savings=round(rng.uniform(0, 20000), 2),
                safe_to_spend_daily=round(rng.uniform(0, 100), 2),
                disposable_left_this_month=round(rng.uniform(0, 3000), 2),
                days_left_in_month=rng.randint(1, 31), rent_buffer=rng.choice([0, 700]))


def test_random_trips_are_consistent():
    rng = random.Random(42)
    cities = re_.list_destinations()
    for _ in range(3000):
        s = random_snapshot(rng)
        unit = rng.choice(["weeks", "months", "years"])
        value = {"weeks": rng.uniform(0.5, 52), "months": rng.uniform(0.2, 36), "years": rng.uniform(0.1, 10)}[unit]
        args = dict(destination=rng.choice(cities), duration_value=value, duration_unit=unit,
                    purpose=rng.choice(["travel", "study"]), months_until_departure=rng.randint(0, 24))
        t = re_.simulate_trip(s, **args, housing_tier="standard")
        assert _finite(t)
        assert t["affordability"]["verdict"] in VERDICT_ORDER
        parts = t["one_time_upfront_total"] + t["living_total_for_stay"] + t["currency_buffer_10_percent"]
        assert abs(parts - t["total_cost"]) <= 0.03
        assert all(v >= 0 for v in t["one_time_upfront"].values())

        # Budget housing is never more expensive.
        cheap = re_.simulate_trip(s, **args, housing_tier="budget")
        assert cheap["total_cost"] <= t["total_cost"]
        assert VERDICT_ORDER[cheap["affordability"]["verdict"]] <= VERDICT_ORDER[t["affordability"]["verdict"]]

        # More savings never makes the verdict worse.
        richer = re_.simulate_trip({**s, "savings": s["savings"] + 5000}, **args)
        assert VERDICT_ORDER[richer["affordability"]["verdict"]] <= VERDICT_ORDER[t["affordability"]["verdict"]]

        # More time to save never makes the verdict worse (when they're saving money each month).
        if s["monthly_income"] >= s["monthly_expenses_estimate"]:
            later = re_.simulate_trip(s, **{**args, "months_until_departure": args["months_until_departure"] + 6})
            assert VERDICT_ORDER[later["affordability"]["verdict"]] <= VERDICT_ORDER[t["affordability"]["verdict"]]


def test_random_trips_longer_stays_cost_more():
    rng = random.Random(7)
    for _ in range(500):
        city = rng.choice(re_.list_destinations())
        a, b = sorted(rng.uniform(0.2, 119) for _ in range(2))
        assert re_.simulate_trip(snap(), city, a, "months")["total_cost"] <= \
            re_.simulate_trip(snap(), city, b, "months")["total_cost"] + 0.01


def test_random_purchases_are_consistent():
    rng = random.Random(1)
    for _ in range(3000):
        s = random_snapshot(rng)
        cat = rng.choice(["Shopping", "Food", "Takeaway", "Bills", "Entertainment"])
        p1, p2 = sorted(round(rng.uniform(0.01, 4000), 2) for _ in range(2))
        r1, r2 = re_.evaluate_purchase(s, "x", p1, cat), re_.evaluate_purchase(s, "x", p2, cat)
        assert _finite(r1)
        # A pricier item never gets a better verdict.
        assert VERDICT_ORDER[r1["verdict"]] <= VERDICT_ORDER[r2["verdict"]]
        assert r1["money_left_this_month_after"] <= s["disposable_left_this_month"]
