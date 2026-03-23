"""PR-to-Jira state transition workflow with idempotent memory dedupe.

This module is intended for automation flows where a new pull request should:
1) resolve a Jira issue key from the PR title, and
2) transition that Jira issue to "Under Review" at most once.

The dedupe rule is Jira-centric:
- If a Jira key has already been processed, subsequent PRs for the same key
  are recorded but the transition is skipped.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Protocol


DEFAULT_MEMORY_STATE: dict[str, Any] = {"transitioned_jira_issues": {}}


class AtlassianClient(Protocol):
    """Interface for Jira lookup and transition operations."""

    def find_jira_issue_key_from_pr_title(self, pr_title: str) -> str | None:
        """Resolve the Jira key from the PR title."""

    def transition_issue_to_under_review(self, issue_key: str) -> bool | None:
        """Move a Jira issue to Under Review."""


class MemoryStore(Protocol):
    """Persistence contract for dedupe state."""

    def load_state(self) -> dict[str, Any]:
        """Load persisted dedupe state."""

    def save_state(self, state: dict[str, Any]) -> None:
        """Persist dedupe state."""


class JsonFileMemoryStore:
    """Simple JSON-file-backed memory store for dedupe state."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load_state(self) -> dict[str, Any]:
        if not self.path.exists():
            return dict(DEFAULT_MEMORY_STATE)

        raw = self.path.read_text(encoding="utf-8").strip()
        if not raw:
            return dict(DEFAULT_MEMORY_STATE)

        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return dict(DEFAULT_MEMORY_STATE)

        transitioned = parsed.get("transitioned_jira_issues")
        if not isinstance(transitioned, dict):
            parsed["transitioned_jira_issues"] = {}

        return parsed

    def save_state(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


@dataclass(frozen=True)
class PrJiraWorkflowResult:
    """Result payload for PR-to-Jira workflow execution."""

    pr_number: int
    pr_title: str
    jira_key: str | None
    transitioned: bool
    skipped_reason: str | None = None


TransitionDecision = PrJiraWorkflowResult
JiraTransitionMemoryStore = JsonFileMemoryStore
AtlassianJiraClient = AtlassianClient


def handle_pr_opened_workflow(
    event_payload: dict[str, Any],
    atlassian_client: AtlassianClient,
    memory_store: MemoryStore,
) -> PrJiraWorkflowResult:
    """Process a PR-open style payload and transition Jira once per key."""
    pr_number = _extract_pr_number(event_payload)
    pr_title = _extract_pr_title(event_payload)

    jira_key = _normalize_jira_key(atlassian_client.find_jira_issue_key_from_pr_title(pr_title))
    if jira_key is None:
        return PrJiraWorkflowResult(
            pr_number=pr_number,
            pr_title=pr_title,
            jira_key=None,
            transitioned=False,
            skipped_reason="jira_not_found",
        )

    state = memory_store.load_state()
    transitioned_jira_issues = state.setdefault("transitioned_jira_issues", {})
    if not isinstance(transitioned_jira_issues, dict):
        transitioned_jira_issues = {}
        state["transitioned_jira_issues"] = transitioned_jira_issues

    issue_entry = transitioned_jira_issues.get(jira_key)
    today = date.today().isoformat()

    if issue_entry is not None:
        if not isinstance(issue_entry, dict):
            issue_entry = {}
        pr_numbers = issue_entry.get("pr_numbers", [])
        if not isinstance(pr_numbers, list):
            pr_numbers = []
        if pr_number not in pr_numbers:
            pr_numbers.append(pr_number)
        issue_entry["pr_numbers"] = sorted(pr_numbers)
        issue_entry["last_seen_date"] = today
        transitioned_jira_issues[jira_key] = issue_entry
        memory_store.save_state(state)
        return PrJiraWorkflowResult(
            pr_number=pr_number,
            pr_title=pr_title,
            jira_key=jira_key,
            transitioned=False,
            skipped_reason="jira_already_processed",
        )

    transition_result = atlassian_client.transition_issue_to_under_review(jira_key)
    transitioned = True if transition_result is None else bool(transition_result)

    transitioned_jira_issues[jira_key] = {
        "pr_numbers": [pr_number],
        "transitioned_to_under_review": transitioned,
        "last_seen_date": today,
    }
    memory_store.save_state(state)

    return PrJiraWorkflowResult(
        pr_number=pr_number,
        pr_title=pr_title,
        jira_key=jira_key,
        transitioned=transitioned,
    )


def _extract_pr_number(event_payload: dict[str, Any]) -> int:
    nested_pr = event_payload.get("pull_request")
    candidate = (
        nested_pr.get("number")
        if isinstance(nested_pr, dict) and "number" in nested_pr
        else event_payload.get("number")
    )
    if not isinstance(candidate, int) or candidate <= 0:
        raise ValueError("PR number is required and must be a positive integer.")
    return candidate


def _extract_pr_title(event_payload: dict[str, Any]) -> str:
    nested_pr = event_payload.get("pull_request")
    candidate = (
        nested_pr.get("title")
        if isinstance(nested_pr, dict) and "title" in nested_pr
        else event_payload.get("title")
    )
    if not isinstance(candidate, str) or not candidate.strip():
        raise ValueError("PR title is required and must be a non-empty string.")
    return candidate.strip()


def _normalize_jira_key(raw_key: Any) -> str | None:
    if not isinstance(raw_key, str):
        return None
    normalized = raw_key.strip().upper()
    return normalized or None


class JiraPrStateManager:
    """Wrapper around the workflow API for call sites."""

    def __init__(self, atlassian_client: AtlassianClient, memory_store: MemoryStore):
        self._atlassian_client = atlassian_client
        self._memory_store = memory_store

    def handle_pr_raised(self, pr_number: int, pr_title: str) -> TransitionDecision:
        return handle_pr_opened_workflow(
            event_payload={"pull_request": {"number": pr_number, "title": pr_title}},
            atlassian_client=self._atlassian_client,
            memory_store=self._memory_store,
        )
