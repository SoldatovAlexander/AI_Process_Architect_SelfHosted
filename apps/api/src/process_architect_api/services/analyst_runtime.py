from dataclasses import dataclass
from difflib import SequenceMatcher
import json
import re

import httpx
from sqlalchemy.orm import Session

from ..analyst.prompts import ANALYST_PATCH_PROMPT_VERSION, analyst_patch_prompt
from ..config import Settings
from ..db_models import AnalystMessage, ProposedPatch, User
from ..deepseek import DeepSeekAnalystTurn, DeepSeekClient, DeepSeekResponseError
from ..localization import normalize_locale
from ..repositories.analyst import list_session_messages
from ..readiness import calculate_readiness
from ..process_ir import upgrade_process_ir
from .analyst import (
    add_assistant_message,
    add_user_message,
    create_proposed_patch,
    require_session_access,
)
from .llm_credentials import resolve_user_llm_connection
from .llm_usage import begin_llm_usage, finish_llm_usage
from .projects import (
    InvalidProcessPatch,
    preview_process_patch,
    require_project_access,
    require_project_revision,
)


class AnalystGeneratedPatchError(RuntimeError):
    pass


@dataclass
class AnalystTurnResult:
    user_message: AnalystMessage
    assistant_message: AnalystMessage
    proposed_patch: ProposedPatch | None


NEXT_STEP_MESSAGES = {
    "ru": {
        "unknown_integrations": "Перейдём к автоматизации CRM. Какие действия она должна выполнять сама: создавать тикет, классифицировать его, назначать исполнителя или отправлять уведомления?",
        "automation_hints_missing": "Какие шаги нужно автоматизировать в первую очередь: создание тикета, классификацию, назначение исполнителя или контроль ответа клиента?",
        "complete": "Основное описание процесса собрано. Следующий шаг — проверить схему и подготовить экспорт.",
        "diagram_ready": "Схема подтверждена. Предлагаю отметить её готовой и перейти к подготовке экспорта.",
        "diagram_ready_summary": "Подтвердить готовность схемы",
        "diagram_ready_reconciled": "Схема подтверждена. Ответ уже отражён в шаге процесса; предлагаю закрыть устаревший вопрос и отметить схему готовой.",
        "diagram_ready_reconciled_summary": "Закрыть решённый вопрос и подтвердить схему",
        "export_ready": "Схема подтверждена и готова. Можно переходить к экспорту.",
        "facts_already_applied": "Это изменение уже отражено в схеме. Новая версия не создана, потому что она ничего бы не изменила.",
        "facts_not_applied": "Ответы сохранены в интервью, но перенести их в схему пока не удалось. Схема ещё не готова к экспорту; повторная отправка не требуется.",
    },
    "en": {
        "unknown_integrations": "Let us move to CRM automation. Which actions should it perform automatically: create the ticket, classify it, assign an owner, or send notifications?",
        "automation_hints_missing": "Which steps should be automated first: ticket creation, classification, assignment, or checking the customer response?",
        "complete": "The main process description is complete. The next step is to review the diagram and prepare the export.",
        "diagram_ready": "The diagram is confirmed. I propose marking it ready and moving to export preparation.",
        "diagram_ready_summary": "Confirm diagram readiness",
        "diagram_ready_reconciled": "The diagram is confirmed. The answer is already reflected in the process step; I propose closing the stale question and marking the diagram ready.",
        "diagram_ready_reconciled_summary": "Close resolved question and confirm diagram",
        "export_ready": "The diagram is confirmed and ready. You can proceed to export.",
        "facts_already_applied": "This change is already reflected in the diagram. No new version was created because it would not change anything.",
        "facts_not_applied": "The answers are saved in the interview, but they could not be applied to the diagram yet. The diagram is not ready for export; you do not need to send them again.",
    },
    "es": {
        "unknown_integrations": "Pasemos a la automatización del CRM. ¿Qué acciones debe realizar por sí solo: crear el ticket, clasificarlo, asignar al responsable o enviar avisos?",
        "automation_hints_missing": "¿Qué pasos deben automatizarse primero: creación, clasificación, asignación o control de la respuesta del cliente?",
        "complete": "La descripción principal del proceso está completa. El siguiente paso es revisar el diagrama y preparar la exportación.",
        "diagram_ready": "El diagrama está confirmado. Propongo marcarlo como listo y preparar la exportación.",
        "diagram_ready_summary": "Confirmar que el diagrama está listo",
        "diagram_ready_reconciled": "El diagrama está confirmado. La respuesta ya está reflejada en el paso; propongo cerrar la pregunta obsoleta y marcar el diagrama como listo.",
        "diagram_ready_reconciled_summary": "Cerrar la pregunta resuelta y confirmar el diagrama",
        "export_ready": "El diagrama está confirmado y listo. Puede continuar con la exportación.",
        "facts_already_applied": "Este cambio ya está reflejado en el diagrama. No se creó una nueva versión porque no cambiaría nada.",
        "facts_not_applied": "Las respuestas están guardadas en la entrevista, pero todavía no se pudieron aplicar al diagrama. El diagrama no está listo para exportar; no hace falta enviarlas de nuevo.",
    },
}


