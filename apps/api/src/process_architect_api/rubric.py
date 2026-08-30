from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db_models import RubricEntry, RubricEntryTranslation, RubricVersion
from .localization import normalize_locale


CURRENT_RUBRIC_VERSION = "core-1.0"


def _labels(ru: str, en: str, es: str) -> dict[str, str]:
    return {"ru": ru, "en": en, "es": es}


RUBRIC_DIMENSIONS = (
    ("process_level", _labels("Уровень процесса", "Process level", "Nivel del proceso")),
    ("business_role", _labels("Роль в бизнесе", "Business role", "Rol empresarial")),
    ("customer_impact", _labels("Влияние на клиента", "Customer impact", "Impacto en el cliente")),
    ("organizational_span", _labels("Охват организации", "Organizational span", "Alcance organizativo")),
    ("automation_mode", _labels("Способ автоматизации", "Automation mode", "Modo de automatizacion")),
    ("domain", _labels("Область бизнеса", "Business domain", "Area de negocio")),
    ("risk", _labels("Уровень риска", "Risk level", "Nivel de riesgo")),
    ("data_sensitivity", _labels("Чувствительность данных", "Data sensitivity", "Sensibilidad de datos")),
    ("human_control", _labels("Контроль человека", "Human control", "Control humano")),
)


RUBRIC_ENTRIES: tuple[tuple[str, str, str | None, dict[str, str], tuple[str, ...]], ...] = (
    ("process_level", "process_map", None, _labels("Карта процессов", "Process map", "Mapa de procesos"), ()),
    ("process_level", "process", "process_map", _labels("Процесс", "Process", "Proceso"), ()),
    ("process_level", "subprocess", "process", _labels("Подпроцесс", "Subprocess", "Subproceso"), ()),
    ("process_level", "scenario", "subprocess", _labels("Сценарий", "Scenario", "Escenario"), ()),
    ("process_level", "operation", "scenario", _labels("Операция", "Operation", "Operacion"), ()),
    ("process_level", "action", "operation", _labels("Действие", "Action", "Accion"), ()),
    ("business_role", "core", None, _labels("Основной", "Core", "Principal"), ()),
    ("business_role", "supporting", None, _labels("Обеспечивающий", "Supporting", "Soporte"), ()),
    ("business_role", "management", None, _labels("Управленческий", "Management", "Gestion"), ()),
    ("customer_impact", "customer_facing", None, _labels("Клиентский", "Customer-facing", "De cara al cliente"), ()),
    ("customer_impact", "internal", None, _labels("Внутренний", "Internal", "Interno"), ()),
    ("organizational_span", "local", None, _labels("Локальный", "Local", "Local"), ()),
    ("organizational_span", "cross_functional", None, _labels("Сквозной", "Cross-functional", "Transversal"), ()),
    ("automation_mode", "rule", None, _labels("Правило", "Rule", "Regla"), ()),
    ("automation_mode", "integration", None, _labels("Интеграция", "Integration", "Integracion"), ()),
    ("automation_mode", "rpa", None, _labels("RPA", "RPA", "RPA"), ()),
    ("automation_mode", "ai_function", None, _labels("AI-функция", "AI function", "Funcion de IA"), ()),
    ("automation_mode", "ai_assistant", None, _labels("AI-ассистент", "AI assistant", "Asistente de IA"), ()),
    ("automation_mode", "ai_agent", None, _labels("AI-агент", "AI agent", "Agente de IA"), ()),
    ("automation_mode", "workflow", None, _labels("Workflow", "Workflow", "Workflow"), ()),
    ("risk", "low", None, _labels("Низкий", "Low", "Bajo"), ()),
    ("risk", "medium", None, _labels("Средний", "Medium", "Medio"), ()),
    ("risk", "high", None, _labels("Высокий", "High", "Alto"), ()),
    ("risk", "critical", None, _labels("Критический", "Critical", "Critico"), ()),
    ("data_sensitivity", "public", None, _labels("Публичные", "Public", "Publicos"), ()),
    ("data_sensitivity", "internal", None, _labels("Внутренние", "Internal", "Internos"), ()),
    ("data_sensitivity", "confidential", None, _labels("Конфиденциальные", "Confidential", "Confidenciales"), ()),
    ("data_sensitivity", "restricted", None, _labels("Ограниченного доступа", "Restricted", "Restringidos"), ()),
    ("human_control", "manual", None, _labels("Полностью вручную", "Manual", "Manual"), ()),
    ("human_control", "review", None, _labels("Проверка результата", "Result review", "Revision del resultado"), ()),
    ("human_control", "approval", None, _labels("Обязательное подтверждение", "Mandatory approval", "Aprobacion obligatoria"), ()),
    ("human_control", "exception_only", None, _labels("Только исключения", "Exceptions only", "Solo excepciones"), ()),
)


