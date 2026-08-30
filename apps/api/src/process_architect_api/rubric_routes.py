from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .auth import CurrentUser
from .database import get_db
from .models import ProjectClassificationRequest, ProjectResponse, RubricResponse
from .project_routes import _translate_error, project_response
from .rubric import CURRENT_RUBRIC_VERSION, get_rubric, validate_entry_ids
from .services.projects import InvalidProcessPatch, ProjectNotFound, RevisionConflict, apply_process_patch
from .services.workspaces import WorkspaceAccessDenied


router = APIRouter(prefix="/api/v1", tags=["rubric"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/rubric", response_model=RubricResponse)
def read_rubric(
    current_user: CurrentUser,
    db: DbSession,
    locale: Annotated[str, Query(min_length=2, max_length=35)] = "ru",
    version: Annotated[str, Query(min_length=1, max_length=64)] = CURRENT_RUBRIC_VERSION,
) -> RubricResponse:
    rubric = get_rubric(db, locale, version)
    if rubric is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "rubric_not_found", "message": "Rubric version does not exist."},
        )
    return RubricResponse.model_validate(rubric)


@router.post(
    "/projects/{project_id}/classification",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def confirm_classification(
    project_id: str,
    request: ProjectClassificationRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> ProjectResponse:
    try:
        if get_rubric(db, "en", request.rubric_version) is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "rubric_not_found", "message": "Rubric version does not exist."},
            )
        validate_entry_ids(db, request.rubric_version, request.entry_ids)
        classification = {
            "rubricVersion": request.rubric_version,
            "status": "confirmed",
            "entryIds": request.entry_ids,
            "classifiedAt": datetime.now(timezone.utc).isoformat(),
            "classifiedByUserId": current_user.id,
        }
        project, _ = apply_process_patch(
            db,
            user=current_user,
            project_id=project_id,
            base_revision_id=request.base_revision_id,
            patch=[{"op": "add", "path": "/classification", "value": classification}],
            source="user",
        )
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_rubric_selection", "message": str(error)},
        ) from error
    except (ProjectNotFound, RevisionConflict, InvalidProcessPatch, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    return project_response(db, project)
