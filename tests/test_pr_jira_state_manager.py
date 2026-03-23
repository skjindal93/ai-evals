from __future__ import annotations

from typing import Any

import pytest

from runner.pr_jira_state_manager import (
    PrJiraWorkflowResult,
    handle_pr_opened_workflow,
)


class FakeAtlassianClient:
    def __init__(self, jira_key: str | None, transition_result: bool | None = True):
        self.jira_key = jira_key
        self.transition_result = transition_result
        self.lookup_calls: list[str] = []
        self.transition_calls: list[str] = []

    def find_jira_issue_key_from_pr_title(self, pr_title: str) -> str | None:
        self.lookup_calls.append(pr_title)
        return self.jira_key

    def transition_issue_to_under_review(self, issue_key: str) -> bool | None:
        self.transition_calls.append(issue_key)
        return self.transition_result


class InMemoryStore:
    def __init__(self, state: dict[str, Any] | None = None):
        self.state = state or {"transitioned_jira_issues": {}}
        self.save_calls = 0

    def load_state(self) -> dict[str, Any]:
        return self.state

    def save_state(self, state: dict[str, Any]) -> None:
        self.state = state
        self.save_calls += 1


def test_transitions_first_seen_jira_and_persists() -> None:
    client = FakeAtlassianClient("aiplat-125", transition_result=True)
    memory = InMemoryStore()

    result = handle_pr_opened_workflow(
        event_payload={"pull_request": {"number": 101, "title": "feat: AIPLAT-125 add thing"}},
        atlassian_client=client,
        memory_store=memory,
    )

    assert result == PrJiraWorkflowResult(
        pr_number=101,
        pr_title="feat: AIPLAT-125 add thing",
        jira_key="AIPLAT-125",
        transitioned=True,
        skipped_reason=None,
    )
    assert client.lookup_calls == ["feat: AIPLAT-125 add thing"]
    assert client.transition_calls == ["AIPLAT-125"]
    assert memory.state["transitioned_jira_issues"]["AIPLAT-125"]["pr_numbers"] == [101]
    assert memory.save_calls == 1


def test_same_jira_same_pr_does_not_transition_again() -> None:
    memory = InMemoryStore(
        {
            "transitioned_jira_issues": {
                "AIPLAT-125": {
                    "pr_numbers": [101],
                    "transitioned_to_under_review": True,
                    "last_seen_date": "2026-03-20",
                }
            }
        }
    )
    client = FakeAtlassianClient("AIPLAT-125")

    result = handle_pr_opened_workflow(
        event_payload={"pull_request": {"number": 101, "title": "chore: AIPLAT-125 retry"}},
        atlassian_client=client,
        memory_store=memory,
    )

    assert result.transitioned is False
    assert result.skipped_reason == "jira_already_processed"
    assert client.transition_calls == []
    assert memory.state["transitioned_jira_issues"]["AIPLAT-125"]["pr_numbers"] == [101]


def test_same_jira_different_pr_is_deduped_but_records_new_pr_number() -> None:
    memory = InMemoryStore(
        {
            "transitioned_jira_issues": {
                "AIPLAT-125": {
                    "pr_numbers": [2],
                    "transitioned_to_under_review": True,
                    "last_seen_date": "2026-03-20",
                }
            }
        }
    )
    client = FakeAtlassianClient("AIPLAT-125")

    result = handle_pr_opened_workflow(
        event_payload={"number": 3, "title": "test: AIPLAT-125"},
        atlassian_client=client,
        memory_store=memory,
    )

    assert result.transitioned is False
    assert result.skipped_reason == "jira_already_processed"
    assert client.transition_calls == []
    assert memory.state["transitioned_jira_issues"]["AIPLAT-125"]["pr_numbers"] == [2, 3]
    assert memory.save_calls == 1


def test_missing_jira_in_title_skips_without_memory_write() -> None:
    client = FakeAtlassianClient(None)
    memory = InMemoryStore()

    result = handle_pr_opened_workflow(
        event_payload={"pull_request": {"number": 42, "title": "refactor: no jira id"}},
        atlassian_client=client,
        memory_store=memory,
    )

    assert result.transitioned is False
    assert result.jira_key is None
    assert result.skipped_reason == "jira_not_found"
    assert client.transition_calls == []
    assert memory.save_calls == 0


def test_blank_jira_key_from_lookup_treated_as_not_found() -> None:
    client = FakeAtlassianClient("   ")
    memory = InMemoryStore()

    result = handle_pr_opened_workflow(
        event_payload={"pull_request": {"number": 11, "title": "feat: maybe jira?"}},
        atlassian_client=client,
        memory_store=memory,
    )

    assert result.transitioned is False
    assert result.jira_key is None
    assert result.skipped_reason == "jira_not_found"
    assert client.transition_calls == []
    assert memory.save_calls == 0


def test_invalid_pr_number_raises() -> None:
    client = FakeAtlassianClient("AIPLAT-125")
    memory = InMemoryStore()

    with pytest.raises(ValueError, match="PR number is required"):
        handle_pr_opened_workflow(
            event_payload={"pull_request": {"number": 0, "title": "feat: AIPLAT-125"}},
            atlassian_client=client,
            memory_store=memory,
        )
