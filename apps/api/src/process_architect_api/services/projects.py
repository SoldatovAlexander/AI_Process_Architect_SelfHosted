from copy import deepcopy
from typing import Any

import jsonpatch
import jsonpointer
from sqlalchemy.orm import Session

from ..db_models import ProcessRevision, Project, User
from ..localization import normalize_locale
from ..process_ir import upgrade_process_ir
from ..repositories.projects import find_project, find_revision, lock_project
from ..services.workspaces import require_membership
from ..validation import validate_process_ir


class InvalidInitialProcess(RuntimeError):
    pass


class ProjectNotFound(RuntimeError):
    pass


class RevisionNotFound(RuntimeError):
    pass


class RevisionConflict(RuntimeError):
    def __init__(self, current_revision_id: str):
        self.current_revision_id = current_revision_id
        super().__init__("The project has changed since the supplied base revision.")


class InvalidProcessPatch(RuntimeError):
    pass


class RevisionNotUndoable(RuntimeError):
    pass


def create_project_with_initial_revision(
    db: Session,
    *,
    user: User,
    workspace_id: str,
    name: str,
    process_ir: dict,
    default_locale: str | None = None,
    target_mode: str = "process",
    source: str = "initial",
    perspective: str = "to_be",
    commit: bool = True,
) -> tuple[Project, ProcessRevision]:
    require_membership(db, workspace_id, user.id)
    process_ir = upgrade_process_ir(process_ir)
    validation = validate_process_ir(process_ir)
    if not validation.valid:
        raise InvalidInitialProcess("Initial Process IR must pass validation.")

    project = Project(
        workspace_id=workspace_id,
        name=name.strip(),
        description=process_ir["process"].get("description", ""),
        default_locale=normalize_locale(default_locale or user.preferred_locale),
        status="draft",
        target_mode=target_mode,
        created_by_user_id=user.id,
    )
    db.add(project)
    db.flush()

    revision = ProcessRevision(
        project_id=project.id,
        version_number=1,
        schema_version=process_ir["schemaVersion"],
        process_ir=deepcopy(process_ir),
        forward_patch=None,
        inverse_patch=None,
        validation_result=validation.model_dump(mode="json"),
        parent_revision_id=None,
        restored_from_revision_id=None,
        source=source,
        perspective=perspective,
        created_by_user_id=user.id,
    )
    db.add(revision)
    db.flush()
    project.current_revision_id = revision.id
    if commit:
        db.commit()
        db.refresh(project)
        db.refresh(revision)
    return project, revision


def require_project_access(
    db: Session,
    project_id: str,
    user_id: str,
    *,
    for_update: bool = False,
) -> Project:
    project = lock_project(db, project_id) if for_update else find_project(db, project_id)
    if project is None:
        raise ProjectNotFound("Project does not exist.")
    require_membership(db, project.workspace_id, user_id)
    return project


def require_project_revision(
    db: Session,
    project: Project,
    revision_id: str,
) -> ProcessRevision:
    revision = find_revision(db, revision_id)
    if revision is None or revision.project_id != project.id:
        raise RevisionNotFound("Revision does not belong to this project.")
    return revision


def _current_revision(db: Session, project: Project) -> ProcessRevision:
    if project.current_revision_id is None:
        raise RevisionNotFound("Project has no current revision.")
    return require_project_revision(db, project, project.current_revision_id)


def _check_base_revision(project: Project, base_revision_id: str) -> None:
    if project.current_revision_id != base_revision_id:
        raise RevisionConflict(project.current_revision_id or "")


