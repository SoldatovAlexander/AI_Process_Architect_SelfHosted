from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import (
    CurrentUser,
    authenticate_user,
    find_user_by_email,
    hash_password,
    issue_token_pair,
    normalize_email,
    revoke_refresh_token,
    rotate_refresh_token,
)
from .config import Settings, get_settings
from .database import get_db
from .db_models import Membership, User
from .localization import normalize_locale
from .models import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
    WorkspaceMembershipResponse,
)
from .repositories.workspaces import list_user_workspaces
from .services.workspaces import create_personal_workspace


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def user_response(user: User, db: Session) -> UserResponse:
    workspaces = list_user_workspaces(db, user.id)
    memberships = {
        membership.workspace_id: membership
        for membership in db.scalars(
            select(Membership).where(Membership.user_id == user.id)
        )
    }
    return UserResponse(
        id=user.id,
        email=user.email,
        preferred_locale=user.preferred_locale,
        is_active=user.is_active,
        active_workspace_id=(
            user.active_workspace_id
            if any(item.id == user.active_workspace_id and item.archived_at is None for item in workspaces)
            else next((item.id for item in workspaces if item.archived_at is None), None)
        ),
        workspaces=[
            WorkspaceMembershipResponse(
                workspace_id=workspace.id,
                workspace_name=workspace.name,
                role=memberships[workspace.id].role,
                default_locale=workspace.default_locale,
                status="archived" if workspace.archived_at is not None else "active",
                archived_at=workspace.archived_at,
            )
            for workspace in workspaces
        ],
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, db: DbSession, settings: AppSettings) -> TokenResponse:
    if find_user_by_email(db, request.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "email_exists", "message": "An account with this email already exists."},
        )
    user = User(
        email=normalize_email(request.email),
        password_hash=hash_password(request.password),
        preferred_locale=normalize_locale(request.preferred_locale),
        service_role=(
            "service_admin"
            if normalize_email(request.email) in settings.service_admin_email_set
            else "user"
        ),
    )
    db.add(user)
    try:
        db.flush()
        create_personal_workspace(db, user)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists.") from error
    db.refresh(user)
    return issue_token_pair(db, user, settings)


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: DbSession, settings: AppSettings) -> TokenResponse:
    user = authenticate_user(db, request.email, request.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials", "message": "Incorrect email or password."},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return issue_token_pair(db, user, settings)


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: RefreshRequest, db: DbSession, settings: AppSettings) -> TokenResponse:
    tokens = rotate_refresh_token(db, request.refresh_token, settings)
    if tokens is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_refresh_token", "message": "Refresh token is invalid or expired."},
        )
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: LogoutRequest, db: DbSession) -> Response:
    revoke_refresh_token(db, request.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
def me(current_user: CurrentUser, db: DbSession) -> UserResponse:
    return user_response(current_user, db)
