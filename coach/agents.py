"""Coach, Buy Advisor and Trip Planner agents.

How they talk to each other:
- All three read one shared AgentContext built fresh for each request. It holds
  the user's financial snapshot and a log of every calculation run.
  (This is the "shared notes" idea, kept as structured data instead of a file
  so numbers stay exact and users never see each other's data.)
- The Coach is the only agent the user chats with. It hands questions to the
  specialists through the ask_buy_advisor / ask_trip_planner tools and gets
  back their reply plus the exact figures they used.
- Specialists get their numbers only from tools backed by rules_engine.py.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import anthropic

from . import rules_engine, training

MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOOL_ROUNDS = 8
MAX_HISTORY_MESSAGES = 20

REFUSAL_REPLY = (
    "Sorry, I can't help with that one. If you're worried about money, "
    "you can always ask to speak to someone at your bank."
)


class CoachUnavailable(RuntimeError):
    """Raised when the Claude API can't be reached or isn't configured."""


# ---------------------------------------------------------------------------
# Shared context
# ---------------------------------------------------------------------------

@dataclass
class AgentContext:
    snapshot: dict[str, Any]
    calculations: list[dict[str, Any]] = field(default_factory=list)
    new_facts: list[str] = field(default_factory=list)  # saved by the bots, returned to the website

    def record(self, agent: str, tool: str, result: dict[str, Any]) -> None:
        self.calculations.append({"agent": agent, "tool": tool, "result": result})

    def last(self, tool: str) -> dict[str, Any] | None:
        for entry in reversed(self.calculations):
            if entry["tool"] == tool:
                return entry["result"]
        return None


ToolHandler = Callable[[dict[str, Any], AgentContext], dict[str, Any]]


@dataclass
class Agent:
    name: str
    system: str
    tools: list[dict[str, Any]]
    handlers: dict[str, ToolHandler]
    effort: str = "medium"


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SHARED_RULES = """\
You are part of PennyWise, a money coach for people on tight or irregular budgets: \
students, gig workers, single parents, pensioners and new migrants in the UK.

Rules you must always follow:
- Numbers come only from tool results. Never calculate, estimate, round differently or \
invent a figure. If a number you need isn't in a tool result, say you don't have it.
- Use plain, warm, non-judgemental English. Short sentences. No jargon; if you must use a \
banking term, explain it in a few words.
- Never shame the user. Never approve credit. Never suggest payday loans or stacking \
Buy Now Pay Later.
- If someone is in financial difficulty, mention that they can talk to their bank or a \
free service like Citizens Advice or StepChange.
- This is guidance, not regulated financial advice.
- Use what you know about the user (see "About this user") to tailor advice, e.g. visa \
rules for international students, irregular income for gig workers, fixed income for \
pensioners. Don't repeat their details back to them unless it helps.
- If something important for a good answer is missing (for example whether their income \
is regular, when they get paid, or what they're saving for), ask one short question. \
Don't ask for things you already know.
- When the user tells you something lasting about themselves (their course, visa, job, \
dependants, payday, regular costs, goals), save it with remember_about_user so PennyWise \
remembers next time. Don't save one-off questions or anything they didn't say.
- If a tool result has "notes" (for example limited history), mention them briefly so the \
user knows how reliable the figures are.
- If a purchase reason_code is "essential_but_over_budget", don't tell them to skip it. \
Gently say it's more than they have left, and suggest talking to the bill provider or \
their bank about a payment plan, or free help from Citizens Advice or StepChange.
- Verdicts are GO, THINK_TWICE or SKIP. Show them to users as "Go", "Think twice" or \
"Skip for now", and always use the verdict the tool returned."""

BUY_ADVISOR_SYSTEM = SHARED_RULES + """

You are the Buy Advisor. For any purchase you answer two separate questions:
A) Can they afford it right now? This comes only from evaluate_purchase.
B) Is it worth it for a student on a tight budget? This is your judgement, using the \
facts from assess_value and the guide below. Record it with record_worth_verdict.