DOMAIN_LABELS = {
    "sales": _labels("Продажи", "Sales", "Ventas"),
    "service": _labels("Клиентский сервис", "Customer service", "Atencion al cliente"),
    "finance": _labels("Финансы", "Finance", "Finanzas"),
    "procurement": _labels("Закупки и склад", "Procurement and inventory", "Compras e inventario"),
    "hr": _labels("Сотрудники", "People", "Personas"),
    "operations": _labels("Операции", "Operations", "Operaciones"),
    "marketing": _labels("Маркетинг", "Marketing", "Marketing"),
    "analytics_compliance": _labels("Аналитика, риски и комплаенс", "Analytics, risk and compliance", "Analitica, riesgo y cumplimiento"),
    "autonomous_agents": _labels("Автономные агенты", "Autonomous agents", "Agentes autonomos"),
    "cross_functional": _labels("Сквозные процессы", "Cross-functional", "Procesos transversales"),
    "ecommerce_inventory": _labels("E-commerce и запасы", "E-commerce and inventory", "Comercio electronico e inventario"),
    "finance_procurement": _labels("Финансы и закупки", "Finance and procurement", "Finanzas y compras"),
    "hr_people": _labels("Сотрудники и HR", "HR and people", "Personas y RR. HH."),
    "it_devops_security": _labels("IT, DevOps и безопасность", "IT, DevOps and security", "TI, DevOps y seguridad"),
    "marketing_content": _labels("Маркетинг и контент", "Marketing and content", "Marketing y contenido"),
    "operations_documents": _labels("Операции и документы", "Operations and documents", "Operaciones y documentos"),
    "sales_crm": _labels("Продажи и CRM", "Sales and CRM", "Ventas y CRM"),
    "support_cx": _labels("Поддержка и клиентский опыт", "Support and customer experience", "Soporte y experiencia del cliente"),
}


def entry_id(dimension: str, code: str) -> str:
    return f"{CURRENT_RUBRIC_VERSION}:{dimension}:{code}"


def localized_entry_names(entry_ids: list[str], locale: str) -> list[str]:
    """Return localized rubric labels without requiring a database session."""
    language = normalize_locale(locale)
    labels_by_id = {
        entry_id(dimension, code): labels[language]
        for dimension, code, _, labels, _ in RUBRIC_ENTRIES
    }
    labels_by_id.update({entry_id("domain", code): labels[language] for code, labels in DOMAIN_LABELS.items()})
    return [labels_by_id[identifier] for identifier in entry_ids if identifier in labels_by_id]


def seed_rubric(db: Session) -> None:
    version = db.get(RubricVersion, CURRENT_RUBRIC_VERSION)
    if version is None:
        db.add(RubricVersion(id=CURRENT_RUBRIC_VERSION, status="active"))
        db.flush()
    entries = list(RUBRIC_ENTRIES) + [
        ("domain", code, None, labels, ()) for code, labels in DOMAIN_LABELS.items()
    ]
    for order, (dimension, code, parent_code, labels, synonyms) in enumerate(entries):
        identifier = entry_id(dimension, code)
        entry = db.get(RubricEntry, identifier)
        if entry is None:
            entry = RubricEntry(
                id=identifier,
                version_id=CURRENT_RUBRIC_VERSION,
                dimension=dimension,
                code=code,
                parent_id=entry_id(dimension, parent_code) if parent_code else None,
                sort_order=order,
                deprecated=False,
            )
            db.add(entry)
            db.flush()
        for locale, name in labels.items():
            translation = db.scalar(select(RubricEntryTranslation).where(
                RubricEntryTranslation.entry_id == identifier,
                RubricEntryTranslation.locale == locale,
            ))
            if translation is None:
                db.add(RubricEntryTranslation(
                    entry_id=identifier,
                    locale=locale,
                    name=name,
                    description="",
                    synonyms=list(synonyms),
                ))
    db.commit()


def get_rubric(db: Session, locale: str, version_id: str = CURRENT_RUBRIC_VERSION) -> dict[str, Any] | None:
    version = db.get(RubricVersion, version_id)
    if version is None:
        return None
    language = normalize_locale(locale)
    rows = db.execute(
        select(RubricEntry, RubricEntryTranslation)
        .join(RubricEntryTranslation, RubricEntryTranslation.entry_id == RubricEntry.id)
        .where(RubricEntry.version_id == version_id, RubricEntryTranslation.locale == language)
        .order_by(RubricEntry.sort_order)
    ).all()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    dimension_labels = dict(RUBRIC_DIMENSIONS)
    for entry, translation in rows:
        grouped[entry.dimension].append({
            "id": entry.id,
            "code": entry.code,
            "parent_id": entry.parent_id,
            "name": translation.name,
            "description": translation.description,
            "synonyms": translation.synonyms,
            "deprecated": entry.deprecated,
        })
    return {
        "version": version.id,
        "status": version.status,
        "dimensions": [
            {"id": dimension, "name": labels[language], "entries": grouped.get(dimension, [])}
            for dimension, labels in RUBRIC_DIMENSIONS
        ],
    }


def validate_entry_ids(db: Session, version_id: str, selected_ids: list[str]) -> None:
    known = set(db.scalars(
        select(RubricEntry.id).where(
            RubricEntry.version_id == version_id,
            RubricEntry.id.in_(selected_ids),
            RubricEntry.deprecated.is_(False),
        )
    ))
    unknown = sorted(set(selected_ids) - known)
    if unknown:
        raise ValueError(f"Unknown rubric entries: {', '.join(unknown)}")
    dimensions = list(db.scalars(select(RubricEntry.dimension).where(RubricEntry.id.in_(selected_ids))))
    if len(dimensions) != len(set(dimensions)):
        raise ValueError("Select at most one rubric entry per dimension.")
