import json
from typing import Any

from ...localization import normalize_locale
from .base import DEFAULT_NODE_TYPES, N8nTarget


TEXT = {
    "ru": {
        "index_title": "Пакет workflow для n8n",
        "index_intro": "Начните с нужного документа и выполняйте пункты сверху вниз.",
        "beginner_file": "`N8N_BEGINNER_GUIDE.md` — куда нажать, как импортировать JSON, создать credentials, проверить и активировать workflow.",
        "process_file": "`PROCESS_SETUP.md` — что именно настроить в узлах этого процесса и как проверить его ветки.",
        "workflow_file": "`{workflow}` — файл workflow для импорта в n8n.",
        "no_beginner": "Общая инструкция не включена. Если вы уже умеете импортировать workflow, сразу откройте `PROCESS_SETUP.md`.",
        "guide_title": "n8n с нуля: импорт и первый безопасный запуск",
        "guide_scope": "Эта инструкция общая. Она показывает интерфейс n8n, но не повторяет настройки конкретного процесса — они находятся в `PROCESS_SETUP.md`.",
        "before": "1. Подготовьте n8n",
        "before_steps": [
            "Откройте вашу n8n в браузере и войдите под учётной записью, которая может создавать workflow и credentials.",
            "Проверьте версию: откройте меню пользователя или раздел About. Для этого пакета нужна линия **{minor}**, проверенная сборка — **{patch}**.",
            "Если импортируете в рабочую n8n, сначала сделайте резервную копию или экспорт текущего workflow, который собираетесь заменить.",
        ],
        "import": "2. Импортируйте JSON",
        "import_steps": [
            "Распакуйте ZIP в отдельную папку. Не пытайтесь импортировать сам ZIP.",
            "В n8n откройте список **Workflows** и создайте новый workflow. В редакторе нажмите меню с тремя точками в правом верхнем углу.",
            "Выберите **Import from File**. Если ваша сборка показывает кнопку Import прямо в списке Workflows, можно использовать её.",
            "Выберите файл `workflow-n8n-{minor}.json` из распакованной папки.",
            "Дождитесь появления схемы и нажмите **Save**. Пока не публикуйте и не активируйте workflow.",
        ],
        "credentials": "3. Подключите учётные данные",
        "credentials_steps": [
            "Откройте `PROCESS_SETUP.md` и найдите раздел «Доступы и credentials». Там перечислены системы именно этого процесса.",
            "Для каждой системы откройте соответствующий узел. В поле **Credential to connect with** выберите существующий credential или нажмите **Create new**.",
            "Вставляйте токены, пароли и ключи только в форму credentials внутри n8n. Не записывайте их в JSON, заметки узла или Markdown-файлы.",
            "Если credential уже создан, проверьте, что он относится к тестовой среде и имеет минимально необходимые права.",
        ],
        "configure": "4. Заполните узлы",
        "configure_steps": [
            "Идите по схеме слева направо. Узлы с красным значком или предупреждением открывайте в первую очередь.",
            "Для каждого узла выполните действие из таблицы в `PROCESS_SETUP.md`. Не придумывайте значения для полей, помеченных как неизвестные.",
            "Чтобы подставить данные предыдущего узла, перетащите нужное поле из панели INPUT или используйте expression. После этого закройте узел и сохраните workflow.",
        ],
        "test": "5. Проверьте без реальных последствий",
        "test_steps": [
            "Используйте тестовые записи и тестовые credentials. Не отправляйте сообщения реальным клиентам и не изменяйте рабочие данные.",
            "Нажмите **Execute workflow** для полного ручного запуска. Для проверки отдельного узла откройте его и выполните только этот шаг.",
            "После каждого запуска откройте **Executions**, выберите выполнение и проверьте вход, выход и ошибку каждого узла.",
            "Пройдите все сценарии из `PROCESS_SETUP.md`, включая отрицательные ветки и ошибки.",
        ],
        "activate": "6. Опубликуйте только после проверки",
        "activate_steps": [
            "Убедитесь, что все обязательные узлы настроены, тесты пройдены, а владельцу процесса понятен результат.",
            "Сохраните workflow. В актуальных версиях n8n используйте **Publish**; в сборках с прежним интерфейсом включите переключатель **Active**.",
            "Сделайте один контролируемый рабочий запуск и проверьте его в **Executions**.",
            "Если результат неверный, сразу снимите workflow с публикации или выключите Active, исправьте настройки и повторите тесты.",
        ],
        "docker": "Локальная тестовая n8n через Docker",
        "docker_note": "Команда создаёт постоянный volume `n8n_data`. Не используйте её как production-конфигурацию без отдельной настройки безопасности, HTTPS и резервного копирования.",
        "help": "Если пункт не совпадает с вашим экраном",
        "help_text": "Названия кнопок могут немного различаться между patch-версиями. Ищите действия Import, Save, Execute, Executions и Publish/Active. Не выбирайте похожую настройку наугад: остановитесь и уточните у администратора n8n.",
        "setup_title": "Настройка процесса «{name}» в n8n",
        "setup_scope": "Этот файл не объясняет общий интерфейс n8n. Он содержит только настройки и проверки для данного workflow.",
        "package": "Файлы и совместимость",
        "access": "Доступы и credentials",
        "no_systems": "В Process IR не указаны внешние системы. Credentials могут появиться после замены узлов-заглушек.",
        "system_line": "**{name}** (`{type}`, статус интеграции: `{status}`): используется в узлах {steps}.{notes}",
        "nodes": "Настройка узлов",
        "node_columns": "| Узел | Тип n8n | Что сделать перед тестом |\n| --- | --- | --- |",
        "ready_node": "Проверить импортированные параметры и входные данные",
        "placeholder_human": "Это передача работы человеку. Оставьте как контрольную точку либо замените формой, уведомлением или задачей в подтверждённой системе",
        "placeholder_system": "Замените No Operation на реальный узел интеграции; затем выберите credential и настройте операцию",
        "placeholder_end": "Конечная контрольная точка; замена не требуется",
        "missing": "Уточнить и заполнить: {fields}",
        "parameters": "Проверить параметры: `{parameters}`",
        "branches": "Ветки, которые нужно проверить",
        "no_branches": "Условных веток нет. Проверьте основной путь от запуска до завершения.",
        "branch_line": "Из **{source}** в **{target}** при условии `{condition}`.",
        "tests": "Сценарии проверки",
        "test_base": "Основной путь: подайте корректные тестовые данные и убедитесь, что выполнение дошло до ожидаемого завершения без красных узлов.",
        "test_failure": "Ошибка интеграции: временно укажите неверный тестовый параметр или используйте безопасный mock и проверьте, что ошибка видна и не вызывает нежелательных действий.",
        "exceptions": "Проверить исключение: {description}",
        "launch": "Перед публикацией",
        "launch_steps": [
            "Все No Operation, кроме конечных и осознанных человеческих контрольных точек, заменены или письменно приняты владельцем процесса.",
            "Во всех рабочих узлах выбраны credentials нужной среды; секретов нет в JSON и заметках.",
            "Пройдены основной путь, каждая условная ветка и сценарий ошибки.",
            "В Executions нет необъяснённых ошибок и персональных данных, которые не должны сохраняться.",
            "Назначен человек, который выключит workflow при ошибке и разберёт неуспешные executions.",
        ],
    },
}


