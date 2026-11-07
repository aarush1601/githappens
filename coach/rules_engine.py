"""Deterministic money maths for the coach agents.

Every number the agents talk about comes from this file. Claude only receives
these results as facts and explains them; it never calculates figures itself.
All amounts are in pounds (same convention as main.py).
"""

from __future__ import annotations

import calendar
import math
from datetime import date, timedelta
from typing import Any

ESSENTIAL_CATEGORIES = {
    "rent", "bills", "food", "groceries", "transport", "healthcare",
    "education", "childcare", "utilities",
}

RENT_CATEGORIES = {"rent"}

CURRENCY_BUFFER_RATE = 0.10       # 10% cushion on all trip costs
LONG_STAY_MONTHS = 6              # inflation multiplier applies above this
BUDGET_HOUSING_FACTOR = 0.70      # "budget" housing tier = 70% of standard rent
WEEKS_PER_MONTH = 4.345
DAYS_PER_MONTH = 30.437
REPEAT_PURCHASE_LIMIT = 3         # 3+ buys in a non-essential category this week -> think twice
MAX_PRICE = 1_000_000
MAX_STAY_MONTHS = 120             # 10 years
MAX_MONTHS_UNTIL_DEPARTURE = 120
STUDENT_VALUE_LIMIT = 0.10        # durable discretionary buys should stay under 10% of free cash

STUDENT_VALUE_GUIDANCE = {
    "espresso machine": {
        "kind": "durable_discretionary",
        "alternative": "Use the campus café, instant coffee, or a shared kitchen machine first.",
        "worthwhile_when": "you would use it at least 4 times a week for 12 weeks and still keep your rent buffer",
    },
    "coffee machine": {
        "kind": "durable_discretionary",
        "alternative": "Use the campus café, instant coffee, or a shared kitchen machine first.",
        "worthwhile_when": "you would use it at least 4 times a week for 12 weeks and still keep your rent buffer",
    },
    "laptop": {
        "kind": "study_enabler",
        "alternative": "Check university loan equipment, refurbished models, and student discounts first.",
        "worthwhile_when": "it is needed for study and the university cannot provide a suitable loan device",
    },
    "textbooks": {
        "kind": "study_enabler",
        "alternative": "Check the library, used copies, e-books, and module resale groups first.",
        "worthwhile_when": "the book is required and no free or used copy is available",
    },
}

CITY_ALIASES = {
    "nyc": "new york", "new york city": "new york", "manhattan": "new york",
    "bombay": "mumbai", "lisboa": "lisbon",
}

# Synthetic cost estimates in GBP (demo data, not live prices).
CITY_COSTS: dict[str, dict[str, float]] = {
    "barcelona": {"flights_return": 120, "visa_study": 0, "visa_travel": 0, "insurance_monthly": 30,
                  "rent_monthly": 750, "food_monthly": 260, "transit_monthly": 45, "annual_inflation": 0.03},
    "paris": {"flights_return": 110, "visa_study": 0, "visa_travel": 0, "insurance_monthly": 30,
              "rent_monthly": 950, "food_monthly": 300, "transit_monthly": 75, "annual_inflation": 0.025},
    "berlin": {"flights_return": 130, "visa_study": 0, "visa_travel": 0, "insurance_monthly": 30,
               "rent_monthly": 800, "food_monthly": 260, "transit_monthly": 50, "annual_inflation": 0.025},
    "amsterdam": {"flights_return": 110, "visa_study": 0, "visa_travel": 0, "insurance_monthly": 35,
                  "rent_monthly": 1100, "food_monthly": 300, "transit_monthly": 90, "annual_inflation": 0.03},
    "lisbon": {"flights_return": 140, "visa_study": 0, "visa_travel": 0, "insurance_monthly": 25,
               "rent_monthly": 700, "food_monthly": 230, "transit_monthly": 35, "annual_inflation": 0.025},
    "new york": {"flights_return": 550, "visa_study": 290, "visa_travel": 17, "insurance_monthly": 120,
                 "rent_monthly": 2200, "food_monthly": 450, "transit_monthly": 105, "annual_inflation": 0.03},
    "toronto": {"flights_return": 520, "visa_study": 115, "visa_travel": 5, "insurance_monthly": 60,
                "rent_monthly": 1400, "food_monthly": 350, "transit_monthly": 90, "annual_inflation": 0.03},
    "tokyo": {"flights_return": 750, "visa_study": 25, "visa_travel": 0, "insurance_monthly": 50,
              "rent_monthly": 800, "food_monthly": 320, "transit_monthly": 60, "annual_inflation": 0.025},
    "dubai": {"flights_return": 420, "visa_study": 250, "visa_travel": 0, "insurance_monthly": 70,
              "rent_monthly": 1300, "food_monthly": 350, "transit_monthly": 60, "annual_inflation": 0.03},
    "mumbai": {"flights_return": 550, "visa_study": 100, "visa_travel": 25, "insurance_monthly": 25,
               "rent_monthly": 450, "food_monthly": 150, "transit_monthly": 20, "annual_inflation": 0.05},
    "sydney": {"flights_return": 1100, "visa_study": 850, "visa_travel": 20, "insurance_monthly": 50,
               "rent_monthly": 1500, "food_monthly": 380, "transit_monthly": 90, "annual_inflation": 0.035},
}


