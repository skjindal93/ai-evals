"""Core evaluation engine for running evals on agent outputs."""
import importlib.util
from pathlib import Path
from typing import Any, Callable

from sdk.datasets import load_dataset
from sdk.registry import load_registry
from sdk.sinks import ScoreSink, StdoutSink
from sdk.types import DatasetItem, Score


def load_evaluator(registry_path: Path, evaluator_path: str) -> Callable:
    """
    Dynamically load an evaluator module.
    
    Args:
        registry_path: Path to registry.yaml (used to resolve relative paths)
        evaluator_path: Relative path to evaluator module
    
    Returns:
        The evaluate function from the module
    
    Raises:
        ValueError: If evaluator cannot be loaded or doesn't have evaluate function
    """
    full_path = registry_path.parent / evaluator_path

    spec = importlib.util.spec_from_file_location("evaluator", full_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load evaluator from {full_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "evaluate"):
        raise ValueError(f"Evaluator {full_path} must have an 'evaluate' function")

    return module.evaluate


def run_eval(
    registry_path: str | Path,
    eval_id: str,
    dataset: list[DatasetItem],
    agent_name: str,
    agent_version: str,
    env: str,
    sinks: list[ScoreSink] | None = None,
) -> list[Score]:
    """
    Run an eval on dataset items (with agent outputs).
    
    **Phase 1 Workflow:**
    1. Load eval definition from registry
    2. For each dataset item with output:
       a. Call evaluator with (input, output, expected)
       b. Evaluator returns scores with context fields
       c. Emit scores to sinks
    
    Args:
        registry_path: Path to registry.yaml
        eval_id: ID of the eval to run (e.g., "groundedness.v1")
        dataset: List of dataset items (must have output populated)
        agent_name: Name of the agent being evaluated
        agent_version: Version/commit of the agent
        env: Environment (e.g., 'local', 'ci', 'prod')
        sinks: List of sinks to emit scores to
    
    Returns:
        List of all scores produced
    
    Raises:
        ValueError: If eval not found, dataset items missing output, etc.
    """
    registry_path = Path(registry_path)
    sinks = sinks or [StdoutSink()]

    # Load registry and find eval
    registry = load_registry(registry_path)
    entry = next((e for e in registry if e.eval_id == eval_id), None)
    if entry is None:
        available = [e.eval_id for e in registry]
        raise ValueError(f"Eval '{eval_id}' not found. Available: {available}")

    # Check environment compatibility
    if entry.environments and env not in entry.environments:
        raise ValueError(
            f"Eval '{eval_id}' not configured for environment '{env}'. "
            f"Supported: {entry.environments}"
        )

    # Load evaluator
    evaluate_fn = load_evaluator(registry_path, entry.evaluator)

    # Validate dataset items have outputs
    items_without_output = [item.id for item in dataset if item.output is None]
    if items_without_output:
        raise ValueError(
            f"Dataset items missing output field: {items_without_output}. "
            f"Agent must populate output before running evals."
        )

    # Run evaluation
    all_scores: list[Score] = []
    for item in dataset:
        # Call evaluator with input/output/expected
        scores = evaluate_fn(
            input=item.input,
            output=item.output,
            expected=item.expected,
            eval_id=eval_id,
            agent_name=agent_name,
            agent_version=agent_version,
            env=env,
        )
        
        # Emit scores
        for score in scores:
            # Enrich with dataset_item_id if not already in metadata
            if "dataset_item_id" not in score.metadata:
                score.metadata["dataset_item_id"] = item.id
            
            all_scores.append(score)
            for sink in sinks:
                sink.emit(score)

    # Flush all sinks
    for sink in sinks:
        sink.flush()

    return all_scores
