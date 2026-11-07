import pytest

from coach import agents, training
from tests.test_coach import FakeClient, text, tool_use


def test_add_list_remove_roundtrip():
    training.add_rule("Mention student discounts for travel.", "trip_planner")
    training.add_rule("Keep replies under 80 words.", "all")
    rules = training.load_rules()
    # File groups by scope: "all" section comes first.
    assert [r["scope"] for r in rules] == ["all", "trip_planner"]
    assert "## Trip Planner\n- Mention student discounts for travel." in training.rules_markdown()

    training.remove_rule(1)
    assert training.load_rules() == [{"scope": "trip_planner", "rule": "Mention student discounts for travel."}]


def test_rule_validation():
    with pytest.raises(ValueError):
        training.add_rule("x", "everyone")
    training.add_rule("Be kind.", "all")
    with pytest.raises(ValueError, match="already saved"):
        training.add_rule("be kind.", "all")
    with pytest.raises(ValueError, match="no rule number 5"):
        training.remove_rule(5)


def test_rules_reach_the_right_agents():
    training.add_rule("Always say hi.", "all")
    training.add_rule("Mention railcards.", "trip_planner")
    assert "Mention railcards." in agents.system_prompt(agents.TRIP_PLANNER)
    assert "Always say hi." in agents.system_prompt(agents.BUY_ADVISOR)
    assert "Mention railcards." not in agents.system_prompt(agents.BUY_ADVISOR)


def test_no_rules_leaves_prompt_unchanged():
    assert agents.system_prompt(agents.BUY_ADVISOR) == agents.BUY_ADVISOR.system


def test_trainer_saves_rule_via_tool():
    client = FakeClient({"You are the Trainer": [
        ([tool_use("t1", "add_rule", {"rule": "Suggest the bus over taxis.", "scope": "buy_advisor"})], "tool_use"),
        ([text("Saved.")], "end_turn"),
    ]})
    out = agents.train_chat("tell it to suggest buses", client=client)
    assert out["reply"] == "Saved."
    assert out["rules"] == [{"number": 1, "scope": "buy_advisor", "rule": "Suggest the bus over taxis."}]
