from sqlalchemy.orm import Session

from ..db_models import Membership, User, Workspace
from ..localization import normalize_locale
from ..config import get_settings
from .entitlements import create_default_commercial_state
from ..repositories.workspaces import find_membership


class WorkspaceAccessDenied(RuntimeError):
    pass


class WorkspaceArchived(WorkspaceAccessDenied):
    pass


def create_personal_workspace(db: Session, user: User) -> Workspace:
    workspace = create_workspace(
        db,
        user=user,
        name="Personal workspace",
        default_locale=user.preferred_locale,
    )
    user.active_workspace_id = workspace.id
    return workspace


def create_workspace(
    db: Session,
    *,
    user: User,
    name: str,
    default_locale: str,
) -> Workspace:
    workspace = Workspace(
        name=name,
        default_locale=normalize_locale(default_locale),
        created_by_user_id=user.id,
    )
    db.add(workspace)
    db.flush()
    db.add(Membership(workspace_id=workspace.id, user_id=user.id, role="owner"))
    db.flush()
    create_default_commercial_state(db, workspace, get_settings())
    return workspace


def require_membership(
    db: Session,
    workspace_id: str,
    user_id: str,
    *,
    allow_archived: bool = False,
) -> Membership:
    membership = find_membership(db, workspace_id, user_id)
    if membership is None:
        raise WorkspaceAccessDenied("User does not belong to this workspace.")
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise WorkspaceAccessDenied("Workspace does not exist.")
    if workspace.archived_at is not None and not allow_archived:
        raise WorkspaceArchived("Workspace is archived.")
    return membership