def _normalize_message(content: str) -> str:
    return re.sub(r"\W+", " ", content.casefold()).strip()


def _preview_analyst_patch(
    process_ir: dict,
    patch: list[dict],
) -> tuple[dict, list[dict], dict]:
    next_process_ir, normalized_patch, validation = preview_process_patch(process_ir, patch)
    existing_actor_ids = {
        actor.get("id") for actor in process_ir.get("actors", []) if isinstance(actor, dict)
    }
    new_actors = [
        actor
        for actor in next_process_ir.get("actors", [])
        if isinstance(actor, dict) and actor.get("id") not in existing_actor_ids
    ]
    referenced_actor_ids = {
        step.get("actorId")
        for step in next_process_ir.get("steps", [])
        if isinstance(step, dict) and step.get("actorId")
    }
    owner_actor_id = next_process_ir.get("passport", {}).get("ownerActorId")
    if owner_actor_id:
        referenced_actor_ids.add(owner_actor_id)
    unused = [actor.get("name") or actor.get("id") for actor in new_actors if actor.get("id") not in referenced_actor_ids]
    if unused:
        raise InvalidProcessPatch(
            "New process participants must be assigned to relevant work or process ownership: "
            + ", ".join(str(item) for item in unused)
        )
    return next_process_ir, normalized_patch, validation


def _question_fragments(content: str) -> list[str]:
    return [
        normalized
        for match in re.finditer(r"[^.!?\n]*[?？]", content)
        if (normalized := _normalize_message(match.group()))
    ]


def _questions_match(first: str, second: str) -> bool:
    if first == second or SequenceMatcher(None, first, second).ratio() >= 0.82:
        return True
    first_tokens = set(first.split())
    second_tokens = set(second.split())
    shared = first_tokens & second_tokens
    return len(shared) >= 5 and len(shared) / min(
        len(first_tokens), len(second_tokens)
    ) >= 0.8


def _message_matches(content: str, previous_content: str) -> bool:
    normalized = _normalize_message(content)
    previous = _normalize_message(previous_content)
    if previous == normalized or SequenceMatcher(None, previous, normalized).ratio() >= 0.9:
        return True
    questions = _question_fragments(content)
    previous_questions = _question_fragments(previous_content)
    return any(
        _questions_match(question, previous_question)
        for question in questions
        for previous_question in previous_questions
    )


def _confirms_diagram(content: str, locale: str) -> bool:
    normalized = _normalize_message(content)
    language = normalize_locale(locale).split("-", 1)[0]
    patterns = {
        "ru": (
            r"\bсхем\w*\b.*\b(?:правильн\w*|верн\w*|корректн\w*|подтвержда\w*|утвержда\w*)\b",
            r"\b(?:подтвержда\w*|утвержда\w*)\b.*\bсхем\w*\b",
        ),
        "en": (
            r"\bdiagram\b.*\b(?:correct|right|approved|confirmed|ready)\b",
            r"\b(?:approve|confirm)\w*\b.*\bdiagram\b",
        ),
        "es": (
            r"\bdiagrama\b.*\b(?:correcto|correcta|aprobado|aprobada|confirmado|confirmada|listo|lista)\b",
            r"\b(?:apruebo|confirmo)\b.*\bdiagrama\b",
        ),
    }
    return any(re.search(pattern, normalized) for pattern in patterns.get(language, ()))


