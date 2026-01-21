"""Registry entry type for eval definitions."""
from typing import Literal

from pydantic import BaseModel


class EvalRegistryEntry(BaseModel):
    """
    Definition of an eval in registry.yaml.

    Each entry describes one eval that can be run by the platform.
    
    Example:
        eval_id: groundedness.v1
        score_name: groundedness
        evaluator: evaluators/groundedness.py
        environments: [ci, prod]
        owner: platform-team
        description: "Check if LLM response is grounded in provided context"
    """

    eval_id: str
    """
    Unique versioned identifier for this eval (e.g., 'groundedness.v1').
    Should be stable across changes. Bump version when logic changes.
    """

    score_name: str
    """
    Stable metric name used for aggregation and monitoring (e.g., 'groundedness').
    Should not change even when eval_id version bumps.
    """

    evaluator: str
    """
    Path to the evaluator module (relative to registry.yaml).
    E.g., 'evaluators/groundedness.py'
    
    Must contain an 'evaluate(input, output, expected) -> list[Score]' function.
    - input: dict[str, Any] - The input sent to the agent
    - output: Any - The agent's output
    - expected: dict[str, Any] | None - Expected values for comparison (if available)
    """

    environments: list[str] | None = None
    """
    Environments where this eval should run (e.g., ['ci', 'prod'], ['local']).
    Optional: if not specified, eval can run in any environment.
    """

    owner: str
    """Team or person responsible for maintaining this eval."""

    description: str | None = None
    """Human-readable description of what this eval measures."""
    
    # Phase 2 fields (not implemented yet)
    # scope: Literal["observation", "trace", "session"] - for trace-based evals
    # selector: str - for picking specific observations from traces