def _validated_document(process_ir: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    process_ir = upgrade_process_ir(process_ir)
    validation = validate_process_ir(process_ir)
    if not validation.valid:
        details = "; ".join(
            f"{issue.path}: {issue.message}"
            for issue in validation.issues[:8]
            if issue.severity == "error"
        )
        raise InvalidProcessPatch(
            f"The resulting Process IR does not pass validation: {details}"
        )
    return process_ir, validation.model_dump(mode="json")


def preview_process_patch(
    process_ir: dict[str, Any],
    patch: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    normalized_source = upgrade_process_ir(process_ir)
    try:
        next_process_ir = jsonpatch.JsonPatch(patch).apply(
            deepcopy(normalized_source),
            in_place=False,
        )
    except (
        jsonpatch.JsonPatchException,
        jsonpointer.JsonPointerException,
        TypeError,
        KeyError,
        IndexError,
    ) as error:
        raise InvalidProcessPatch(f"Invalid JSON Patch: {error}") from error
    if not isinstance(next_process_ir, dict):
        raise InvalidProcessPatch("Process IR root must remain an object.")
    next_process_ir, validation = _validated_document(next_process_ir)
    normalized_patch = jsonpatch.make_patch(normalized_source, next_process_ir).patch
    if not normalized_patch:
        raise InvalidProcessPatch("The change does not modify Process IR.")
    return next_process_ir, normalized_patch, validation


def _append_revision(
    db: Session,
    *,
    project: Project,
    current: ProcessRevision,
    next_process_ir: dict[str, Any],
    user: User,
    source: str,
    perspective: str | None = None,
    restored_from_revision_id: str | None = None,
    commit: bool = True,
) -> ProcessRevision:
    next_process_ir, validation = _validated_document(next_process_ir)
    forward_patch = jsonpatch.make_patch(current.process_ir, next_process_ir).patch
    if not forward_patch:
        raise InvalidProcessPatch("The change does not modify Process IR.")
    inverse_patch = jsonpatch.make_patch(next_process_ir, current.process_ir).patch
    revision = ProcessRevision(
        project_id=project.id,
        version_number=current.version_number + 1,
        schema_version=next_process_ir["schemaVersion"],
        process_ir=deepcopy(next_process_ir),
        forward_patch=forward_patch,
        inverse_patch=inverse_patch,
        validation_result=validation,
        parent_revision_id=current.id,
        restored_from_revision_id=restored_from_revision_id,
        source=source,
        perspective=perspective or ("to_be" if current.perspective == "as_is" else current.perspective),
        created_by_user_id=user.id,
    )
    db.add(revision)
    db.flush()
    project.current_revision_id = revision.id
    project.description = next_process_ir["process"].get("description", "")
    if commit:
        db.commit()
        db.refresh(project)
        db.refresh(revision)
    return revision


def apply_process_patch(
    db: Session,
    *,
    user: User,
    project_id: str,
    base_revision_id: str,
    patch: list[dict[str, Any]],
    source: str = "user",
    perspective: str | None = None,
    commit: bool = True,
) -> tuple[Project, ProcessRevision]:
    project = require_project_access(db, project_id, user.id, for_update=True)
    _check_base_revision(project, base_revision_id)
    current = _current_revision(db, project)
    next_process_ir, _, _ = preview_process_patch(current.process_ir, patch)
    revision = _append_revision(
        db,
        project=project,
        current=current,
        next_process_ir=next_process_ir,
        user=user,
        source=source,
        perspective=perspective,
        commit=commit,
    )
    return project, revision


def undo_last_revision(
    db: Session,
    *,
    user: User,
    project_id: str,
    base_revision_id: str,
) -> tuple[Project, ProcessRevision]:
    project = require_project_access(db, project_id, user.id, for_update=True)
    _check_base_revision(project, base_revision_id)
    current = _current_revision(db, project)
    if not current.inverse_patch:
        raise RevisionNotUndoable("The current revision has no safe inverse patch.")
    try:
        restored_ir = jsonpatch.JsonPatch(current.inverse_patch).apply(
            deepcopy(current.process_ir),
            in_place=False,
        )
    except jsonpatch.JsonPatchException as error:
        raise RevisionNotUndoable("The stored inverse patch cannot be applied.") from error
    revision = _append_revision(
        db,
        project=project,
        current=current,
        next_process_ir=restored_ir,
        user=user,
        source="undo",
    )
    return project, revision


def restore_revision(
    db: Session,
    *,
    user: User,
    project_id: str,
    base_revision_id: str,
    target_revision_id: str,
) -> tuple[Project, ProcessRevision]:
    project = require_project_access(db, project_id, user.id, for_update=True)
    _check_base_revision(project, base_revision_id)
    current = _current_revision(db, project)
    target = require_project_revision(db, project, target_revision_id)
    revision = _append_revision(
        db,
        project=project,
        current=current,
        next_process_ir=deepcopy(target.process_ir),
        user=user,
        source="restore",
        restored_from_revision_id=target.id,
    )
    return project, revision


def archive_project(db: Session, *, user: User, project_id: str) -> Project:
    project = require_project_access(db, project_id, user.id, for_update=True)
    project.status = "archived"
    db.commit()
    db.refresh(project)
    return project
