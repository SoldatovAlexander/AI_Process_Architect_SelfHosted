# CODEX GUIDE — работа с библиотекой процессов n8n → Semantic Process Graph

Версия: **1.0**
Связанные файлы: `n8n_process_library_50_v1.json`, `process_template_schema_v1.json`

## 1. Цель

Реализовать воспроизводимый pipeline, который получает исходный n8n workflow JSON и преобразует его в независимый от конкретных SaaS **Semantic Process Graph (SPG)**, пригодный для:

- отображения/редактирования как бизнес-процесса;
- последующей генерации BPMN;
- выбора локальных implementation adapters;
- обратной генерации n8n workflow;
- построения библиотеки типовых процессов для МСП.

Главный принцип: **не делать 1:1 mapping n8n node → business node**. n8n описывает реализацию. SPG должен описывать смысл процесса.

## 2. Входные артефакты

1. `n8n_process_library_50_v1.json` — manifest выбранных процессов.
2. Исходный n8n workflow JSON, полученный из разрешённого источника.
3. `process_template_schema_v1.json` — минимальная схема нормализованного шаблона.
4. Таблица node mappings, которую Codex должен расширять по мере разбора workflow.

## 3. Запрещённые действия

Codex **НЕ ДОЛЖЕН**:

- запускать импортированный workflow;
- активировать triggers/webhooks;
- использовать найденные credentials или secrets;
- экспортировать/сохранять decrypted credentials;
- выполнять JavaScript/Python из Code nodes во время анализа;
- устанавливать community nodes автоматически;
- считать конкретный SaaS частью канонической бизнес-модели;
- перепубликовывать verbatim source JSON без `license_status=approved`;
- удалять provenance исходного шаблона.

## 4. Pipeline

### Stage A — Intake

На входе создать immutable source snapshot:

```text
sources/n8n/<template_id>/source.workflow.json
sources/n8n/<template_id>/source.meta.json
```

`source.meta.json` должен содержать:

```json
{
  "provider": "n8n",
  "template_id": 9439,
  "source_url": "...",
  "retrieved_at": "ISO-8601",
  "license_status": "review_required",
  "sha256": "..."
}
```

### Stage B — Static Safety Scan

До семантического анализа сформировать `security_report.json`.

Проверять минимум:

- наличие credentials references;
- community/custom nodes;
- Code / Function / Execute Command nodes;
- filesystem nodes;
- HTTP Request destinations;
- unprotected webhook triggers;
- expressions, содержащие потенциальные secrets;
- destructive operations: delete, revoke, refund, disable, update, execute;
- AI Agent / tool nodes с внешними действиями.

Результат:

```json
{
  "risk_level": "low|medium|high",
  "requires_manual_review": true,
  "findings": []
}
```

### Stage C — Technical Graph

Разобрать исходные `nodes` и `connections` без изменения порядка и создать промежуточный граф.

Каждый technical node хранит:

- source node id;
- source node name;
- n8n node type;
- typeVersion;
- operation/resource;
- input/output degree;
- referenced credentials **только как тип**, без значения;
- expressions summary;
- external service;
- risk flags.

Не включать в смысловой граф `Sticky Note` и canvas coordinates.

### Stage D — Node Role Classification

Каждому technical node присвоить одну или несколько ролей:

```text
TRIGGER
INGEST
VALIDATE
TRANSFORM
ENRICH
CLASSIFY
DECIDE
WAIT
HUMAN_APPROVAL
CALL_EXTERNAL_SERVICE
READ_DATA
WRITE_DATA
SEND_MESSAGE
RECEIVE_MESSAGE
GENERATE_DOCUMENT
PARSE_DOCUMENT
AI_REASONING
LOOP
MERGE
ERROR_HANDLER
AUDIT
END
```

Классификация должна быть детерминированной там, где это возможно. LLM использовать только для неоднозначных Code/AI/HTTP nodes.