Steps:
1. Work out the item, the price in pounds, a spending category (Food, Transport, Shopping, \
Entertainment, Bills, Healthcare, Education, Other) and an item_type. If the price is \
missing, ask for it instead of guessing.
2. Call evaluate_purchase and assess_value. For assess_value, only pass usage or spending \
the user told you (convert "every day" to 7). If they give a price per time and how often \
("£3.20 a coffee, 5 times a week"), pass replaces_cost_each and replaces_times_per_week and \
let the tool multiply. Never multiply or add numbers yourself. If the item would \
replace something they buy regularly (an espresso machine replaces coffee out, a bike \
replaces bus fares), pass replaces_category with the category they'd normally spend it in.
3. Decide worth (WORTH_IT, DEPENDS or NOT_WORTH_IT) and call record_worth_verdict.
4. Reply: both verdicts, the main reasons, and one cheaper or better option (no prices).

Student worth-it guide:
- Usually worth it: things that protect health, safety, study or the ability to work. \
For example good walking shoes for someone who walks a lot, a warm winter coat, bedding, \
a laptop or charger needed for coursework, required textbooks (library and second-hand \
first), a bike or bus pass that cuts transport costs. For things used every day, paying a \
bit more for quality often saves money over time.
- Usually not worth it: single-purpose or luxury gadgets (an espresso machine, an air fryer \
when there's an oven), upgrading something that still works, trend or impulse buys, items \
with running costs (pods, refills, subscriptions), and bulky things that are hard to move \
between student houses or take home after the course.
- Start from the student_rule_of_thumb in assess_value, then adjust with the facts:
  - usually_not_worth_it: say NOT_WORTH_IT unless they've shown it replaces a regular \
spend that pays back quickly (pays_back_quickly true), then DEPENDS or WORTH_IT.
  - usually_worth_it: say WORTH_IT unless the price looks far above what the need calls for.
  - depends: low cost_per_use for something used often, or a quick payback, points to \
WORTH_IT. If you don't know how often they'd use it, say DEPENDS and ask.
- Affordability and worth are separate. Something can be affordable but not worth it (an \
espresso machine), or worth it but not affordable right now (good shoes when money is \
tight). In that case suggest ways to make room for it, or a good-quality cheaper route \
like outlet stores, sales or second-hand in good condition.
- If they've already bought it, never make them feel bad. Be honest about the value, \
suggest how to get the most out of it, and if it isn't worth it, mention they may be able \
to return it within the shop's returns window.

When the message says it comes from the purchase tracker, keep it to about 90 words: \
both verdicts, the main reason, and end with one friendly question whose answer could \
change your view (for example how often they'd use it, or how much they spend on coffee \
out each week)."""

TRIP_PLANNER_SYSTEM = SHARED_RULES + """

You are the Trip Planner. You plan trips and study-abroad stays and test whether \
the user can afford them.
1. You need: destination city, how long (weeks/months/years), purpose (study or \
travel), and how many months until they leave. If something important is missing, \
use a sensible default (travel, 3 months until departure) and say what you assumed.
2. Call simulate_trip. If the city isn't supported, tell the user which cities are.
3. If the verdict is SKIP and a budget-housing option is in the result, you may call \
simulate_trip again with housing_tier "budget" to compare.
4. Reply with: total cost, the split between one-time upfront and monthly living costs, \
the verdict, and how much to save per day to get there. Mention the 10% currency buffer. \
Keep it under 150 words."""

COACH_SYSTEM = SHARED_RULES + """

You are the Coach, the friendly front door of PennyWise. You chat with the user about \
their money.
- For "should I buy X?", "can I afford X?" or "is X worth it?" about an item, call \
ask_buy_advisor. If you're continuing a chat about a purchase, include the item, price \
and everything the user has told you since (how often they'd use it, what it replaces).
- The Buy Advisor gives two verdicts: whether they can afford it and whether it's worth \
it. Pass on both.
- For trips, holidays, moving or studying abroad, call ask_trip_planner.
- For general questions about their spending, call get_financial_snapshot.
- For "where will I be in a year?" or "what if my rent goes up / I lose shifts / my phone \
breaks?", call project_future. Give the key figures it returns, say whether and when money \
would run out, mention if a typical amount was used, and suggest the Financial Time Travel \
screen to explore it with the slider. Be calm and practical, never alarming.
- For explaining a banking term, just answer.
Pass the specialist the user's full question, including any prices, places and dates. \
When a specialist replies, pass on its answer in your own voice without changing any \
number or verdict. Keep replies short and conversational."""


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

SNAPSHOT_TOOL = {
    "name": "get_financial_snapshot",
    "description": (
        "Get the user's current finances: income, spending this month and last 30 days, "
        "spending by category, rent buffer, money left this month, daily safe-to-spend, "
        "savings and savings goals. All amounts in GBP."
    ),
    "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
}

EVALUATE_PURCHASE_TOOL = {
    "name": "evaluate_purchase",
    "description": (
        "Check whether the user can afford a purchase right now. Returns a verdict "
        "(GO, THINK_TWICE or SKIP), a reason code, and the effect on money left this month "
        "and on daily safe-to-spend."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "item": {"type": "string", "description": "What they want to buy, e.g. 'new trainers'."},
            "price": {"type": "number", "description": "Price in GBP."},
            "category": {
                "type": "string",
                "description": "Spending category, e.g. Food, Transport, Shopping, Entertainment, Bills.",
            },
        },
        "required": ["item", "price", "category"],
        "additionalProperties": False,
    },
}

REMEMBER_TOOL = {
    "name": "remember_about_user",
    "description": "Save one short, lasting fact the user told you about themselves, e.g. 'On a Student visa, can work 20 hours a week in term time'.",
    "input_schema": {
        "type": "object",
        "properties": {"fact": {"type": "string", "description": "One short fact in the third person, under 200 characters."}},
        "required": ["fact"],
        "additionalProperties": False,
    },
}

ASSESS_VALUE_TOOL = {
    "name": "assess_value",
    "description": (
        "Value-for-money facts for a purchase: the student rule of thumb for this type of item, "
        "typical lifespan, share of money left and of income, cost per use (if uses_per_week is "
        "given), and how fast it pays for itself if it replaces a regular spend."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "item": {"type": "string"},
            "price": {"type": "number", "description": "Price in GBP."},
            "item_type": {"type": "string", "enum": list(rules_engine.ITEM_TYPES)},
            "uses_per_week": {"type": "number", "description": "Only if the user said how often they'd use it."},
            "replaces_category": {
                "type": "string",
                "description": "Spending category this would replace, e.g. 'Coffee' or 'Transport'.",
            },
            "replaces_weekly_spend": {
                "type": "number",
                "description": "Only if the user gave a weekly total for what this replaces.",
            },
            "replaces_cost_each": {
                "type": "number",
                "description": "If the user gave a price per time instead (e.g. £3.20 per coffee). Use with replaces_times_per_week.",
            },
            "replaces_times_per_week": {
                "type": "number",
                "description": "How many times a week they buy what this replaces (e.g. 5 coffees). Use with replaces_cost_each.",
            },
        },
        "required": ["item", "price", "item_type"],
        "additionalProperties": False,
    },
}

