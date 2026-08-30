from copy import deepcopy
from typing import Annotated, Any, Callable, TypeVar
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from .auth import CurrentUser
from .config import Settings, get_settings
from .database import get_db
from .entitlement_dependencies import (
    AgentExportEntitlement,
    BpmnExportEntitlement,
    CodeGenerateEntitlement,
    N8nExportEntitlement,
    SpecExportEntitlement,
)
from .exporters import (
    SUPPORTED_APP_TARGETS,
    SUPPORTED_AGENT_TARGETS,
    generate_app_spec,
    generate_agent_package,
    generate_bpmn,
    generate_drawio,
    generate_export_package,
    generate_n8n_package,
    generate_spec,
)
from .exporters.n8n import SUPPORTED_TARGETS, export_n8n
from .exporters.n8n.python_code import PythonCodePolicyError
from .exporters.n8n.python_code import (
    GENERATOR_VERSION,
    generate_numeric_threshold_source,
    operation_spec_hash,
    source_hash,
    validate_python_code_artifact,
    verify_python_fixtures,
)
from .exporters.n8n.registry import TARGETS
from .models import PythonCodeGenerationRequest, PythonCodeValidationRequest, PythonCodeValidationResponse
from .validation import validate_process_ir
from .process_ir import upgrade_process_ir
from .localization import normalize_locale
from .services.billing_usage import metered_operation


router = APIRouter(prefix="/api/v1/exports", tags=["exports"])
DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]
IdempotencyHeader = Annotated[
    str | None,
    Header(alias="Idempotency-Key", min_length=8, max_length=128),
]
T = TypeVar("T")


def _metered_export(
    db: Session,
    settings: Settings,
    *,
    workspace_id: str,
    operation: str,
    idempotency_key: str | None,
    generate: Callable[[], T],
) -> T:
    request_key = idempotency_key or f"server:{uuid4()}"
    with metered_operation(
        db,
        workspace_id=workspace_id,
        settings=settings,
        metric="export",
        operation=operation,
        request_key=request_key,
    ):
        return generate()


def _validated(process_ir: dict[str, Any]) -> tuple[dict[str, Any], Any]:
    normalized = upgrade_process_ir(process_ir)
    validation = validate_process_ir(normalized)
    if not validation.valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_process_ir", "validation": validation.model_dump()},
        )
    return normalized, validation


def _export_locale(locale: str) -> str:
    try:
        return normalize_locale(locale)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_locale", "message": str(error)},
        ) from error


def _code_policy_error(error: PythonCodePolicyError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": error.code, "message": error.detail},
    )


@router.post("/n8n/python-code/generate")
def generate_python_code(
    current_user: CurrentUser,
    request: PythonCodeGenerationRequest,
    _entitlement: CodeGenerateEntitlement,
) -> dict[str, Any]:
    process_ir, _ = _validated(request.process_ir)
    step = next((item for item in process_ir["steps"] if item["id"] == request.step_id), None)
    if not step:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "step_not_found"})
    rule = next((item for item in process_ir["businessRules"] if item["id"] == request.business_rule_id), None)
    if not rule or request.step_id not in rule.get("appliesToStepIds", []) or not rule.get("source"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "python_business_rule_mismatch"})
    source = generate_numeric_threshold_source(
        request.input_field, request.output_field, request.operator, request.threshold,
    )
    sample_value = request.threshold
    expected_value = {
        "<": sample_value < request.threshold,
        "<=": sample_value <= request.threshold,
        "==": sample_value == request.threshold,
        "!=": sample_value != request.threshold,
        ">=": sample_value >= request.threshold,
        ">": sample_value > request.threshold,
    }[request.operator]
    artifact = {
        "strategy": "python_code",
        "reasonStandardNodesInsufficient": request.reason,
        "businessRuleIds": [request.business_rule_id],
        "runtimeProfile": "n8n_native_python",
        "source": source,
        "inputExample": [{"json": {request.input_field: sample_value}}],
        "outputExample": [{"json": {request.input_field: sample_value, request.output_field: expected_value}}],
        "errorExample": [{"json": {}}],
        "expectedError": "ValueError",
        "errorCases": [f"Missing {request.input_field} raises ValueError", f"Non-numeric {request.input_field} raises TypeError"],
        "prohibitions": ["network", "filesystem", "credentials", "dynamic_code"],
        "generatorVersion": GENERATOR_VERSION,
        "contentHash": source_hash(source),
        "approvalStatus": "draft",
        "operationSpec": {
            "kind": "numeric_threshold", "inputField": request.input_field, "outputField": request.output_field,
            "operator": request.operator, "threshold": request.threshold,
        },
    }
    return {"artifact": artifact, "template": "numeric_threshold/1.0"}


