import json


CROSS_INTERVIEW_CONFLICT_PROMPT_VERSION = "cross-interview-conflicts-v1"


def cross_interview_conflict_prompt(*, language: str, facts: list[dict]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": (
            "Compare confirmed facts from different reviewed interviews. Return JSON only with key conflicts. "
            "Report only facts that cannot both be true for the same process scope or rule. Different steps, roles, time periods, optional variants, missing detail, or merely different wording are not conflicts. "
            "Every conflict must cite at least two supplied fact references from at least two different analysis IDs. Never invent references or facts. "
            "Write summary, question, and reason in the requested language for a non-specialist. "
            "Exact shape: {conflicts:[{summary,question,reason,fact_references:[{analysis_id,fact_index}]}]}."
        )},
        {"role": "user", "content": f"Output language: {language}\nConfirmed facts:\n{json.dumps(facts, ensure_ascii=False)}"},
    ]
