from sqlalchemy.orm import Session

from ..db_models import InterviewAnalysis, User
from ..process_templates import suggest_process_template
from .interview_proposals import InterviewAnalysisNotFound
from .interviews import InterviewRevisionConflict, _require_document


def match_interview_template(
    db: Session,
    *,
    user: User,
    analysis_id: str,
    locale: str,
    excluded_ids: list[str],
) -> tuple[InterviewAnalysis, list[int], dict | None]:
    analysis = db.get(InterviewAnalysis, analysis_id)
    if analysis is None:
        raise InterviewAnalysisNotFound("Interview analysis does not exist.")
    document = _require_document(db, analysis.document_id, user)
    if document.status != "reviewed" or document.segments_sha256 != analysis.segments_sha256:
        raise InterviewRevisionConflict("The transcript or analysis changed. Review and analyze it again.")

    confirmed_facts = analysis.result.get("confirmed_facts", [])
    confirmed_indices = list(range(len(confirmed_facts)))
    confirmed_text = "\n".join(item["statement"] for item in confirmed_facts)
    suggestion = suggest_process_template(
        confirmed_text,
        locale,
        set(excluded_ids),
    ) if confirmed_text else None
    return analysis, confirmed_indices, suggestion
