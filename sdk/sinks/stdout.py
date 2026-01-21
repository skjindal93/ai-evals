"""Stdout sink for terminal output."""
import json
from dataclasses import asdict

from sdk.types import Score
from sdk.sinks.base import ScoreSink, _is_passing


class StdoutSink(ScoreSink):
    """
    Print scores to stdout (terminal).

    Used for local development and immediate feedback.
    Supports pretty-printed format (with colors/symbols) or JSON.
    """

    def __init__(self, pretty: bool = True):
        """
        Initialize stdout sink.

        Args:
            pretty: If True, use pretty format with ✓/✗ symbols.
                   If False, output raw JSON (one score per line).
        """
        self.pretty = pretty
        self.total = 0
        self.passed = 0

    def emit(self, score: Score) -> None:
        """Print score to stdout."""
        self.total += 1
        if _is_passing(score):
            self.passed += 1

        if self.pretty:
            status = "✓" if score.value else "✗" if isinstance(score.value, bool) else ""
            print(f"  {score.score_name}: {score.value} {status}")
            if score.comment:
                print(f"    └─ {score.comment}")
        else:
            print(json.dumps(asdict(score)))

    def flush(self) -> None:
        """Print summary statistics."""
        if self.pretty and self.total > 0:
            print(f"\nSummary: {self.passed}/{self.total} passed")
