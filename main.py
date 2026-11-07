
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import date
from collections import defaultdict

from database import get_connection, create_tables

app = FastAPI(title="NatWest Financial Tracker")

create_tables()


# -----------------------------
# TRANSACTION MODEL
# -----------------------------

class Transaction(BaseModel):
    amount: float
    transaction_type: str  # income or expense
    category: str
    description: str = ""
    transaction_date: date


# -----------------------------
# ADD TRANSACTION
# -----------------------------

@app.post("/transactions")
def add_transaction(transaction: Transaction):

    if transaction.amount <= 0:
        raise HTTPException(400, "Amount must be greater than zero")

    if transaction.transaction_type not in ["income", "expense"]:
        raise HTTPException(400, "Type must be income or expense")

    connection = get_connection()

    cursor = connection.execute("""
        INSERT INTO transactions
        (amount, transaction_type, category, description, transaction_date)
        VALUES (?, ?, ?, ?, ?)
    """, (
        transaction.amount,
        transaction.transaction_type,
        transaction.category,
        transaction.description,
        transaction.transaction_date.isoformat()
    ))

    connection.commit()
    transaction_id = cursor.lastrowid
    connection.close()

    return {
        "message": "Transaction added successfully",
        "transaction_id": transaction_id
    }


# -----------------------------
# DAILY TRACKER
# -----------------------------

@app.get("/daily/{selected_date}")
def daily_tracker(selected_date: date):

    connection = get_connection()

    transactions = connection.execute("""
        SELECT * FROM transactions
        WHERE transaction_date = ?
        ORDER BY id DESC
    """, (selected_date.isoformat(),)).fetchall()

    connection.close()

    income = sum(
        t["amount"] for t in transactions
        if t["transaction_type"] == "income"
    )

    expenses = sum(
        t["amount"] for t in transactions
        if t["transaction_type"] == "expense"
    )

    return {
        "date": selected_date,
        "income": round(income, 2),
        "expenses": round(expenses, 2),
        "daily_balance": round(income - expenses, 2),
        "transactions": [dict(t) for t in transactions]
    }


# -----------------------------
# MONTHLY TRACKER
# -----------------------------

@app.get("/monthly/{year}/{month}")
def monthly_tracker(year: int, month: int):

    if month < 1 or month > 12:
        raise HTTPException(400, "Invalid month")

    month_key = f"{year:04d}-{month:02d}"

    connection = get_connection()

    transactions = connection.execute("""
        SELECT * FROM transactions
        WHERE transaction_date LIKE ?
    """, (month_key + "%",)).fetchall()

    connection.close()

    income = 0
    expenses = 0
    category_totals = defaultdict(float)
    daily_totals = defaultdict(float)

    for t in transactions:

        amount = t["amount"]

        if t["transaction_type"] == "income":
            income += amount

        else:
            expenses += amount
            category_totals[t["category"]] += amount
            daily_totals[t["transaction_date"]] += amount

    return {
        "month": month_key,
        "total_income": round(income, 2),
        "total_expenses": round(expenses, 2),
        "remaining_balance": round(income - expenses, 2),

        # Data for pie chart
        "category_breakdown": {
            category: round(amount, 2)
            for category, amount in category_totals.items()
        },

        # Data for daily spending graph
        "daily_spending": [
            {"date": day, "amount": round(amount, 2)}
            for day, amount in sorted(daily_totals.items())
        ]
    }


# -----------------------------
# SAVINGS AND FINANCIAL ADVICE
# -----------------------------

