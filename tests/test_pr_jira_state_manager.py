from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from runner.pr_jira_state_manager import (
    JiraPrStateManager,
    TransitionDecision,
    handle_pr_opened_workflow,
)


@dataclass
class FakeAtlassianClient:
    jira_key: str | None
    transition_result: bool = True
    find_calls: list[str] = field(default_factory=list)
    transition_calls: list[str] = field(default_factory=list)

    def find_jira_issue_key_from_pr_title(self, pr_title: str) -> str | None:
        self.find_calls.append(pr_title)
        return self.jira_key

    def transition_issue_to_under_review(self, issue_key: str) -> bool:
        self.transition_calls.append(issue_key)
        return self.transition_result


class InMemoryStore:
    def __init__(self, initial_state: dict[str, Any] | None = None) -> None:
        self.state = initial_state or {}

    def read_state(self) -> dict[str, Any]:
        return self.state

    def write_state(self, state: dict[str, Any]) -> None:
        self.state = state


def test_first_seen_jira_key_transitions_and_persists() -> None:
    payload = {"pull_request": {"number": 9, "title": "feat: AIPLAT-999 add workflow"}}
    atlassian = FakeAtlassianClient(jira_key="AIPLAT-999", transition_result=True)
    memory = InMemoryStore()

    decision = handle_pr_opened_workflow(payload, atlassian, memory)

    assert decision == TransitionDecision(
        pr_number=9,
        pr_title="feat: AIPLAT-999 add workflow",
        jira_key="AIPLAT-999",
        already_processed=False,
        transitioned=True,
        reason="Transition attempted for first-seen Jira key",
    )
    assert atlassian.find_calls == ["feat: AIPLAT-999 add workflow"]
    assert atlassian.transition_calls == ["AIPLAT-999"]
    assert memory.state == {
        "transitioned_jira_issues": {
            "AIPLAT-999": {
                "pr_numbers": [9],
                "transitioned_to_under_review": True,
            }
        }
    }


def test_existing_jira_key_skips_transition_and_appends_pr_number() -> None:
    payload = {"number": 11, "title": "fix: AIPLAT-999 retry path"}
    atlassian = FakeAtlassianClient(jira_key="AIPLAT-999")
    memory = InMemoryStore(
        {
            "transitioned_jira_issues": {
                "AIPLAT-999": {
                    "pr_numbers": [9],
                    "transitioned_to_under_review": True,
                }
            }
        }
    )

    manager = JiraPrStateManager(atlassian_client=atlassian, memory_store=memory)
    decision = manager.handle_pr_raised(payload)

    assert decision.already_processed is True
    assert decision.transitioned is False
    assert atlassian.transition_calls == []
    assert memory.state["transitioned_jira_issues"]["AIPLAT-999"]["pr_numbers"] == [9, 11]


def test_no_jira_key_found_does_not_transition_or_mutate_state() -> None:
    payload = {"pull_request": {"number": 4, "title": "chore: update docs"}}
    atlassian = FakeAtlassianClient(jira_key=None)
    memory = InMemoryStore({})

    decision = handle_pr_opened_workflow(payload, atlassian, memory)

    assert decision.jira_key is None
    assert decision.transitioned is False
    assert decision.already_processed is False
    assert atlassian.transition_calls == []
    assert memory.state == {}


def test_missing_pr_number_raises_value_error() -> None:
    payload = {"pull_request": {"title": "feat: AIPLAT-123"}}
    atlassian = FakeAtlassianClient(jira_key="AIPLAT-123")
    memory = InMemoryStore()

    with pytest.raises(ValueError, match="PR number is missing or invalid"):
        handle_pr_opened_workflow(payload, atlassian, memory)
