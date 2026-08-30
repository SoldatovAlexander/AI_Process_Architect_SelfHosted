from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "service_role IN ('user', 'service_admin', 'support', 'billing_admin', 'viewer')",
            name="ck_user_service_role",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    preferred_locale: Mapped[str] = mapped_column(String(35), default="ru")
    llm_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    active_workspace_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True
    )
    service_role: Mapped[str] = mapped_column(String(32), default="user", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    refresh_sessions: Mapped[list["RefreshSession"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    llm_credentials: Mapped[list["UserLLMCredential"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserLLMCredential(Base):
    __tablename__ = "user_llm_credentials"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_user_llm_credential_provider"),
        CheckConstraint(
            "provider IN ('deepseek', 'openai', 'openai_compatible')",
            name="ck_user_llm_credential_provider",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32), index=True)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_url: Mapped[str] = mapped_column(String(2_000))
    model: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    user: Mapped[User] = relationship(back_populates="llm_credentials")


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped[User] = relationship(back_populates="refresh_sessions")


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(160))
    default_locale: Mapped[str] = mapped_column(String(35), default="ru")
    created_by_user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    archived_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    commercial_state: Mapped["WorkspaceCommercialState | None"] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_membership_workspace_user"),
        CheckConstraint("role IN ('owner', 'member')", name="ck_membership_role"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    workspace: Mapped[Workspace] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class WorkspaceInvitation(Base):
    __tablename__ = "workspace_invitations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name="ck_workspace_invitation_status",
        ),
        CheckConstraint("role IN ('member')", name="ck_workspace_invitation_role"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), index=True)
    role: Mapped[str] = mapped_column(String(32), default="member")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    invited_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    accepted_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WorkspaceCommercialState(Base):
    __tablename__ = "workspace_commercial_states"
    __table_args__ = (
        CheckConstraint(
            "status IN ('trial', 'active', 'grace', 'read_only', 'expired', 'revoked')",
            name="ck_workspace_commercial_state_status",
        ),
        CheckConstraint(
            "source IN ('deployment', 'subscription', 'license', 'manual')",
            name="ck_workspace_commercial_state_source",
        ),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    plan_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    source: Mapped[str] = mapped_column(String(32), default="deployment", index=True)
    catalog_version: Mapped[str] = mapped_column(String(32))
    entitlement_overrides: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), default=dict
    )
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    grace_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    workspace: Mapped[Workspace] = relationship(back_populates="commercial_state")


class InstallationState(Base):
    __tablename__ = "installation_states"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="installation")
    deployment_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WorkspaceLicense(Base):
    __tablename__ = "workspace_licenses"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'superseded', 'revoked')",
            name="ck_workspace_license_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    license_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    key_id: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    signature: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    activation_source: Mapped[str] = mapped_column(String(16))
    activated_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AdminAuditEvent(Base):
    __tablename__ = "admin_audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    actor_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(96), index=True)
    target_type: Mapped[str] = mapped_column(String(48), index=True)
    target_id: Mapped[str] = mapped_column(String(128), index=True)
    reason: Mapped[str] = mapped_column(String(240))
    details: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class BillingSubscription(Base):
    __tablename__ = "billing_subscriptions"
    __table_args__ = (
        UniqueConstraint("provider", "external_subscription_id", name="uq_billing_subscription_provider_external"),
        CheckConstraint(
            "status IN ('trialing', 'active', 'past_due', 'paused', 'canceled', 'expired')",
            name="ck_billing_subscription_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32), index=True)
    external_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    external_subscription_id: Mapped[str] = mapped_column(String(255))
    plan_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class BillingEvent(Base):
    __tablename__ = "billing_events"
    __table_args__ = (
        UniqueConstraint("provider", "external_event_id", name="uq_billing_event_provider_external"),
        CheckConstraint(
            "status IN ('processed', 'ignored', 'failed')",
            name="ck_billing_event_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    provider: Mapped[str] = mapped_column(String(32), index=True)
    external_event_id: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(96), index=True)
    workspace_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True
    )
    subscription_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("billing_subscriptions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    invoice_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("billing_invoices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    payload_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), index=True)
    reason_code: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class BillingInvoice(Base):
    __tablename__ = "billing_invoices"
    __table_args__ = (
        UniqueConstraint("provider", "external_invoice_id", name="uq_billing_invoice_provider_external"),
        CheckConstraint(
            "provider_status IN ('draft', 'open', 'paid', 'payment_failed', 'void', 'uncollectible')",
            name="ck_billing_invoice_provider_status",
        ),
        CheckConstraint("provider_amount_due_minor >= 0", name="ck_billing_invoice_amount_due_nonnegative"),
        CheckConstraint("provider_amount_paid_minor >= 0", name="ck_billing_invoice_amount_paid_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    provider: Mapped[str] = mapped_column(String(32), index=True)
    external_invoice_id: Mapped[str] = mapped_column(String(255))
    workspace_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True
    )
    subscription_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("billing_subscriptions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    external_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    external_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    provider_status: Mapped[str] = mapped_column(String(32), index=True)
    currency: Mapped[str] = mapped_column(String(3))
    provider_amount_due_minor: Mapped[int] = mapped_column(Integer)
    provider_amount_paid_minor: Mapped[int] = mapped_column(Integer)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    latest_occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class BillingInvoiceSnapshot(Base):
    __tablename__ = "billing_invoice_snapshots"
    __table_args__ = (
        UniqueConstraint("billing_event_id", name="uq_billing_invoice_snapshot_event"),
        CheckConstraint(
            "reconciliation_status IN ('matched', 'mismatch', 'unpriced', 'unmapped', 'stale')",
            name="ck_billing_invoice_snapshot_status",
        ),
        CheckConstraint("provider_amount_due_minor >= 0", name="ck_billing_invoice_snapshot_amount_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    invoice_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("billing_invoices.id", ondelete="CASCADE"), index=True
    )
    billing_event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("billing_events.id", ondelete="RESTRICT")
    )
    workspace_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True
    )
    pricing_catalog_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    currency: Mapped[str] = mapped_column(String(3))
    expected_amount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_amount_due_minor: Mapped[int] = mapped_column(Integer)
    discrepancy_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reconciliation_status: Mapped[str] = mapped_column(String(32), index=True)
    usage_sha256: Mapped[str] = mapped_column(String(64))
    usage_snapshot: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class BillingUsageReservation(Base):
    __tablename__ = "billing_usage_reservations"
    __table_args__ = (
        UniqueConstraint("workspace_id", "metric", "idempotency_key", name="uq_billing_usage_idempotency"),
        CheckConstraint("quantity > 0", name="ck_billing_usage_quantity_positive"),
        CheckConstraint(
            "status IN ('reserved', 'consumed', 'released')",
            name="ck_billing_usage_reservation_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    metric: Mapped[str] = mapped_column(String(64), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BillingUsageEvent(Base):
    __tablename__ = "billing_usage_events"
    __table_args__ = (
        UniqueConstraint("reservation_id", "transition", name="uq_billing_usage_event_transition"),
        CheckConstraint(
            "transition IN ('reserved', 'consumed', 'released')",
            name="ck_billing_usage_event_transition",
        ),
        CheckConstraint("quantity > 0", name="ck_billing_usage_event_quantity_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    reservation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("billing_usage_reservations.id", ondelete="CASCADE"), index=True
    )
    transition: Mapped[str] = mapped_column(String(32), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    reason_code: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class LLMUsageRecord(Base):
    __tablename__ = "llm_usage_records"
    __table_args__ = (
        UniqueConstraint("reservation_id", name="uq_llm_usage_reservation"),
        CheckConstraint(
            "outcome IN ('success', 'partial', 'provider_error')",
            name="ck_llm_usage_outcome",
        ),
        CheckConstraint(
            "pricing_basis IN ('reported_cache', 'cache_miss_assumed', 'unpriced')",
            name="ck_llm_usage_pricing_basis",
        ),
        CheckConstraint(
            "request_count >= 0 AND input_tokens >= 0 AND cache_hit_tokens >= 0 "
            "AND cache_miss_tokens >= 0 AND output_tokens >= 0",
            name="ck_llm_usage_nonnegative",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    reservation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("billing_usage_reservations.id", ondelete="RESTRICT")
    )
    operation: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(255), index=True)
    outcome: Mapped[str] = mapped_column(String(32), index=True)
    request_count: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int] = mapped_column(Integer)
    cache_hit_tokens: Mapped[int] = mapped_column(Integer)
    cache_miss_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    estimated_cost_picousd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pricing_catalog_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pricing_basis: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


json_document = JSON().with_variant(JSONB(), "postgresql")


class RuntimeConnectionProfile(Base):
    __tablename__ = "runtime_connection_profiles"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_runtime_profile_workspace_name"),
        CheckConstraint("kind IN ('n8n', 'openclaw', 'hermes')", name="ck_runtime_profile_kind"),
        CheckConstraint("status IN ('draft', 'verified', 'failed', 'disabled')", name="ck_runtime_profile_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(32), index=True)
    endpoint_url: Mapped[str] = mapped_column(String(2_000))
    secret_ref: Mapped[str] = mapped_column(String(255))
    n8n_minor: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    detected_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_check_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class RuntimeConnectionCheck(Base):
    __tablename__ = "runtime_connection_checks"
    __table_args__ = (
        CheckConstraint("status IN ('verified', 'failed')", name="ck_runtime_connection_check_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("runtime_connection_profiles.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    result_code: Mapped[str] = mapped_column(String(64))
    detected_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    checked_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class N8nPublication(Base):
    __tablename__ = "n8n_publications"
    __table_args__ = (
        UniqueConstraint("profile_id", "idempotency_key", name="uq_n8n_publication_profile_idempotency"),
        CheckConstraint("status IN ('publishing', 'published', 'failed', 'deleted', 'deletion_failed')", name="ck_n8n_publication_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    revision_id: Mapped[str] = mapped_column(String(36), ForeignKey("process_revisions.id", ondelete="RESTRICT"), index=True)
    profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("runtime_connection_profiles.id", ondelete="RESTRICT"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    workflow_sha256: Mapped[str] = mapped_column(String(64), index=True)
    remote_workflow_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentPackageDelivery(Base):
    __tablename__ = "agent_package_deliveries"
    __table_args__ = (
        UniqueConstraint("profile_id", "idempotency_key", name="uq_agent_package_delivery_profile_idempotency"),
        CheckConstraint("runtime IN ('openclaw', 'hermes')", name="ck_agent_package_delivery_runtime"),
        CheckConstraint("status IN ('storing', 'stored', 'failed', 'deleted', 'deletion_failed')", name="ck_agent_package_delivery_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    revision_id: Mapped[str] = mapped_column(String(36), ForeignKey("process_revisions.id", ondelete="RESTRICT"), index=True)
    profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("runtime_connection_profiles.id", ondelete="RESTRICT"), index=True)
    runtime: Mapped[str] = mapped_column(String(32), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    package_sha256: Mapped[str] = mapped_column(String(64), index=True)
    package_size: Mapped[int] = mapped_column(Integer)
    file_count: Mapped[int] = mapped_column(Integer)
    remote_package_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    stored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'active', 'archived')", name="ck_project_status"),
        CheckConstraint("target_mode IN ('process', 'agent')", name="ck_project_target_mode"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    default_locale: Mapped[str] = mapped_column(String(35), default="ru")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    target_mode: Mapped[str] = mapped_column(String(32), default="process")
    current_revision_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("process_revisions.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class RubricVersion(Base):
    __tablename__ = "rubric_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RubricEntry(Base):
    __tablename__ = "rubric_entries"
    __table_args__ = (
        UniqueConstraint("version_id", "dimension", "code", name="uq_rubric_entry_version_dimension_code"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("rubric_versions.id", ondelete="RESTRICT"),
        index=True,
    )
    dimension: Mapped[str] = mapped_column(String(64), index=True)
    code: Mapped[str] = mapped_column(String(64))
    parent_id: Mapped[str | None] = mapped_column(
        String(128),
        ForeignKey("rubric_entries.id", ondelete="RESTRICT"),
        nullable=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    deprecated: Mapped[bool] = mapped_column(Boolean, default=False)


class RubricEntryTranslation(Base):
    __tablename__ = "rubric_entry_translations"
    __table_args__ = (
        UniqueConstraint("entry_id", "locale", name="uq_rubric_translation_entry_locale"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    entry_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("rubric_entries.id", ondelete="CASCADE"),
        index=True,
    )
    locale: Mapped[str] = mapped_column(String(35))
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    synonyms: Mapped[list[str]] = mapped_column(json_document, default=list)


class TemplateCollection(Base):
    __tablename__ = "template_collections"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_template_collection_user_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    is_favorites: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UserProcessTemplate(Base):
    __tablename__ = "user_process_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    locale: Mapped[str] = mapped_column(String(35), default="ru")
    target_mode: Mapped[str] = mapped_column(String(32), default="process")
    process_ir: Mapped[dict] = mapped_column(json_document)
    rubric_entry_ids: Mapped[list[str]] = mapped_column(json_document, default=list)
    source_project_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    source_revision_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("process_revisions.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class TemplateCollectionItem(Base):
    __tablename__ = "template_collection_items"
    __table_args__ = (
        UniqueConstraint("collection_id", "template_source", "template_id", name="uq_template_collection_item"),
        CheckConstraint("template_source IN ('catalog', 'user')", name="ck_template_collection_item_source"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    collection_id: Mapped[str] = mapped_column(String(36), ForeignKey("template_collections.id", ondelete="CASCADE"), index=True)
    template_source: Mapped[str] = mapped_column(String(32))
    template_id: Mapped[str] = mapped_column(String(160), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class N8nImportArtifact(Base):
    __tablename__ = "n8n_import_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    revision_id: Mapped[str] = mapped_column(String(36), ForeignKey("process_revisions.id", ondelete="CASCADE"), unique=True, index=True)
    source_minor: Mapped[str] = mapped_column(String(16))
    workflow_name: Mapped[str] = mapped_column(String(200))
    source_sha256: Mapped[str] = mapped_column(String(64), index=True)
    source_workflow: Mapped[dict] = mapped_column(json_document)
    diagnostics: Mapped[dict] = mapped_column(json_document)
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProjectArchiveRestore(Base):
    __tablename__ = "project_archive_restores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    archive_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source_project_id: Mapped[str] = mapped_column(String(36), index=True)
    restored_project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    restored_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    restored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key", name="uq_agent_run_project_idempotency"),
        CheckConstraint("runtime IN ('openclaw', 'hermes')", name="ck_agent_run_runtime"),
        CheckConstraint("status IN ('created', 'running', 'awaiting_approval', 'completed', 'failed', 'escalated', 'cancelled')", name="ck_agent_run_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    revision_id: Mapped[str] = mapped_column(String(36), ForeignKey("process_revisions.id", ondelete="RESTRICT"), index=True)
    runtime: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="created", index=True)
    contract_version: Mapped[str] = mapped_column(String(32), default="1.1")
    idempotency_key: Mapped[str] = mapped_column(String(128))
    max_steps: Mapped[int] = mapped_column(Integer, default=20)
    max_tool_calls: Mapped[int] = mapped_column(Integer, default=10)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300)
    max_cost_microunits: Mapped[int] = mapped_column(Integer, default=0)
    steps_used: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls_used: Mapped[int] = mapped_column(Integer, default=0)
    cost_microunits: Mapped[int] = mapped_column(Integer, default=0)
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class AgentRunEvent(Base):
    __tablename__ = "agent_run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_agent_run_event_sequence"),
        CheckConstraint("actor_type IN ('user', 'system', 'agent')", name="ck_agent_run_event_actor"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    external_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(16))
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metrics: Mapped[dict] = mapped_column(json_document, default=dict)
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AgentDispatchJob(Base):
    __tablename__ = "agent_dispatch_jobs"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_agent_dispatch_job_run"),
        CheckConstraint("status IN ('queued', 'leased', 'retry_wait', 'dispatched', 'dead_letter', 'cancelled')", name="ck_agent_dispatch_job_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class AgentIncident(Base):
    __tablename__ = "agent_incidents"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_agent_incident_run"),
        CheckConstraint("status IN ('open', 'resolved', 'replayed')", name="ck_agent_incident_status"),
        CheckConstraint("category IN ('dispatch', 'runtime', 'limit', 'timeout', 'escalation')", name="ck_agent_incident_category"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    reason_code: Mapped[str] = mapped_column(String(64))
    resolution_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    replay_run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    resolved_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class AgentEvaluationRun(Base):
    __tablename__ = "agent_evaluation_runs"
    __table_args__ = (
        CheckConstraint("runtime IN ('openclaw', 'hermes')", name="ck_agent_evaluation_runtime"),
        CheckConstraint("status IN ('passed', 'failed')", name="ck_agent_evaluation_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    revision_id: Mapped[str] = mapped_column(String(36), ForeignKey("process_revisions.id", ondelete="RESTRICT"), index=True)
    runtime: Mapped[str] = mapped_column(String(32))
    suite_version: Mapped[str] = mapped_column(String(32), default="1")
    status: Mapped[str] = mapped_column(String(16), index=True)
    model_fingerprint: Mapped[str] = mapped_column(String(64))
    results: Mapped[list[dict]] = mapped_column(json_document)
    passed_count: Mapped[int] = mapped_column(Integer)
    total_count: Mapped[int] = mapped_column(Integer)
    cost_microunits: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AgentBaselineDecision(Base):
    __tablename__ = "agent_baseline_decisions"
    __table_args__ = (
        CheckConstraint("runtime IN ('openclaw', 'hermes')", name="ck_agent_baseline_runtime"),
        CheckConstraint("action IN ('approve', 'rollback')", name="ck_agent_baseline_action"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    evaluation_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_evaluation_runs.id", ondelete="RESTRICT"), index=True)
    runtime: Mapped[str] = mapped_column(String(32), index=True)
    action: Mapped[str] = mapped_column(String(16))
    reason_code: Mapped[str] = mapped_column(String(64))
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProcessRevision(Base):
    __tablename__ = "process_revisions"
    __table_args__ = (
        UniqueConstraint("project_id", "version_number", name="uq_revision_project_version"),
        CheckConstraint(
            "source IN ('initial', 'user', 'analyst', 'template', 'import', 'undo', 'restore')",
            name="ck_revision_source",
        ),
        CheckConstraint(
            "perspective IN ('as_is', 'to_be')",
            name="ck_revision_perspective",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[str] = mapped_column(String(32))
    process_ir: Mapped[dict] = mapped_column(json_document)
    forward_patch: Mapped[list[dict] | None] = mapped_column(json_document, nullable=True)
    inverse_patch: Mapped[list[dict] | None] = mapped_column(json_document, nullable=True)
    validation_result: Mapped[dict] = mapped_column(json_document)
    parent_revision_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("process_revisions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    restored_from_revision_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("process_revisions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(String(32))
    perspective: Mapped[str] = mapped_column(String(16), default="to_be")
    created_by_user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AnalystSession(Base):
    __tablename__ = "analyst_sessions"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('discovery', 'refinement', 'export_preparation', 'as_is_completion')",
            name="ck_analyst_session_mode",
        ),
        CheckConstraint(
            "status IN ('active', 'closed')",
            name="ck_analyst_session_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    started_from_revision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("process_revisions.id", ondelete="RESTRICT"),
    )
    mode: Mapped[str] = mapped_column(String(32))
    locale: Mapped[str] = mapped_column(String(35))
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_by_user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class AnalystMessage(Base):
    __tablename__ = "analyst_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_analyst_message_role"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analyst_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    revision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("process_revisions.id", ondelete="RESTRICT"),
    )
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(String(35))
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class InterviewDocument(Base):
    __tablename__ = "interview_documents"
    __table_args__ = (
        CheckConstraint("source_format IN ('plain', 'txt', 'md', 'srt', 'vtt', 'docx', 'odt', 'google_docs', 'yandex_docs')", name="ck_interview_document_format"),
        CheckConstraint("status IN ('draft', 'reviewed', 'purged')", name="ck_interview_document_status"),
        UniqueConstraint("session_id", "content_sha256", name="uq_interview_document_session_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analyst_sessions.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    source_format: Mapped[str] = mapped_column(String(16))
    source_url: Mapped[str | None] = mapped_column(String(2_000), nullable=True)
    language: Mapped[str] = mapped_column(String(35))
    original_text: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    segments_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    data_residency: Mapped[str] = mapped_column(String(64), default="local")
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purge_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class InterviewSegment(Base):
    __tablename__ = "interview_segments"
    __table_args__ = (UniqueConstraint("document_id", "ordinal", name="uq_interview_segment_ordinal"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("interview_documents.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str | None] = mapped_column(String(160), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    start_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class InterviewAnalysis(Base):
    __tablename__ = "interview_analyses"
    __table_args__ = (UniqueConstraint("document_id", "segments_sha256", name="uq_interview_analysis_document_hash"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("interview_documents.id", ondelete="CASCADE"), index=True)
    segments_sha256: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(json_document)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(64))
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProposedPatch(Base):
    __tablename__ = "proposed_patches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected')",
            name="ck_proposed_patch_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analyst_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    base_revision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("process_revisions.id", ondelete="RESTRICT"),
    )
    source_message_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("analyst_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    patch: Mapped[list[dict]] = mapped_column(json_document)
    summary: Mapped[str] = mapped_column(Text)
    validation_result: Mapped[dict] = mapped_column(json_document)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    accepted_revision_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("process_revisions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    resolved_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InterviewProposalEvidence(Base):
    __tablename__ = "interview_proposal_evidence"

    proposal_id: Mapped[str] = mapped_column(String(36), ForeignKey("proposed_patches.id", ondelete="CASCADE"), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(String(36), ForeignKey("interview_analyses.id", ondelete="RESTRICT"), index=True)
    segments_sha256: Mapped[str] = mapped_column(String(64))
    selected_fact_indices: Mapped[list] = mapped_column(json_document)
    segment_ids: Mapped[list] = mapped_column(json_document)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class InterviewProposalEvidenceSource(Base):
    __tablename__ = "interview_proposal_evidence_sources"
    __table_args__ = (UniqueConstraint("proposal_id", "analysis_id", name="uq_interview_proposal_evidence_source"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    proposal_id: Mapped[str] = mapped_column(String(36), ForeignKey("proposed_patches.id", ondelete="CASCADE"), index=True)
    analysis_id: Mapped[str] = mapped_column(String(36), ForeignKey("interview_analyses.id", ondelete="RESTRICT"), index=True)
    segments_sha256: Mapped[str] = mapped_column(String(64))
    selected_fact_indices: Mapped[list] = mapped_column(json_document)
    segment_ids: Mapped[list] = mapped_column(json_document)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CrossInterviewConflict(Base):
    __tablename__ = "cross_interview_conflicts"
    __table_args__ = (
        UniqueConstraint("session_id", "evidence_sha256", "fingerprint", name="uq_cross_interview_conflict_evidence"),
        CheckConstraint("status IN ('pending', 'confirmed', 'dismissed')", name="ck_cross_interview_conflict_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("analyst_sessions.id", ondelete="CASCADE"), index=True)
    evidence_sha256: Mapped[str] = mapped_column(String(64), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text)
    question: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    fact_references: Mapped[list] = mapped_column(json_document)
    segment_ids: Mapped[list] = mapped_column(json_document)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(64))
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    resolved_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CrossInterviewConflictScan(Base):
    __tablename__ = "cross_interview_conflict_scans"
    __table_args__ = (UniqueConstraint("session_id", "evidence_sha256", name="uq_cross_interview_conflict_scan"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("analyst_sessions.id", ondelete="CASCADE"), index=True)
    evidence_sha256: Mapped[str] = mapped_column(String(64), index=True)
    source_count: Mapped[int] = mapped_column(Integer)
    fact_count: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(64))
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ImmutableRevisionError(RuntimeError):
    pass


@event.listens_for(AdminAuditEvent, "before_update")
@event.listens_for(AdminAuditEvent, "before_delete")
def prevent_admin_audit_mutation(mapper, connection, target) -> None:
    raise ImmutableRevisionError("Administrative audit events are immutable.")


@event.listens_for(BillingEvent, "before_update")
@event.listens_for(BillingEvent, "before_delete")
def prevent_billing_event_mutation(mapper, connection, target) -> None:
    raise ImmutableRevisionError("Billing events are immutable.")


@event.listens_for(BillingUsageEvent, "before_update")
@event.listens_for(BillingUsageEvent, "before_delete")
def prevent_billing_usage_event_mutation(mapper, connection, target) -> None:
    raise ImmutableRevisionError("Billing usage events are immutable.")


@event.listens_for(BillingInvoiceSnapshot, "before_update")
@event.listens_for(BillingInvoiceSnapshot, "before_delete")
def prevent_billing_invoice_snapshot_mutation(mapper, connection, target) -> None:
    raise ImmutableRevisionError("Billing invoice snapshots are immutable.")


@event.listens_for(LLMUsageRecord, "before_update")
@event.listens_for(LLMUsageRecord, "before_delete")
def prevent_llm_usage_record_mutation(mapper, connection, target) -> None:
    raise ImmutableRevisionError("LLM usage records are immutable.")


@event.listens_for(ProcessRevision, "before_update")
def prevent_revision_update(mapper, connection, target) -> None:
    raise ImmutableRevisionError("ProcessRevision records are immutable.")


@event.listens_for(ProcessRevision, "before_delete")
def prevent_revision_delete(mapper, connection, target) -> None:
    raise ImmutableRevisionError("ProcessRevision records cannot be deleted directly.")


@event.listens_for(AgentRunEvent, "before_update")
@event.listens_for(AgentRunEvent, "before_delete")
def prevent_agent_run_event_mutation(mapper, connection, target) -> None:
    raise ImmutableRevisionError("AgentRunEvent records are immutable.")


@event.listens_for(AgentEvaluationRun, "before_update")
@event.listens_for(AgentEvaluationRun, "before_delete")
@event.listens_for(AgentBaselineDecision, "before_update")
@event.listens_for(AgentBaselineDecision, "before_delete")
def prevent_agent_evidence_mutation(mapper, connection, target) -> None:
    raise ImmutableRevisionError("Agent evaluation evidence is immutable.")


@event.listens_for(InterviewAnalysis, "before_update")
@event.listens_for(InterviewAnalysis, "before_delete")
def prevent_interview_analysis_mutation(mapper, connection, target) -> None:
    raise ImmutableRevisionError("Interview analysis evidence is immutable.")


@event.listens_for(InterviewProposalEvidence, "before_update")
@event.listens_for(InterviewProposalEvidence, "before_delete")
@event.listens_for(InterviewProposalEvidenceSource, "before_update")
@event.listens_for(InterviewProposalEvidenceSource, "before_delete")
def prevent_interview_proposal_evidence_mutation(mapper, connection, target) -> None:
    raise ImmutableRevisionError("Interview proposal evidence is immutable.")


@event.listens_for(CrossInterviewConflictScan, "before_update")
@event.listens_for(CrossInterviewConflictScan, "before_delete")
def prevent_cross_interview_conflict_scan_mutation(mapper, connection, target) -> None:
    raise ImmutableRevisionError("Cross-interview conflict scans are immutable.")
