from __future__ import annotations

from typing import Any

import pytest

from runner.pr_jira_state_manager import (
    PrJiraWorkflowResult,
    WorkflowResult,
    handle_pr_opened_workflow,
)


class InMemoryStore:
    def __init__(self, initial: dict[str, Any] | None = None):
        self.state = initial or {}
        self.save_calls = 0

    def load(self) -> dict[str, Any]:
        return self.state

    def save(self, state: dict[str, Any]) -> None:
        self.state = state
        self.save_calls += 1


class InMemoryStateStore:
    def __init__(self, initial: dict[str, Any] | None = None):
        self.state = initial or {}
        self.save_calls = 0

    def load_state(self) -> dict[str, Any]:
        return self.state

    def save_state(self, state: dict[str, Any]) -> None:
        self.state = state
        self.save_calls += 1


class FakeAtlassianClient:
    def __init__(self, title_to_issue: dict[str, str | None]):
        self.title_to_issue = title_to_issue
        self.transitioned: list[str] = []

    def find_jira_issue_key_from_pr_title(self, pr_title: str) -> str | None:
        return self.title_to_issue.get(pr_title)

    def transition_issue_to_under_review(self, issue_key: str) -> None:
        self.transitioned.append(issue_key)


def _event(pr_number: int, pr_title: str) -> dict[str, Any]:
    return {"pull_request": {"number": pr_number, "title": pr_title}}


def test_first_pr_for_jira_transitions_and_persists() -> None:
    store = InMemoryStore()
    client = FakeAtlassianClient({"INC-1001 add review endpoint": "INC-1001"})

    result = handle_pr_opened_workflow(
        event_payload=_event(42, "INC-1001 add review endpoint"),
        atlassian_client=client,
        memory_store=store,
    )

    assert isinstance(result, WorkflowResult)
    assert result.transitioned is True
    assert result.jira_issue_key == "INC-1001"
    assert result.jira_key == "INC-1001"
    assert client.transitioned == ["INC-1001"]
    assert store.state == {
        "transitioned_jira_issues": {"INC-1001": {"pr_numbers": [42]}},
    }
    assert store.save_calls == 1


def test_second_pr_for_same_jira_skips_transition_but_tracks_pr_number() -> None:
    store = InMemoryStore({"transitioned_jira_issues": {"INC-1001": {"pr_numbers": [42]}}})
    client = FakeAtlassianClient({"INC-1001 follow-up fixes": "inc-1001"})

    result = handle_pr_opened_workflow(
        event_payload=_event(43, "INC-1001 follow-up fixes"),
        atlassian_client=client,
        memory_store=store,
    )

    assert result.transitioned is False
    assert result.skipped_reason == "jira_already_transitioned"
    assert client.transitioned == []
    assert store.state["transitioned_jira_issues"]["INC-1001"]["pr_numbers"] == [42, 43]
    assert store.save_calls == 1


def test_no_jira_found_skips_without_state_change() -> None:
    initial = {"transitioned_jira_issues": {"INC-1001": {"pr_numbers": [42]}}}
    store = InMemoryStore(initial.copy())
    client = FakeAtlassianClient({"chore: bump deps": None})

    result = handle_pr_opened_workflow(
        event_payload=_event(44, "chore: bump deps"),
        atlassian_client=client,
        memory_store=store,
    )

    assert result.transitioned is False
    assert result.jira_issue_key is None
    assert result.skipped_reason == "no_jira_found_from_title"
    assert client.transitioned == []
    assert store.state == initial
    assert store.save_calls == 0


def test_blank_jira_key_from_lookup_skips_without_transition() -> None:
    store = InMemoryStore()
    client = FakeAtlassianClient({"INC-1001 malformed mapping": "   "})

    result = handle_pr_opened_workflow(
        event_payload=_event(45, "INC-1001 malformed mapping"),
        atlassian_client=client,
        memory_store=store,
    )

    assert result.transitioned is False
    assert result.jira_issue_key is None
    assert result.skipped_reason == "no_jira_found_from_title"
    assert client.transitioned == []
    assert store.state == {}
    assert store.save_calls == 0


def test_top_level_event_fields_are_supported() -> None:
    store = InMemoryStore()
    client = FakeAtlassianClient({"feat: INC-2002": "inc-2002"})

    result = handle_pr_opened_workflow(
        event_payload={"number": 7, "title": "feat: INC-2002"},
        atlassian_client=client,
        memory_store=store,
    )

    assert result.transitioned is True
    assert result.jira_issue_key == "INC-2002"
    assert store.state["transitioned_jira_issues"]["INC-2002"]["pr_numbers"] == [7]


def test_state_store_load_state_save_state_methods_are_supported() -> None:
    store = InMemoryStateStore()
    client = FakeAtlassianClient({"INC-3003 add thing": "INC-3003"})

    result = handle_pr_opened_workflow(
        event_payload=_event(8, "INC-3003 add thing"),
        atlassian_client=client,
        memory_store=store,
    )

    assert result.transitioned is True
    assert store.state["transitioned_jira_issues"]["INC-3003"]["pr_numbers"] == [8]
    assert store.save_calls == 1


def test_missing_pr_number_raises_value_error() -> None:
    store = InMemoryStore()
    client = FakeAtlassianClient({})

    with pytest.raises(ValueError, match="Missing PR number"):
        handle_pr_opened_workflow(
            event_payload={"pull_request": {"title": "INC-1001 add review endpoint"}},
            atlassian_client=client,
            memory_store=store,
        )


def test_invalid_pr_number_raises_value_error() -> None:
    store = InMemoryStore()
    client = FakeAtlassianClient({})

    with pytest.raises(ValueError, match="positive integer"):
        handle_pr_opened_workflow(
            event_payload={"pull_request": {"number": 0, "title": "INC-1001 add review endpoint"}},
            atlassian_client=client,
            memory_store=store,
        )


def test_missing_pr_title_raises_value_error() -> None:
    store = InMemoryStore()
    client = FakeAtlassianClient({})

    with pytest.raises(ValueError, match="Missing PR title"):
        handle_pr_opened_workflow(
            event_payload={"pull_request": {"number": 99}},
            atlassian_client=client,
            memory_store=store,
        )


def test_result_alias_supports_jira_key_constructor_arg() -> None:
    result = PrJiraWorkflowResult(
        pr_number=1,
        pr_title="feat: INC-1",
        jira_key="INC-1",
        transitioned=True,
    )
    assert result.jira_issue_key == "INC-1"
    assert result.jira_key == "INC-1"
