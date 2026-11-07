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
You are part of PocketWise, a money coach for people on tight or irregular budgets: \
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
- If a tool result has "notes" (for example limited history), mention them briefly so the \
user knows how reliable the figures are.
- If a purchase reason_code is "essential_but_over_budget", don't tell them to skip it. \
Gently say it's more than they have left, and suggest talking to the bill provider or \
their bank about a payment plan, or free help from Citizens Advice or StepChange.
- Verdicts are GO, THINK_TWICE or SKIP. Show them to users as "Go", "Think twice" or \
"Skip for now", and always use the verdict the tool returned.
- For purchase questions, distinguish affordability from student value. Explain the \
"student_value_reason" and "cheaper_student_alternative" fields from the rules engine; \
do not call an expensive durable item worthwhile merely because it fits this month."""

BUY_ADVISOR_SYSTEM = SHARED_RULES + """

You are the Buy Advisor. You answer "should I buy this?" questions.
1. Work out the item, the price in pounds, and a category (Food, Transport, Shopping, \
Entertainment, Bills, Healthcare, Education, Other). If the price is missing, ask for it \
instead of guessing.
2. Call evaluate_purchase.
3. Reply in 2-4 sentences: the verdict, the main reason, what it does to their daily \
safe-to-spend, and one cheaper or greener alternative (for example second-hand, \
waiting for a sale, or the bus instead of a taxi). Don't put a price on the alternative."""

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

You are the Coach, the friendly front door of PocketWise. You chat with the user about \
their money.
- For "should I buy X?" or "can I afford X?" about an item, call ask_buy_advisor.
- For trips, holidays, moving or studying abroad, call ask_trip_planner.
- For general questions about their spending, call get_financial_snapshot.
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
    tools=[SNAPSHOT_TOOL, EVALUATE_PURCHASE_TOOL],
    handlers={"get_financial_snapshot": _snapshot_handler, "evaluate_purchase": _evaluate_purchase_handler},
    effort="low",
)

TRIP_PLANNER = Agent(
    name="trip_planner",
    system=TRIP_PLANNER_SYSTEM,
    tools=[SNAPSHOT_TOOL, LIST_DESTINATIONS_TOOL, SIMULATE_TRIP_TOOL],
    handlers={
        "get_financial_snapshot": _snapshot_handler,
        "list_destinations": _list_destinations_handler,
        "simulate_trip": _simulate_trip_handler,
    },
    effort="low",
)


def _make_delegate(client: anthropic.Anthropic, specialist: Agent) -> ToolHandler:
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
            _delegate_tool("ask_buy_advisor", "Ask the Buy Advisor whether the user should buy a specific item."),
            _delegate_tool("ask_trip_planner", "Ask the Trip Planner to cost a trip or study-abroad stay and check affordability."),
        ],
        handlers={
            "get_financial_snapshot": _snapshot_handler,
            "ask_buy_advisor": _make_delegate(client, BUY_ADVISOR),
            "ask_trip_planner": _make_delegate(client, TRIP_PLANNER),
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


def system_prompt(agent: Agent) -> str:
    """Built-in prompt plus any rules taught in training mode (coach_rules.md)."""
    taught = training.rules_for(agent.name)
    if not taught:
        return agent.system
    lines = "\n".join(f"- {rule}" for rule in taught)
    return (
        f"{agent.system}\n\nExtra guidance from the PocketWise team. Follow it, but if any of it "
        f"conflicts with the rules above, the rules above win:\n{lines}"
    )


def run_agent(client: anthropic.Anthropic, agent: Agent, messages: list[dict], ctx: AgentContext) -> str:
    """Run one agent until it gives a final answer. `messages` is extended in place."""
    system = system_prompt(agent)
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
        "trip_plan": ctx.last("simulate_trip"),
    }


def buy_check(snapshot: dict, item: str, price: float, category: str = "Other",
              client: anthropic.Anthropic | None = None) -> dict[str, Any]:
    """Verdict and numbers come from code; Claude adds the explanation."""
    result = rules_engine.evaluate_purchase(snapshot, item, price, category)
    if client is None:
        try:
            client = get_client()
        except CoachUnavailable:
            return {
                **result,
                "explanation": (
                    f"{result['student_value_reason']} "
                    f"{result['cheaper_student_alternative']} "
                    "This is a deterministic rules-only explanation because the coach provider is unavailable."
                ),
                "provider": "rules_only",
            }
    ctx = AgentContext(snapshot=snapshot)
    question = f"Should I buy this? Item: {item}. Price: £{price:.2f}. Category: {category}."
    explanation = run_agent(client, BUY_ADVISOR, [{"role": "user", "content": question}], ctx)
    return {**(ctx.last("evaluate_purchase") or result), "explanation": explanation, "provider": "agent"}


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
    return {**computed, "explanation": explanation}


# ---------------------------------------------------------------------------
# Training mode: the Trainer agent edits coach_rules.md
# ---------------------------------------------------------------------------

TRAINER_SYSTEM = """\
You are the Trainer for PocketWise, a money coach app. You are talking to the team that \
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
