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
BILL_CATEGORIES = {"bills", "utilities"}

CURRENCY_BUFFER_RATE = 0.10       # 10% cushion on all trip costs
LONG_STAY_MONTHS = 6              # inflation multiplier applies above this
BUDGET_HOUSING_FACTOR = 0.70      # "budget" housing tier = 70% of standard rent
WEEKS_PER_MONTH = 4.345
DAYS_PER_MONTH = 30.437
REPEAT_PURCHASE_LIMIT = 3         # 3+ buys in a non-essential category this week -> think twice
MAX_PRICE = 1_000_000
MAX_STAY_MONTHS = 120             # 10 years
MAX_MONTHS_UNTIL_DEPARTURE = 120
PAYBACK_GOOD_WEEKS = 8           # pays for itself within ~2 months -> strong value signal

# Typical lifespans and a student rule of thumb per item type. Claude picks the type
# for any item; the keyword list is only used when Claude is unavailable.
ITEM_TYPES: dict[str, dict[str, Any]] = {
    "everyday_essential": {"lifespan_months": 18, "rule_of_thumb": "usually_worth_it",
                           "hint": "Everyday essentials like walking shoes, a winter coat or bedding protect your health and comfort. For things you use daily, good quality often saves money over time."},
    "study_or_work_tool": {"lifespan_months": 36, "rule_of_thumb": "usually_worth_it",
                           "hint": "Things you need for your course or your job usually pay off. Check the library, university loan schemes and refurbished options first."},
    "health_and_safety": {"lifespan_months": 24, "rule_of_thumb": "usually_worth_it",
                          "hint": "Health and safety items (glasses, a bike helmet, medicine) are worth prioritising."},
    "kitchen_gadget": {"lifespan_months": 36, "rule_of_thumb": "usually_not_worth_it",
                       "hint": "Single-purpose kitchen gadgets are rarely worth it on a student budget, especially with running costs (pods, beans, repairs) and moving between houses. They can make sense if they replace something you already buy often."},
    "tech_gadget": {"lifespan_months": 36, "rule_of_thumb": "depends",
                    "hint": "Gadgets are worth it if you'd use them a lot and they replace something, not if they upgrade something that still works."},
    "clothing_fashion": {"lifespan_months": 18, "rule_of_thumb": "depends",
                         "hint": "Fashion buys are worth it if you'll wear them often. Trend items rarely are."},
    "furniture_or_bulky": {"lifespan_months": 48, "rule_of_thumb": "usually_not_worth_it",
                           "hint": "Bulky items are hard to move between student houses or take home after your course. Second-hand or borrowing is usually better."},
    "hobby_or_sport": {"lifespan_months": 24, "rule_of_thumb": "depends",
                       "hint": "Hobby gear is worth it if you already do the hobby regularly. Try borrowing or second-hand first."},
    "treat_or_experience": {"lifespan_months": 0, "rule_of_thumb": "depends",
                            "hint": "Treats and experiences are fine in moderation and can be good for wellbeing. Just watch how often they add up."},
    "other": {"lifespan_months": 24, "rule_of_thumb": "depends",
              "hint": "Think about how often you'd use it, whether it replaces something you pay for, and whether it can wait."},
}

_ITEM_TYPE_KEYWORDS = [
    ("kitchen_gadget", ["espresso", "coffee machine", "air fryer", "blender", "nespresso", "juicer", "toaster", "smoothie maker"]),
    ("study_or_work_tool", ["textbook", "laptop", "charger", "calculator", "printer", "course book", "work boots", "uniform"]),
    ("health_and_safety", ["glasses", "helmet", "medicine", "contact lens", "first aid", "dentist"]),
    ("everyday_essential", ["walking shoes", "trainers", "boots", "winter coat", "coat", "bedding", "duvet", "towel", "backpack", "umbrella"]),
    ("furniture_or_bulky", ["sofa", "desk", "chair", "tv", "television", "bookcase", "mattress"]),
    ("tech_gadget", ["headphones", "airpods", "earbuds", "smartwatch", "watch", "tablet", "ipad", "console", "ps5", "xbox", "speaker", "phone"]),
    ("hobby_or_sport", ["guitar", "gym", "yoga", "bike", "camera", "racket", "football"]),
    ("treat_or_experience", ["takeaway", "cinema", "concert", "festival", "meal out", "ticket", "night out"]),
    ("clothing_fashion", ["jacket", "dress", "jeans", "hoodie", "shirt", "top"]),
]


