"""
LLM-as-judge evaluators for the Oasia agent workflow.

Four scorers are provided, each extending weave.Scorer and decorated
with @weave.op() so every judge call is itself traced in Weave:

  RelevanceScorer       — Is the response on-topic for the MBS question?
  FinancialAccuracyScorer — Are financial terms/concepts used correctly?
  ActionabilityScorer   — Is the response concrete and actionable?
  ToolCoverageScorer    — Did the agent invoke the expected tools?

All scorers return a dict with:
  {"score": 0.0–1.0, "passed": bool, "reasoning": str}

Usage (see evals/run_evals.py):
  evaluation = weave.Evaluation(
      dataset=EVAL_DATASET,
      scorers=[RelevanceScorer(), FinancialAccuracyScorer(), ...],
  )
"""
from __future__ import annotations

import json
import os
from typing import Any

import weave


_JUDGE_MODEL = os.getenv("WEAVE_JUDGE_MODEL", "gpt-4o")

_JSON_FORMAT = {"type": "json_object"}

_SYSTEM = (
    "You are an expert evaluator for an Agency MBS (Mortgage-Backed Securities) "
    "trading desk AI assistant. You score AI-generated responses on the dimension "
    "specified. Return ONLY valid JSON with keys: score (float 0-1), passed (bool), "
    "reasoning (str, ≤ 60 words)."
)


def _llm_judge(prompt: str) -> dict:
    """Call the judge LLM and parse the JSON result."""
    import openai
    client = openai.OpenAI()
    resp = client.chat.completions.create(
        model=_JUDGE_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user",   "content": prompt},
        ],
        response_format=_JSON_FORMAT,
        temperature=0,
        max_tokens=256,
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        result = json.loads(raw)
        return {
            "score":     float(result.get("score", 0.0)),
            "passed":    bool(result.get("passed", False)),
            "reasoning": str(result.get("reasoning", "")),
        }
    except (json.JSONDecodeError, ValueError):
        return {"score": 0.0, "passed": False, "reasoning": "Judge returned invalid JSON."}


# ─── Scorer 1: Relevance ──────────────────────────────────────────────────────

class RelevanceScorer(weave.Scorer):
    """
    Judge: Does the response directly and fully address the user's question
    in the context of MBS portfolio management?

    Score 1.0 = fully on-topic, addresses all key aspects of the question.
    Score 0.0 = completely off-topic or refuses to answer.
    """

    @weave.op()
    def score(self, output: str, question: str, **kwargs) -> dict:
        prompt = f"""
Question asked to the MBS trading desk AI:
\"\"\"{question}\"\"\"

AI response:
\"\"\"{output}\"\"\"

Score the RELEVANCE of the response (0–1):
  1.0 — fully addresses the question with MBS-specific detail
  0.5 — partially addresses, missing key aspects
  0.0 — off-topic, generic, or refuses to answer

Return JSON: {{"score": <float>, "passed": <bool (>=0.6)>, "reasoning": <str>}}
""".strip()
        return _llm_judge(prompt)


# ─── Scorer 2: Financial Accuracy ────────────────────────────────────────────

class FinancialAccuracyScorer(weave.Scorer):
    """
    Judge: Are MBS financial concepts, metrics, and terminology used correctly?

    Checks for correct use of OAS, OAD, convexity, CPR, EVE, WAC, WALA, etc.
    Penalises hallucinated numbers or backwards relationships
    (e.g. claiming higher OAS means lower spread).
    """

    @weave.op()
    def score(self, output: str, question: str, expected_topics: list | None = None, **kwargs) -> dict:
        topics_hint = (
            f"Key MBS topics expected: {', '.join(expected_topics)}."
            if expected_topics else ""
        )
        prompt = f"""
Question: \"\"\"{question}\"\"\"
{topics_hint}

AI response:
\"\"\"{output}\"\"\"

Score FINANCIAL ACCURACY (0–1) for an MBS trading desk context:
  1.0 — all financial terms/metrics are correct; relationships are accurate
  0.5 — minor errors or imprecise terminology
  0.0 — significant errors (e.g. wrong direction of duration, hallucinated OAS values)

Return JSON: {{"score": <float>, "passed": <bool (>=0.7)>, "reasoning": <str>}}
""".strip()
        return _llm_judge(prompt)


# ─── Scorer 3: Actionability ──────────────────────────────────────────────────

class ActionabilityScorer(weave.Scorer):
    """
    Judge: Is the response concrete and actionable for a portfolio manager?

    A good response gives specific numbers, pool IDs, or clear next steps —
    not vague statements like "OAS can vary depending on conditions".
    """

    @weave.op()
    def score(self, output: str, question: str, **kwargs) -> dict:
        prompt = f"""
A portfolio manager asked an MBS trading desk AI:
\"\"\"{question}\"\"\"

AI response:
\"\"\"{output}\"\"\"

Score ACTIONABILITY (0–1):
  1.0 — gives specific metrics, pool IDs, or clear next steps a PM can act on
  0.5 — some specifics but also vague or incomplete conclusions
  0.0 — only generic statements, no concrete data or recommendations

Return JSON: {{"score": <float>, "passed": <bool (>=0.6)>, "reasoning": <str>}}
""".strip()
        return _llm_judge(prompt)


# ─── Scorer 4: Tool Coverage ──────────────────────────────────────────────────

class ToolCoverageScorer(weave.Scorer):
    """
    Judge: Did the agent invoke the expected analytics tools?

    Compares the tools mentioned / evidenced in the response against
    the `expected_tools` field from the evaluation dataset.
    Does a soft match — checks for tool-name keywords in the response
    or explicit tool-result patterns (table, OAS= prefix, etc.).
    """

    @weave.op()
    def score(
        self,
        output: str,
        expected_tools: list | None = None,
        **kwargs,
    ) -> dict:
        if not expected_tools:
            return {"score": 1.0, "passed": True, "reasoning": "No expected tools specified."}

        tools_str = ", ".join(expected_tools)
        prompt = f"""
The following MBS agent response was generated. We expected the agent to use
these analytics tools during its reasoning: [{tools_str}].

Agent response:
\"\"\"{output}\"\"\"

Score TOOL COVERAGE (0–1):
  1.0 — response clearly reflects data from all expected tools
         (correct metrics, structure consistent with tool outputs)
  0.5 — evidence of some but not all expected tools
  0.0 — response ignores the expected tools entirely (e.g. generic answer with no data)

Return JSON: {{"score": <float>, "passed": <bool (>=0.5)>, "reasoning": <str>}}
""".strip()
        return _llm_judge(prompt)
