import json

from ..db_models import InterviewAnalysis, InterviewDocument, InterviewSegment


INTERVIEW_PROPOSAL_PROMPT_VERSION = "interview-proposal-v1"
INTERVIEW_DRAFT_PROMPT_VERSION = "interview-process-draft-v1"
MULTI_INTERVIEW_DRAFT_PROMPT_VERSION = "multi-interview-process-draft-v1"


def interview_proposal_prompt(*, document: InterviewDocument, analysis: InterviewAnalysis, selected_facts: list[dict], segments: list[InterviewSegment], process_ir: dict) -> list[dict[str, str]]:
    evidence_ids = {segment_id for fact in selected_facts for segment_id in fact["segment_ids"]}
    evidence = [{"id": item.id, "speaker": item.speaker, "text": item.text} for item in segments if item.id in evidence_ids]
    return [
        {"role": "system", "content": (
            "You prepare a reviewable RFC 6902 JSON Patch for the supplied Current Process IR. Use only the explicitly selected confirmed facts and their evidence. "
            "Do not use candidate facts, contradictions, clarification questions, or outside knowledge. Do not invent actors, systems, rules, identifiers, sequence, or integration settings. "
            "If a selected fact cannot be represented safely, leave it unapplied and explain that in message. Preserve all unrelated Process IR content. "
            "Return one JSON object only with message, summary, and patch. patch must be a non-empty array of valid RFC 6902 operations against Current Process IR. "
            "Use ordinary workplace language for message and summary, in the interview language."
        )},
        {"role": "user", "content": (
            f"Interview language: {document.language}\nAnalysis ID: {analysis.id}\n"
            f"Selected confirmed facts:\n{json.dumps(selected_facts, ensure_ascii=False)}\n"
            f"Evidence segments:\n{json.dumps(evidence, ensure_ascii=False)}\n"
            f"Current Process IR:\n{json.dumps(process_ir, ensure_ascii=False)}"
        )},
    ]


def interview_process_draft_prompt(*, document: InterviewDocument, analysis: InterviewAnalysis, confirmed_facts: list[dict], segments: list[InterviewSegment], process_ir: dict) -> list[dict[str, str]]:
    evidence_ids = {segment_id for fact in confirmed_facts for segment_id in fact["segment_ids"]}
    evidence = [{"id": item.id, "speaker": item.speaker, "text": item.text} for item in segments if item.id in evidence_ids]
    questions = [{"question": item["question"], "priority": item["priority"], "segment_ids": item["segment_ids"]} for item in analysis.result.get("clarification_questions", [])]
    return [
        {"role": "system", "content": (
            "You prepare one reviewable RFC 6902 JSON Patch that turns Current Process IR into a coherent multi-step process draft. "
            "Use all and only Confirmed facts and their Evidence segments for factual content. Do not use candidate facts, contradictions, or outside knowledge. "
            "Derive sequence only when explicitly stated. Preserve uncertainty: clarification questions may become Process IR openQuestions but never answers, conditions, parameters, actors, systems, or rules. "
            "Create or update a connected graph with start, confirmed tasks or decisions, edges, and end. A decision requires an explicit confirmed branching rule; otherwise use a task and an open question. "
            "Do not invent integration methods, field schemas, thresholds, owners, identifiers, or automation settings. Preserve unrelated confirmed Current Process IR content. "
            "Return one JSON object only with message, summary, and a non-empty RFC 6902 patch valid against Current Process IR. Use ordinary workplace language for message and summary, in the interview language."
        )},
        {"role": "user", "content": (
            f"Interview language: {document.language}\nAnalysis ID: {analysis.id}\n"
            f"Confirmed facts:\n{json.dumps(confirmed_facts, ensure_ascii=False)}\n"
            f"Evidence segments:\n{json.dumps(evidence, ensure_ascii=False)}\n"
            f"Clarification questions (open questions only):\n{json.dumps(questions, ensure_ascii=False)}\n"
            f"Current Process IR:\n{json.dumps(process_ir, ensure_ascii=False)}"
        )},
    ]


def multi_interview_process_draft_prompt(*, language: str, facts: list[dict], evidence: list[dict], questions: list[dict], process_ir: dict) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": (
            "You prepare one reviewable RFC 6902 JSON Patch that turns Current Process IR into a coherent multi-step process draft based on multiple reviewed interviews. "
            "Use all and only Aggregated confirmed facts and their Evidence records. Repeated evidence supports one fact and must not create repeated steps. "
            "No unresolved contradictions are supplied. Do not infer answers from omissions, candidate facts, or outside knowledge. "
            "Derive sequence only when explicitly stated. Clarification questions may become Process IR openQuestions but never answers, conditions, parameters, actors, systems, or rules. "
            "Create or update a connected graph with start, confirmed tasks or decisions, edges, and end. A decision requires an explicit confirmed branching rule. "
            "Do not invent integration methods, field schemas, thresholds, owners, identifiers, or automation settings. Preserve unrelated confirmed Current Process IR content. "
            "Return one JSON object only with message, summary, and a non-empty RFC 6902 patch valid against Current Process IR. Use ordinary workplace language for message and summary in the requested language."
        )},
        {"role": "user", "content": (
            f"Output language: {language}\n"
            f"Aggregated confirmed facts:\n{json.dumps(facts, ensure_ascii=False)}\n"
            f"Evidence records:\n{json.dumps(evidence, ensure_ascii=False)}\n"
            f"Clarification questions (open questions only):\n{json.dumps(questions, ensure_ascii=False)}\n"
            f"Current Process IR:\n{json.dumps(process_ir, ensure_ascii=False)}"
        )},
    ]
