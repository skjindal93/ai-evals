"""PR to Jira state management workflow utilities.

This module is designed for automation flows where a new pull request should:
1. resolve a Jira issue from the PR title (via Atlassian search), and
2. transition that Jira issue to "Under Review" exactly once.

The idempotency rule is Jira-centric:
- if a Jira issue has already been transitioned by this workflow,
  future PRs mapping to the same Jira issue will be tracked but skipped.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class AtlassianWorkflowClient(Protocol):
    """Minimal Atlassian operations required by the workflow."""

    def find_jira_issue_key_from_pr_title(self, pr_title: str) -> str | None:
        """Return Jira issue key associated with the PR title."""

    def transition_issue_to_under_review(self, issue_key: str) -> None:
        """Move a Jira issue to the Under Review state."""


class WorkflowMemoryStore(Protocol):
    """Storage interface for maintaining Jira transition state."""

    def load(self) -> dict[str, Any]:
        """Load the persisted state map."""

    def save(self, state: dict[str, Any]) -> None:
        """Persist the state map."""


@dataclass(frozen=True)
class WorkflowResult:
    """Outcome details for one PR workflow execution."""

    pr_number: int
    pr_title: str
    jira_issue_key: str | None
    transitioned: bool
    skipped_reason: str | None = None


class JsonFileMemoryStore:
    """Simple JSON-backed memory store for workflow state."""

    def __init__(self, path: str | Path):
        self._path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        raw = self._path.read_text(encoding="utf-8")
        if not raw.strip():
            return {}
        return json.loads(raw)

    def save(self, state: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _extract_pr_number(event: dict[str, Any]) -> int:
    pull_request = event.get("pull_request")
    if isinstance(pull_request, dict) and isinstance(pull_request.get("number"), int):
        pr_number = pull_request["number"]
        if pr_number > 0:
            return pr_number
    if isinstance(event.get("number"), int):
        pr_number = event["number"]
        if pr_number > 0:
            return pr_number
    raise ValueError("Missing PR number in event payload.")


def _extract_pr_title(event: dict[str, Any]) -> str:
    pull_request = event.get("pull_request")
    if isinstance(pull_request, dict) and isinstance(pull_request.get("title"), str):
        title = pull_request["title"].strip()
        if title:
            return title
    if isinstance(event.get("title"), str):
        title = event["title"].strip()
        if title:
            return title
    raise ValueError("Missing PR title in event payload.")


def _normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(state, dict):
        state = {}

    transitioned = state.get("transitioned_jira_issues")
    if not isinstance(transitioned, dict):
        transitioned = {}
        state["transitioned_jira_issues"] = transitioned

    return state


def handle_pr_opened_workflow(
    event_payload: dict[str, Any],
    atlassian_client: AtlassianWorkflowClient,
    memory_store: WorkflowMemoryStore,
) -> WorkflowResult:
    """Process a PR-opened event and transition corresponding Jira issue.

    The workflow is idempotent per Jira issue key:
    - First PR for issue -> transition to Under Review and persist state.
    - Subsequent PRs for same issue -> do not transition again.
    """
    pr_number = _extract_pr_number(event_payload)
    pr_title = _extract_pr_title(event_payload)

    jira_issue_key = atlassian_client.find_jira_issue_key_from_pr_title(pr_title)
    if jira_issue_key is None:
        return WorkflowResult(
            pr_number=pr_number,
            pr_title=pr_title,
            jira_issue_key=None,
            transitioned=False,
            skipped_reason="no_jira_found_from_title",
        )

    if not isinstance(jira_issue_key, str):
        return WorkflowResult(
            pr_number=pr_number,
            pr_title=pr_title,
            jira_issue_key=None,
            transitioned=False,
            skipped_reason="no_jira_found_from_title",
        )

    issue_key = jira_issue_key.upper().strip()
    if not issue_key:
        return WorkflowResult(
            pr_number=pr_number,
            pr_title=pr_title,
            jira_issue_key=None,
            transitioned=False,
            skipped_reason="no_jira_found_from_title",
        )
    state = _normalize_state(memory_store.load())
    transitioned_jira_issues: dict[str, Any] = state["transitioned_jira_issues"]

    if issue_key in transitioned_jira_issues:
        entry = transitioned_jira_issues[issue_key]
        if not isinstance(entry, dict):
            entry = {}
            transitioned_jira_issues[issue_key] = entry
        existing_prs = entry.get("pr_numbers")
        if not isinstance(existing_prs, list):
            existing_prs = []
            entry["pr_numbers"] = existing_prs
        if pr_number not in existing_prs:
            existing_prs.append(pr_number)
        memory_store.save(state)
        return WorkflowResult(
            pr_number=pr_number,
            pr_title=pr_title,
            jira_issue_key=issue_key,
            transitioned=False,
            skipped_reason="jira_already_transitioned",
        )

    atlassian_client.transition_issue_to_under_review(issue_key)
    transitioned_jira_issues[issue_key] = {"pr_numbers": [pr_number]}
    memory_store.save(state)

    return WorkflowResult(
        pr_number=pr_number,
        pr_title=pr_title,
        jira_issue_key=issue_key,
        transitioned=True,
    )


# Backward-compatible API aliases used by existing imports/tests.
AtlassianJiraClient = AtlassianWorkflowClient
TransitionDecision = WorkflowResult
JiraTransitionMemoryStore = JsonFileMemoryStore


class JiraPrStateManager:
    """OO wrapper around ``handle_pr_opened_workflow``."""

    def __init__(self, atlassian_client: AtlassianWorkflowClient, memory_store: WorkflowMemoryStore):
        self.atlassian_client = atlassian_client
        self.memory_store = memory_store

    def handle_pr_raised(self, pr_number: int, pr_title: str) -> TransitionDecision:
        return handle_pr_opened_workflow(
            event_payload={"pull_request": {"number": pr_number, "title": pr_title}},
            atlassian_client=self.atlassian_client,
            memory_store=self.memory_store,
        )