@router.post("/n8n/python-code/validate", response_model=PythonCodeValidationResponse)
def validate_python_code(
    current_user: CurrentUser,
    request: PythonCodeValidationRequest,
    _entitlement: CodeGenerateEntitlement,
) -> PythonCodeValidationResponse:
    process_ir, _ = _validated(request.process_ir)
    step = next((item for item in process_ir["steps"] if item["id"] == request.step_id), None)
    if not step:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "step_not_found"})
    strategy = request.custom_logic.get("strategy", "python_code")
    if strategy not in {"python_code", "python_service", "typescript_node"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "python_strategy_required"})
    artifact = {
        **request.custom_logic,
        "strategy": strategy,
        "runtimeProfile": {"python_code": "n8n_native_python", "python_service": "external_python_service", "typescript_node": "native_typescript_node"}[strategy],
        "generatorVersion": GENERATOR_VERSION,
        "contentHash": source_hash(str(request.custom_logic.get("source", ""))),
        "approvalStatus": "draft",
    }
    if strategy == "python_service":
        artifact["dependencyProfile"] = request.custom_logic.get("dependencyProfile", "core")
    else:
        artifact.pop("dependencyProfile", None)
    if strategy == "typescript_node" and isinstance(artifact.get("operationSpec"), dict):
        artifact.setdefault("fallbackReason", request.custom_logic.get("fallbackReason"))
    candidate = {
        **step,
        "automationHint": {"target": "n8n", "nodeType": "apa.numericThreshold" if strategy == "typescript_node" else ("n8n-nodes-base.httpRequest" if strategy == "python_service" else "n8n-nodes-base.code")},
        "customLogic": {**artifact, "approvalStatus": "approved"},
    }
    checks = {"syntax": "failed", "policy": "failed", "provenance": "failed", "fixtures": "failed", "execution": "failed"}
    errors: list[dict[str, str]] = []
    execution: dict[str, Any] | None = None
    candidate_process = deepcopy(process_ir)
    step_index = next(index for index, item in enumerate(candidate_process["steps"]) if item["id"] == request.step_id)
    candidate_process["steps"][step_index] = candidate
    candidate_validation = validate_process_ir(candidate_process)
    if not candidate_validation.valid:
        errors.append({"code": "python_artifact_schema_invalid", "message": candidate_validation.issues[0].message})
        return PythonCodeValidationResponse(valid=False, artifact=artifact, checks=checks, errors=errors, execution=None)
    try:
        validate_python_code_artifact(process_ir, candidate, TARGETS[request.target_minor], require_execution=False)
        for name in ("syntax", "policy", "provenance", "fixtures"):
            checks[name] = "passed"
        execution = verify_python_fixtures(artifact)
        if strategy == "typescript_node":
            execution["operationSpecHash"] = operation_spec_hash(artifact["operationSpec"])
        artifact["executionEvidence"] = execution
        checks["execution"] = "passed"
    except PythonCodePolicyError as error:
        errors.append({"code": error.code, "message": error.detail})
        if error.code not in {"python_syntax_invalid"}:
            checks["syntax"] = "passed"
        if error.code not in {"python_syntax_invalid", "python_policy_violation", "python_artifact_incomplete"}:
            checks["policy"] = "passed"
        if error.code not in {"python_business_rules_missing", "python_business_rule_mismatch", "python_business_rule_source_missing"}:
            checks["provenance"] = "passed"
        if error.code not in {"python_fixture_shape_invalid", "python_fixture_result_mismatch", "python_fixture_error_mismatch"}:
            checks["fixtures"] = "passed"
    return PythonCodeValidationResponse(valid=not errors, artifact=artifact, checks=checks, errors=errors, execution=execution)


