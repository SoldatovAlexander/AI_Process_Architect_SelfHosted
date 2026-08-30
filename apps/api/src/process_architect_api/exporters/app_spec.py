from typing import Any

from ..localization import normalize_locale
from ..models import ValidationResult
from ..process_ir import upgrade_process_ir


SUPPORTED_APP_TARGETS = ("cursor", "codex", "google_ai_studio", "bolt", "generic")

TARGETS = {
    "cursor": {
        "name": "Cursor",
        "docs": "https://docs.cursor.com/context/rules-for-ai",
        "ru": [
            "Откройте пустой репозиторий или существующий проект в Cursor и добавьте этот файл в корень как `SPEC.md`.",
            "Попросите Agent сначала изучить ТЗ и создать поэтапный план, не меняя код.",
            "После согласования плана поручайте реализацию по одному этапу с запуском тестов после каждого этапа.",
            "Постоянные правила проекта храните в `.cursor/rules` или корневом `AGENTS.md`.",
        ],
        "en": [
            "Open an empty repository or existing project in Cursor and add this file as root-level `SPEC.md`.",
            "Ask Agent to read the specification and create an implementation plan without changing code.",
            "Approve the plan, then implement one stage at a time and run tests after each stage.",
            "Keep persistent project rules in `.cursor/rules` or root-level `AGENTS.md`.",
        ],
        "es": [
            "Abra un repositorio vacío o un proyecto existente en Cursor y añada este archivo como `SPEC.md` en la raíz.",
            "Pida al Agent que estudie la especificación y prepare un plan sin modificar código.",
            "Apruebe el plan e implemente una etapa cada vez, ejecutando pruebas después de cada etapa.",
            "Guarde las reglas permanentes en `.cursor/rules` o en `AGENTS.md` en la raíz.",
        ],
    },
    "codex": {
        "name": "Codex / ChatGPT",
        "docs": "https://help.openai.com/en/articles/10169521-projects-in-chatgpt",
        "ru": [
            "Для Codex поместите файл в репозиторий как `SPEC.md`, откройте рабочую папку и попросите сначала проверить ТЗ и составить план.",
            "Добавьте в корневой `AGENTS.md` команды запуска, тестирования и ограничения архитектуры.",
            "Для ChatGPT добавьте файл в источники проекта и закрепите в инструкциях проекта требование считать его источником истины.",
            "Реализуйте этапы последовательно; после каждого этапа требуйте тесты, краткий отчёт и список оставшихся рисков.",
        ],
        "en": [
            "For Codex, place this file in the repository as `SPEC.md`, open the workspace, and ask for a review and plan first.",
            "Put build commands, test commands, and architecture constraints in root-level `AGENTS.md`.",
            "For ChatGPT, add the file to Project sources and state in Project instructions that it is the source of truth.",
            "Implement in stages; require tests, a short report, and remaining risks after each stage.",
        ],
        "es": [
            "Para Codex, guarde este archivo como `SPEC.md`, abra el workspace y solicite primero una revisión y un plan.",
            "Incluya comandos de ejecución, pruebas y restricciones en `AGENTS.md` en la raíz.",
            "Para ChatGPT, añada el archivo a las fuentes del Proyecto e indique que es la fuente de verdad.",
            "Implemente por etapas; exija pruebas, un informe breve y los riesgos restantes tras cada etapa.",
        ],
    },
    "google_ai_studio": {
        "name": "Google AI Studio",
        "docs": "https://ai.google.dev/gemini-api/docs/aistudio-build-mode",
        "ru": [
            "Откройте Build mode, выберите Web App и вставьте раздел «Начальный промпт» вместе с этим ТЗ.",
            "Для веб-приложения учитывайте среду React на клиенте и Node.js на сервере.",
            "API-ключи добавляйте только через Secrets в Settings; не помещайте их в клиентский код.",
            "Проверяйте результат в Preview, затем экспортируйте в GitHub/ZIP или публикуйте в Cloud Run.",
        ],
        "en": [
            "Open Build mode, select Web App, and submit the Initial prompt together with this specification.",
            "For a web app, account for the React client and Node.js server runtime.",
            "Add API keys only through Settings > Secrets; never put them in client code.",
            "Verify the app in Preview, then export to GitHub/ZIP or publish to Cloud Run.",
        ],
        "es": [
            "Abra Build mode, seleccione Web App y envíe el Prompt inicial junto con esta especificación.",
            "Para una app web, tenga en cuenta el cliente React y el runtime Node.js del servidor.",
            "Añada claves solo mediante Settings > Secrets; nunca en el código del cliente.",
            "Verifique en Preview y después exporte a GitHub/ZIP o publique en Cloud Run.",
        ],
    },
    "bolt": {
        "name": "Bolt.new",
        "docs": "https://support.bolt.new/best-practices/prompting-effectively",
        "ru": [
            "Вставьте раздел «Начальный промпт» первым сообщением, затем приложите остальную часть ТЗ.",
            "Сначала создайте каркас приложения, модель данных и авторизацию; интеграции подключайте отдельными этапами.",
            "После каждого этапа проверяйте Preview и исправляйте ошибки до перехода к следующему этапу.",
            "Секреты храните в настройках проекта Bolt, а не в исходном коде или сообщениях.",
        ],
        "en": [
            "Use the Initial prompt as the first message, then provide the rest of this specification.",
            "Build the application shell, data model, and authentication first; add integrations in separate stages.",
            "Verify Preview and fix errors after each stage before moving on.",
            "Store secrets in Bolt project settings, never in source code or prompts.",
        ],
        "es": [
            "Use el Prompt inicial como primer mensaje y después proporcione el resto de la especificación.",
            "Cree primero la base, el modelo de datos y la autenticación; añada integraciones por etapas.",
            "Revise Preview y corrija errores después de cada etapa.",
            "Guarde secretos en la configuración de Bolt, nunca en código o prompts.",
        ],
    },
    "generic": {
        "name": "Universal AI Builder",
        "docs": "",
        "ru": [
            "Добавьте этот файл в контекст AI-среды как основной источник требований.",
            "Сначала запросите план архитектуры, структуры данных и этапов реализации.",
            "Согласуйте план и реализуйте приложение небольшими проверяемыми этапами.",
            "Не передавайте модели реальные секреты; используйте переменные окружения и `.env.example`.",
        ],
        "en": [
            "Add this file to the AI builder context as the primary source of requirements.",
            "Request an architecture, data model, and staged implementation plan first.",
            "Approve the plan and implement in small, verifiable stages.",
            "Do not provide real secrets; use environment variables and `.env.example`.",
        ],
        "es": [
            "Añada este archivo al contexto como fuente principal de requisitos.",
            "Solicite primero un plan de arquitectura, datos y etapas de implementación.",
            "Apruebe el plan e implemente en etapas pequeñas y verificables.",
            "No proporcione secretos reales; use variables de entorno y `.env.example`.",
        ],
    },
}