TEXT["en"] = {
    **TEXT["ru"],
    "index_title": "n8n workflow package", "index_intro": "Open the document that matches your experience and follow it from top to bottom.",
    "beginner_file": "`N8N_BEGINNER_GUIDE.md` — where to click, how to import JSON, create credentials, test, and activate a workflow.",
    "process_file": "`PROCESS_SETUP.md` — exactly what to configure and test for this process.", "workflow_file": "`{workflow}` — the workflow JSON to import into n8n.",
    "no_beginner": "The general guide is not included. If you already know how to import a workflow, open `PROCESS_SETUP.md`.",
    "guide_title": "n8n from zero: import and first safe run", "guide_scope": "This is a general UI guide. Process-specific settings are only in `PROCESS_SETUP.md`.",
    "before": "1. Prepare n8n", "import": "2. Import the JSON", "credentials": "3. Connect credentials", "configure": "4. Configure nodes", "test": "5. Test without real-world effects", "activate": "6. Publish only after testing",
    "before_steps": [
        "Open your n8n in a browser and sign in with an account that can create workflows and credentials.",
        "Check the version in the user menu or About page. This package targets **{minor}** and was tested with **{patch}**.",
        "For a production instance, back up the instance or export the workflow you intend to replace.",
    ],
    "import_steps": [
        "Extract the ZIP into its own folder. Do not import the ZIP itself.",
        "In n8n, open **Workflows**, create a workflow, and use the three-dot menu in the upper-right editor area.",
        "Choose **Import from File**. If your build shows Import in the workflow list, that action is also valid.",
        "Select `workflow-n8n-{minor}.json` from the extracted folder.",
        "Wait for the canvas to appear and select **Save**. Do not publish or activate it yet.",
    ],
    "credentials_steps": [
        "Open `PROCESS_SETUP.md` and find Access and credentials. It lists the systems used by this process.",
        "Open each relevant node. Under **Credential to connect with**, select an existing credential or choose **Create new**.",
        "Enter tokens, passwords, and keys only in n8n's credential form. Never place them in workflow JSON, node notes, or Markdown.",
        "For an existing credential, confirm it targets the test environment and has only the required permissions.",
    ],
    "configure_steps": [
        "Move through the canvas from left to right. Open nodes with red icons or warnings first.",
        "For each node, perform the action listed in `PROCESS_SETUP.md`. Do not invent values for unknown fields.",
        "Map earlier data by dragging a field from INPUT or by using an expression. Close the node and save the workflow.",
    ],
    "test_steps": [
        "Use test records and test credentials. Do not message real customers or modify production data.",
        "Select **Execute workflow** for a full manual run. Open a node and execute only that step when testing it in isolation.",
        "After every run, open **Executions** and inspect each node's input, output, and error.",
        "Run every scenario in `PROCESS_SETUP.md`, including negative branches and failures.",
    ],
    "activate_steps": [
        "Confirm all required nodes are configured, tests pass, and the process owner understands the outcome.",
        "Save the workflow. Use **Publish** in current n8n versions, or switch **Active** on in builds with the earlier UI.",
        "Run one controlled production case and inspect it in **Executions**.",
        "If the result is wrong, unpublish or deactivate immediately, correct the configuration, and rerun the tests.",
    ],
    "docker": "Local test n8n with Docker", "help": "If your screen looks different", "setup_title": "Configure “{name}” in n8n", "setup_scope": "This file covers only the settings and tests for this workflow.",
    "docker_note": "This command creates the persistent `n8n_data` volume. It is not a production configuration without separate security, HTTPS, and backup setup.",
    "help_text": "Button labels may vary slightly between patch versions. Look for Import, Save, Execute, Executions, and Publish/Active. Do not guess when a setting is unclear; stop and ask the n8n administrator.",
    "package": "Files and compatibility", "access": "Access and credentials", "nodes": "Node configuration", "branches": "Branches to test", "tests": "Test scenarios", "launch": "Before publishing",
    "no_systems": "No external systems are confirmed in Process IR. Credentials may be required after placeholder replacement.",
    "system_line": "**{name}** (`{type}`, integration status: `{status}`): used by {steps}.{notes}",
    "node_columns": "| Node | n8n type | Required action before testing |\n| --- | --- | --- |", "ready_node": "Verify imported parameters and input mapping",
    "placeholder_human": "Human handoff: keep it as a checkpoint or replace it with a confirmed form, notification, or task node", "placeholder_system": "Replace No Operation with the real integration node, select its credential, and configure the operation", "placeholder_end": "End checkpoint; no replacement required",
    "missing": "Clarify and fill: {fields}", "parameters": "Verify parameters: `{parameters}`", "no_branches": "There are no conditional branches. Test the main path from trigger to completion.",
    "branch_line": "From **{source}** to **{target}** when `{condition}`.", "test_base": "Happy path: use valid test data and confirm the run reaches the expected end without failed nodes.",
    "test_failure": "Integration failure: use a safe mock or invalid test parameter and confirm the error is visible without unwanted side effects.", "exceptions": "Test exception: {description}",
    "launch_steps": [
        "Every No Operation node except end markers and intentional human checkpoints is replaced or explicitly accepted by the process owner.",
        "Every live node uses credentials for the correct environment; no secrets appear in JSON or notes.",
        "The happy path, every conditional branch, and the failure scenario have passed.",
        "Executions contain no unexplained failures or personal data that should not be retained.",
        "A named person is responsible for deactivating the workflow and reviewing failed executions.",
    ],
}


