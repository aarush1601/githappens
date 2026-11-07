import pytest

from coach import training


@pytest.fixture(autouse=True)
def isolated_rules_file(tmp_path, monkeypatch):
    """Never let tests read or write the real coach_rules.md."""
    monkeypatch.setattr(training, "RULES_PATH", tmp_path / "coach_rules.md")