### Stage E — Collapse Technical Chains

Объединять низкоуровневые узлы в бизнес-задачу, если они совместно реализуют одну операцию.

Пример:

```text
Gmail Trigger -> Code normalize -> IF required fields
```

может стать:

```text
ReceiveTask: "Получить и проверить обращение"
```

Но gateway сохранять отдельно, если ветвление имеет бизнес-смысл.

### Stage F — Semantic Graph

Использовать semantic types из `process_template_schema_v1.json`.

Базовый mapping:

| n8n intent | SPG |
|---|---|
| Trigger/Webhook/Schedule | start_event / message_event / timer_event |
| IF/Switch with business condition | exclusive_gateway |
| Parallel fan-out | parallel_gateway |
| Wait | timer_event |
| human approval | user_task |
| API/App operation | service_task |
| rules/scoring | business_rule_task |
| Code with business transformation | script_task или service_task |
| send email/message | send_task |
| receive external event | receive_task |
| end/response | end_event |

### Stage G — Adapter Abstraction

Конкретные сервисы заменить adapter role.

Минимальный registry:

```text
crm
email
messenger
calendar
file_storage
document_editor
document_parser
accounting
inventory
ecommerce
payment
ticketing
task_tracker
hr_system
identity
database
table
knowledge_base
web_scraper
analytics
ad_platform
llm
speech_to_text
notification
```

Пример:

```text
HubSpot       -> crm
Airtable      -> table | crm
Google Sheets -> table
Gmail         -> email
Slack         -> messenger
Telegram      -> messenger | approval_channel
Google Drive  -> file_storage
OpenAI        -> llm
Shopify       -> ecommerce
Zendesk       -> ticketing
```

Для российского implementation profile хранить candidates отдельно, например:

```json
{
  "role": "crm",
  "candidates": ["Bitrix24", "amoCRM", "1C CRM", "PostgreSQL custom"]
}
```

### Stage H — Business Naming

Имена semantic nodes писать глаголом и объектом:

- `Проверить комплектность заявки`
- `Назначить ответственного менеджера`
- `Запросить согласование расходов`

Не использовать в canonical name названия SaaS, кроме случаев, когда сервис является бизнес-объектом процесса.

### Stage I — Quality Gates

Перед статусом `approved` процесс должен пройти проверки:

1. Есть ровно один логический start (или явно описанная группа альтернативных starts).
2. Есть достижимый end для каждой основной ветки.
3. Нет dangling edges.
4. Gateway имеет минимум 2 исходящих пути, если это business gateway.
5. Все conditions читаемы на бизнес-языке.
6. Все service-specific действия имеют adapter role.
7. Credentials/secrets отсутствуют.
8. Все destructive actions отмечены warning.
9. Human approval сохранён и не схлопнут в автоматический task.
10. Provenance заполнен.
11. `license_status != approved` запрещает bundled source distribution.
12. Confidence < 0.80 => `review_status=needs_review`.

## 5. Рекомендуемая структура репозитория

```text
process-library/
  manifest/
    n8n_process_library_50_v1.json
  schema/
    process_template_schema_v1.json
  mappings/
    n8n_node_roles.json
    adapter_registry.json
  sources/
    n8n/<template_id>/
      source.workflow.json
      source.meta.json
      security_report.json
  normalized/
    <process_id>/
      process.json
      mapping.json
      review.md
  tests/
    fixtures/
    test_parser.py
    test_normalizer.py
    test_quality_gates.py
```

## 6. Mapping artifact

Для каждого процесса обязательно создавать `mapping.json`:

```json
{
  "source_template_id": 9439,
  "semantic_process_id": "finance.invoice_intake_processing",
  "groups": [
    {
      "semantic_node_id": "receive_invoice",
      "source_node_ids": ["node-a", "node-b"],
      "reason": "Trigger and attachment split implement one business intake step"
    }
  ],
  "dropped_nodes": [
    {"source_node_id": "sticky-1", "reason": "visual annotation"}
  ]
}
```