WORTH_VERDICTS = ("WORTH_IT", "DEPENDS", "NOT_WORTH_IT")
NEED_LEVELS = ("essential", "useful", "nice_to_have", "impulse")

RECORD_WORTH_TOOL = {
    "name": "record_worth_verdict",
    "description": "Record your judgement of whether this purchase is worth it for a student.",
    "input_schema": {
        "type": "object",
        "properties": {
            "item": {"type": "string"},
            "worth_verdict": {"type": "string", "enum": list(WORTH_VERDICTS)},
            "need_level": {"type": "string", "enum": list(NEED_LEVELS)},
            "reasons": {
                "type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3,
                "description": "1-3 short plain-English reasons, no figures that aren't from tools.",
            },
            "better_option": {"type": "string", "description": "One cheaper or better option, without a price."},
        },
        "required": ["item", "worth_verdict", "need_level", "reasons", "better_option"],
        "additionalProperties": False,
    },
}

PROJECT_FUTURE_TOOL = {
    "name": "project_future",
    "description": (
        "Financial Time Travel calculator. Projects the user's savings balance at 1 month, 1 year "
        "and 5 years if nothing changes, and with a what-if scenario: phone_breaks, laptop_breaks, "
        "rent_rises, lose_a_shift or income_drops_20. Shows when money would run out, if ever."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "scenario": {"type": "string", "enum": list(rules_engine.WHAT_IF_SCENARIOS)},
            "amount": {
                "type": "number",
                "description": (
                    "Only if the user gave it: repair cost for phone/laptop, monthly rent increase, "
                    "pay per shift for lose_a_shift, or the percentage for income_drops_20. "
                    "Leave out to use a typical amount."
                ),
            },
        },
        "required": ["scenario"],
        "additionalProperties": False,
    },
}