@app.get("/financial-advice/{year}/{month}")
def financial_advice(year: int, month: int):

    summary = monthly_tracker(year, month)

    income = summary["total_income"]
    expenses = summary["total_expenses"]
    balance = summary["remaining_balance"]

    advice = []

    if income == 0:
        advice.append(
            "Add your income to receive personalised savings insights."
        )

    else:
        savings_rate = (balance / income) * 100

        if savings_rate < 0:
            advice.append(
                "Your expenses are higher than your income. "
                "Review non-essential spending and upcoming bills."
            )

        elif savings_rate < 10:
            advice.append(
                "Try setting aside a small amount regularly. "
                "Start with an achievable savings target."
            )

        elif savings_rate < 20:
            advice.append(
                "Good progress. Consider gradually increasing "
                "your monthly savings."
            )

        else:
            advice.append(
                "Great savings progress. Consider building "
                "your emergency fund and longer-term savings."
            )

        advice.append(
            f"Your savings rate this month is {savings_rate:.1f}%."
        )

    if balance > 0:
        advice.append(
            f"You have £{balance:.2f} remaining based on "
            "the transactions recorded this month."
        )

    return {
        "month": summary["month"],
        "savings_rate": (
            round((balance / income) * 100, 2)
            if income > 0 else None
        ),
        "advice": advice
    }


# -----------------------------
# HOME PAGE / API CHECK
# -----------------------------

@app.get("/")
def home():
    return {
        "message": "NatWest Financial Tracker API is running!"
    }


# -----------------------------
# SAVINGS GOALS
# -----------------------------

class SavingsGoal(BaseModel):
    goal_name: str
    target_amount: float
    current_amount: float = 0
    target_date: date


@app.post("/savings-goals")
def create_savings_goal(goal: SavingsGoal):

    if goal.target_amount <= 0 or goal.current_amount < 0:
        raise HTTPException(400, "Invalid savings amount")

    if goal.current_amount > goal.target_amount:
        raise HTTPException(400, "Current savings cannot exceed target")

    connection = get_connection()

    cursor = connection.execute("""
        INSERT INTO savings_goals
        (goal_name, target_amount, current_amount, target_date)
        VALUES (?, ?, ?, ?)
    """, (
        goal.goal_name,
        goal.target_amount,
        goal.current_amount,
        goal.target_date.isoformat()
    ))

    connection.commit()
    goal_id = cursor.lastrowid
    connection.close()

    return {
        "message": "Savings goal created",
        "goal_id": goal_id
    }


@app.get("/savings-goals")
def get_savings_goals():

    connection = get_connection()

    goals = connection.execute(
        "SELECT * FROM savings_goals"
    ).fetchall()

    connection.close()

    results = []

    for goal in goals:

        remaining = goal["target_amount"] - goal["current_amount"]

        progress = (
            goal["current_amount"] / goal["target_amount"]
        ) * 100

        results.append({
            "id": goal["id"],
            "goal_name": goal["goal_name"],
            "target_amount": goal["target_amount"],
            "current_amount": goal["current_amount"],
            "remaining_amount": round(remaining, 2),
            "progress_percentage": round(progress, 2),
            "target_date": goal["target_date"]
        })

    return {"goals": results}


# -----------------------------
# EMERGENCY FUND CALCULATOR
# -----------------------------

class EmergencyFundInput(BaseModel):
    monthly_essential_expenses: float
    current_emergency_savings: float


@app.post("/emergency-fund")
def calculate_emergency_fund(data: EmergencyFundInput):

    if data.monthly_essential_expenses <= 0:
        raise HTTPException(400, "Expenses must be greater than zero")

    if data.current_emergency_savings < 0:
        raise HTTPException(400, "Savings cannot be negative")

    three_month_target = data.monthly_essential_expenses * 3
    six_month_target = data.monthly_essential_expenses * 6

    remaining_for_three = max(
        0, three_month_target - data.current_emergency_savings
    )

    remaining_for_six = max(
        0, six_month_target - data.current_emergency_savings
    )

    return {
        "current_savings": data.current_emergency_savings,
        "three_month_target": three_month_target,
        "six_month_target": six_month_target,
        "remaining_for_three_month_target": remaining_for_three,
        "remaining_for_six_month_target": remaining_for_six,
        "message": "A useful starting target is 3–6 months of essential expenses."
    }


# -----------------------------
# AI COACH AGENTS
# (Coach + Buy Advisor + Trip Planner, see coach/agents.py)
# -----------------------------

import os
from typing import Literal, Optional

from fastapi.middleware.cors import CORSMiddleware
from pydantic import Field

