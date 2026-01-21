# AI Evals Platform

A minimal platform for evaluating AI agent outputs across local development, CI pipelines, and production.

## Quick Start

```bash
# Install
pip install -e .

# Run eval
ai-evals \
  -r examples/evals/registry.yaml \
  -e groundedness.v1 \
  -d examples/datasets/regression.jsonl \
  --agent-name my-agent \
  --agent-version v1.0
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  1. Dataset (input + expected)                              │
│                    ↓                                        │
│  2. Agent runs, populates output                            │
│                    ↓                                        │
│  3. Dataset (input + output + expected)                     │
│                    ↓                                        │
│  4. Evaluator → Score                                       │
│                    ↓                                        │
│  5. Sinks (stdout, JSON, Langfuse)                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Workflow

### Step 1: Create Dataset

```jsonl
{"id": "test-001", "input": {"prompt": "What is 2+2?", "context": "Basic math."}, "expected": {"contains": "4"}}
{"id": "test-002", "input": {"prompt": "Capital of France?", "context": "Paris is the capital of France."}}
```

### Step 2: Run Agent (populate output)

```python
from sdk import load_dataset

dataset = load_dataset("dataset.jsonl")
for item in dataset:
    item.output = my_agent.run(item.input)

# Save to new file with outputs
with open("dataset_with_outputs.jsonl", "w") as f:
    for item in dataset:
        f.write(item.model_dump_json() + "\n")
```

### Step 3: Run Evals

```bash
ai-evals \
  -r registry.yaml \
  -e groundedness.v1 \
  -d dataset_with_outputs.jsonl \
  --agent-name my-agent \
  --agent-version abc123
```

---

## Registry Format

```yaml
- eval_id: groundedness.v1
  score_name: groundedness
  evaluator: evaluators/groundedness.py
  environments: [local, ci, prod]
  owner: platform-team
  description: "LLM judge: Check if answer is grounded in context"
```

| Field | Description |
|-------|-------------|
| `eval_id` | Versioned identifier (bump when logic changes) |
| `score_name` | Stable metric name for aggregation |
| `evaluator` | Path to Python module with `evaluate()` function |
| `environments` | Where this eval runs (optional) |
| `owner` | Team responsible |
| `description` | What it measures |

---

## Dataset Format

```jsonl
{"id": "test-001", "input": {"prompt": "...", "context": "..."}, "output": "...", "expected": {"contains": "4"}}
```

| Field | Required | Description |
|-------|----------|-------------|
| `id` | ✅ | Unique test case ID |
| `input` | ✅ | Dict sent to agent |
| `output` | ✅* | Agent's response (*must be populated before eval) |
| `expected` | ❌ | Expected criteria (for benchmarks) |
| `tags` | ❌ | Tags for filtering |

---

## Score Format

```json
{
  "score_name": "groundedness",
  "value": 0.85,
  "eval_id": "groundedness.v1",
  "agent_name": "my-agent",
  "agent_version": "abc123",
  "env": "ci",
  "comment": "Answer is well-grounded in the provided context",
  "metadata": {
    "dataset_item_id": "test-001",
    "judge_model": "gpt-4o-mini"
  }
}
```

---

## Creating Evaluators

### Using LLM Judge

```python
from typing import Any
from sdk.judges import run_llm_judge
from sdk.types import Score

def evaluate(
    input: dict[str, Any],
    output: Any,
    expected: dict[str, Any] | None,
    eval_id: str,
    agent_name: str,
    agent_version: str,
    env: str,
) -> list[Score]:
    verdict = run_llm_judge(
        rubric_id="groundedness.v1",
        answer=str(output),
        evidence=input.get("context", ""),
    )
    
    return [
        Score(
            score_name="groundedness",
            value=verdict.score,
            eval_id=eval_id,
            agent_name=agent_name,
            agent_version=agent_version,
            env=env,
            comment=verdict.reason,
            metadata={"judge_model": verdict.model},
        )
    ]
```

### Custom Logic

```python
def evaluate(input, output, expected, eval_id, agent_name, agent_version, env):
    # Your logic here
    substring = expected.get("contains", "") if expected else ""
    passed = substring.lower() in str(output).lower()
    
    return [
        Score(
            score_name="contains_check",
            value=passed,
            eval_id=eval_id,
            agent_name=agent_name,
            agent_version=agent_version,
            env=env,
        )
    ]
```

---

## CLI Reference

```bash
ai-evals \
  -r registry.yaml \           # Path to registry
  -e groundedness.v1 \         # Eval ID to run
  -d dataset.jsonl \           # Dataset with outputs
  --agent-name my-agent \      # Agent name (required)
  --agent-version v1.0 \       # Agent version (required)
  --env ci \                   # Environment (default: local)
  -o results/ \                # Export JSON results
  --langfuse \                 # Send to Langfuse
  -q                           # Quiet mode
```

---

## Project Structure

```
sdk/
├── __init__.py
├── datasets.py          # load_dataset()
├── registry.py          # load_registry()
├── types/
│   ├── score.py         # Score
│   ├── dataset.py       # DatasetItem
│   └── registry.py      # EvalRegistryEntry
├── judges/
│   ├── base.py          # Judge interface, JudgeVerdict
│   └── llm_judge.py     # LLMRubricJudge, run_llm_judge
└── sinks/
    ├── base.py          # ScoreSink interface
    ├── stdout.py        # StdoutSink
    ├── json_file.py     # JsonFileSink
    └── langfuse.py      # LangfuseSink

runner/
├── cli.py               # Typer CLI
└── engine.py            # run_eval()

examples/
├── evals/
│   ├── registry.yaml
│   └── evaluators/
│       └── groundedness.py
└── datasets/
    └── regression.jsonl
```

---

## CI Integration

```yaml
# .github/workflows/evals.yml
name: Run Evals

on:
  pull_request:
    branches: [main]

jobs:
  evals:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Install
        run: pip install -e .
      
      - name: Run agent on dataset
        run: python my_agent.py --input dataset.jsonl --output outputs.jsonl
      
      - name: Run evals
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          ai-evals -r evals/registry.yaml \
            -e groundedness.v1 \
            -d outputs.jsonl \
            --agent-name my-agent \
            --agent-version ${{ github.sha }} \
            --env ci \
            -o results/
      
      - uses: actions/upload-artifact@v4
        with:
          name: eval-results
          path: results/
```

---

## Extensibility

| Extension | How |
|-----------|-----|
| Custom Evaluator | Implement `evaluate(input, output, expected, ...) -> list[Score]` |
| Custom Judge | Extend `Judge` ABC |
| Custom Sink | Implement `ScoreSink` ABC |
| Custom Rubric | Add to `RUBRICS` dict in `llm_judge.py` |