LIST_DESTINATIONS_TOOL = {
    "name": "list_destinations",
    "description": "List the cities the trip simulator has cost data for.",
    "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
}

SIMULATE_TRIP_TOOL = {
    "name": "simulate_trip",
    "description": (
        "Cost a trip or study-abroad stay and test it against the user's finances. "
        "Returns one-time upfront costs, monthly living costs, a 10% currency buffer, "
        "the total, an affordability verdict (GO, THINK_TWICE or SKIP) and how much to save per day."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "destination": {"type": "string", "description": "City name, e.g. 'Barcelona'."},
            "duration_value": {"type": "number", "description": "Length of stay, e.g. 2."},
            "duration_unit": {"type": "string", "enum": ["weeks", "months", "years"]},
            "purpose": {"type": "string", "enum": ["travel", "study"]},
            "months_until_departure": {"type": "integer", "description": "Months from now until they leave."},
            "housing_tier": {"type": "string", "enum": ["standard", "budget"]},
        },
        "required": [
            "destination", "duration_value", "duration_unit",
            "purpose", "months_until_departure", "housing_tier",
        ],
        "additionalProperties": False,
    },
}


def _delegate_tool(name: str, description: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The user's question with every detail they gave (items, prices, places, dates).",
                }
            },
            "required": ["question"],
            "additionalProperties": False,
        },
    }


def _snapshot_handler(_: dict, ctx: AgentContext) -> dict:
    return ctx.snapshot


def _evaluate_purchase_handler(args: dict, ctx: AgentContext) -> dict:
    return rules_engine.evaluate_purchase(
        ctx.snapshot, str(args["item"]), float(args["price"]), str(args.get("category") or "Other")
    )


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _same_fact(a: str, b: str) -> bool:
    wa, wb = _words(a), _words(b)
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.75


def _remember_handler(args: dict, ctx: AgentContext) -> dict:
    fact = " ".join(str(args.get("fact", "")).split())[:200]
    if not fact:
        raise ValueError("The fact is empty.")
    known = list((ctx.snapshot.get("about_user") or {}).get("facts", [])) + ctx.new_facts
    if any(_same_fact(fact, k) for k in known):
        return {"saved": False, "reason": "Already known."}
    if len(ctx.new_facts) >= 5:
        raise ValueError("Already saved 5 facts this turn.")
    ctx.new_facts.append(fact)
    return {"saved": True, "fact": fact}


def _assess_value_handler(args: dict, ctx: AgentContext) -> dict:
    def opt(name):
        value = args.get(name)
        return float(value) if value is not None else None

    return rules_engine.assess_value(
        ctx.snapshot, str(args["item"]), float(args["price"]), str(args.get("item_type") or "other"),
        uses_per_week=opt("uses_per_week"),
        replaces_category=(str(args["replaces_category"]) if args.get("replaces_category") else None),
        replaces_weekly_spend=opt("replaces_weekly_spend"),
        replaces_cost_each=opt("replaces_cost_each"),
        replaces_times_per_week=opt("replaces_times_per_week"),
    )


def _record_worth_handler(args: dict, ctx: AgentContext) -> dict:
    """Validate Claude's worth-it judgement before it's shown to anyone."""
    verdict, need = args.get("worth_verdict"), args.get("need_level")
    if verdict not in WORTH_VERDICTS:
        raise ValueError(f"worth_verdict must be one of {WORTH_VERDICTS}")
    if need not in NEED_LEVELS:
        raise ValueError(f"need_level must be one of {NEED_LEVELS}")
    reasons = [" ".join(str(r).split())[:240] for r in (args.get("reasons") or []) if str(r).strip()]
    if not 1 <= len(reasons) <= 3:
        raise ValueError("Give between 1 and 3 reasons.")
    return {
        "item": str(args.get("item", ""))[:200],
        "worth_verdict": verdict,
        "need_level": need,
        "reasons": reasons,
        "better_option": " ".join(str(args.get("better_option", "")).split())[:240],
    }