TEXT["es"] = {
    **TEXT["en"],
    "index_title": "Paquete de workflow para n8n", "index_intro": "Abra el documento adecuado y siga los pasos de arriba abajo.",
    "beginner_file": "`N8N_BEGINNER_GUIDE.md` — dónde pulsar, importar JSON, crear credenciales, probar y activar.",
    "process_file": "`PROCESS_SETUP.md` — configuración y pruebas específicas de este proceso.", "workflow_file": "`{workflow}` — JSON para importar en n8n.",
    "no_beginner": "La guía general no está incluida. Abra `PROCESS_SETUP.md` si ya sabe importar workflows.",
    "guide_title": "n8n desde cero: importar y ejecutar con seguridad", "guide_scope": "Esta guía explica la interfaz general. La configuración del proceso está solo en `PROCESS_SETUP.md`.",
    "before": "1. Prepare n8n", "import": "2. Importe el JSON", "credentials": "3. Conecte credenciales", "configure": "4. Configure los nodos", "test": "5. Pruebe sin efectos reales", "activate": "6. Publique solo después de probar",
    "before_steps": [
        "Abra n8n en el navegador e inicie sesión con una cuenta que pueda crear workflows y credenciales.",
        "Compruebe la versión en el menú de usuario o en About. Este paquete usa **{minor}** y fue probado con **{patch}**.",
        "Si usa una instancia productiva, haga una copia de seguridad o exporte primero el workflow que va a sustituir.",
    ],
    "import_steps": [
        "Descomprima el ZIP en una carpeta. No importe el ZIP directamente.",
        "En n8n, abra **Workflows**, cree un workflow y pulse el menú de tres puntos del editor.",
        "Seleccione **Import from File**. También puede usar Import desde la lista de workflows si aparece allí.",
        "Seleccione `workflow-n8n-{minor}.json` en la carpeta descomprimida.",
        "Espere a que aparezca el diagrama y pulse **Save**. No publique ni active todavía.",
    ],
    "credentials_steps": [
        "Abra `PROCESS_SETUP.md` y busque Accesos y credenciales. Allí están los sistemas de este proceso.",
        "Abra cada nodo correspondiente. En **Credential to connect with**, elija una credencial o pulse **Create new**.",
        "Introduzca tokens, contraseñas y claves solo en el formulario de credenciales de n8n. Nunca en JSON, notas o Markdown.",
        "Si reutiliza una credencial, confirme que apunta al entorno de prueba y tiene permisos mínimos.",
    ],
    "configure_steps": [
        "Recorra el diagrama de izquierda a derecha. Abra primero los nodos con iconos rojos o avisos.",
        "En cada nodo, realice la acción indicada en `PROCESS_SETUP.md`. No invente valores desconocidos.",
        "Mapee datos anteriores arrastrando campos desde INPUT o usando una expresión. Cierre el nodo y guarde.",
    ],
    "test_steps": [
        "Use datos y credenciales de prueba. No escriba a clientes reales ni cambie datos productivos.",
        "Pulse **Execute workflow** para una ejecución manual completa. Para un nodo aislado, ábralo y ejecute solo ese paso.",
        "Después de cada prueba, abra **Executions** y revise entradas, salidas y errores de cada nodo.",
        "Ejecute todos los escenarios de `PROCESS_SETUP.md`, incluidas ramas negativas y errores.",
    ],
    "activate_steps": [
        "Confirme que los nodos están configurados, las pruebas pasan y el propietario entiende el resultado.",
        "Guarde el workflow. Use **Publish** en versiones actuales o active **Active** en interfaces anteriores.",
        "Realice un caso productivo controlado y revíselo en **Executions**.",
        "Si el resultado es incorrecto, despublique o desactive, corrija y repita las pruebas.",
    ],
    "docker": "n8n local de prueba con Docker", "help": "Si su pantalla es diferente", "setup_title": "Configurar «{name}» en n8n", "setup_scope": "Este archivo contiene solo la configuración y pruebas de este workflow.",
    "docker_note": "El comando crea el volumen persistente `n8n_data`. No es una configuración productiva sin seguridad, HTTPS y copias de respaldo.",
    "help_text": "Los nombres pueden cambiar ligeramente entre versiones patch. Busque Import, Save, Execute, Executions y Publish/Active. Si una opción no está clara, deténgase y consulte al administrador de n8n.",
    "package": "Archivos y compatibilidad", "access": "Accesos y credenciales", "nodes": "Configuración de nodos", "branches": "Ramas que debe probar", "tests": "Escenarios de prueba", "launch": "Antes de publicar",
    "no_systems": "Process IR no confirma sistemas externos. Puede necesitar credenciales después de sustituir nodos provisionales.",
    "system_line": "**{name}** (`{type}`, estado de integración: `{status}`): usado por {steps}.{notes}",
    "node_columns": "| Nodo | Tipo n8n | Acción necesaria antes de probar |\n| --- | --- | --- |", "ready_node": "Revise los parámetros importados y el mapeo de entradas",
    "placeholder_human": "Entrega a una persona: mantenga el control o sustitúyalo por un formulario, aviso o tarea confirmada", "placeholder_system": "Sustituya No Operation por el nodo real, seleccione credencial y configure la operación", "placeholder_end": "Punto final; no necesita sustitución",
    "missing": "Aclare y complete: {fields}", "parameters": "Revise parámetros: `{parameters}`", "no_branches": "No hay ramas condicionales. Pruebe el camino principal desde inicio hasta fin.",
    "branch_line": "De **{source}** a **{target}** cuando `{condition}`.", "test_base": "Camino principal: use datos válidos y confirme que llega al final esperado sin nodos fallidos.",
    "test_failure": "Fallo de integración: use un mock seguro o un parámetro de prueba incorrecto y confirme que el error es visible sin efectos no deseados.", "exceptions": "Pruebe la excepción: {description}",
    "launch_steps": [
        "Cada nodo No Operation, salvo finales y controles humanos intencionados, fue sustituido o aceptado por el propietario.",
        "Cada nodo real usa credenciales del entorno correcto; no hay secretos en JSON ni notas.",
        "Pasaron el camino principal, todas las ramas y el escenario de error.",
        "Executions no contiene fallos sin explicar ni datos personales que no deban conservarse.",
        "Hay una persona responsable de desactivar el workflow y revisar ejecuciones fallidas.",
    ],
}


