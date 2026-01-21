"""Dataset item type for test cases."""
from typing import Any

from pydantic import BaseModel


class DatasetItem(BaseModel):
    """
    A single test case in a dataset.

    Supports three modes:
    1. **Input-only** (before agent runs): {"id": "...", "input": {...}, "expected": {...}}
    2. **With output** (after agent runs): {"id": "...", "input": {...}, "output": {...}, "expected": {...}}
    3. **Production** (no expected): {"id": "...", "input": {...}, "output": {...}}
    
    **Workflows**:
    
    **CI/Local with agent runner:**
    1. Load dataset with input + expected
    2. Agent iterates over items, populates output field
    3. Eval runner matches by id, evaluates output against expected
    
    **CI/Local with pre-captured outputs:**
    1. Load dataset with input + output + expected (agent already ran)
    2. Eval runner directly evaluates output against expected
    
    **Production:**
    1. Agent dumps (id, input, output) pairs
    2. Eval runner evaluates (no expected comparison)
    """

    id: str
    """Unique identifier for this test case (e.g., 'test-001')."""

    input: dict[str, Any]
    """
    Input sent to the agent.
    Common formats:
    - {"prompt": "..."} for completion
    - {"messages": [...]} for chat
    - {"query": "...", "context": "..."} for RAG
    """

    output: Any | None = None
    """
    Agent output (populated by agent after execution).
    Can be string, dict, list, or any serializable data.
    
    - If None: Agent hasn't run yet, runner needs to execute agent
    - If present: Agent already ran, runner evaluates this output
    """

    expected: dict[str, Any] | None = None
    """
    Expected signals for evaluation (only for CI/local testing).
    Common formats:
    - {"contains": "keyword"} for substring checks
    - {"schema": {...}} for JSON schema validation
    - {"keywords": ["auth", "token"]} for custom judges
    
    Not used in production (where we just evaluate output quality, no comparison).
    """

    tags: list[str] = []
    """
    Tags for organizing and filtering test cases.
    E.g., ["regression", "critical"], ["math", "easy"]
    """
