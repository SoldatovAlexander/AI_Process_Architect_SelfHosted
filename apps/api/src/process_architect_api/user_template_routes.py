from copy import deepcopy
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .auth import CurrentUser
from .database import get_db
from .entitlement_dependencies import PrivateTemplateEntitlement
from .db_models import TemplateCollection, TemplateCollectionItem, UserProcessTemplate
from .localization import normalize_locale
from .models import (
    ProcessTemplateResponse,
    TemplateCollectionCreateRequest,
    TemplateCollectionItemRequest,
    TemplateCollectionItemResponse,
    TemplateCollectionResponse,
    UserTemplateCreateRequest,
)
from .process_templates import find_process_template
from .services.projects import ProjectNotFound, RevisionNotFound, require_project_access, require_project_revision
from .services.workspaces import WorkspaceAccessDenied


router = APIRouter(prefix="/api/v1", tags=["user-templates"])
DbSession = Annotated[Session, Depends(get_db)]


def _favorites(db: Session, user_id: str) -> TemplateCollection:
    collection = db.scalar(select(TemplateCollection).where(
        TemplateCollection.user_id == user_id,
        TemplateCollection.is_favorites.is_(True),
    ))
    if collection is None:
        collection = TemplateCollection(user_id=user_id, name="Favorites", is_favorites=True)
        db.add(collection)
        db.commit()
        db.refresh(collection)
    return collection


def _require_collection(db: Session, collection_id: str, user_id: str) -> TemplateCollection:
    collection = db.get(TemplateCollection, collection_id)
    if collection is None or collection.user_id != user_id:
        raise HTTPException(status_code=404, detail={"code": "collection_not_found", "message": "Template collection does not exist."})
    return collection


def _require_user_template(db: Session, template_id: str, user_id: str) -> UserProcessTemplate:
    template = db.get(UserProcessTemplate, template_id)
    if template is None or template.user_id != user_id:
        raise HTTPException(status_code=404, detail={"code": "user_template_not_found", "message": "User template does not exist."})
    return template


def _collection_response(db: Session, collection: TemplateCollection) -> TemplateCollectionResponse:
    count = db.scalar(select(func.count()).select_from(TemplateCollectionItem).where(TemplateCollectionItem.collection_id == collection.id)) or 0
    return TemplateCollectionResponse(id=collection.id, name=collection.name, is_favorites=collection.is_favorites, item_count=count, created_at=collection.created_at)


def _serialize_user_template(db: Session, template: UserProcessTemplate, locale: str) -> ProcessTemplateResponse:
    collection_ids = list(db.scalars(select(TemplateCollectionItem.collection_id).where(
        TemplateCollectionItem.template_source == "user",
        TemplateCollectionItem.template_id == template.id,
    )))
    favorites_id = _favorites(db, template.user_id).id
    process_ir = deepcopy(template.process_ir)
    steps = process_ir.get("steps", [])
    return ProcessTemplateResponse(
        id=template.id,
        category="personal",
        category_name={"ru": "Личные шаблоны", "en": "Personal templates", "es": "Plantillas personales"}[normalize_locale(locale)],
        name=template.name,
        description=template.description,
        step_count=len(steps),
        actor_count=len(process_ir.get("actors", [])),
        system_count=len(process_ir.get("systems", [])),
        preview_steps=[step.get("title", "") for step in steps if step.get("type") not in {"start", "end"}],
        process_ir=process_ir,
        status="ready",
        agent_enabled=template.target_mode == "agent",
        search_terms=[],
        rubric_entry_ids=template.rubric_entry_ids,
        source="user",
        collection_ids=collection_ids,
        favorite=favorites_id in collection_ids,
    )


@router.get("/template-collections", response_model=list[TemplateCollectionResponse])
def list_collections(current_user: CurrentUser, db: DbSession) -> list[TemplateCollectionResponse]:
    _favorites(db, current_user.id)
    collections = list(db.scalars(select(TemplateCollection).where(TemplateCollection.user_id == current_user.id).order_by(TemplateCollection.is_favorites.desc(), TemplateCollection.name)))
    return [_collection_response(db, item) for item in collections]


@router.post("/template-collections", response_model=TemplateCollectionResponse, status_code=status.HTTP_201_CREATED)
def create_collection(
    request: TemplateCollectionCreateRequest,
    current_user: CurrentUser,
    db: DbSession,
    _entitlement: PrivateTemplateEntitlement,
) -> TemplateCollectionResponse:
    _favorites(db, current_user.id)
    existing_names = db.scalars(select(TemplateCollection.name).where(TemplateCollection.user_id == current_user.id))
    duplicate = any(name.casefold() == request.name.casefold() for name in existing_names)
    if duplicate:
        raise HTTPException(status_code=409, detail={"code": "collection_exists", "message": "A collection with this name already exists."})
    collection = TemplateCollection(user_id=current_user.id, name=request.name, is_favorites=False)
    db.add(collection); db.commit(); db.refresh(collection)
    return _collection_response(db, collection)


