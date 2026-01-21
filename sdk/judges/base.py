"""Base abstractions for judges."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class JudgeVerdict:
    """
    Result from a judge evaluation.

    Contains the score, reasoning, and metadata about how it was judged.
    """

    score: float
    """
    Normalized score from 0.0 to 1.0.
    - 1.0: Perfect/fully satisfies criteria
    - 0.5: Partially satisfies
    - 0.0: Does not satisfy
    """

    reason: str | None
    """Human-readable explanation of the score (e.g., 'Missing key information')."""

    model: str | None = None
    """
    Identifier for the judge that produced this verdict.
    - For LLM judges: model name (e.g., 'gpt-4.1-mini')
    - For custom judges: custom identifier (e.g., 'custom:keyword_presence')
    """

    rubric_id: str | None = None
    """
    ID of the rubric/criteria used (for LLM judges with versioned rubrics).
    E.g., 'groundedness.v1', 'helpfulness.v2'
    """


class Judge(ABC):
    """
    Base class for all judges (LLM-based, rule-based, custom).

    Judges evaluate model outputs and return a verdict with score and reasoning.
    Teams can extend this to create custom evaluation logic.
    """

    @abstractmethod
    def evaluate(self, answer: str, context: dict[str, Any]) -> JudgeVerdict:
        """
        Evaluate an answer and return a verdict.

        Args:
            answer: The model output to evaluate (text, JSON, etc. as string)
            context: Additional context needed for evaluation
                - 'evidence': Retrieved docs or tool outputs (for grounding)
                - 'expected': Expected output or signals (for comparison)
                - Any other custom keys needed by the judge

        Returns:
            JudgeVerdict with score (0-1), reason, and metadata

        Example:
            verdict = judge.evaluate(
                answer="Paris is the capital of France",
                context={"evidence": "France's capital is Paris."}
            )
            # JudgeVerdict(score=1.0, reason="Fully supported", ...)
        """
        pass