def guess_item_type(item: str) -> str:
    """Keyword fallback, only used when Claude can't classify the item."""
    words = f" {' '.join((item or '').lower().split())} "
    for item_type, keywords in _ITEM_TYPE_KEYWORDS:
        if any(f" {k}" in words for k in keywords):
            return item_type
    return "other"


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
    about_user = profile.pop("about", None)

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

    income_month = income_30d = expenses_month = expenses_30d = discretionary_30d = rent_month = bills_month = 0.0
    last_rent: tuple[date, float] | None = None
    earliest: date | None = None
    category_month: dict[str, float] = {}
    category_30d: dict[str, float] = {}
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
            if key in BILL_CATEGORIES:
                bills_month += amount
        if in_30d:
            expenses_30d += amount
            category_30d[category] = category_30d.get(category, 0) + amount
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
    # If the user told us their monthly rent and bills, protect whatever hasn't been paid yet.
    if "monthly_rent" in profile:
        rent_due = max(float(profile["monthly_rent"]) - rent_month, 0.0)
    bills_due = max(float(profile.get("monthly_bills", 0)) - bills_month, 0.0)
    if profile.get("essentials_paid_this_month"):
        rent_due = bills_due = 0.0

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

    history_days = (today - earliest).days + 1 if earliest else 0
    planned = sum(float(profile.get(k, 0)) for k in ("monthly_rent", "monthly_bills", "monthly_everyday"))
    if "monthly_expenses" in profile:
        monthly_expenses = float(profile["monthly_expenses"])
    elif planned and history_days < 21:
        # Not enough history yet: use what they told us they usually spend.
        monthly_expenses = max(expenses_30d, planned)
    else:
        monthly_expenses = expenses_30d
    rent_buffer = float(profile.get("rent_buffer", rent_due))
    savings = float(profile.get("savings", savings_from_goals))
    disposable_left = max(disposable - rent_buffer - bills_due, 0.0)

    current_balance = profile.get("current_balance")
    if current_balance is not None:
        # Never suggest spending more than they actually have right now.
        from_balance = max(float(current_balance) - rent_buffer - bills_due, 0.0)
        if from_balance < disposable_left:
            disposable_left = from_balance
            notes.append(f"Based on the £{float(current_balance):,.2f} you have right now, after rent and bills still due.")

    if monthly_income == 0:
        notes.append("No income recorded, so affordability checks will be very cautious.")
    if history_days < 21 and "monthly_expenses" not in profile and not planned:
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
        "bills_still_due_this_month": _money(bills_due),
        "current_balance": _money(float(current_balance)) if current_balance is not None else None,
        "disposable_left_this_month": _money(disposable_left),
        "safe_to_spend_daily": _money(disposable_left / days_left),
        "savings": _money(savings),
        "spending_by_category_this_month": {k: _money(v) for k, v in sorted(category_month.items())},
        "spending_by_category_last_30_days": {k: _money(v) for k, v in sorted(category_30d.items())},
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
        "about_user": about_user,
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

    if price > left and essential:
        # Never tell someone to "skip" rent or a bill; flag it so the coach offers support options.
        verdict, reason = "THINK_TWICE", "essential_but_over_budget"
    elif price > left:
        verdict, reason = "SKIP", "would_dip_into_rent_buffer" if snapshot["rent_buffer"] > 0 else "more_than_money_left_this_month"
    elif essential:
        verdict, reason = "GO", "essential_and_affordable"
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
        "short_by": _money(max(-remaining_after, 0)),
        "would_use_rent_or_bill_money": remaining_after < 0 and (snapshot["rent_buffer"] + snapshot.get("bills_still_due_this_month", 0)) > 0,
        "safe_to_spend_daily_before": _money(safe_daily),
        "safe_to_spend_daily_after": _money(max(remaining_after, 0) / days_left),
        "days_of_daily_budget_this_costs": _money(price / safe_daily) if safe_daily > 0 else None,
        "same_category_purchases_last_7_days": same_category_this_week,
    }