@router.get("/template-collection-items", response_model=list[TemplateCollectionItemResponse])
def list_collection_items(current_user: CurrentUser, db: DbSession) -> list[TemplateCollectionItemResponse]:
    rows = db.execute(
        select(TemplateCollectionItem)
        .join(TemplateCollection, TemplateCollection.id == TemplateCollectionItem.collection_id)
        .where(TemplateCollection.user_id == current_user.id)
    ).scalars()
    return [TemplateCollectionItemResponse(
        collection_id=item.collection_id,
        template_source=item.template_source,
        template_id=item.template_id,
    ) for item in rows]


@router.delete("/template-collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(collection_id: str, current_user: CurrentUser, db: DbSession) -> Response:
    collection = _require_collection(db, collection_id, current_user.id)
    if collection.is_favorites:
        raise HTTPException(status_code=409, detail={"code": "favorites_required", "message": "Favorites cannot be deleted."})
    db.delete(collection); db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/template-collections/{collection_id}/items", status_code=status.HTTP_204_NO_CONTENT)
def add_collection_item(collection_id: str, request: TemplateCollectionItemRequest, current_user: CurrentUser, db: DbSession) -> Response:
    _require_collection(db, collection_id, current_user.id)
    if request.template_source == "catalog":
        if find_process_template(request.template_id) is None:
            raise HTTPException(status_code=404, detail={"code": "template_not_found", "message": "Catalog template does not exist."})
    else:
        _require_user_template(db, request.template_id, current_user.id)
    existing = db.scalar(select(TemplateCollectionItem).where(
        TemplateCollectionItem.collection_id == collection_id,
        TemplateCollectionItem.template_source == request.template_source,
        TemplateCollectionItem.template_id == request.template_id,
    ))
    if existing is None:
        db.add(TemplateCollectionItem(collection_id=collection_id, template_source=request.template_source, template_id=request.template_id))
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/template-collections/{collection_id}/items/{template_source}/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_collection_item(collection_id: str, template_source: str, template_id: str, current_user: CurrentUser, db: DbSession) -> Response:
    _require_collection(db, collection_id, current_user.id)
    db.execute(delete(TemplateCollectionItem).where(
        TemplateCollectionItem.collection_id == collection_id,
        TemplateCollectionItem.template_source == template_source,
        TemplateCollectionItem.template_id == template_id,
    )); db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/user-templates", response_model=list[ProcessTemplateResponse])
def list_user_templates(
    current_user: CurrentUser,
    db: DbSession,
    locale: Annotated[str, Query(min_length=2, max_length=35)] = "ru",
) -> list[ProcessTemplateResponse]:
    templates = list(db.scalars(select(UserProcessTemplate).where(UserProcessTemplate.user_id == current_user.id).order_by(UserProcessTemplate.updated_at.desc())))
    return [_serialize_user_template(db, item, locale) for item in templates]


@router.post("/projects/{project_id}/user-templates", response_model=ProcessTemplateResponse, status_code=status.HTTP_201_CREATED)
def save_project_as_template(
    project_id: str,
    request: UserTemplateCreateRequest,
    current_user: CurrentUser,
    db: DbSession,
    _entitlement: PrivateTemplateEntitlement,
) -> ProcessTemplateResponse:
    try:
        project = require_project_access(db, project_id, current_user.id)
        if project.current_revision_id is None:
            raise RevisionNotFound("Project has no current revision.")
        revision = require_project_revision(db, project, project.current_revision_id)
    except (ProjectNotFound, RevisionNotFound, WorkspaceAccessDenied) as error:
        raise HTTPException(status_code=404, detail={"code": "project_not_found", "message": str(error)}) from error
    collections = [_require_collection(db, identifier, current_user.id) for identifier in set(request.collection_ids)]
    if request.favorite:
        collections.append(_favorites(db, current_user.id))
    process_ir = deepcopy(revision.process_ir)
    template = UserProcessTemplate(
        user_id=current_user.id,
        name=request.name,
        description=request.description or process_ir.get("process", {}).get("description", ""),
        locale=normalize_locale(project.default_locale),
        target_mode=project.target_mode,
        process_ir=process_ir,
        rubric_entry_ids=process_ir.get("classification", {}).get("entryIds", []),
        source_project_id=project.id,
        source_revision_id=revision.id,
    )
    db.add(template); db.flush()
    for collection in {item.id: item for item in collections}.values():
        db.add(TemplateCollectionItem(collection_id=collection.id, template_source="user", template_id=template.id))
    db.commit(); db.refresh(template)
    return _serialize_user_template(db, template, project.default_locale)


@router.delete("/user-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_template(template_id: str, current_user: CurrentUser, db: DbSession) -> Response:
    template = _require_user_template(db, template_id, current_user.id)
    db.execute(delete(TemplateCollectionItem).where(TemplateCollectionItem.template_source == "user", TemplateCollectionItem.template_id == template.id))
    db.delete(template); db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