@router.post("/spec")
def spec_export(
    current_user: CurrentUser,
    entitlement: SpecExportEntitlement,
    db: DbSession,
    settings: AppSettings,
    idempotency_key: IdempotencyHeader = None,
    process_ir: dict[str, Any] = Body(),
) -> Response:
    process_ir, validation = _validated(process_ir)
    process_id = process_ir["process"]["id"]
    content = _metered_export(
        db, settings, workspace_id=entitlement.workspace_id, operation="export.spec",
        idempotency_key=idempotency_key, generate=lambda: generate_spec(process_ir, validation),
    )
    return Response(
        content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{process_id}-spec.md"'},
    )


@router.post("/app-spec/{target_id}")
def app_spec_export(
    target_id: str,
    current_user: CurrentUser,
    entitlement: SpecExportEntitlement,
    db: DbSession,
    settings: AppSettings,
    idempotency_key: IdempotencyHeader = None,
    locale: str = Query(default="en"),
    process_ir: dict[str, Any] = Body(),
) -> Response:
    process_ir, validation = _validated(process_ir)
    locale = _export_locale(locale)
    if target_id not in SUPPORTED_APP_TARGETS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "unsupported_app_target", "supported": SUPPORTED_APP_TARGETS},
        )
    process_id = process_ir["process"]["id"]
    content = _metered_export(
        db, settings, workspace_id=entitlement.workspace_id, operation=f"export.app-spec.{target_id}",
        idempotency_key=idempotency_key,
        generate=lambda: generate_app_spec(process_ir, validation, target_id, locale),
    )
    return Response(
        content,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="{process_id}-app-spec-{target_id}.md"'
        },
    )


@router.post("/agent/{target_id}/package")
def agent_package_export(
    target_id: str,
    current_user: CurrentUser,
    entitlement: AgentExportEntitlement,
    db: DbSession,
    settings: AppSettings,
    idempotency_key: IdempotencyHeader = None,
    locale: str = Query(default="en"),
    process_ir: dict[str, Any] = Body(),
) -> Response:
    process_ir, _ = _validated(process_ir)
    locale = _export_locale(locale)
    if target_id not in SUPPORTED_AGENT_TARGETS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "unsupported_agent_target", "supported": SUPPORTED_AGENT_TARGETS},
        )
    process_id = process_ir["process"]["id"]
    package = _metered_export(
        db, settings, workspace_id=entitlement.workspace_id, operation=f"export.agent.{target_id}",
        idempotency_key=idempotency_key,
        generate=lambda: generate_agent_package(process_ir, target_id, locale),
    )
    return Response(
        package,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{process_id}-agent-{target_id}.zip"'
        },
    )


@router.post("/bpmn")
def bpmn_export(
    current_user: CurrentUser,
    entitlement: BpmnExportEntitlement,
    db: DbSession,
    settings: AppSettings,
    idempotency_key: IdempotencyHeader = None,
    process_ir: dict[str, Any] = Body(),
) -> Response:
    process_ir, _ = _validated(process_ir)
    process_id = process_ir["process"]["id"]
    content = _metered_export(
        db, settings, workspace_id=entitlement.workspace_id, operation="export.bpmn",
        idempotency_key=idempotency_key, generate=lambda: generate_bpmn(process_ir),
    )
    return Response(
        content,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{process_id}.bpmn"'},
    )