## 7. Работа с Code nodes

Code node анализировать статически:

1. Не исполнять код.
2. Извлечь imported modules / external calls / field transformations.
3. Определить side effects.
4. Если код только форматирует данные — присоединить к соседней semantic task.
5. Если код реализует существенное бизнес-правило — создать `business_rule_task` или `script_task`.
6. Если назначение неоднозначно — сохранить raw snippet hash и выставить `needs_review`.

## 8. Работа с AI nodes

Не превращать каждый LLM call в отдельную бизнес-задачу. Определять функцию:

- extraction;
- classification;
- summarization;
- generation;
- recommendation;
- decision support;
- agentic action selection.

Если AI принимает необратимое решение (оплата, refund, блокировка пользователя, удаление, юридическое согласование), добавить warning и требование human gate, если его нет в source workflow.

## 9. Error handling enrichment

Источник может не содержать качественной обработки ошибок. Codex должен различать:

- `source_graph` — что реально было в n8n;
- `normalized_graph` — семантически эквивалентная модель;
- `recommended_enhancements` — улучшения, которых в исходнике не было.

Нельзя молча добавлять retry/HITL/fallback внутрь normalized graph. Улучшения идут отдельным списком.

Рекомендуемые проверки:

```text
retry
idempotency
timeout
fallback
human approval
audit log
notification
compensation
dead-letter/error path
```

## 10. Definition of Done для одного импортированного процесса

Процесс считается подготовленным, когда существуют:

- source snapshot;
- checksum;
- provenance;
- security report;
- technical graph;
- node-role classification;
- semantic process JSON, валидный по schema;
- adapter slots;
- source→semantic mapping;
- Russian title/description;
- quality report;
- license flag;
- unit tests для parser/normalizer fixture.

## 11. Порядок обработки первых 50

### Wave 1 — P0

Сначала обрабатывать все `priority=P0`. Они должны сформировать базовые mapping rules.

### Wave 2 — P1

Добавить новые паттерны: AI, approvals, procurement, SEO, RAG, predictive inventory.

### Wave 3 — P2

Использовать для расширения edge cases после стабилизации parser/normalizer.

## 12. Первая инженерная задача для Codex

Создать CLI:

```bash
process-import n8n   --input source.workflow.json   --meta source.meta.json   --output normalized/<process_id>/
```

CLI должен последовательно создавать:

```text
security_report.json
technical_graph.json
node_roles.json
process.json
mapping.json
review.md
```

Добавить режим:

```bash
--dry-run
```

Он является default. Никаких внешних вызовов и execution исходного workflow.

## 13. Acceptance criteria первой версии конвертера

- парсит стандартный n8n workflow JSON;
- корректно читает `nodes` и `connections`;
- игнорирует визуальные annotations;
- сохраняет branching topology;
- распознаёт trigger / IF / Switch / Wait / Code / HTTP / app nodes;
- выделяет adapter roles минимум для 20 распространённых сервисов;
- группирует технические цепочки без потери gateway;
- валидирует output по JSON Schema;
- генерирует mapping source→semantic;
- не делает network calls в dry-run;
- не исполняет Code node;
- не переносит credentials;
- выдаёт warnings по dangerous/community/custom nodes;
- имеет fixtures минимум для 5 P0 процессов разных классов.

## 14. Пять fixtures для первого спринта

1. `sales.lead_dedup_sync` — простой branching + CRM sync.
2. `finance.invoice_intake_processing` — email + document + AI + storage.
3. `support.sla_monitoring_escalation` — schedule + thresholds + escalation.
4. `hr.access_provisioning_onboarding` — role-based branching + external systems.
5. `documents.multi_level_approval` — stateful human approval loop.

Эти пять процессов покрывают основные конструкции, которые затем масштабируются на остальные 45.
