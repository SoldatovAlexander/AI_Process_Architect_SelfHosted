from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .database import get_db
from .db_models import RefreshSession, User
from .models import TokenResponse


password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("not-a-real-user-password")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    return password_hash.verify(password, encoded_hash)


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = find_user_by_email(db, email)
    if user is None:
        verify_password(password, DUMMY_HASH)
        return None
    if not verify_password(password, user.password_hash) or not user.is_active:
        return None
    return user


def _refresh_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _create_access_token(user: User, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "email": user.email,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(
        payload,
        settings.auth_secret_key.get_secret_value(),
        algorithm="HS256",
    )


def issue_token_pair(db: Session, user: User, settings: Settings) -> TokenResponse:
    refresh_token = token_urlsafe(48)
    db.add(
        RefreshSession(
            user_id=user.id,
            token_hash=_refresh_hash(refresh_token),
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    db.commit()
    return TokenResponse(
        access_token=_create_access_token(user, settings),
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


def rotate_refresh_token(db: Session, token: str, settings: Settings) -> TokenResponse | None:
    session = db.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == _refresh_hash(token))
    )
    now = datetime.now(timezone.utc)
    if session is None or session.revoked_at is not None:
        return None
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now or not session.user.is_active:
        return None

    session.revoked_at = now
    db.commit()
    return issue_token_pair(db, session.user, settings)


def revoke_refresh_token(db: Session, token: str) -> bool:
    session = db.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == _refresh_hash(token))
    )
    if session is None or session.revoked_at is not None:
        return False
    session.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return True


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "invalid_access_token", "message": "Could not validate credentials."},
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.auth_secret_key.get_secret_value(),
            algorithms=["HS256"],
        )
        if payload.get("type") != "access" or not isinstance(payload.get("sub"), str):
            raise credentials_error
    except InvalidTokenError as error:
        raise credentials_error from error

    user = db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise credentials_error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
