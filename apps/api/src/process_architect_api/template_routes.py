from typing import Annotated

import jsonpatch
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .auth import CurrentUser
from .database import get_db
from .localization import normalize_locale
from .models import (
    ProcessTemplateApplyRequest,
    ProcessTemplateResponse,
    ProcessTemplateSuggestionRequest,
    ProcessTemplateSuggestionResponse,
    ProjectResponse,
)
from .process_templates import (
    build_process_template,
    find_process_template,
    get_process_template,
    list_process_templates,
    suggest_process_template,
)
from .project_routes import _translate_error, project_response
from .rubric import CURRENT_RUBRIC_VERSION, validate_entry_ids
from .services.projects import (
    InvalidProcessPatch,
    ProjectNotFound,
    RevisionConflict,
    apply_process_patch,
    require_project_access,
    require_project_revision,
)
from .services.workspaces import WorkspaceAccessDenied


router = APIRouter(prefix="/api/v1", tags=["templates"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/process-templates", response_model=list[ProcessTemplateResponse])
def list_templates(
    current_user: CurrentUser,
    db: DbSession,
    locale: Annotated[str, Query(min_length=2, max_length=35)] = "ru",
    rubric_entry_ids: Annotated[list[str] | None, Query(alias="rubricEntryId")] = None,
) -> list[ProcessTemplateResponse]:
    selected = rubric_entry_ids or []
    try:
        validate_entry_ids(db, CURRENT_RUBRIC_VERSION, selected)
    except ValueError as error:
        raise HTTPException(status_code=422, detail={"code": "invalid_rubric_filter", "message": str(error)}) from error
    return [
        ProcessTemplateResponse.model_validate(item)
        for item in list_process_templates(normalize_locale(locale), set(selected))
    ]


@router.get("/process-templates/{template_id}", response_model=ProcessTemplateResponse)
def get_template(
    template_id: str,
    current_user: CurrentUser,
    locale: Annotated[str, Query(min_length=2, max_length=35)] = "ru",
) -> ProcessTemplateResponse:
    template = get_process_template(template_id, normalize_locale(locale))
    if template is None:
        raise HTTPException(status_code=404, detail={"code": "template_not_found", "message": "Process template does not exist."})
    return ProcessTemplateResponse.model_validate(template)


@router.post("/process-templates/suggest", response_model=ProcessTemplateSuggestionResponse | None)
def suggest_template(
    request: ProcessTemplateSuggestionRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> ProcessTemplateSuggestionResponse | None:
    try:
        validate_entry_ids(db, CURRENT_RUBRIC_VERSION, request.rubric_entry_ids)
    except ValueError as error:
        raise HTTPException(status_code=422, detail={"code": "invalid_rubric_filter", "message": str(error)}) from error
    result = suggest_process_template(
        request.text,
        request.locale,
        set(request.excluded_ids),
        set(request.rubric_entry_ids),
    )
    return ProcessTemplateSuggestionResponse.model_validate(result) if result else None


@router.post(
    "/projects/{project_id}/templates/{template_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def apply_template(
    project_id: str,
    template_id: str,
    request: ProcessTemplateApplyRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> ProjectResponse:
    spec = find_process_template(template_id)
    if spec is None:
        raise HTTPException(status_code=404, detail={"code": "template_not_found", "message": "Process template does not exist."})
    try:
        project = require_project_access(db, project_id, current_user.id)
        if project.current_revision_id is None:
            raise ProjectNotFound("Project has no current revision.")
        if project.current_revision_id != request.base_revision_id:
            raise RevisionConflict(project.current_revision_id)
        current_ir = require_project_revision(db, project, project.current_revision_id).process_ir
        next_ir = build_process_template(spec, request.locale)
        next_ir["process"]["id"] = current_ir["process"]["id"]
        for question in next_ir.get("openQuestions", []):
            target = question.get("target", {})
            if target.get("entity") == "process":
                target["id"] = current_ir["process"]["id"]
        patch = jsonpatch.make_patch(current_ir, next_ir).patch
        if not patch:
            return project_response(db, project)
        project, _ = apply_process_patch(
            db,
            user=current_user,
            project_id=project_id,
            base_revision_id=request.base_revision_id,
            patch=patch,
            source="template",
        )
    except (ProjectNotFound, RevisionConflict, InvalidProcessPatch, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    return project_response(db, project)