def _money(value: float) -> float:
    return round(value + 0.0, 2)


# ---------------------------------------------------------------------------
# Shared user snapshot (the "shared notes" every agent reads)
# ---------------------------------------------------------------------------

def build_snapshot(connection, today: date | None = None, profile: dict | None = None) -> dict[str, Any]:
    """Summarise the user's finances from the database.

    `profile` can override derived values: monthly_income, monthly_expenses,
    rent_buffer, savings.
    """
    today = today or date.today()
    profile = {k: v for k, v in (profile or {}).items() if v is not None}

    month_start = today.replace(day=1)
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    days_left = days_in_month - today.day + 1
    thirty_days_ago = today - timedelta(days=29)
    week_ago = today - timedelta(days=6)

    rows = connection.execute(
        "SELECT amount, transaction_type, category, description, transaction_date "
        "FROM transactions WHERE transaction_date >= ? AND transaction_date <= ?",
        (min(month_start, thirty_days_ago).isoformat(), today.isoformat()),
    ).fetchall()

    income_month = income_30d = expenses_month = expenses_30d = discretionary_30d = rent_month = 0.0
    last_rent: tuple[date, float] | None = None
    earliest: date | None = None
    category_month: dict[str, float] = {}
    category_week_counts: dict[str, int] = {}

    for r in rows:
        tx_date = date.fromisoformat(r["transaction_date"])
        category = (r["category"] or "Other").strip()
        key = category.lower()
        amount = float(r["amount"])
        if not math.isfinite(amount) or amount < 0:
            continue
        in_month = tx_date >= month_start
        in_30d = tx_date >= thirty_days_ago
        earliest = tx_date if earliest is None else min(earliest, tx_date)

        if r["transaction_type"] == "income":
            income_month += amount if in_month else 0
            income_30d += amount if in_30d else 0
            continue

        if in_month:
            expenses_month += amount
            category_month[category] = category_month.get(category, 0) + amount
            if key in RENT_CATEGORIES:
                rent_month += amount
        if in_30d:
            expenses_30d += amount
            if key not in ESSENTIAL_CATEGORIES:
                discretionary_30d += amount
            if key in RENT_CATEGORIES and (last_rent is None or tx_date >= last_rent[0]):
                last_rent = (tx_date, amount)
        if tx_date >= week_ago:
            category_week_counts[key] = category_week_counts.get(key, 0) + 1

    goals = connection.execute(
        "SELECT goal_name, target_amount, current_amount, target_date FROM savings_goals"
    ).fetchall()
    savings_from_goals = sum(float(g["current_amount"]) for g in goals)

    # Rent still due this month: if rent hasn't been paid yet this month, protect
    # the last rent amount. If it has been paid, it's already in this month's spending.
    rent_due = last_rent[1] if (last_rent and rent_month == 0) else 0.0

    notes = []
    if "monthly_income" in profile:
        monthly_income = float(profile["monthly_income"])
        disposable = monthly_income - expenses_month
    elif income_month > 0:
        monthly_income = income_month
        disposable = income_month - expenses_month
    else:
        # Payday hasn't happened yet this month: use the last 30 days instead.
        monthly_income = income_30d
        disposable = income_30d - expenses_30d
        notes.append("No income yet this month, so money left is based on the last 30 days.")

    monthly_expenses = float(profile.get("monthly_expenses", expenses_30d))
    rent_buffer = float(profile.get("rent_buffer", rent_due))
    savings = float(profile.get("savings", savings_from_goals))
    disposable_left = max(disposable - rent_buffer, 0.0)

    history_days = (today - earliest).days + 1 if earliest else 0
    if monthly_income == 0:
        notes.append("No income recorded, so affordability checks will be very cautious.")
    if history_days < 21 and "monthly_expenses" not in profile:
        notes.append(f"Only {history_days} days of history, so monthly spending is a rough estimate.")

    return {
        "date": today.isoformat(),
        "days_left_in_month": days_left,
        "monthly_income": _money(monthly_income),
        "spent_this_month": _money(expenses_month),
        "spent_last_30_days": _money(expenses_30d),
        "monthly_expenses_estimate": _money(monthly_expenses),
        "monthly_discretionary_spend": _money(discretionary_30d),
        "rent_buffer": _money(rent_buffer),
        "disposable_left_this_month": _money(disposable_left),
        "safe_to_spend_daily": _money(disposable_left / days_left),
        "savings": _money(savings),
        "spending_by_category_this_month": {k: _money(v) for k, v in sorted(category_month.items())},
        "purchases_per_category_last_7_days": dict(sorted(category_week_counts.items())),
        "savings_goals": [
            {
                "name": g["goal_name"],
                "target": _money(g["target_amount"]),
                "saved": _money(g["current_amount"]),
                "target_date": g["target_date"],
            }
            for g in goals
        ],
        "has_data": bool(rows) or "monthly_income" in profile,
        "history_days": history_days,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# "Should I buy this?"
# ---------------------------------------------------------------------------

def evaluate_purchase(snapshot: dict, item: str, price: float, category: str = "Other") -> dict[str, Any]:
    if not math.isfinite(price) or price <= 0:
        raise ValueError("Price must be a number greater than zero.")
    if price > MAX_PRICE:
        raise ValueError(f"Price is too large (max £{MAX_PRICE:,}).")

    category = (category or "Other").strip() or "Other"
    essential = category.lower() in ESSENTIAL_CATEGORIES
    left = snapshot["disposable_left_this_month"]
    days_left = snapshot["days_left_in_month"]
    safe_daily = snapshot["safe_to_spend_daily"]
    counts = {k.lower(): v for k, v in snapshot["purchases_per_category_last_7_days"].items()}
    same_category_this_week = counts.get(category.lower(), 0)
    remaining_after = left - price
    item_key = " ".join((item or "").lower().split())
    guidance = next(
        (value for key, value in STUDENT_VALUE_GUIDANCE.items() if key in item_key),
        None,
    )
    student_value_kind = guidance["kind"] if guidance else "ordinary_discretionary"
    student_value_limit = _money(left * STUDENT_VALUE_LIMIT)
    student_value_concern = bool(
        guidance
        and guidance["kind"] == "durable_discretionary"
        and price > student_value_limit
    )

    if price > left and essential:
        # Never tell someone to "skip" rent or a bill; flag it so the coach offers support options.
        verdict, reason = "THINK_TWICE", "essential_but_over_budget"
    elif price > left:
        verdict, reason = "SKIP", "would_dip_into_rent_buffer" if snapshot["rent_buffer"] > 0 else "more_than_money_left_this_month"
    elif essential:
        verdict, reason = "GO", "essential_and_affordable"
    elif student_value_concern:
        verdict, reason = "THINK_TWICE", "durable_purchase_over_student_value_limit"
    elif price > 0.5 * left:
        verdict, reason = "THINK_TWICE", "uses_over_half_of_money_left_this_month"
    elif same_category_this_week >= REPEAT_PURCHASE_LIMIT:
        verdict, reason = "THINK_TWICE", "frequent_category_this_week"
    else:
        verdict, reason = "GO", "fits_flexible_budget"

    return {
        "item": item,
        "price": _money(price),
        "category": category,
        "essential": essential,
        "verdict": verdict,
        "reason_code": reason,
        "money_left_this_month_before": _money(left),
        "money_left_this_month_after": _money(max(remaining_after, 0)),
        "rent_buffer_shortfall": _money(max(-remaining_after, 0)),
        "safe_to_spend_daily_before": _money(safe_daily),
        "safe_to_spend_daily_after": _money(max(remaining_after, 0) / days_left),
        "days_of_daily_budget_this_costs": _money(price / safe_daily) if safe_daily > 0 else None,
        "same_category_purchases_last_7_days": same_category_this_week,
        "student_value": "low" if student_value_concern else ("high" if essential or guidance else "medium"),
        "student_value_kind": student_value_kind,
        "student_value_limit": student_value_limit,
        "student_value_reason": (
            f"This is above 10% of your money left after protected costs. "
            f"It may be worthwhile only if {guidance['worthwhile_when']}."
            if student_value_concern
            else (
                f"Student check: {guidance['worthwhile_when']}."
                if guidance else
                "Student check: compare the price with repeat use, a student discount, and a cheaper alternative."
            )
        ),
        "cheaper_student_alternative": guidance["alternative"] if guidance else "Check a refurbished, second-hand, library, or campus option first.",
    }


# ---------------------------------------------------------------------------
# International trip & study-abroad simulator
# ---------------------------------------------------------------------------

def list_destinations() -> list[str]:
    return sorted(CITY_COSTS)


def _stay_in_months(duration_value: float, duration_unit: str) -> float:
    unit = duration_unit.lower().rstrip("s")
    if not math.isfinite(duration_value) or duration_value <= 0:
        raise ValueError("Duration must be a number greater than zero.")
    factors = {"week": 1 / WEEKS_PER_MONTH, "month": 1.0, "year": 12.0}
    if unit not in factors:
        raise ValueError("duration_unit must be weeks, months or years.")
    months = duration_value * factors[unit]
    if months > MAX_STAY_MONTHS:
        raise ValueError(f"Stays longer than {MAX_STAY_MONTHS // 12} years aren't supported.")
    return months


def _trip_costs(city: dict, months: float, purpose: str, housing_tier: str) -> dict[str, float]:
    rent = city["rent_monthly"] * (BUDGET_HOUSING_FACTOR if housing_tier == "budget" else 1.0)
    visa = city["visa_study"] if purpose == "study" else city["visa_travel"]
    upfront = {
        "flights_return": city["flights_return"],
        "visa": visa,
        "housing_deposit": rent if months >= 1 else 0.0,
        "health_insurance": city["insurance_monthly"] * months,
    }
    monthly_living = rent + city["food_monthly"] + city["transit_monthly"]
    # Prices rise gradually over a long stay, so use the average rise across the stay.
    inflation_multiplier = 1 + city["annual_inflation"] * (months / 12) / 2 if months > LONG_STAY_MONTHS else 1.0
    living_total = monthly_living * months * inflation_multiplier
    subtotal = sum(upfront.values()) + living_total
    buffer = subtotal * CURRENCY_BUFFER_RATE
    return {
        "upfront": upfront,
        "upfront_total": sum(upfront.values()),
        "monthly_rent": rent,
        "monthly_living": monthly_living,
        "inflation_multiplier": inflation_multiplier,
        "living_total": living_total,
        "currency_buffer": buffer,
        "total": subtotal + buffer,
    }


def simulate_trip(
    snapshot: dict,
    destination: str,
    duration_value: float,
    duration_unit: str,
    purpose: str = "travel",
    months_until_departure: int = 3,
    housing_tier: str = "standard",
) -> dict[str, Any]:
    key = " ".join(destination.split(",")[0].lower().split())
    key = CITY_ALIASES.get(key, key)
    if key not in CITY_COSTS:
        raise ValueError(
            f"No cost data for '{destination}'. Known destinations: {', '.join(list_destinations())}."
        )
    purpose = "study" if purpose.lower().startswith("stud") else "travel"
    housing_tier = "budget" if housing_tier == "budget" else "standard"
    if not 0 <= months_until_departure <= MAX_MONTHS_UNTIL_DEPARTURE:
        raise ValueError(f"months_until_departure must be between 0 and {MAX_MONTHS_UNTIL_DEPARTURE}.")

    months = _stay_in_months(duration_value, duration_unit)
    costs = _trip_costs(CITY_COSTS[key], months, purpose, housing_tier)
    total = costs["total"]

    surplus = snapshot["monthly_income"] - snapshot["monthly_expenses_estimate"]
    discretionary = snapshot["monthly_discretionary_spend"]
    savings_now = snapshot["savings"]
    saving_months = months_until_departure
    projected = max(savings_now + surplus * saving_months, 0.0)
    gap = max(total - projected, 0.0)
    cut_capacity = discretionary * saving_months

    if gap == 0:
        cut_needed = 0.0
    elif cut_capacity > 0:
        cut_needed = gap / cut_capacity
    else:
        cut_needed = math.inf

    if cut_needed <= 0.5:
        verdict = "GO"
    elif cut_needed <= 1.0:
        verdict = "THINK_TWICE"
    else:
        verdict = "SKIP"

    still_needed = max(total - savings_now, 0.0)
    if saving_months > 0:
        required_monthly = still_needed / saving_months
        daily_saving = required_monthly / DAYS_PER_MONTH
    else:
        required_monthly = daily_saving = None  # leaving now: no time to save

    suggestions: dict[str, Any] = {}
    if verdict == "SKIP":
        monthly_capacity = surplus + 0.5 * discretionary
        suggestions["months_to_delay_departure_to"] = (
            math.ceil(still_needed / monthly_capacity) if monthly_capacity > 0 else None
        )
        if housing_tier == "standard":
            cheaper = _trip_costs(CITY_COSTS[key], months, purpose, "budget")
            suggestions["budget_housing_total"] = _money(cheaper["total"])
            suggestions["budget_housing_saves"] = _money(total - cheaper["total"])

    return {
        "destination": key.title(),
        "purpose": purpose,
        "stay_months": round(months, 2),
        "months_until_departure": months_until_departure,
        "housing_tier": housing_tier,
        "one_time_upfront": {k: _money(v) for k, v in costs["upfront"].items()},
        "one_time_upfront_total": _money(costs["upfront_total"]),
        "monthly_living": {
            "rent": _money(costs["monthly_rent"]),
            "food": _money(CITY_COSTS[key]["food_monthly"]),
            "transit": _money(CITY_COSTS[key]["transit_monthly"]),
            "total": _money(costs["monthly_living"]),
        },
        "living_total_for_stay": _money(costs["living_total"]),
        "inflation_multiplier": round(costs["inflation_multiplier"], 4),
        "currency_buffer_10_percent": _money(costs["currency_buffer"]),
        "total_cost": _money(total),
        "affordability": {
            "verdict": verdict,
            "savings_now": _money(savings_now),
            "monthly_surplus": _money(surplus),
            "projected_savings_by_departure": _money(projected),
            "shortfall_without_cuts": _money(gap),
            "discretionary_cut_needed_percent": None if math.isinf(cut_needed) else round(cut_needed * 100, 1),
        },
        "budget_sync": (
            {
                "save_per_month": _money(required_monthly),
                "save_per_day": _money(daily_saving),
                "safe_to_spend_daily_now": snapshot["safe_to_spend_daily"],
                "safe_to_spend_daily_with_trip_saving": _money(max(snapshot["safe_to_spend_daily"] - daily_saving, 0)),
                "saving_fits_in_daily_budget": daily_saving <= snapshot["safe_to_spend_daily"],
            }
            if daily_saving is not None
            else {"leaving_now": True, "amount_needed_from_savings": _money(total),
                  "shortfall_from_savings": _money(still_needed)}
        ),
        "suggestions": suggestions,
        "assumptions": [
            "Costs are synthetic demo estimates in GBP, not live prices.",
            "Flights are a return trip from the UK.",
            "Visa costs assume a UK passport; other nationalities may pay more.",
            "A 10% currency buffer is added to every cost.",
            f"Stays over {LONG_STAY_MONTHS} months include local inflation.",
            "Home rent during the stay is not included.",
        ],
    }
