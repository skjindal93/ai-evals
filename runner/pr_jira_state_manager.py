"""PR to Jira transition workflow with idempotent memory state."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Protocol


class AtlassianClientProtocol(Protocol):
    """Interface required from an Atlassian client implementation."""

    def find_jira_issue_key_from_pr_title(self, pr_title: str) -> str | None:
        """Resolve the Jira issue key associated with a PR title."""

    def transition_issue_to_under_review(self, issue_key: str) -> bool:
        """Move the issue to Under Review. Returns True on transition."""


class MemoryStoreProtocol(Protocol):
    """Interface for persistent transition-memory storage."""

    def read_state(self) -> dict[str, Any]:
        """Load current memory state."""

    def write_state(self, state: dict[str, Any]) -> None:
        """Persist memory state."""


@dataclass(frozen=True)
class TransitionDecision:
    """Result details for a PR-open workflow execution."""

    pr_number: int
    pr_title: str
    jira_key: str | None
    already_processed: bool
    transitioned: bool
    reason: str


class JsonFileMemoryStore:
    """Simple JSON-file-backed memory storage."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def read_state(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}

        raw = self.path.read_text(encoding="utf-8").strip()
        if not raw:
            return {}

        state = json.loads(raw)
        if not isinstance(state, dict):
            raise ValueError("Memory store JSON root must be an object")
        return state

    def write_state(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


# Backward-compatible alias used by previous automation code.
JiraTransitionMemoryStore = JsonFileMemoryStore


def _extract_pr_number(event_payload: dict[str, Any]) -> int:
    pull_request = event_payload.get("pull_request")
    if isinstance(pull_request, dict) and pull_request.get("number") is not None:
        pr_number = pull_request["number"]
    else:
        pr_number = event_payload.get("number")

    if not isinstance(pr_number, int) or pr_number <= 0:
        raise ValueError("PR number is missing or invalid in event payload")
    return pr_number


def _extract_pr_title(event_payload: dict[str, Any]) -> str:
    pull_request = event_payload.get("pull_request")
    if isinstance(pull_request, dict) and pull_request.get("title") is not None:
        pr_title = pull_request["title"]
    else:
        pr_title = event_payload.get("title")

    if not isinstance(pr_title, str) or not pr_title.strip():
        raise ValueError("PR title is missing or invalid in event payload")
    return pr_title.strip()


def _ensure_memory_shape(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    transitioned = state.get("transitioned_jira_issues")
    if transitioned is None:
        transitioned = {}
        state["transitioned_jira_issues"] = transitioned
    if not isinstance(transitioned, dict):
        raise ValueError("`transitioned_jira_issues` must be an object")
    return transitioned


def _append_pr_number(record: dict[str, Any], pr_number: int) -> None:
    pr_numbers = record.setdefault("pr_numbers", [])
    if not isinstance(pr_numbers, list):
        raise ValueError("`pr_numbers` must be a list")
    if pr_number not in pr_numbers:
        pr_numbers.append(pr_number)


def handle_pr_opened_workflow(
    event_payload: dict[str, Any],
    atlassian_client: AtlassianClientProtocol,
    memory_store: MemoryStoreProtocol,
) -> TransitionDecision:
    """
    Handle PR-open workflow:
    1) extract PR number/title
    2) resolve Jira key from title using Atlassian client
    3) transition first-seen Jira key to Under Review
    4) persist key to memory to avoid duplicate transitions
    """

    pr_number = _extract_pr_number(event_payload)
    pr_title = _extract_pr_title(event_payload)

    jira_key = atlassian_client.find_jira_issue_key_from_pr_title(pr_title)
    if jira_key is None:
        return TransitionDecision(
            pr_number=pr_number,
            pr_title=pr_title,
            jira_key=None,
            already_processed=False,
            transitioned=False,
            reason="No Jira key found from PR title",
        )

    jira_key = jira_key.strip().upper()
    if not jira_key:
        return TransitionDecision(
            pr_number=pr_number,
            pr_title=pr_title,
            jira_key=None,
            already_processed=False,
            transitioned=False,
            reason="No Jira key found from PR title",
        )

    state = memory_store.read_state()
    transitioned_jira_issues = _ensure_memory_shape(state)

    existing = transitioned_jira_issues.get(jira_key)
    if isinstance(existing, dict):
        _append_pr_number(existing, pr_number)
        memory_store.write_state(state)
        return TransitionDecision(
            pr_number=pr_number,
            pr_title=pr_title,
            jira_key=jira_key,
            already_processed=True,
            transitioned=False,
            reason="Jira key already processed; skipped transition",
        )

    transitioned = atlassian_client.transition_issue_to_under_review(jira_key)
    transitioned_jira_issues[jira_key] = {
        "pr_numbers": [pr_number],
        "transitioned_to_under_review": bool(transitioned),
    }
    memory_store.write_state(state)

    return TransitionDecision(
        pr_number=pr_number,
        pr_title=pr_title,
        jira_key=jira_key,
        already_processed=False,
        transitioned=bool(transitioned),
        reason="Transition attempted for first-seen Jira key",
    )


class JiraPrStateManager:
    """Backward-compatible wrapper class used by older call sites."""

    def __init__(
        self,
        atlassian_client: AtlassianClientProtocol,
        memory_store: MemoryStoreProtocol,
    ) -> None:
        self.atlassian_client = atlassian_client
        self.memory_store = memory_store

    def handle_pr_raised(self, event_payload: dict[str, Any]) -> TransitionDecision:
        return handle_pr_opened_workflow(
            event_payload=event_payload,
            atlassian_client=self.atlassian_client,
            memory_store=self.memory_store,
        )
