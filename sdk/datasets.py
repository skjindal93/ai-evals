"""Dataset loading utilities."""
import json
from pathlib import Path

from sdk.types import DatasetItem


def load_dataset(path: str | Path) -> list[DatasetItem]:
    """
    Load dataset from JSONL file.

    Each line must be a valid JSON object matching the DatasetItem schema.

    Args:
        path: Path to .jsonl file

    Returns:
        List of validated DatasetItem objects

    Raises:
        ValueError: If any line fails to parse or validate
    """
    path = Path(path)
    items = []

    with path.open() as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                items.append(DatasetItem.model_validate(data))
            except Exception as e:
                raise ValueError(f"Error parsing line {line_num}: {e}") from e

    return items