TEXT = {
    "ru": {
        "spec": "ТЗ на создание приложения",
        "target": "Целевая среда",
        "source": "Process IR",
        "how": "Как использовать это ТЗ",
        "prompt": "Начальный промпт",
        "prompt_text": "Создай работоспособное приложение по приведённому ниже ТЗ. Сначала изучи требования, перечисли неоднозначности и предложи поэтапный план. Не начинай реализацию до проверки плана. Не выдумывай бизнес-правила, интеграции и реквизиты. После согласования реализуй приложение, добавь тесты и проверь критерии приёмки.",
        "goal": "Цель приложения",
        "passport": "Паспорт и границы процесса",
        "states": "Состояния и жизненный цикл",
        "rules": "Бизнес-правила",
        "execution": "Границы человека, системы и ИИ",
        "performed_by": "Выполняет",
        "autonomy": "Самостоятельность",
        "approval": "Подтверждение человека",
        "restrictions": "Запреты и ограничения",
        "starts_when": "Начало",
        "ends_when": "Завершение",
        "in_scope": "Входит в процесс",
        "out_of_scope": "Не входит в процесс",
        "yes": "да",
        "no": "нет",
        "requirements": "Функциональные требования",
        "roles": "Роли и права",
        "systems": "Внешние системы",
        "data": "Данные",
        "flow": "Переходы и условия",
        "exceptions": "Исключения",
        "delivery": "Результат разработки",
        "acceptance": "Критерии приёмки",
        "questions": "Открытые вопросы",
        "validation": "Проверка исходной модели",
        "none": "Не указано.",
        "owner": "Исполнитель/система",
        "inputs": "Входные данные",
        "outputs": "Результаты",
        "operation": "Операция",
        "missing": "Не заполнено",
        "required": "обязательное",
        "always": "всегда",
        "delivery_items": [
            "Работоспособный исходный код с воспроизводимой установкой зависимостей.",
            "`README.md` с командами локального запуска, тестирования, сборки и развёртывания.",
            "`.env.example` только с названиями переменных, без реальных реквизитов.",
            "Миграции базы данных или явная настройка локального хранилища, если требуется сохранение данных.",
            "Автоматические тесты основных правил, ветвлений и сценариев ошибок.",
            "Адаптивный интерфейс с состояниями загрузки, пустых данных, проверки, ошибок и ограничений доступа.",
        ],
        "acceptance_items": [
            "Каждый шаг и переход Process IR представлен в приложении.",
            "Условия ветвления приводят к документированному следующему шагу.",
            "Ограничения ролей и границы внешних систем соблюдаются.",
            "Обязательные данные проверяются до завершения перехода.",
            "Исключения видны пользователю и оставляют проверяемый результат.",
            "Тесты и production-сборка завершаются успешно.",
        ],
    },
    "en": {
        "spec": "Application implementation specification",
        "target": "Target environment",
        "source": "Process IR",
        "how": "How to use this specification",
        "prompt": "Initial prompt",
        "prompt_text": "Build a working application from the specification below. First review the requirements, list ambiguities, and propose a staged plan. Do not implement before the plan is reviewed. Do not invent business rules, integrations, or credentials. After approval, implement the app, add tests, and verify the acceptance criteria.",
        "goal": "Application goal",
        "passport": "Process passport and boundaries",
        "states": "States and lifecycle",
        "rules": "Business rules",
        "execution": "Human, system, and AI boundaries",
        "performed_by": "Performed by",
        "autonomy": "Autonomy",
        "approval": "Human approval",
        "restrictions": "Restrictions",
        "starts_when": "Starts when",
        "ends_when": "Ends when",
        "in_scope": "In scope",
        "out_of_scope": "Out of scope",
        "yes": "yes",
        "no": "no",
        "requirements": "Functional requirements",
        "roles": "Roles and permissions",
        "systems": "External systems",
        "data": "Data",
        "flow": "Transitions and conditions",
        "exceptions": "Exceptions",
        "delivery": "Delivery contract",
        "acceptance": "Acceptance criteria",
        "questions": "Open questions",
        "validation": "Source model validation",
        "none": "Not specified.",
        "owner": "Owner/system",
        "inputs": "Inputs",
        "outputs": "Outputs",
        "operation": "Operation",
        "missing": "Missing configuration",
        "required": "required",
        "always": "always",
        "delivery_items": [
            "Runnable source code with reproducible dependency installation.",
            "`README.md` with local start, test, build, and deployment commands.",
            "`.env.example` containing variable names only; no real credentials.",
            "Database migrations or an explicit local persistence setup when storage is required.",
            "Automated tests for core rules, branches, and failure paths.",
            "Responsive UI with loading, empty, validation, error, and permission states.",
        ],
        "acceptance_items": [
            "Every Process IR step and transition is represented in the application.",
            "Branch conditions produce the documented next step.",
            "Role restrictions and system boundaries are enforced.",
            "Required data is validated before a transition is completed.",
            "Exceptions are visible to the user and leave an auditable result.",
            "Tests and production build complete successfully.",
        ],
    },
    "es": {
        "spec": "Especificación para crear la aplicación",
        "target": "Entorno objetivo",
        "source": "Process IR",
        "how": "Cómo usar esta especificación",
        "prompt": "Prompt inicial",
        "prompt_text": "Cree una aplicación funcional según la especificación. Primero revise requisitos, enumere ambigüedades y proponga un plan por etapas. No implemente antes de revisar el plan. No invente reglas, integraciones ni credenciales. Tras la aprobación, implemente, añada pruebas y verifique los criterios de aceptación.",
        "goal": "Objetivo de la aplicación",
        "passport": "Pasaporte y límites del proceso",
        "states": "Estados y ciclo de vida",
        "rules": "Reglas de negocio",
        "execution": "Límites entre persona, sistema e IA",
        "performed_by": "Ejecutado por",
        "autonomy": "Autonomía",
        "approval": "Aprobación humana",
        "restrictions": "Restricciones",
        "starts_when": "Inicio",
        "ends_when": "Finalización",
        "in_scope": "Incluido",
        "out_of_scope": "No incluido",
        "yes": "sí",
        "no": "no",
        "requirements": "Requisitos funcionales",
        "roles": "Roles y permisos",
        "systems": "Sistemas externos",
        "data": "Datos",
        "flow": "Transiciones y condiciones",
        "exceptions": "Excepciones",
        "delivery": "Resultado de desarrollo",
        "acceptance": "Criterios de aceptación",
        "questions": "Preguntas abiertas",
        "validation": "Validación del modelo fuente",
        "none": "No especificado.",
        "owner": "Responsable/sistema",
        "inputs": "Entradas",
        "outputs": "Resultados",
        "operation": "Operación",
        "missing": "Configuración pendiente",
        "required": "obligatorio",
        "always": "siempre",
        "delivery_items": [
            "Código fuente ejecutable con instalación reproducible de dependencias.",
            "`README.md` con comandos de inicio local, pruebas, compilación y despliegue.",
            "`.env.example` solo con nombres de variables, sin credenciales reales.",
            "Migraciones o configuración explícita de persistencia cuando sea necesaria.",
            "Pruebas automáticas para reglas, ramas y escenarios de error.",
            "Interfaz adaptable con estados de carga, vacío, validación, error y permisos.",
        ],
        "acceptance_items": [
            "Cada paso y transición de Process IR está representado en la aplicación.",
            "Las condiciones de rama producen el siguiente paso documentado.",
            "Se aplican las restricciones de rol y los límites de sistemas externos.",
            "Los datos obligatorios se validan antes de completar una transición.",
            "Las excepciones son visibles y dejan un resultado auditable.",
            "Las pruebas y la compilación de producción terminan correctamente.",
        ],
    },
}