def _project_future_handler(args: dict, ctx: AgentContext) -> dict:
    amount = args.get("amount")
    result = rules_engine.project_future(
        ctx.snapshot, str(args.get("scenario") or "none"), float(amount) if amount is not None else None
    )
    # The month-by-month series is for charts; the agent only needs the summary.
    return {k: v for k, v in result.items() if k != "monthly_balances"}


def _list_destinations_handler(_: dict, ctx: AgentContext) -> dict:
    return {"destinations": rules_engine.list_destinations()}


def _simulate_trip_handler(args: dict, ctx: AgentContext) -> dict:
    return rules_engine.simulate_trip(
        ctx.snapshot,
        destination=str(args["destination"]),
        duration_value=float(args["duration_value"]),
        duration_unit=str(args["duration_unit"]),
        purpose=str(args.get("purpose") or "travel"),
        months_until_departure=int(args.get("months_until_departure", 3)),
        housing_tier=str(args.get("housing_tier") or "standard"),
    )


BUY_ADVISOR = Agent(
    name="buy_advisor",
    system=BUY_ADVISOR_SYSTEM,
    tools=[SNAPSHOT_TOOL, EVALUATE_PURCHASE_TOOL, ASSESS_VALUE_TOOL, RECORD_WORTH_TOOL, REMEMBER_TOOL],
    handlers={
        "get_financial_snapshot": _snapshot_handler,
        "remember_about_user": _remember_handler,
        "evaluate_purchase": _evaluate_purchase_handler,
        "assess_value": _assess_value_handler,
        "record_worth_verdict": _record_worth_handler,
    },
    effort="low",
)

TRIP_PLANNER = Agent(
    name="trip_planner",
    system=TRIP_PLANNER_SYSTEM,
    tools=[SNAPSHOT_TOOL, LIST_DESTINATIONS_TOOL, SIMULATE_TRIP_TOOL, REMEMBER_TOOL],
    handlers={
        "get_financial_snapshot": _snapshot_handler,
        "remember_about_user": _remember_handler,
        "list_destinations": _list_destinations_handler,
        "simulate_trip": _simulate_trip_handler,
    },
    effort="low",
)


def _without_memory(agent: Agent) -> Agent:
    """When the Coach hands off, it does the remembering; the specialist just answers."""
    return Agent(
        name=agent.name, system=agent.system, effort=agent.effort,
        tools=[t for t in agent.tools if t["name"] != "remember_about_user"],
        handlers={k: v for k, v in agent.handlers.items() if k != "remember_about_user"},
    )


def _make_delegate(client: anthropic.Anthropic, specialist: Agent) -> ToolHandler:
    specialist = _without_memory(specialist)

    def handler(args: dict, ctx: AgentContext) -> dict:
        start = len(ctx.calculations)
        reply = run_agent(client, specialist, [{"role": "user", "content": str(args["question"])}], ctx)
        facts = [c["result"] for c in ctx.calculations[start:] if c["tool"] != "get_financial_snapshot"]
        return {"specialist_reply": reply, "figures_used": facts}

    return handler


def make_coach(client: anthropic.Anthropic) -> Agent:
    return Agent(
        name="coach",
        system=COACH_SYSTEM,
        tools=[
            SNAPSHOT_TOOL,
            REMEMBER_TOOL,
            _delegate_tool("ask_buy_advisor", "Ask the Buy Advisor whether the user should buy a specific item."),
            _delegate_tool("ask_trip_planner", "Ask the Trip Planner to cost a trip or study-abroad stay and check affordability."),
            PROJECT_FUTURE_TOOL,
        ],
        handlers={
            "get_financial_snapshot": _snapshot_handler,
            "remember_about_user": _remember_handler,
            "ask_buy_advisor": _make_delegate(client, BUY_ADVISOR),
            "ask_trip_planner": _make_delegate(client, TRIP_PLANNER),
            "project_future": _project_future_handler,
        },
        effort="medium",
    )


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