def _text(locale: str) -> dict[str, Any]:
    return TEXT.get(normalize_locale(locale).split("-", 1)[0], TEXT["en"])


def generate_n8n_package_index(target: N8nTarget, locale: str, include_general_guide: bool) -> str:
    text = _text(locale)
    workflow = f"workflow-n8n-{target.minor}.json"
    lines = [f"# {text['index_title']}", "", text["index_intro"], ""]
    if include_general_guide:
        lines.append(f"1. {text['beginner_file']}")
        lines.append(f"2. {text['process_file']}")
        lines.append(f"3. {text['workflow_file'].format(workflow=workflow)}")
    else:
        lines.extend([text["no_beginner"], "", f"1. {text['process_file']}", f"2. {text['workflow_file'].format(workflow=workflow)}"])
    return "\n".join(lines) + "\n"


def generate_n8n_general_guide(target: N8nTarget, locale: str) -> str:
    text = _text(locale)
    lines = [f"# {text['guide_title']}", "", text["guide_scope"], ""]
    for heading, key in [
        ("before", "before_steps"), ("import", "import_steps"), ("credentials", "credentials_steps"),
        ("configure", "configure_steps"), ("test", "test_steps"), ("activate", "activate_steps"),
    ]:
        lines.extend([f"## {text[heading]}", ""])
        lines.extend(f"{index}. {item.format(minor=target.minor, patch=target.tested_patch)}" for index, item in enumerate(text[key], 1))
        lines.append("")
    lines.extend([
        f"## {text['docker']}", "", "```bash",
        f"docker run --rm -it -p 5678:5678 -v n8n_data:/home/node/.n8n n8nio/n8n:{target.tested_patch}",
        "```", "", text["docker_note"], "", f"## {text['help']}", "", text["help_text"], "",
    ])
    return "\n".join(lines)


