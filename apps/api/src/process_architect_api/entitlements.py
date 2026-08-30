from __future__ import annotations

import json
from functools import lru_cache
from typing import Literal

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field

from .paths import WORKSPACE_ROOT


CATALOG_PATH = WORKSPACE_ROOT / "config" / "entitlements" / "v1" / "catalog.json"
CATALOG_SCHEMA_PATH = WORKSPACE_ROOT / "02_architecture" / "schemas" / "entitlement-catalog-v1.schema.json"


class EntitlementDefinition(BaseModel):
    id: str
    kind: Literal["boolean", "integer"]
    description: str


class PlanDefinition(BaseModel):
    id: str
    audience: Literal["hosted", "self_hosted", "internal"]
    name: str
    entitlements: dict[str, bool | int]


class EntitlementCatalog(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: Literal["1"] = Field(alias="schemaVersion")
    catalog_version: str = Field(alias="catalogVersion")
    entitlements: list[EntitlementDefinition]
    plans: list[PlanDefinition]

    def plan(self, plan_id: str) -> PlanDefinition:
        plan = next((item for item in self.plans if item.id == plan_id), None)
        if plan is None:
            raise EntitlementCatalogError(f"Unknown entitlement plan: {plan_id}")
        return plan

    def definition(self, entitlement_id: str) -> EntitlementDefinition:
        definition = next((item for item in self.entitlements if item.id == entitlement_id), None)
        if definition is None:
            raise EntitlementCatalogError(f"Unknown entitlement: {entitlement_id}")
        return definition


class EntitlementCatalogError(RuntimeError):
    pass


@lru_cache
def get_entitlement_catalog() -> EntitlementCatalog:
    try:
        document = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        schema = json.loads(CATALOG_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EntitlementCatalogError(f"Cannot read entitlement catalog: {error}") from error
    errors = sorted(Draft202012Validator(schema).iter_errors(document), key=lambda item: list(item.path))
    if errors:
        details = "; ".join(f"/{'/'.join(map(str, error.path))}: {error.message}" for error in errors[:10])
        raise EntitlementCatalogError(f"Invalid entitlement catalog: {details}")
    catalog = EntitlementCatalog.model_validate(document)
    definitions = {item.id: item for item in catalog.entitlements}
    if len(definitions) != len(catalog.entitlements):
        raise EntitlementCatalogError("Entitlement IDs must be unique.")
    if len({item.id for item in catalog.plans}) != len(catalog.plans):
        raise EntitlementCatalogError("Plan IDs must be unique.")
    expected = set(definitions)
    for plan in catalog.plans:
        if set(plan.entitlements) != expected:
            raise EntitlementCatalogError(f"Plan {plan.id} must define every entitlement exactly once.")
        for entitlement_id, value in plan.entitlements.items():
            kind = definitions[entitlement_id].kind
            if kind == "boolean" and type(value) is not bool:
                raise EntitlementCatalogError(f"Plan {plan.id} has a non-boolean value for {entitlement_id}.")
            if kind == "integer" and (type(value) is not int or value < -1):
                raise EntitlementCatalogError(f"Plan {plan.id} has an invalid integer value for {entitlement_id}.")
    return catalog


def clear_entitlement_catalog_cache() -> None:
    get_entitlement_catalog.cache_clear()
