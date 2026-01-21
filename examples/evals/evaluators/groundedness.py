"""Groundedness evaluator using LLM judge."""
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
    """
    Evaluate if the answer is grounded in provided evidence.
    
    Uses LLM-as-a-judge to check if the agent's output is supported by
    the evidence/context provided in the input.
    
    Args:
        input: Must contain 'context' or 'evidence' field with source material
        output: The agent's answer to evaluate
        expected: Not used for this eval
        eval_id: ID of this eval
        agent_name: Name of the agent being evaluated
        agent_version: Version of the agent
        env: Environment (local, ci, prod)
    
    Returns:
        List with single Score (0-1 float indicating groundedness)
    """
    answer = str(output or "")
    evidence = input.get("context") or input.get("evidence", "")

    verdict = run_llm_judge(
        rubric_id="groundedness.v1",
        answer=answer,
        evidence=evidence,
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
            metadata={
                "judge_model": verdict.model,
                "rubric_id": verdict.rubric_id,
            },
        )
    ]