def _claims_process_ready(content: str, locale: str) -> bool:
    normalized = _normalize_message(content)
    negated = (
        r"\bне\b.{0,20}\bготов\w*\b",
        r"\bnot\b.{0,20}\bready\b",
        r"\bno\b.{0,20}\blist[oa]\b",
        r"\bне удалось\b",
        r"\bcould not\b",
        r"\bno se pudieron\b",
    )
    if any(re.search(pattern, normalized) for pattern in negated):
        return False
    patterns = {
        "ru": (
            r"\b(?:схем|процесс|описани|интервью)\w*\b.*\b(?:готов|подтвержд|заверш|собран)\w*\b",
            r"\b(?:готов|переход)\w*\b.*\bэкспорт\w*\b",
            r"\b(?:изменени|уточнени)\w*\b.*\bне\b.*\bтребу\w*\b",
        ),
        "en": (
            r"\b(?:diagram|process|description|interview)\b.*\b(?:ready|confirmed|complete|completed)\b",
            r"\bready\b.*\bexport\b",
            r"\bno\b.*\b(?:additional|further)?\s*changes?\b.*\b(?:needed|required)\b",
        ),
        "es": (
            r"\b(?:diagrama|proceso|descripción|entrevista)\b.*\b(?:listo|lista|confirmado|confirmada|completo|completa)\b",
            r"\blist[oa]\b.*\bexport",
            r"\bno\b.*\b(?:se\s+)?(?:necesitan|requieren)\b.*\bcambios\b",
        ),
    }
    preferred_language = normalize_locale(locale).split("-", 1)[0]
    ordered_languages = [preferred_language, *(item for item in patterns if item != preferred_language)]
    return any(
        re.search(pattern, normalized)
        for language in ordered_languages
        for pattern in patterns.get(language, ())
    )


def _capture_confirmed_facts(
    locale: str,
    process_ir: dict,
    conversation: list[dict[str, str]],
) -> DeepSeekAnalystTurn | None:
    commands = {"continue", "продолжай", "продолжить", "continua", "continuar"}
    facts = []
    for message in conversation:
        if message["role"] != "user":
            continue
        content = message["content"].strip()
        if _normalize_message(content) in commands or len(content) < 20:
            continue
        if content not in facts:
            facts.append(content)
    if not facts:
        return None

    language = normalize_locale(locale).split("-", 1)[0]
    labels = {
        "ru": ("Подтверждённые детали интервью", "Сохранить подтверждённые детали интервью", "Ответы собраны. Предлагаю сохранить подтверждённые детали в схеме; структурирование отдельных шагов продолжим после принятия изменения."),
        "en": ("Confirmed interview details", "Save confirmed interview details", "The answers are collected. I propose saving the confirmed details in the diagram; individual steps can be structured after this change is accepted."),
        "es": ("Detalles confirmados de la entrevista", "Guardar detalles confirmados de la entrevista", "Las respuestas están recopiladas. Propongo guardar los detalles confirmados en el diagrama; estructuraremos los pasos después de aceptar el cambio."),
    }
    heading, summary, message = labels.get(language, labels["en"])
    current = process_ir.get("process", {}).get("description", "").strip()
    missing = [fact for fact in facts if _normalize_message(fact) not in _normalize_message(current)]
    if not missing:
        return None
    captured = f"{heading}:\n" + "\n".join(f"- {fact}" for fact in missing)
    description = f"{current}\n\n{captured}".strip()
    return DeepSeekAnalystTurn(
        message=message,
        summary=summary,
        patch=[{"op": "replace", "path": "/process/description", "value": description}],
    )


def _repeats_recent_message(
    content: str,
    conversation: list[dict[str, str]],
) -> bool:
    if not _normalize_message(content):
        return False
    for message in conversation:
        if message["role"] != "assistant":
            continue
        if _message_matches(content, message["content"]):
            return True
    return False


