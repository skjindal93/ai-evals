"""PR to Jira state management with deduplicated transitions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

JIRA_KEY_PATTERN = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")


class AtlassianJiraClient(Protocol):
    """Interface for Jira operations backed by Atlassian MCP calls."""

    def find_jira_from_pr_title(self, pr_title: str) -> str | None:
        """Return Jira key for a PR title, or None if no match is found."""

    def transition_to_under_review(self, jira_key: str) -> None:
        """Move Jira issue into the Under Review state."""


@dataclass(frozen=True)
class TransitionDecision:
    """Outcome of processing a pull request event."""

    action: Literal["transitioned", "skipped_existing", "no_jira_found"]
    jira_key: str | None = None


class JiraTransitionMemoryStore:
    """Persistent deduplication store for Jira transition state."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    @staticmethod
    def _default_state() -> dict[str, dict[str, dict[str, int]]]:
        return {"jira_keys": {}}

    def _read_state(self) -> dict[str, dict[str, dict[str, int]]]:
        if not self.path.exists():
            return self._default_state()

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._default_state()

        jira_keys = raw.get("jira_keys", {})
        if not isinstance(jira_keys, dict):
            return self._default_state()

        return {"jira_keys": jira_keys}

    def _write_state(self, state: dict[str, dict[str, dict[str, int]]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")

    def has_jira(self, jira_key: str) -> bool:
        state = self._read_state()
        return jira_key in state["jira_keys"]

    def remember_jira(self, jira_key: str, pr_number: int) -> None:
        state = self._read_state()
        existing = state["jira_keys"].get(jira_key)

        if existing is None:
            state["jira_keys"][jira_key] = {
                "first_pr_number": pr_number,
                "latest_pr_number": pr_number,
            }
        else:
            existing["latest_pr_number"] = pr_number

        self._write_state(state)


def extract_jira_key(text: str) -> str | None:
    """Extract Jira key from text such as a PR title."""
    match = JIRA_KEY_PATTERN.search(text.upper())
    if not match:
        return None
    return match.group(1)


class JiraPrStateManager:
    """Coordinates PR events with Jira transitions and memory state."""

    def __init__(self, atlassian_client: AtlassianJiraClient, memory_store: JiraTransitionMemoryStore):
        self.atlassian_client = atlassian_client
        self.memory_store = memory_store

    def _resolve_jira_key(self, pr_title: str) -> str | None:
        title_key = extract_jira_key(pr_title)
        if title_key:
            return title_key

        return self.atlassian_client.find_jira_from_pr_title(pr_title)

    def handle_pr_raised(self, pr_number: int, pr_title: str) -> TransitionDecision:
        """
        Handle a PR-raised event.

        Behavior:
        - Resolve Jira from PR title (direct key extraction first, then Atlassian search).
        - If Jira was already transitioned previously, skip.
        - Otherwise, move Jira to Under Review and persist memory.
        """
        jira_key = self._resolve_jira_key(pr_title)
        if not jira_key:
            return TransitionDecision(action="no_jira_found")

        if self.memory_store.has_jira(jira_key):
            self.memory_store.remember_jira(jira_key, pr_number)
            return TransitionDecision(action="skipped_existing", jira_key=jira_key)

        self.atlassian_client.transition_to_under_review(jira_key)
        self.memory_store.remember_jira(jira_key, pr_number)
        return TransitionDecision(action="transitioned", jira_key=jira_key)
