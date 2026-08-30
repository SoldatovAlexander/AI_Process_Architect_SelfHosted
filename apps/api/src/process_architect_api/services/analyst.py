from typing import Any

from sqlalchemy.orm import Session

from ..db_models import (
    AnalystMessage,
    AnalystSession,
    ProposedPatch,
    User,
    utc_now,
)
from ..localization import normalize_locale
from ..repositories.analyst import (
    find_analyst_session,
    find_message,
    lock_proposal,
)
from .projects import (
    InvalidProcessPatch,
    RevisionConflict,
    apply_process_patch,
    preview_process_patch,
    require_project_access,
    require_project_revision,
)


class AnalystSessionNotFound(RuntimeError):
    pass


class AnalystSessionClosed(RuntimeError):
    pass


class AnalystMessageNotFound(RuntimeError):
    pass


class ProposedPatchNotFound(RuntimeError):
    pass


class ProposedPatchResolved(RuntimeError):
    pass


class ProposedPatchBaseMismatch(RuntimeError):
    pass


AS_IS_WELCOME = {
    "ru": "Начнём с назначения процесса. Какой результат этот workflow должен давать бизнесу? Кто отвечает за этот результат?",
    "en": "Let us start with the process purpose. What business outcome should this workflow produce? Who is accountable for that outcome?",
    "es": "Empecemos por el propósito del proceso. ¿Qué resultado de negocio debe producir este workflow? ¿Quién responde por ese resultado?",
}


def create_analyst_session(
    db: Session,
    *,
    user: User,
    project_id: str,
    mode: str,
    locale: str | None,
) -> AnalystSession:
    project = require_project_access(db, project_id, user.id)
    if project.current_revision_id is None:
        raise InvalidProcessPatch("Project has no current Process IR revision.")
    current_revision = require_project_revision(db, project, project.current_revision_id)
    if mode == "as_is_completion" and current_revision.perspective != "as_is":
        raise InvalidProcessPatch("AS-IS completion can only start from an AS-IS revision.")
    session = AnalystSession(
        project_id=project.id,
        started_from_revision_id=project.current_revision_id,
        mode=mode,
        locale=normalize_locale(locale or project.default_locale),
        status="active",
        created_by_user_id=user.id,
    )
    db.add(session)
    db.flush()
    if mode == "as_is_completion":
        language = session.locale.split("-", 1)[0]
        db.add(AnalystMessage(
            session_id=session.id,
            revision_id=project.current_revision_id,
            role="assistant",
            content=AS_IS_WELCOME.get(language, AS_IS_WELCOME["en"]),
            locale=session.locale,
            provider=None,
            model=None,
            prompt_version="as-is-completion-v1",
            created_by_user_id=None,
        ))
    db.commit()
    db.refresh(session)
    return session


def require_session_access(db: Session, session_id: str, user_id: str) -> AnalystSession:
    session = find_analyst_session(db, session_id)
    if session is None:
        raise AnalystSessionNotFound("Analyst session does not exist.")
    require_project_access(db, session.project_id, user_id)
    return session


def add_user_message(
    db: Session,
    *,
    user: User,
    session_id: str,
    content: str,
) -> AnalystMessage:
    session = require_session_access(db, session_id, user.id)
    if session.status != "active":
        raise AnalystSessionClosed("Analyst session is closed.")
    project = require_project_access(db, session.project_id, user.id)
    if project.current_revision_id is None:
        raise InvalidProcessPatch("Project has no current Process IR revision.")
    message = AnalystMessage(
        session_id=session.id,
        revision_id=project.current_revision_id,
        role="user",
        content=content.strip(),
        locale=session.locale,
        provider=None,
        model=None,
        prompt_version=None,
        created_by_user_id=user.id,
    )
    session.updated_at = utc_now()
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def add_assistant_message(
    db: Session,
    *,
    user: User,
    session_id: str,
    revision_id: str,
    content: str,
    provider: str,
    model: str,
    prompt_version: str,
    commit: bool = True,
) -> AnalystMessage:
    session = require_session_access(db, session_id, user.id)
    if session.status != "active":
        raise AnalystSessionClosed("Analyst session is closed.")
    project = require_project_access(db, session.project_id, user.id)
    require_project_revision(db, project, revision_id)
    message = AnalystMessage(
        session_id=session.id,
        revision_id=revision_id,
        role="assistant",
        content=content.strip(),
        locale=session.locale,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        created_by_user_id=None,
    )
    session.updated_at = utc_now()
    db.add(message)
    db.flush()
    if commit:
        db.commit()
        db.refresh(message)
    return message