def _condition(edge: dict[str, Any]) -> str:
    condition = edge.get("condition")
    if not condition:
        return "always"
    return f"{condition.get('left')} {condition.get('operator')} {condition.get('right')}"


def generate_n8n_process_guide(process_ir: dict[str, Any], target: N8nTarget, locale: str) -> str:
    text = _text(locale)
    workflow = f"workflow-n8n-{target.minor}.json"
    steps_by_id = {step["id"]: step for step in process_ir["steps"]}
    lines = [
        f"# {text['setup_title'].format(name=process_ir['process']['name'])}", "", text["setup_scope"], "",
        f"## {text['package']}", "", f"- Workflow: `{workflow}`", f"- n8n: `{target.minor}`", f"- Tested patch: `{target.tested_patch}`", f"- Process IR: `{process_ir['schemaVersion']}`", "",
        f"## {text['access']}", "",
    ]
    used_systems: dict[str, list[str]] = {}
    for step in process_ir["steps"]:
        if step.get("systemId"):
            used_systems.setdefault(step["systemId"], []).append(step["title"])
    systems = {system["id"]: system for system in process_ir["systems"]}
    if not used_systems:
        lines.extend([text["no_systems"], ""])
    else:
        for system_id, step_names in used_systems.items():
            system = systems.get(system_id, {"name": system_id, "type": "unknown", "integrationStatus": "unknown", "notes": ""})
            notes = f" {system.get('notes', '').strip()}" if system.get("notes") else ""
            lines.append("- " + text["system_line"].format(name=system["name"], type=system.get("type", "unknown"), status=system.get("integrationStatus", "unknown"), steps=", ".join(f"**{name}**" for name in step_names), notes=notes))
        lines.append("")
    lines.extend([f"## {text['nodes']}", "", text["node_columns"]])
    for step in process_ir["steps"]:
        node_type = (step.get("automationHint") or {}).get("nodeType") or DEFAULT_NODE_TYPES[step["type"]]
        actions: list[str] = []
        if node_type == "n8n-nodes-base.noOp":
            if step["type"] == "end":
                actions.append(text["placeholder_end"])
            elif step["type"] == "human_task":
                actions.append(text["placeholder_human"])
            else:
                actions.append(text["placeholder_system"])
        else:
            actions.append(text["ready_node"])
        if step.get("missingFields"):
            actions.append(text["missing"].format(fields=", ".join(step["missingFields"])))
        parameters = step.get("operation", {}).get("parameters") or {}
        if parameters:
            actions.append(text["parameters"].format(parameters=json.dumps(parameters, ensure_ascii=False, separators=(",", ":"))))
        lines.append(f"| **{step['title']}** | `{node_type}` | {'; '.join(actions)} |")
    lines.extend(["", f"## {text['branches']}", ""])
    branches = [edge for edge in process_ir["edges"] if edge.get("condition")]
    if branches:
        for edge in branches:
            lines.append("- " + text["branch_line"].format(source=steps_by_id[edge["from"]]["title"], target=steps_by_id[edge["to"]]["title"], condition=_condition(edge)))
    else:
        lines.append(text["no_branches"])
    lines.extend(["", f"## {text['tests']}", "", f"1. {text['test_base']}"])
    for index, edge in enumerate(branches, 2):
        lines.append(f"{index}. " + text["branch_line"].format(source=steps_by_id[edge["from"]]["title"], target=steps_by_id[edge["to"]]["title"], condition=_condition(edge)))
    next_index = 2 + len(branches)
    for exception in process_ir.get("exceptions", []):
        description = exception.get("description") or exception.get("name") or exception.get("id") or "documented exception"
        lines.append(f"{next_index}. {text['exceptions'].format(description=description)}")
        next_index += 1
    lines.append(f"{next_index}. {text['test_failure']}")
    lines.extend(["", f"## {text['launch']}", ""])
    lines.extend(f"- [ ] {item}" for item in text["launch_steps"])
    lines.append("")
    return "\n".join(lines)


def generate_n8n_readme(process_ir: dict[str, Any], target: N8nTarget, locale: str) -> str:
    """Compatibility alias for callers that expect the process-specific guide."""
    return generate_n8n_process_guide(process_ir, target, locale)