def assess_value(
    snapshot: dict,
    item: str,
    price: float,
    item_type: str = "other",
    uses_per_week: float | None = None,
    replaces_category: str | None = None,
    replaces_weekly_spend: float | None = None,
    replaces_cost_each: float | None = None,
    replaces_times_per_week: float | None = None,
) -> dict[str, Any]:
    """Value-for-money figures for a purchase. The worth-it judgement itself is made by
    the Buy Advisor using these facts; this function never says "buy" or "don't"."""
    if not math.isfinite(price) or not 0 < price <= MAX_PRICE:
        raise ValueError("Price must be a number greater than zero.")
    if item_type not in ITEM_TYPES:
        raise ValueError(f"item_type must be one of: {', '.join(ITEM_TYPES)}")
    if uses_per_week is not None and (not math.isfinite(uses_per_week) or not 0 < uses_per_week <= 100):
        raise ValueError("uses_per_week must be between 0 and 100.")
    if replaces_weekly_spend is not None and (not math.isfinite(replaces_weekly_spend) or not 0 < replaces_weekly_spend <= 10_000):
        raise ValueError("replaces_weekly_spend must be between 0 and 10,000.")
    if (replaces_cost_each is None) != (replaces_times_per_week is None):
        raise ValueError("Give both replaces_cost_each and replaces_times_per_week, or neither.")
    if replaces_cost_each is not None:
        if not (math.isfinite(replaces_cost_each) and 0 < replaces_cost_each <= 1000
                and math.isfinite(replaces_times_per_week) and 0 < replaces_times_per_week <= 100):
            raise ValueError("replaces_cost_each must be 0-1000 and replaces_times_per_week 0-100.")

    info = ITEM_TYPES[item_type]
    lifespan = info["lifespan_months"]
    income = snapshot["monthly_income"]
    left = snapshot["disposable_left_this_month"]
    result: dict[str, Any] = {
        "item": item,
        "price": _money(price),
        "item_type": item_type,
        "student_rule_of_thumb": info["rule_of_thumb"],
        "student_hint": info["hint"],
        "typical_lifespan_months": lifespan or None,
        "percent_of_money_left_this_month": round(price / left * 100, 1) if left > 0 else None,
        "percent_of_monthly_income": round(price / income * 100, 1) if income > 0 else None,
        "cost_per_use": None,
        "uses_over_lifespan": None,
        "replaces_spending": None,
        "notes": [],
    }

    if uses_per_week is not None and lifespan:
        uses = uses_per_week * lifespan * WEEKS_PER_MONTH
        result["uses_over_lifespan"] = round(uses)
        result["cost_per_use"] = _money(price / uses)
    elif uses_per_week is None and lifespan:
        result["notes"].append("Ask how often they'd use it to work out cost per use.")

    weekly, source = None, None
    if replaces_weekly_spend is not None:
        weekly, source = replaces_weekly_spend, "what you told me"
    elif replaces_cost_each is not None:
        weekly, source = replaces_cost_each * replaces_times_per_week, "what you told me"
    elif replaces_category:
        spend = {k.lower(): v for k, v in snapshot.get("spending_by_category_last_30_days", {}).items()}
        total = spend.get(replaces_category.strip().lower(), 0.0)
        if total > 0:
            weekly, source = total / (30 / 7), f"your {replaces_category} spending in the last 30 days"
        else:
            result["notes"].append(f"No {replaces_category} spending in the last 30 days, so it doesn't replace a current habit.")
    if weekly:
        weeks = price / weekly
        result["replaces_spending"] = {
            "weekly_spend_replaced": _money(weekly),
            "source": source,
            "pays_for_itself_in_weeks": round(weeks, 1),
            "pays_back_quickly": weeks <= PAYBACK_GOOD_WEEKS,
        }
        result["notes"].append("Payback ignores running costs like beans, pods, refills or repairs.")
    return result


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


# ---------------------------------------------------------------------------
# Financial Time Travel: future balance and what-if scenarios
# ---------------------------------------------------------------------------

TIME_TRAVEL_HORIZONS = (1, 12, 60)  # 1 month, 1 year, 5 years
TIME_TRAVEL_MAX_MONTHS = 60