def _run_tool(agent: Agent, block, ctx: AgentContext) -> dict[str, Any]:
    handler = agent.handlers.get(block.name)
    if handler is None:
        return {"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                "content": f"Unknown tool: {block.name}"}
    try:
        result = handler(dict(block.input or {}), ctx)
    except (KeyError, TypeError, ValueError) as exc:
        return {"type": "tool_result", "tool_use_id": block.id, "is_error": True, "content": str(exc)}
    ctx.record(agent.name, block.name, result)
    return {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)}


PERSONA_LABELS = {
    "international_student": "international student", "student": "UK student", "gig_worker": "gig worker",
    "single_parent": "single parent", "pensioner": "pensioner", "new_migrant": "new migrant to the UK",
    "working": "working", "other": "other",
}


def about_user_block(snapshot: dict) -> str:
    about = snapshot.get("about_user")
    if not about:
        return ""
    lines = [f"- They are: {PERSONA_LABELS.get(about.get('persona'), 'other')}"]
    if about.get("name"):
        lines.append(f"- Name: {about['name']}")
    lines.append(f"- Income is {about.get('income_type', 'fixed')}")
    if about.get("home_country"):
        lines.append(f"- Home country: {about['home_country']}")
    if about.get("goal"):
        lines.append(f"- What they're working towards: {about['goal']}")
    lines += [f"- {fact}" for fact in about.get("facts", [])]
    return ("\n\nAbout this user (from their PennyWise profile; their money figures come from "
            "get_financial_snapshot):\n" + "\n".join(lines))


def system_prompt(agent: Agent) -> str:
    """Built-in prompt plus any rules taught in training mode (coach_rules.md)."""
    taught = training.rules_for(agent.name)
    if not taught:
        return agent.system
    lines = "\n".join(f"- {rule}" for rule in taught)
    return (
        f"{agent.system}\n\nExtra guidance from the PennyWise team. Follow it, but if any of it "
        f"conflicts with the rules above, the rules above win:\n{lines}"
    )


