from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import AnalystMessage, AnalystSession, InterviewAnalysis, InterviewDocument, InterviewSegment, ProposedPatch


def find_analyst_session(db: Session, session_id: str) -> AnalystSession | None:
    return db.get(AnalystSession, session_id)


def list_project_sessions(db: Session, project_id: str) -> list[AnalystSession]:
    return list(
        db.scalars(
            select(AnalystSession)
            .where(AnalystSession.project_id == project_id)
            .order_by(AnalystSession.created_at)
        )
    )


def list_session_messages(db: Session, session_id: str) -> list[AnalystMessage]:
    return list(
        db.scalars(
            select(AnalystMessage)
            .where(AnalystMessage.session_id == session_id)
            .order_by(AnalystMessage.created_at, AnalystMessage.id)
        )
    )


def list_session_proposals(db: Session, session_id: str) -> list[ProposedPatch]:
    return list(
        db.scalars(
            select(ProposedPatch)
            .where(ProposedPatch.session_id == session_id)
            .order_by(ProposedPatch.created_at, ProposedPatch.id)
        )
    )


def list_session_interviews(db: Session, session_id: str) -> list[InterviewDocument]:
    return list(db.scalars(select(InterviewDocument).where(InterviewDocument.session_id == session_id).order_by(InterviewDocument.created_at, InterviewDocument.id)))


def list_interview_segments(db: Session, document_id: str) -> list[InterviewSegment]:
    return list(db.scalars(select(InterviewSegment).where(InterviewSegment.document_id == document_id).order_by(InterviewSegment.ordinal)))


def lock_interview_document(db: Session, document_id: str) -> InterviewDocument | None:
    return db.scalar(select(InterviewDocument).where(InterviewDocument.id == document_id).with_for_update())


def latest_interview_analysis(db: Session, document_id: str) -> InterviewAnalysis | None:
    return db.scalar(select(InterviewAnalysis).where(InterviewAnalysis.document_id == document_id).order_by(InterviewAnalysis.created_at.desc(), InterviewAnalysis.id.desc()).limit(1))


def find_interview_analysis(db: Session, document_id: str, segments_sha256: str) -> InterviewAnalysis | None:
    return db.scalar(select(InterviewAnalysis).where(InterviewAnalysis.document_id == document_id, InterviewAnalysis.segments_sha256 == segments_sha256))


def find_message(db: Session, message_id: str) -> AnalystMessage | None:
    return db.get(AnalystMessage, message_id)


def lock_proposal(db: Session, proposal_id: str) -> ProposedPatch | None:
    return db.scalar(
        select(ProposedPatch)
        .where(ProposedPatch.id == proposal_id)
        .with_for_update()
    )