# Synthetic default amounts (GBP) used when the user doesn't give their own.
WHAT_IF_SCENARIOS: dict[str, dict[str, Any]] = {
    "none": {"label": "No change", "kind": "none", "default_amount": 0},
    "phone_breaks": {"label": "Phone breaks", "kind": "one_off_cost", "default_amount": 250},
    "laptop_breaks": {"label": "Laptop breaks", "kind": "one_off_cost", "default_amount": 500},
    "rent_rises": {"label": "Rent rises", "kind": "monthly_cost_increase", "default_amount": 50},
    "lose_a_shift": {"label": "Lose a shift each week", "kind": "monthly_income_loss_per_weekly_shift", "default_amount": 60},
    "income_drops_20": {"label": "Income drops 20%", "kind": "income_percent_drop", "default_amount": 20},
}


def project_future(snapshot: dict, scenario: str = "none", amount: float | None = None,
                   months: int = TIME_TRAVEL_MAX_MONTHS) -> dict[str, Any]:
    """Project the user's savings balance month by month, with and without a what-if.

    Assumes their current monthly income and spending carry on. No interest, inflation
    or pay rises are included, so it's a simple "if nothing else changes" view.
    """
    if scenario not in WHAT_IF_SCENARIOS:
        raise ValueError(f"scenario must be one of: {', '.join(WHAT_IF_SCENARIOS)}")
    if not 1 <= months <= TIME_TRAVEL_MAX_MONTHS:
        raise ValueError(f"months must be between 1 and {TIME_TRAVEL_MAX_MONTHS}.")
    info = WHAT_IF_SCENARIOS[scenario]
    used_default = amount is None
    amount = float(info["default_amount"] if amount is None else amount)
    if not math.isfinite(amount) or amount < 0 or amount > MAX_PRICE:
        raise ValueError("amount must be a positive number.")
    if info["kind"] == "income_percent_drop" and amount > 100:
        raise ValueError("Income drop can't be more than 100%.")

    income = snapshot["monthly_income"]
    spending = snapshot["monthly_expenses_estimate"]
    essentials = max(spending - snapshot.get("monthly_discretionary_spend", 0.0), 0.0)
    start = snapshot["savings"]

    one_off = income_change = cost_change = 0.0
    kind = info["kind"]
    if kind == "one_off_cost":
        one_off = amount
    elif kind == "monthly_cost_increase":
        cost_change = amount
    elif kind == "monthly_income_loss_per_weekly_shift":
        income_change = -amount * WEEKS_PER_MONTH
    elif kind == "income_percent_drop":
        income_change = -income * amount / 100

    base_net = income - spending
    what_if_net = base_net + income_change - cost_change

    def series(net: float, shock: float) -> list[float]:
        return [_money(start - shock + net * m) for m in range(months + 1)]

    baseline, what_if = series(base_net, 0.0), series(what_if_net, one_off)

    def first_negative(values: list[float]) -> int | None:
        return next((m for m, v in enumerate(values) if v < 0), None)

    def at(values: list[float]) -> dict[str, float]:
        return {f"{h}_months": values[h] for h in TIME_TRAVEL_HORIZONS if h <= months}

    result = {
        "scenario": scenario,
        "scenario_label": info["label"],
        "amount_used": _money(amount),
        "amount_is_default_estimate": used_default and scenario != "none",
        "starting_savings": _money(start),
        "monthly_net_now": _money(base_net),
        "monthly_net_with_what_if": _money(what_if_net),
        "one_off_cost": _money(one_off),
        "baseline_balance": at(baseline),
        "what_if_balance": at(what_if),
        "difference_after": {k: _money(what_if[int(k.split('_')[0])] - baseline[int(k.split('_')[0])])
                             for k in at(baseline)},
        "baseline_runs_out_in_month": first_negative(baseline),
        "what_if_runs_out_in_month": first_negative(what_if),
        "months_of_essentials_covered_now": round(start / essentials, 1) if essentials > 0 else None,
        "monthly_balances": {"baseline": baseline, "what_if": what_if},  # for the Time Travel slider/chart
        "assumptions": [
            "Your current monthly income and spending carry on unchanged.",
            "No interest, inflation or pay rises are included.",
            "Changes like a rent rise or lost shift are assumed to last for the whole period.",
        ],
        "notes": list(snapshot.get("notes", [])),
    }
    if result["amount_is_default_estimate"]:
        result["notes"].append(f"Used a typical amount (£{amount:,.0f}) because none was given.")
    return result
