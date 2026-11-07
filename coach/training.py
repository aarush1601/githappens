"""Training mode: teach the coach extra rules that are saved to coach_rules.md.

The Trainer agent turns what the team says into short rules and saves them.
Every coach agent reads the file on each request (see agents.py), so rules
apply straight away. Taught rules sit *below* the built-in safety rules and
can never override them.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

RULES_PATH = Path(__file__).with_name("coach_rules.md")

SCOPES = {
    "all": "All agents",
    "coach": "Coach",
    "buy_advisor": "Buy Advisor",
    "trip_planner": "Trip Planner",
}
_TITLE_TO_SCOPE = {title: scope for scope, title in SCOPES.items()}
_lock = threading.Lock()

HEADER = (
    "# Coach training rules\n\n"
    "Written in training mode (/train). Every coach agent reads this file on each request.\n"
    "These rules can never override the built-in safety rules in agents.py.\n"
)


def load_rules() -> list[dict[str, str]]:
    """Parse the md file into [{"scope": ..., "rule": ...}] in file order."""
    if not RULES_PATH.exists():
        return []
    rules, scope = [], None
    for line in RULES_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            scope = _TITLE_TO_SCOPE.get(line[3:].strip())
        elif line.startswith("- ") and scope:
            rules.append({"scope": scope, "rule": line[2:].strip()})
    return rules


def _save(rules: list[dict[str, str]]) -> None:
    parts = [HEADER]
    for scope, title in SCOPES.items():
        items = [r["rule"] for r in rules if r["scope"] == scope]
        parts.append(f"\n## {title}\n")
        parts.extend(f"- {item}\n" for item in items)
    RULES_PATH.write_text("".join(parts), encoding="utf-8")


def numbered(rules: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [{"number": i + 1, **r} for i, r in enumerate(rules)]


def add_rule(rule: str, scope: str) -> dict[str, Any]:
    rule = " ".join(rule.split())
    if not rule:
        raise ValueError("Rule text is empty.")
    if len(rule) > 500:
        raise ValueError("Keep each rule under 500 characters.")
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of: {', '.join(SCOPES)}")
    with _lock:
        rules = load_rules()
        if any(r["rule"].lower() == rule.lower() and r["scope"] == scope for r in rules):
            raise ValueError("That rule is already saved.")
        rules.append({"scope": scope, "rule": rule})
        _save(rules)
        return {"saved": {"scope": scope, "rule": rule}, "rules": numbered(load_rules())}


def remove_rule(number: int) -> dict[str, Any]:
    with _lock:
        rules = load_rules()
        if not 1 <= number <= len(rules):
            raise ValueError(f"There is no rule number {number}. There are {len(rules)} rules.")
        removed = rules.pop(number - 1)
        _save(rules)
        return {"removed": removed, "rules": numbered(load_rules())}


def rules_for(agent_name: str) -> list[str]:
    return [r["rule"] for r in load_rules() if r["scope"] in ("all", agent_name)]


def rules_markdown() -> str:
    return RULES_PATH.read_text(encoding="utf-8") if RULES_PATH.exists() else HEADER


if not RULES_PATH.exists():
    _save([])
