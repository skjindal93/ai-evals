"""Base sink abstraction."""
from abc import ABC, abstractmethod

from sdk.types import Score


def _is_passing(score: Score) -> bool:
    """
    Check if a score is considered passing.

    Args:
        score: Score to check

    Returns:
        True if score.value is True (for bool) or >= 0.5 (for float)
    """
    if isinstance(score.value, bool):
        return score.value
    if isinstance(score.value, float):
        return score.value >= 0.5
    return False


class ScoreSink(ABC):
    """
    Base class for score output destinations.

    Sinks receive scores from evaluators and handle output formatting,
    storage, or transmission to external systems.
    """

    @abstractmethod
    def emit(self, score: Score) -> None:
        """
        Emit a single score.

        Called once per score as evaluators produce them.

        Args:
            score: The score to output
        """
        pass

    @abstractmethod
    def flush(self) -> None:
        """
        Flush any buffered scores and output summary.

        Called once at the end of an eval run.
        """
        pass