def create_proposed_patch(
    db: Session,
    *,
    user: User,
    session_id: str,
    base_revision_id: str,
    patch: list[dict[str, Any]],
    summary: str,
    source_message_id: str | None = None,
    allow_stale: bool = False,
    commit: bool = True,
) -> ProposedPatch:
    session = require_session_access(db, session_id, user.id)
    if session.status != "active":
        raise AnalystSessionClosed("Analyst session is closed.")
    project = require_project_access(db, session.project_id, user.id)
    if not allow_stale and project.current_revision_id != base_revision_id:
        raise RevisionConflict(project.current_revision_id or "")
    base_revision = require_project_revision(db, project, base_revision_id)
    source_message = None
    if source_message_id is not None:
        source_message = find_message(db, source_message_id)
        if source_message is None or source_message.session_id != session.id:
            raise AnalystMessageNotFound("Source message does not belong to this session.")
    _, normalized_patch, validation = preview_process_patch(base_revision.process_ir, patch)
    proposal = ProposedPatch(
        session_id=session.id,
        project_id=project.id,
        base_revision_id=base_revision.id,
        source_message_id=source_message.id if source_message else None,
        patch=normalized_patch,
        summary=summary.strip(),
        validation_result=validation,
        status="pending",
        accepted_revision_id=None,
        created_by_user_id=user.id,
        resolved_by_user_id=None,
        resolved_at=None,
    )
    session.updated_at = utc_now()
    db.add(proposal)
    db.flush()
    if commit:
        db.commit()
        db.refresh(proposal)
    return proposal


def accept_proposed_patch(
    db: Session,
    *,
    user: User,
    proposal_id: str,
    base_revision_id: str,
) -> tuple[ProposedPatch, str]:
    proposal = lock_proposal(db, proposal_id)
    if proposal is None:
        raise ProposedPatchNotFound("Proposed patch does not exist.")
    session = require_session_access(db, proposal.session_id, user.id)
    if proposal.status != "pending":
        raise ProposedPatchResolved("Proposed patch is already resolved.")
    if proposal.base_revision_id != base_revision_id:
        raise ProposedPatchBaseMismatch("Acceptance base does not match the proposal base.")
    _, revision = apply_process_patch(
        db,
        user=user,
        project_id=proposal.project_id,
        base_revision_id=base_revision_id,
        patch=proposal.patch,
        source="analyst",
        perspective="to_be" if session.mode == "as_is_completion" else None,
        commit=False,
    )
    now = utc_now()
    proposal.status = "accepted"
    proposal.accepted_revision_id = revision.id
    proposal.resolved_by_user_id = user.id
    proposal.resolved_at = now
    session.updated_at = now
    db.commit()
    db.refresh(proposal)
    return proposal, revision.id


def reject_proposed_patch(
    db: Session,
    *,
    user: User,
    proposal_id: str,
) -> ProposedPatch:
    proposal = lock_proposal(db, proposal_id)
    if proposal is None:
        raise ProposedPatchNotFound("Proposed patch does not exist.")
    session = require_session_access(db, proposal.session_id, user.id)
    if proposal.status != "pending":
        raise ProposedPatchResolved("Proposed patch is already resolved.")
    now = utc_now()
    proposal.status = "rejected"
    proposal.resolved_by_user_id = user.id
    proposal.resolved_at = now
    session.updated_at = now
    db.commit()
    db.refresh(proposal)
    return proposal


def close_analyst_session(
    db: Session,
    *,
    user: User,
    session_id: str,
) -> AnalystSession:
    session = require_session_access(db, session_id, user.id)
    if session.status == "closed":
        return session
    session.status = "closed"
    session.updated_at = utc_now()
    db.commit()
    db.refresh(session)
    return session
