"""Score type for evaluation results."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Score:
    """
    The output of an eval - a measured value for a specific execution.

    Scores are emitted by evaluators and sent to sinks (stdout, JSON files, Langfuse).
    """

    # Core measurement
    score_name: str
    """Stable metric name (e.g., 'groundedness', 'contains_check')."""

    value: float | bool
    """The measured value. Float for continuous scores (0-1), bool for binary pass/fail."""

    # Context (required for tracking and analysis)
    eval_id: str
    """Versioned eval identifier (e.g., 'groundedness.v1'). Critical for tracking eval changes."""

    agent_name: str
    """Name of the agent being evaluated (e.g., 'unified-agent', 'rag-chatbot')."""

    agent_version: str
    """Version/commit of the agent (e.g., 'abc123', 'v2.1.0'). Essential for regression tracking."""

    env: str
    """Environment where eval ran (e.g., 'local', 'ci', 'prod'). Used for filtering and analysis."""

    # Optional - Langfuse linking
    trace_id: str | None = None
    """Optional: Trace ID in Langfuse for linking score to trace visualization."""

    observation_id: str | None = None
    """Optional: Observation ID in Langfuse for linking score to specific LLM call."""

    comment: str | None = None
    """Human-readable explanation of the score (e.g., why it failed, what was wrong)."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """
    Additional context about the score.
    Common keys: judge_model, rubric_id, latency_ms, dataset_item_id, etc.
    """
