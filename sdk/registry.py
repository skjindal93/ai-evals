"""Registry loading utilities."""
from pathlib import Path

import yaml

from sdk.types import EvalRegistryEntry


def load_registry(path: str | Path) -> list[EvalRegistryEntry]:
    """
    Load and validate registry.yaml file.

    Args:
        path: Path to registry.yaml

    Returns:
        List of validated EvalRegistryEntry objects

    Raises:
        ValueError: If registry format is invalid
        ValidationError: If entries don't match schema
    """
    path = Path(path)
    with path.open() as f:
        data = yaml.safe_load(f)

    if not isinstance(data, list):
        raise ValueError(f"Registry must be a list, got {type(data)}")

    return [EvalRegistryEntry.model_validate(entry) for entry in data]