def _condition(condition: dict[str, Any] | None, always: str) -> str:
    if not condition:
        return always
    return f"{condition['left']} {condition['operator']} {condition['right']}"


def generate_app_spec(
    process_ir: dict[str, Any],
    validation: ValidationResult,
    target_id: str,
    locale: str,
) -> str:
    process_ir = upgrade_process_ir(process_ir)
    target = TARGETS[target_id]
    language = normalize_locale(locale).split("-", 1)[0]
    text = TEXT.get(language, TEXT["en"])
    guidance = target.get(language, target["en"])
    process = process_ir["process"]
    actors = {item["id"]: item["name"] for item in process_ir["actors"]}
    systems = {item["id"]: item["name"] for item in process_ir["systems"]}
    data = {item["id"]: item["name"] for item in process_ir["dataObjects"]}
    steps = {item["id"]: item["title"] for item in process_ir["steps"]}
    lines = [
        f"# {process['name']} — {text['spec']}",
        "",
        f"- {text['target']}: **{target['name']}**",
        f"- {text['source']}: `{process_ir['schemaVersion']}`",
        f"- {text['validation']}: {validation.counts.errors} errors, {validation.counts.warnings} warnings",
        "",
        f"## {text['how']}",
        "",
    ]
    lines.extend(f"{index}. {item}" for index, item in enumerate(guidance, 1))
    if target["docs"]:
        lines.extend(["", f"- Documentation: {target['docs']}"])
    lines.extend(
        [
            "",
            f"## {text['prompt']}",
            "",
            "> " + text["prompt_text"],
            "",
            f"## {text['goal']}",
            "",
            process["description"] or text["none"],
            "",
            f"## {text['passport']}",
            "",
            f"- {process_ir['passport']['goal'] or text['none']}",
            f"- {text['owner']}: {actors.get(process_ir['passport']['ownerActorId'], text['none'])}",
            f"- {text['starts_when']}: {process_ir['passport']['startsWhen'] or text['none']}",
            f"- {text['ends_when']}: {process_ir['passport']['endsWhen'] or text['none']}",
            f"- {text['in_scope']}: {', '.join(process_ir['passport']['inScope']) or text['none']}",
            f"- {text['out_of_scope']}: {', '.join(process_ir['passport']['outOfScope']) or text['none']}",
            "",
            f"## {text['requirements']}",
            "",
        ]
    )
    for index, step in enumerate(process_ir["steps"], 1):
        owner = actors.get(step["actorId"]) or systems.get(step["systemId"]) or text["none"]
        inputs = ", ".join(data.get(item, item) for item in step["inputs"]) or text["none"]
        outputs = ", ".join(data.get(item, item) for item in step["outputs"]) or text["none"]
        lines.extend(
            [
                f"### FR-{index:02d}. {step['title']}",
                "",
                step["description"] or text["none"],
                "",
                f"- {text['owner']}: {owner}",
                f"- {text['inputs']}: {inputs}",
                f"- {text['outputs']}: {outputs}",
                f"- {text['operation']}: `{step['operation']['kind']}:{step['operation']['name']}`",
                f"- {text['performed_by']}: `{step['execution']['performedBy']}`",
                f"- {text['autonomy']}: `{step['execution']['autonomy']}`",
                f"- {text['approval']}: {text['yes'] if step['execution']['approvalRequired'] else text['no']}",
                f"- {text['restrictions']}: {', '.join(step['execution']['restrictions']) or text['none']}",
                f"- {text['missing']}: {', '.join(step['missingFields']) or text['none']}",
                "",
            ]
        )
    lines.extend([f"## {text['roles']}", ""])
    lines.extend(
        f"- **{actor['name']}** ({actor['type']}): {', '.join(actor['responsibilities']) or text['none']}"
        for actor in process_ir["actors"]
    )
    if not process_ir["actors"]:
        lines.append(text["none"])
    lines.extend(["", f"## {text['systems']}", ""])
    lines.extend(
        f"- **{system['name']}**: {system['type']}; {system['integrationStatus']}; {system['notes'] or text['none']}"
        for system in process_ir["systems"]
    )
    if not process_ir["systems"]:
        lines.append(text["none"])
    lines.extend(["", f"## {text['data']}", ""])
    for item in process_ir["dataObjects"]:
        fields = ", ".join(
            f"{field['name']} ({field['type']}{', ' + text['required'] if field['required'] else ''})"
            for field in item["fields"]
        )
        lines.append(f"- **{item['name']}**: {fields or text['none']}")
    if not process_ir["dataObjects"]:
        lines.append(text["none"])
    lines.extend(["", f"## {text['states']}", ""])
    state_names = {item["id"]: item["name"] for item in process_ir["states"]}
    lines.extend(
        f"- `{state['id']}` **{state['name']}**: initial={state['initial']}, terminal={state['terminal']}"
        for state in process_ir["states"]
    )
    lines.extend(
        f"- {state_names.get(item['fromStateId'], 'start')} → {state_names.get(item['toStateId'], item['toStateId'])}: {item['trigger']}"
        for item in process_ir["stateTransitions"]
    )
    if not process_ir["states"]:
        lines.append(text["none"])
    lines.extend(["", f"## {text['rules']}", ""])
    lines.extend(
        f"- `{rule['id']}` **{rule['name']}**: {rule['description']} ({rule['type']}; source: {rule['source'] or text['none']})"
        for rule in process_ir["businessRules"]
    )
    if not process_ir["businessRules"]:
        lines.append(text["none"])
    lines.extend(["", f"## {text['execution']}", ""])
    lines.extend(
        f"- **{step['title']}**: {step['execution']['performedBy']} / {step['execution']['autonomy']}; "
        f"approval={text['yes'] if step['execution']['approvalRequired'] else text['no']}; "
        f"restrictions={', '.join(step['execution']['restrictions']) or text['none']}"
        for step in process_ir["steps"]
    )
    lines.extend(["", f"## {text['flow']}", ""])
    lines.extend(
        f"- {steps[edge['from']]} → {steps[edge['to']]} (`{_condition(edge['condition'], text['always'])}`)"
        for edge in process_ir["edges"]
    )
    lines.extend(["", f"## {text['exceptions']}", ""])
    lines.extend(
        f"- **{steps[item['sourceStepId']]}**: {item['trigger']} → {item['handling']}"
        for item in process_ir["exceptions"]
    )
    if not process_ir["exceptions"]:
        lines.append(text["none"])
    lines.extend(
        [
            "",
            f"## {text['delivery']}",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in text["delivery_items"])
    lines.extend(["", f"## {text['acceptance']}", ""])
    lines.extend(f"- {item}" for item in text["acceptance_items"])
    lines.extend(["", f"## {text['questions']}", ""])
    lines.extend(f"- **{item['priority']}**: {item['question']}" for item in process_ir["openQuestions"])
    if not process_ir["openQuestions"]:
        lines.append(text["none"])
    return "\n".join(lines).strip() + "\n"