@router.post("/drawio")
def drawio_export(
    current_user: CurrentUser,
    entitlement: BpmnExportEntitlement,
    db: DbSession,
    settings: AppSettings,
    idempotency_key: IdempotencyHeader = None,
    process_ir: dict[str, Any] = Body(),
) -> Response:
    process_ir, _ = _validated(process_ir)
    process_id = process_ir["process"]["id"]
    content = _metered_export(
        db, settings, workspace_id=entitlement.workspace_id, operation="export.drawio",
        idempotency_key=idempotency_key, generate=lambda: generate_drawio(process_ir),
    )
    return Response(
        content,
        media_type="application/vnd.jgraph.mxfile",
        headers={"Content-Disposition": f'attachment; filename="{process_id}-bpmn.drawio"'},
    )


@router.post("/n8n/{target_minor}")
def n8n_export(
    target_minor: str,
    current_user: CurrentUser,
    entitlement: N8nExportEntitlement,
    db: DbSession,
    settings: AppSettings,
    idempotency_key: IdempotencyHeader = None,
    process_ir: dict[str, Any] = Body(),
) -> dict[str, Any]:
    process_ir, _ = _validated(process_ir)
    if target_minor not in SUPPORTED_TARGETS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "unsupported_n8n_target", "supported": SUPPORTED_TARGETS},
        )
    try:
        return _metered_export(
            db, settings, workspace_id=entitlement.workspace_id,
            operation=f"export.n8n.{target_minor}", idempotency_key=idempotency_key,
            generate=lambda: export_n8n(process_ir, target_minor),
        )
    except PythonCodePolicyError as error:
        raise _code_policy_error(error) from error


@router.post("/n8n/{target_minor}/package")
def n8n_package_export(
    target_minor: str,
    current_user: CurrentUser,
    entitlement: N8nExportEntitlement,
    db: DbSession,
    settings: AppSettings,
    idempotency_key: IdempotencyHeader = None,
    locale: str = Query(default="en"),
    include_general_guide: bool = Query(default=True, alias="includeGeneralGuide"),
    process_ir: dict[str, Any] = Body(),
) -> Response:
    process_ir, _ = _validated(process_ir)
    locale = _export_locale(locale)
    if target_minor not in SUPPORTED_TARGETS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "unsupported_n8n_target", "supported": SUPPORTED_TARGETS},
        )
    process_id = process_ir["process"]["id"]
    try:
        package = _metered_export(
            db, settings, workspace_id=entitlement.workspace_id,
            operation=f"export.n8n-package.{target_minor}", idempotency_key=idempotency_key,
            generate=lambda: generate_n8n_package(process_ir, target_minor, locale, include_general_guide),
        )
    except PythonCodePolicyError as error:
        raise _code_policy_error(error) from error
    return Response(
        package,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{process_id}-n8n-{target_minor}.zip"'
        },
    )


@router.post("/package/{target_minor}")
def package_export(
    target_minor: str,
    current_user: CurrentUser,
    spec_entitlement: SpecExportEntitlement,
    _bpmn_entitlement: BpmnExportEntitlement,
    _n8n_entitlement: N8nExportEntitlement,
    db: DbSession,
    settings: AppSettings,
    idempotency_key: IdempotencyHeader = None,
    process_ir: dict[str, Any] = Body(),
) -> Response:
    process_ir, validation = _validated(process_ir)
    if target_minor not in SUPPORTED_TARGETS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "unsupported_n8n_target", "supported": SUPPORTED_TARGETS},
        )
    process_id = process_ir["process"]["id"]
    try:
        package = _metered_export(
            db, settings, workspace_id=spec_entitlement.workspace_id,
            operation=f"export.package.{target_minor}", idempotency_key=idempotency_key,
            generate=lambda: generate_export_package(process_ir, validation, target_minor),
        )
    except PythonCodePolicyError as error:
        raise _code_policy_error(error) from error
    return Response(
        package,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{process_id}-{target_minor}.zip"'},
    )
