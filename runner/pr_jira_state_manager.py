"""PR to Jira state management workflow utilities.

This module supports automation flows where a newly raised pull request should:
1) resolve a Jira issue from the PR title, and
2) transition that Jira issue to "Under Review" exactly once.

Idempotency is Jira-centric: once a Jira issue key is recorded as transitioned,
future PRs mapped to that key are tracked but not transitioned again.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AtlassianWorkflowClient(Protocol):
    """Minimal Atlassian operations required by this workflow."""

    def find_jira_issue_key_from_pr_title(self, pr_title: str) -> str | None:
        """Resolve a Jira issue key from a PR title."""

    def transition_issue_to_under_review(self, issue_key: str) -> bool | None:
        """Move the Jira issue to the "Under Review" state."""


@runtime_checkable
class WorkflowMemoryStore(Protocol):
    """Persistence contract for workflow state.

    Supported method pairs:
    - load() / save()
    - load_state() / save_state()
    """

    def load(self) -> dict[str, Any]:
        """Load state (legacy name)."""

    def save(self, state: dict[str, Any]) -> None:
        """Save state (legacy name)."""

    def load_state(self) -> dict[str, Any]:
        """Load state."""

    def save_state(self, state: dict[str, Any]) -> None:
        """Save state."""


@dataclass(frozen=True, init=False)
class WorkflowResult:
    """Outcome details for one PR workflow execution.

    The constructor accepts either ``jira_issue_key=...`` or ``jira_key=...``
    to remain compatible with existing integrations/tests.
    """

    pr_number: int
    pr_title: str
    jira_issue_key: str | None
    transitioned: bool
    skipped_reason: str | None = None

    def __init__(
        self,
        pr_number: int,
        pr_title: str,
        transitioned: bool,
        jira_issue_key: str | None = None,
        skipped_reason: str | None = None,
        jira_key: str | None = None,
    ) -> None:
        if jira_issue_key is not None and jira_key is not None and jira_issue_key != jira_key:
            raise ValueError("jira_issue_key and jira_key cannot disagree.")
        normalized_key = jira_issue_key if jira_issue_key is not None else jira_key

        object.__setattr__(self, "pr_number", pr_number)
        object.__setattr__(self, "pr_title", pr_title)
        object.__setattr__(self, "jira_issue_key", normalized_key)
        object.__setattr__(self, "transitioned", transitioned)
        object.__setattr__(self, "skipped_reason", skipped_reason)

    @property
    def jira_key(self) -> str | None:
        """Alias for jira_issue_key used by older code paths."""
        return self.jira_issue_key


class JsonFileMemoryStore:
    """JSON-backed memory store for workflow state."""

    def __init__(self, path: str | Path):
        self._path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        raw = self._path.read_text(encoding="utf-8")
        if not raw.strip():
            return {}
        loaded = json.loads(raw)
        return loaded if isinstance(loaded, dict) else {}

    def save(self, state: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")

    # Compatibility with integrations expecting load_state/save_state.
    def load_state(self) -> dict[str, Any]:
        return self.load()

    def save_state(self, state: dict[str, Any]) -> None:
        self.save(state)


def _extract_pr_number(event_payload: dict[str, Any]) -> int:
    pull_request = event_payload.get("pull_request")
    if isinstance(pull_request, dict) and isinstance(pull_request.get("number"), int):
        pr_number = pull_request["number"]
    elif isinstance(event_payload.get("number"), int):
        pr_number = event_payload["number"]
    else:
        raise ValueError(
            "Missing PR number in event payload. PR number is required and must be a positive integer."
        )

    if pr_number <= 0:
        raise ValueError(
            "Missing PR number in event payload. PR number is required and must be a positive integer."
        )
    return pr_number


def _extract_pr_title(event_payload: dict[str, Any]) -> str:
    pull_request = event_payload.get("pull_request")
    title_candidate: Any = None
    if isinstance(pull_request, dict) and isinstance(pull_request.get("title"), str):
        title_candidate = pull_request["title"]
    elif isinstance(event_payload.get("title"), str):
        title_candidate = event_payload["title"]

    if not isinstance(title_candidate, str) or not title_candidate.strip():
        raise ValueError(
            "Missing PR title in event payload. PR title is required and must be a non-empty string."
        )
    return title_candidate.strip()


def _normalize_jira_key(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    normalized = raw.strip().upper()
    return normalized or None


def _normalize_state(state: Any) -> dict[str, Any]:
    if not isinstance(state, dict):
        state = {}

    transitioned = state.get("transitioned_jira_issues")
    if not isinstance(transitioned, dict):
        transitioned = {}
        state["transitioned_jira_issues"] = transitioned

    return state


def _memory_load(memory_store: WorkflowMemoryStore) -> dict[str, Any]:
    if hasattr(memory_store, "load_state"):
        loaded = memory_store.load_state()  # type: ignore[call-arg]
    elif hasattr(memory_store, "load"):
        loaded = memory_store.load()  # type: ignore[call-arg]
    else:
        raise TypeError("memory_store must implement load()/save() or load_state()/save_state().")
    return loaded if isinstance(loaded, dict) else {}


def _memory_save(memory_store: WorkflowMemoryStore, state: dict[str, Any]) -> None:
    if hasattr(memory_store, "save_state"):
        memory_store.save_state(state)  # type: ignore[call-arg]
        return
    if hasattr(memory_store, "save"):
        memory_store.save(state)  # type: ignore[call-arg]
        return
    raise TypeError("memory_store must implement load()/save() or load_state()/save_state().")


def handle_pr_opened_workflow(
    event_payload: dict[str, Any],
    atlassian_client: AtlassianWorkflowClient,
    memory_store: WorkflowMemoryStore,
) -> WorkflowResult:
    """Process a PR-raised event and transition the linked Jira issue once."""

    pr_number = _extract_pr_number(event_payload)
    pr_title = _extract_pr_title(event_payload)

    jira_issue_key = _normalize_jira_key(
        atlassian_client.find_jira_issue_key_from_pr_title(pr_title)
    )
    if jira_issue_key is None:
        return WorkflowResult(
            pr_number=pr_number,
            pr_title=pr_title,
            jira_issue_key=None,
            transitioned=False,
            skipped_reason="no_jira_found_from_title",
        )

    state = _normalize_state(_memory_load(memory_store))
    transitioned_jira_issues: dict[str, Any] = state["transitioned_jira_issues"]

    if jira_issue_key in transitioned_jira_issues:
        entry = transitioned_jira_issues[jira_issue_key]
        if not isinstance(entry, dict):
            entry = {}
            transitioned_jira_issues[jira_issue_key] = entry

        existing_prs = entry.get("pr_numbers")
        if not isinstance(existing_prs, list):
            existing_prs = []
            entry["pr_numbers"] = existing_prs

        if pr_number not in existing_prs:
            existing_prs.append(pr_number)

        _memory_save(memory_store, state)
        return WorkflowResult(
            pr_number=pr_number,
            pr_title=pr_title,
            jira_issue_key=jira_issue_key,
            transitioned=False,
            skipped_reason="jira_already_transitioned",
        )

    atlassian_client.transition_issue_to_under_review(jira_issue_key)
    transitioned_jira_issues[jira_issue_key] = {"pr_numbers": [pr_number]}
    _memory_save(memory_store, state)

    return WorkflowResult(
        pr_number=pr_number,
        pr_title=pr_title,
        jira_issue_key=jira_issue_key,
        transitioned=True,
    )


# Compatibility aliases used by existing imports/tests.
AtlassianClient = AtlassianWorkflowClient
AtlassianJiraClient = AtlassianWorkflowClient
MemoryStore = WorkflowMemoryStore
PrJiraWorkflowResult = WorkflowResult
TransitionDecision = WorkflowResult
JiraTransitionMemoryStore = JsonFileMemoryStore


class JiraPrStateManager:
    """OO wrapper around ``handle_pr_opened_workflow``."""

    def __init__(self, atlassian_client: AtlassianWorkflowClient, memory_store: WorkflowMemoryStore):
        self.atlassian_client = atlassian_client
        self.memory_store = memory_store

    def handle_pr_raised(
        self,
        pr_number_or_event: int | dict[str, Any],
        pr_title: str | None = None,
    ) -> TransitionDecision:
        if isinstance(pr_number_or_event, dict):
            event_payload = pr_number_or_event
        else:
            if pr_title is None or not isinstance(pr_title, str):
                raise ValueError("pr_title is required when passing a PR number directly.")
            event_payload = {"pull_request": {"number": pr_number_or_event, "title": pr_title}}

        return handle_pr_opened_workflow(
            event_payload=event_payload,
            atlassian_client=self.atlassian_client,
            memory_store=self.memory_store,
        )