def run_agent(client: anthropic.Anthropic, agent: Agent, messages: list[dict], ctx: AgentContext) -> str:
    """Run one agent until it gives a final answer. `messages` is extended in place."""
    system = system_prompt(agent) + about_user_block(ctx.snapshot)
    for _ in range(MAX_TOOL_ROUNDS):
        try:
            response = client.beta.messages.create(
                model=MODEL,
                max_tokens=16000,
                system=system,
                tools=agent.tools,
                messages=messages,
                output_config={"effort": agent.effort},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.AuthenticationError as exc:
            raise CoachUnavailable("The Claude API key is missing or invalid.") from exc
        except (anthropic.RateLimitError, anthropic.APIConnectionError) as exc:
            raise CoachUnavailable("The coach is busy right now. Please try again shortly.") from exc
        except anthropic.APIStatusError as exc:
            raise CoachUnavailable(f"Claude API error ({exc.status_code}).") from exc

        if response.stop_reason == "refusal":
            return REFUSAL_REPLY

        # Keep the full content (including thinking blocks) for the next request.
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "tool_use":
            results = [_run_tool(agent, b, ctx) for b in response.content if b.type == "tool_use"]
            messages.append({"role": "user", "content": results})
            continue
        if response.stop_reason == "pause_turn":
            continue

        return "".join(b.text for b in response.content if b.type == "text").strip()

    raise CoachUnavailable(f"{agent.name} didn't finish within {MAX_TOOL_ROUNDS} steps.")


# ---------------------------------------------------------------------------
# Entry points used by the API
# ---------------------------------------------------------------------------

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        try:
            _client = anthropic.Anthropic()
        except anthropic.AnthropicError as exc:
            raise CoachUnavailable("Set ANTHROPIC_API_KEY to use the coach.") from exc
    return _client


def _clean_history(history: list[dict] | None) -> list[dict]:
    cleaned = [
        {"role": m["role"], "content": str(m["content"])}
        for m in (history or [])
        if m.get("role") in ("user", "assistant") and str(m.get("content", "")).strip()
    ][-MAX_HISTORY_MESSAGES:]
    while cleaned and cleaned[0]["role"] != "user":
        cleaned.pop(0)
    return cleaned


def coach_chat(snapshot: dict, message: str, history: list[dict] | None = None,
               client: anthropic.Anthropic | None = None) -> dict[str, Any]:
    client = client or get_client()
    ctx = AgentContext(snapshot=snapshot)
    messages = _clean_history(history) + [{"role": "user", "content": message}]
    reply = run_agent(client, make_coach(client), messages, ctx)
    return {
        "reply": reply,
        "purchase_check": ctx.last("evaluate_purchase"),
        "value_check": ctx.last("assess_value"),
        "worth_check": ctx.last("record_worth_verdict"),
        "trip_plan": ctx.last("simulate_trip"),
        "time_travel": ctx.last("project_future"),
        "new_facts": ctx.new_facts,
    }


def _offline_purchase(snapshot: dict, item: str, price: float, category: str) -> dict[str, Any]:
    """Rules-only answer used when Claude is unavailable (keeps Copilot's fallback idea)."""
    afford = rules_engine.evaluate_purchase(snapshot, item, price, category)
    value = rules_engine.assess_value(snapshot, item, price, rules_engine.guess_item_type(item))
    label = {"GO": "Go", "THINK_TWICE": "Think twice", "SKIP": "Skip for now"}[afford["verdict"]]
    explanation = (
        f"Can you afford it? {label}. Money left this month would go from "
        f"£{afford['money_left_this_month_before']:.2f} to £{afford['money_left_this_month_after']:.2f}. "
        f"Is it worth it? {value['student_hint']} "
        "(The AI coach is offline, so this is a rules-only answer.)"
    )
    return {"purchase_check": afford, "value_check": value, "worth_check": None, "new_facts": [],
            "explanation": explanation, "provider": "rules_only"}


def _purchase_agent(snapshot: dict, item: str, price: float, category: str, question: str,
                    client: anthropic.Anthropic | None) -> dict[str, Any]:
    if client is None:
        try:
            client = get_client()
        except CoachUnavailable:
            return _offline_purchase(snapshot, item, price, category)
    ctx = AgentContext(snapshot=snapshot)
    explanation = run_agent(client, BUY_ADVISOR, [{"role": "user", "content": question}], ctx)
    return {
        # The affordability verdict always comes from code, even if the agent skipped the tool.
        "purchase_check": ctx.last("evaluate_purchase") or rules_engine.evaluate_purchase(snapshot, item, price, category),
        "value_check": ctx.last("assess_value"),
        "worth_check": ctx.last("record_worth_verdict"),
        "explanation": explanation,
        "provider": "agent",
        "new_facts": ctx.new_facts,
    }


def buy_check(snapshot: dict, item: str, price: float, category: str = "Other",
              client: anthropic.Anthropic | None = None) -> dict[str, Any]:
    """'Should I buy this?' Affordability from code, worth-it judgement from the Buy Advisor."""
    rules_engine.evaluate_purchase(snapshot, item, price, category)  # validate before any AI call
    question = f"Should I buy this, and is it worth it? Item: {item}. Price: £{price:.2f}. Category: {category}."
    return _purchase_agent(snapshot, item, price, category, question, client)


def purchase_review(snapshot: dict, item: str, price: float, category: str = "Other",
                    status: str = "bought", client: anthropic.Anthropic | None = None) -> dict[str, Any]:
    """Opening message when a purchase is logged in the purchase tracker.

    Returns `history` so the user can keep chatting about it through /api/coach.
    """
    rules_engine.evaluate_purchase(snapshot, item, price, category)
    when = "I've just bought" if status == "bought" else "I'm thinking of buying"
    question = (f"From the purchase tracker: {when} {item} for £{price:.2f} (category: {category}). "
                "Is it worth it for me?")
    result = _purchase_agent(snapshot, item, price, category, question, client)
    result["history"] = [
        {"role": "user", "content": f"{when} {item} for £{price:.2f}. Is it worth it?"},
        {"role": "assistant", "content": result["explanation"]},
    ]
    return result


def trip_plan(snapshot: dict, destination: str, duration_value: float, duration_unit: str,
              purpose: str = "travel", months_until_departure: int = 3, housing_tier: str = "standard",
              client: anthropic.Anthropic | None = None) -> dict[str, Any]:
    """Costs and verdict come from code; Claude adds the explanation."""
    computed = rules_engine.simulate_trip(
        snapshot, destination, duration_value, duration_unit, purpose, months_until_departure, housing_tier
    )
    client = client or get_client()
    ctx = AgentContext(snapshot=snapshot)
    question = (
        f"Plan this trip and tell me if I can afford it: {duration_value:g} {duration_unit} in "
        f"{destination}, purpose: {purpose}, leaving in {months_until_departure} months, "
        f"{housing_tier} housing."
    )
    explanation = run_agent(client, TRIP_PLANNER, [{"role": "user", "content": question}], ctx)
    return {**computed, "explanation": explanation, "new_facts": ctx.new_facts}


# ---------------------------------------------------------------------------
# Training mode: the Trainer agent edits coach_rules.md
# ---------------------------------------------------------------------------

TRAINER_SYSTEM = """\
You are the Trainer for PennyWise, a money coach app. You are talking to the team that \
builds the app (not to end users). They teach the coach by giving you rules, and you save \
them to the coach's rules file with your tools.

The coach has three agents: the Coach (chats with users and hands off), the Buy Advisor \
("should I buy this?") and the Trip Planner (trips and study abroad).

How to work:
- When the team gives a rule, rewrite it as one short, clear instruction the coach can \
follow, pick who it applies to (all, coach, buy_advisor, trip_planner), and save it with \
add_rule. If they give several rules at once, save each one separately.
- If a message is vague, ask one short question before saving.
- When asked what the coach knows, call list_rules. To delete a rule, call list_rules \
first, then remove_rule with the right number.
- After saving or removing, say in one or two lines exactly what changed.

Do NOT save rules that would make the coach: invent or calculate numbers itself (all \
figures come from the app's calculator), change how verdicts or money maths are worked \
out, shame users, approve credit, recommend payday loans or stacking Buy Now Pay Later, \
or give regulated financial advice. Explain kindly why, and suggest a safe version. \
If they want the maths or verdict thresholds changed, tell them that's a code change in \
coach/rules_engine.py, not a rule.

Rules can also be facts the coach should know (for example local support services or \
student discounts), tone guidance, or things to always or never mention."""

TRAINER_TOOLS = [
    {
        "name": "list_rules",
        "description": "List every saved rule with its number and which agent it applies to.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "add_rule",
        "description": "Save one new rule to the coach's rules file. It applies from the next request.",
        "input_schema": {
            "type": "object",
            "properties": {
                "rule": {"type": "string", "description": "One short, clear instruction for the coach."},
                "scope": {"type": "string", "enum": list(training.SCOPES)},
            },
            "required": ["rule", "scope"],
            "additionalProperties": False,
        },
    },
    {
        "name": "remove_rule",
        "description": "Delete a saved rule by its number from list_rules.",
        "input_schema": {
            "type": "object",
            "properties": {"number": {"type": "integer"}},
            "required": ["number"],
            "additionalProperties": False,
        },
    },
]

TRAINER = Agent(
    name="trainer",
    system=TRAINER_SYSTEM,
    tools=TRAINER_TOOLS,
    handlers={
        "list_rules": lambda _a, _c: {"rules": training.numbered(training.load_rules())},
        "add_rule": lambda a, _c: training.add_rule(str(a["rule"]), str(a["scope"])),
        "remove_rule": lambda a, _c: training.remove_rule(int(a["number"])),
    },
    effort="low",
)


def train_chat(message: str, history: list[dict] | None = None,
               client: anthropic.Anthropic | None = None) -> dict[str, Any]:
    client = client or get_client()
    ctx = AgentContext(snapshot={})
    messages = _clean_history(history) + [{"role": "user", "content": message}]
    reply = run_agent(client, TRAINER, messages, ctx)
    return {"reply": reply, "rules": training.numbered(training.load_rules())}
