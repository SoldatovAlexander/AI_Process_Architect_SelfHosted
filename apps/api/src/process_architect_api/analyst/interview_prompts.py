import json

from ..db_models import InterviewDocument, InterviewSegment


INTERVIEW_ANALYSIS_PROMPT_VERSION = "interview-analysis-v1"


def interview_analysis_prompt(document: InterviewDocument, segments: list[InterviewSegment]) -> list[dict[str, str]]:
    transcript = [{"id": item.id, "speaker": item.speaker, "text": item.text, "startMs": item.start_ms, "endMs": item.end_ms} for item in segments]
    return [
        {"role": "system", "content": (
            "You analyze a reviewed customer interview for business process design. Return one JSON object only. "
            "Do not create Process IR or implementation details. Classify direct supported statements as confirmed_facts; "
            "inferences or ambiguous claims as candidate_facts with a reason; mutually incompatible statements as contradictions; "
            "and missing information needed to define the process as clarification_questions. Every item must cite segment_ids from the supplied transcript only. "
            "A contradiction must cite at least two segments. Do not repeat the same meaning in confirmed_facts and candidate_facts. "
            "Questions use priority blocking, important, or optional and must be understandable to a non-specialist. Write all statements and questions in the interview language. "
            "Exact output keys: confirmed_facts[{statement,segment_ids}], candidate_facts[{statement,reason,segment_ids}], "
            "contradictions[{summary,segment_ids,question}], clarification_questions[{question,reason,priority,segment_ids}]."
        )},
        {"role": "user", "content": f"Interview language: {document.language}\nReviewed transcript JSON:\n{json.dumps(transcript, ensure_ascii=False)}"},
    ]
