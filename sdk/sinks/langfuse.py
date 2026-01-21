"""Langfuse sink for visualization and debugging."""
from langfuse import Langfuse

from sdk.types import Score
from sdk.sinks.base import ScoreSink


class LangfuseSink(ScoreSink):
    """
    Write scores to Langfuse for visualization and debugging.

    Used in CI and production to attach eval results to traces.
    Requires Langfuse environment variables to be set.
    """

    def __init__(self):
        """
        Initialize Langfuse sink.

        Requires environment variables:
        - LANGFUSE_PUBLIC_KEY
        - LANGFUSE_SECRET_KEY
        - LANGFUSE_HOST
        """
        self.client = Langfuse()

    def emit(self, score: Score) -> None:
        """
        Write score to Langfuse.

        Score will be attached to the specified trace/observation.
        """
        self.client.score(
            name=score.score_name,
            value=float(score.value) if isinstance(score.value, bool) else score.value,
            trace_id=score.trace_id,
            observation_id=score.observation_id,
            comment=score.comment,
            metadata=score.metadata,
        )

    def flush(self) -> None:
        """Flush buffered writes to Langfuse."""
        self.client.flush()