def _answers_after_repeated_message(
    content: str,
    conversation: list[dict[str, str]],
) -> list[str]:
    for index, message in enumerate(conversation):
        if message["role"] != "assistant":
            continue
        if _message_matches(content, message["content"]):
            return [
                item["content"]
                for item in conversation[index + 1 :]
                if item["role"] == "user"
            ]
    return []


def _next_step_fallback(
    locale: str,
    *,
    patch_created: bool,
    readiness_context: dict,
    conversation: list[dict[str, str]],
) -> str:
    language = normalize_locale(locale).split("-", 1)[0]
    if patch_created:
        messages = {
            "ru": "Ответ учтён. Предлагаю применить подготовленное изменение процесса.",
            "en": "The answer is recorded. I propose applying the prepared process change.",
            "es": "La respuesta está registrada. Propongo aplicar el cambio preparado al proceso.",
        }
        return messages.get(language, messages["en"])

    localized = NEXT_STEP_MESSAGES.get(language, NEXT_STEP_MESSAGES["en"])
    reason_codes = [
        reason
        for category in readiness_context.get("categories", {}).values()
        for reason in category.get("reason_codes", [])
    ]
    previous_assistant = {
        _normalize_message(message["content"])
        for message in conversation
        if message["role"] == "assistant"
    }
    for reason in [*reason_codes, "complete"]:
        candidate = localized.get(reason)
        if candidate and _normalize_message(candidate) not in previous_assistant:
            return candidate
    return localized["complete"]


def _readiness_fallback_turn(
    locale: str,
    *,
    process_ir: dict,
    readiness_context: dict,
    conversation: list[dict[str, str]],
) -> DeepSeekAnalystTurn:
    message = _next_step_fallback(
        locale,
        patch_created=False,
        readiness_context=readiness_context,
        conversation=conversation,
    )
    language = normalize_locale(locale).split("-", 1)[0]
    localized = NEXT_STEP_MESSAGES.get(language, NEXT_STEP_MESSAGES["en"])
    if process_ir.get("process", {}).get("maturity") == "diagram_ready":
        return DeepSeekAnalystTurn(message=localized["export_ready"], summary="", patch=[])
    steps_by_id = {step.get("id"): step for step in process_ir.get("steps", [])}
    blocking_indexes = [
        index
        for index, question in enumerate(process_ir.get("openQuestions", []))
        if question.get("blocksAutomationReady")
    ]
    resolved_indexes = []
    for index in blocking_indexes:
        question = process_ir["openQuestions"][index]
        target = question.get("target", {})
        step = steps_by_id.get(target.get("id")) if target.get("entity") == "step" else None
        if (
            step
            and step.get("type") == "system_task"
            and not step.get("missingFields")
            and step.get("description", "").strip()
            and step.get("automationHint")
        ):
            resolved_indexes.append(index)
    unresolved_blocking_count = len(blocking_indexes) - len(resolved_indexes)
    if (
        message == localized["complete"]
        and unresolved_blocking_count == 0
        and process_ir.get("process", {}).get("maturity") == "draft"
    ):
        patch = [
            {"op": "remove", "path": f"/openQuestions/{index}"}
            for index in reversed(resolved_indexes)
        ]
        patch.append(
            {
                "op": "replace",
                "path": "/process/maturity",
                "value": "diagram_ready",
            }
        )
        return DeepSeekAnalystTurn(
            message=localized["diagram_ready_reconciled"] if resolved_indexes else localized["diagram_ready"],
            summary=localized["diagram_ready_reconciled_summary"] if resolved_indexes else localized["diagram_ready_summary"],
            patch=patch,
        )
    return DeepSeekAnalystTurn(message=message, summary="", patch=[])


