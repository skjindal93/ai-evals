from pathlib import Path

from runner.pr_jira_state_manager import JiraPrStateManager, JiraTransitionMemoryStore


class FakeAtlassianClient:
    def __init__(self, title_map: dict[str, str | None]):
        self.title_map = title_map
        self.find_calls: list[str] = []
        self.transition_calls: list[str] = []

    def find_jira_from_pr_title(self, pr_title: str) -> str | None:
        self.find_calls.append(pr_title)
        return self.title_map.get(pr_title)

    def transition_to_under_review(self, jira_key: str) -> None:
        self.transition_calls.append(jira_key)


def test_transitions_new_jira_and_persists_state(tmp_path: Path) -> None:
    store = JiraTransitionMemoryStore(tmp_path / "jira_state.json")
    client = FakeAtlassianClient({"Refactor checkout flow": "PAY-123"})
    manager = JiraPrStateManager(client, store)

    decision = manager.handle_pr_raised(pr_number=10, pr_title="Refactor checkout flow")

    assert decision.action == "transitioned"
    assert decision.jira_key == "PAY-123"
    assert client.transition_calls == ["PAY-123"]
    assert client.find_calls == ["Refactor checkout flow"]
    assert store.has_jira("PAY-123")


def test_duplicate_jira_does_not_transition_again(tmp_path: Path) -> None:
    store = JiraTransitionMemoryStore(tmp_path / "jira_state.json")
    client = FakeAtlassianClient({})
    manager = JiraPrStateManager(client, store)

    first = manager.handle_pr_raised(pr_number=21, pr_title="PLAT-404 initial work")
    second = manager.handle_pr_raised(pr_number=22, pr_title="PLAT-404 follow-up")

    assert first.action == "transitioned"
    assert second.action == "skipped_existing"
    assert first.jira_key == "PLAT-404"
    assert second.jira_key == "PLAT-404"
    assert client.transition_calls == ["PLAT-404"]


def test_no_jira_match_is_noop(tmp_path: Path) -> None:
    store = JiraTransitionMemoryStore(tmp_path / "jira_state.json")
    client = FakeAtlassianClient({"No ticket in title": None})
    manager = JiraPrStateManager(client, store)

    decision = manager.handle_pr_raised(pr_number=31, pr_title="No ticket in title")

    assert decision.action == "no_jira_found"
    assert decision.jira_key is None
    assert client.transition_calls == []
    assert client.find_calls == ["No ticket in title"]
