"""LLM-as-a-judge implementation with predefined rubrics."""
import json
from typing import Any

from openai import OpenAI

from sdk.judges.base import Judge, JudgeVerdict

# Built-in rubrics maintained by the platform
RUBRICS = {
    "groundedness.v1": """You are evaluating whether an AI answer is grounded in the provided evidence.

Evidence:
{evidence}

Answer:
{answer}

Score from 0.0 to 1.0:
- 1.0: Fully supported by evidence
- 0.5: Partially supported, some claims unsupported
- 0.0: Not supported or contradicts evidence

Respond ONLY with JSON: {{"score": <float>, "reason": "<brief explanation>"}}""",
    "helpfulness.v1": """You are evaluating whether an AI answer is helpful and complete.

Answer:
{answer}

Score from 0.0 to 1.0:
- 1.0: Comprehensive, accurate, directly addresses the question
- 0.5: Partially helpful, missing some information
- 0.0: Unhelpful, incorrect, or off-topic

Respond ONLY with JSON: {{"score": <float>, "reason": "<brief explanation>"}}""",
}


class LLMRubricJudge(Judge):
    """
    LLM-as-a-judge using predefined rubrics.

    Uses an LLM (e.g., GPT-4) to evaluate outputs against structured criteria.
    Platform provides built-in rubrics; teams can also define custom ones.
    """

    def __init__(self, rubric_id: str, model: str = "gpt-4.1-mini", client: OpenAI | None = None):
        """
        Initialize an LLM rubric judge.

        Args:
            rubric_id: ID of the built-in rubric to use (e.g., 'groundedness.v1')
            model: OpenAI model to use for judging (default: gpt-4.1-mini)
            client: Optional OpenAI client (will create default if not provided)

        Raises:
            ValueError: If rubric_id is not found in built-in rubrics
        """
        if rubric_id not in RUBRICS:
            raise ValueError(f"Unknown rubric: {rubric_id}. Available: {list(RUBRICS.keys())}")

        self.rubric_id = rubric_id
        self.model = model
        self.client = client or OpenAI()

    def evaluate(self, answer: str, context: dict[str, Any]) -> JudgeVerdict:
        """
        Evaluate answer using the configured rubric.

        Args:
            answer: The model output to evaluate
            context: Dict with 'evidence' key (for grounding rubrics)

        Returns:
            JudgeVerdict with score (0-1), reason, model, and rubric_id

        Raises:
            ValueError: If LLM response cannot be parsed
        """
        evidence = context.get("evidence", "N/A")
        prompt = RUBRICS[self.rubric_id].format(answer=answer, evidence=evidence)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )

        content = response.choices[0].message.content or ""

        try:
            result = json.loads(content)
            return JudgeVerdict(
                score=float(result["score"]),
                reason=result.get("reason"),
                model=self.model,
                rubric_id=self.rubric_id,
            )
        except (json.JSONDecodeError, KeyError) as e:
            raise ValueError(f"Failed to parse judge response: {content}") from e


def run_llm_judge(
    rubric_id: str,
    answer: str,
    evidence: str | None = None,
    model: str = "gpt-4.1-mini",
    client: OpenAI | None = None,
) -> JudgeVerdict:
    """
    Helper function to run an LLM judge with a predefined rubric.

    This is a convenience wrapper around LLMRubricJudge for simple use cases.
    For custom judges or reusable judge instances, use LLMRubricJudge directly.

    Args:
        rubric_id: ID of the built-in rubric (e.g., 'groundedness.v1')
        answer: The model output to evaluate
        evidence: Optional evidence/context for grounding (default: None)
        model: OpenAI model to use (default: gpt-4.1-mini)
        client: Optional OpenAI client

    Returns:
        JudgeVerdict with score, reason, and metadata

    Example:
        verdict = run_llm_judge(
            rubric_id="groundedness.v1",
            answer="Paris is the capital of France",
            evidence="France's capital is Paris."
        )
        # JudgeVerdict(score=1.0, reason="Fully supported", ...)
    """
    judge = LLMRubricJudge(rubric_id=rubric_id, model=model, client=client)
    return judge.evaluate(answer=answer, context={"evidence": evidence})