async def run_analyst_turn(
    db: Session,
    *,
    user: User,
    session_id: str,
    content: str,
    settings: Settings,
) -> AnalystTurnResult:
    session = require_session_access(db, session_id, user.id)
    project = require_project_access(db, session.project_id, user.id)
    existing_messages = list_session_messages(db, session.id)
    latest_message = existing_messages[-1] if existing_messages else None
    if (
        latest_message is not None
        and latest_message.role == "user"
        and latest_message.content == content.strip()
        and latest_message.revision_id == project.current_revision_id
    ):
        user_message = latest_message
    else:
        user_message = add_user_message(
            db,
            user=user,
            session_id=session_id,
            content=content,
        )
    base_revision = require_project_revision(db, project, user_message.revision_id)
    history = list_session_messages(db, session.id)[-20:]
    conversation = [
        {"role": message.role, "content": message.content}
        for message in history
    ]
    process_ir = upgrade_process_ir(base_revision.process_ir)
    readiness_context = calculate_readiness(
        process_ir,
        base_revision.id,
    ).model_dump(mode="json")
    prompt = analyst_patch_prompt(
        process_ir=process_ir,
        locale=session.locale,
        mode=session.mode,
        conversation=conversation,
        readiness_context=readiness_context,
        target_mode=project.target_mode,
    )
    deterministic_confirmation = (
        process_ir.get("process", {}).get("maturity") == "diagram_ready"
        and _confirms_diagram(content, session.locale)
    )
    usage_meter = None
    if not deterministic_confirmation:
        usage_meter = begin_llm_usage(
            db,
            workspace_id=project.workspace_id,
            settings=settings,
            operation="analyst_turn",
            idempotency_key=f"analyst:{user_message.id}",
        )
    async with httpx.AsyncClient(timeout=settings.deepseek_timeout_seconds) as http_client:
        connection = resolve_user_llm_connection(db, user, settings)
        client = DeepSeekClient(settings, http_client, connection)
        if deterministic_confirmation:
            generated = _readiness_fallback_turn(
                session.locale,
                process_ir=process_ir,
                readiness_context=readiness_context,
                conversation=conversation,
            )
        else:
            try:
                generated = await client.propose_process_patch(prompt)
            except DeepSeekResponseError:
                generated = _readiness_fallback_turn(
                    session.locale,
                    process_ir=process_ir,
                    readiness_context=readiness_context,
                    conversation=conversation,
                )
        if (
            not deterministic_confirmation
            and not generated.patch
            and _claims_process_ready(generated.message, session.locale)
        ):
            completion_output = json.dumps(
                {
                    "message": generated.message,
                    "summary": generated.summary,
                    "patch": generated.patch,
                },
                ensure_ascii=False,
            )
            correction_prompt = [
                *prompt,
                {"role": "assistant", "content": completion_output},
                {
                    "role": "user",
                    "content": (
                        "This draft claims that the process or diagram is ready but returns an empty "
                        "patch. The user's confirmed facts are still only in the conversation. Compare "
                        "all user answers attached to the Current Process IR revision with the Current "
                        "Process IR and return a valid RFC 6902 patch that applies every useful missing "
                        "fact. Do not claim readiness. If no safe patch can be produced, return an empty "
                        "patch and explicitly say that the answers are saved but the diagram has not "
                        "been updated and is not ready for export. Return the same output contract."
                    ),
                },
            ]
            generated = await client.propose_process_patch(correction_prompt)
            if not generated.patch and _claims_process_ready(generated.message, session.locale):
                language = normalize_locale(session.locale).split("-", 1)[0]
                localized = NEXT_STEP_MESSAGES.get(language, NEXT_STEP_MESSAGES["en"])
                generated = DeepSeekAnalystTurn(
                    message=localized["facts_not_applied"],
                    summary="",
                    patch=[],
                )
        if not deterministic_confirmation and _repeats_recent_message(
            generated.message, conversation
        ):
            relevant_answers = _answers_after_repeated_message(
                generated.message,
                conversation,
            )
            repeated_output = json.dumps(
                {
                    "message": generated.message,
                    "summary": generated.summary,
                    "patch": generated.patch,
                },
                ensure_ascii=False,
            )
            correction_prompt = [
                *prompt,
                {"role": "assistant", "content": repeated_output},
                {
                    "role": "user",
                    "content": (
                        "This draft repeats an analyst response already shown to the user. Re-read the "
                        "user responses that followed its first occurrence and the Current Process IR. "
                        f"Those responses are: {json.dumps(relevant_answers, ensure_ascii=False)}. Apply "
                        "their supplied business facts with a JSON Patch, including resolving matching "
                        "open questions and missing fields. Do not ask the same or an equivalent "
                        "question. If one detail is still missing, acknowledge what is known and ask "
                        "only for that unresolved detail in more specific wording. Return the same "
                        "output contract."
                    ),
                },
            ]
            generated = await client.propose_process_patch(correction_prompt)
            if _repeats_recent_message(generated.message, conversation):
                if generated.patch:
                    generated = DeepSeekAnalystTurn(
                        message=_next_step_fallback(
                            session.locale,
                            patch_created=True,
                            readiness_context=readiness_context,
                            conversation=conversation,
                        ),
                        summary=generated.summary,
                        patch=generated.patch,
                    )
                else:
                    generated = _readiness_fallback_turn(
                        session.locale,
                        process_ir=process_ir,
                        readiness_context=readiness_context,
                        conversation=conversation,
                    )
        if (
            not deterministic_confirmation
            and not generated.patch
            and _claims_process_ready(generated.message, session.locale)
        ):
            captured = _capture_confirmed_facts(session.locale, process_ir, conversation)
            if captured is not None:
                generated = captured
        if generated.patch:
            try:
                _preview_analyst_patch(base_revision.process_ir, generated.patch)
            except InvalidProcessPatch as error:
                rejected_output = json.dumps(
                    {
                        "message": generated.message,
                        "summary": generated.summary,
                        "patch": generated.patch,
                    },
                    ensure_ascii=False,
                )
                repair_prompt = [
                    *prompt,
                    {"role": "assistant", "content": rejected_output},
                    {
                        "role": "user",
                        "content": (
                            "The proposed JSON Patch was rejected. Correct the patch against the "
                            "original Current Process IR and return the same output contract. Do not "
                            "repeat invalid operations and do not add unsupported fields. If a safe "
                            f"correction is impossible, return an empty patch. Validation error: {error}"
                        ),
                    },
                ]
                generated = await client.propose_process_patch(repair_prompt)
                if generated.patch:
                    try:
                        _preview_analyst_patch(base_revision.process_ir, generated.patch)
                    except InvalidProcessPatch as repair_error:
                        language = normalize_locale(session.locale).split("-", 1)[0]
                        localized = NEXT_STEP_MESSAGES.get(language, NEXT_STEP_MESSAGES["en"])
                        key = (
                            "facts_already_applied"
                            if "does not modify Process IR" in str(repair_error)
                            else "facts_not_applied"
                        )
                        generated = DeepSeekAnalystTurn(
                            message=localized[key], summary="", patch=[]
                        )
                elif _claims_process_ready(generated.message, session.locale):
                    captured = _capture_confirmed_facts(session.locale, process_ir, conversation)
                    if captured is not None:
                        generated = captured
                else:
                    language = normalize_locale(session.locale).split("-", 1)[0]
                    localized = NEXT_STEP_MESSAGES.get(language, NEXT_STEP_MESSAGES["en"])
                    generated = DeepSeekAnalystTurn(
                        message=localized["facts_not_applied"], summary="", patch=[]
                    )

    if usage_meter is not None:
        finish_llm_usage(
            db,
            meter=usage_meter,
            provider=connection.provider,
            model=connection.model,
            observations=client.usage_observations,
            settings=settings,
        )

    assistant_message = add_assistant_message(
        db,
        user=user,
        session_id=session.id,
        revision_id=base_revision.id,
        content=generated.message,
        provider=connection.provider,
        model=connection.model,
        prompt_version=ANALYST_PATCH_PROMPT_VERSION,
        commit=not generated.patch,
    )
    proposal = None
    if generated.patch:
        try:
            proposal = create_proposed_patch(
                db,
                user=user,
                session_id=session.id,
                base_revision_id=base_revision.id,
                patch=generated.patch,
                summary=generated.summary or generated.message,
                source_message_id=assistant_message.id,
                allow_stale=True,
                commit=True,
            )
        except InvalidProcessPatch as error:
            db.rollback()
            raise AnalystGeneratedPatchError(str(error)) from error
    return AnalystTurnResult(
        user_message=user_message,
        assistant_message=assistant_message,
        proposed_patch=proposal,
    )