from coach import agents, rules_engine
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request, exc: RequestValidationError):
    """Return validation errors without echoing the input (NaN/Infinity can't be sent as JSON)."""
    errors = [{"loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class Profile(BaseModel):
    """Optional overrides when the database doesn't have the full picture yet."""
    monthly_income: Optional[float] = Field(None, ge=0, le=1_000_000, allow_inf_nan=False)
    monthly_expenses: Optional[float] = Field(None, ge=0, le=1_000_000, allow_inf_nan=False)
    rent_buffer: Optional[float] = Field(None, ge=0, le=1_000_000, allow_inf_nan=False)
    savings: Optional[float] = Field(None, ge=0, le=10_000_000, allow_inf_nan=False)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=8000)


class CoachRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatMessage] = Field([], max_length=40)
    profile: Optional[Profile] = None


class BuyCheckRequest(BaseModel):
    item: str = Field(..., min_length=1, max_length=200)
    price: float = Field(..., gt=0, le=1_000_000, allow_inf_nan=False)
    category: str = Field("Other", max_length=50)
    profile: Optional[Profile] = None


class TripPlanRequest(BaseModel):
    destination: str = Field(..., min_length=1, max_length=100)
    duration_value: float = Field(..., gt=0, le=520, allow_inf_nan=False)
    duration_unit: Literal["weeks", "months", "years"] = "weeks"
    purpose: Literal["travel", "study"] = "travel"
    months_until_departure: int = Field(3, ge=0, le=120)
    housing_tier: Literal["standard", "budget"] = "standard"
    profile: Optional[Profile] = None


def _snapshot(profile: Optional[Profile]) -> dict:
    connection = get_connection()
    try:
        return rules_engine.build_snapshot(
            connection, profile=profile.model_dump() if profile else None
        )
    finally:
        connection.close()


def _coach_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except agents.CoachUnavailable as exc:
        raise HTTPException(503, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/snapshot")
def get_snapshot():
    """The figures every agent works from (no AI call)."""
    return _snapshot(None)


@app.get("/api/trip-destinations")
def get_trip_destinations():
    return {"destinations": rules_engine.list_destinations()}


@app.post("/api/coach")
def coach(request: CoachRequest):
    """Chat with the Coach. It hands off to the Buy Advisor / Trip Planner as needed."""
    return _coach_call(
        agents.coach_chat,
        _snapshot(request.profile),
        request.message,
        [m.model_dump() for m in request.history],
    )


@app.post("/api/buy-check")
def buy_check(request: BuyCheckRequest):
    """'Should I buy this?' Verdict from the rules engine, explanation from Claude."""
    return _coach_call(
        agents.buy_check,
        _snapshot(request.profile),
        request.item,
        request.price,
        request.category,
    )


@app.post("/api/trip-plan")
def trip_plan(request: TripPlanRequest):
    """Trip / study-abroad simulator. Costs from the rules engine, explanation from Claude."""
    return _coach_call(
        agents.trip_plan,
        _snapshot(request.profile),
        request.destination,
        request.duration_value,
        request.duration_unit,
        request.purpose,
        request.months_until_departure,
        request.housing_tier,
    )


from fastapi.responses import FileResponse


@app.get("/chat", include_in_schema=False)
def chat_page():
    """Simple test chat page for the coach."""
    return FileResponse(os.path.join(os.path.dirname(__file__), "coach", "chat.html"))


# -----------------------------
# TRAINING MODE (teach the coach rules -> coach/coach_rules.md)
# Only available when the server is started with TRAINING_MODE=1
# -----------------------------

from fastapi.responses import PlainTextResponse

from coach import training


def _require_training_mode():
    if os.environ.get("TRAINING_MODE") != "1":
        raise HTTPException(404, "Training mode is off. Start the server with TRAINING_MODE=1.")


class TrainRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[ChatMessage] = []


@app.get("/train", include_in_schema=False)
def train_page():
    _require_training_mode()
    return FileResponse(os.path.join(os.path.dirname(__file__), "coach", "chat.html"))


@app.post("/api/train")
def train(request: TrainRequest):
    _require_training_mode()
    return _coach_call(agents.train_chat, request.message, [m.model_dump() for m in request.history])


@app.get("/api/train/rules", response_class=PlainTextResponse)
def train_rules():
    _require_training_mode()
    return training.rules_markdown()
