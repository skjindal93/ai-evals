"""JSON file sink for CI artifacts."""
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from sdk.types import Score
from sdk.sinks.base import ScoreSink, _is_passing


class JsonFileSink(ScoreSink):
    """
    Export results to JSON file.

    Used for CI artifacts and offline review.
    Creates timestamped files with all scores and summary.
    """

    def __init__(self, output_dir: str | Path):
        """
        Initialize JSON file sink.

        Args:
            output_dir: Directory to write results to (will be created if needed)
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.scores: list[Score] = []
        self.run_id = datetime.now().strftime("run_%Y%m%d_%H%M%S")

    def emit(self, score: Score) -> None:
        """Buffer score for later writing."""
        self.scores.append(score)

    def flush(self) -> None:
        """Write all scores to JSON file."""
        if not self.scores:
            return

        output = {
            "run_id": self.run_id,
            "scores": [asdict(s) for s in self.scores],
            "summary": {
                "total": len(self.scores),
                "passed": sum(1 for s in self.scores if _is_passing(s)),
            },
        }

        path = self.output_dir / f"{self.run_id}.json"
        with path.open("w") as f:
            json.dump(output, f, indent=2)
        print(f"Results written to {path}")
