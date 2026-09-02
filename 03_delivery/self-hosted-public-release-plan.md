# План self-hosted поставки и публичного репозитория

Статус: детальный план self-hosted public release. Общий порядок и приоритеты определяются в
[`current-delivery-plan.md`](current-delivery-plan.md).

## Цель

Подготовить самостоятельную self-hosted поставку AI Process Architect, которую можно установить на
Ubuntu/Docker без доступа к hosted-инфраструктуре, платёжным данным или приватным ключам издателя.
После чистой установки и приёмки выделить её в публичный репозиторий и выпустить первый публичный
релиз.

## Архитектурное разделение

### Hosted-сервис

- закрытая инфраструктура сервиса;
- hosted subscriptions, metering, Stripe и отчётность;
- системный LLM-ключ сервиса;
- hosted Admin API;
- License Control Plane как внутренний issuer;
- приватные ключи подписи лицензий.

### License Control Plane

- отдельный закрытый Python-сервис или защищённый issuer CLI на переходном этапе;
- собственная БД или ledger выданных лицензий;
- выпуск, продление, отзыв и ручное approval;
- RBAC и журнал действий;
- приватный Ed25519-ключ только в окружении издателя;
- клиент получает только подписанный license envelope или activation code.

### Self-hosted поставка

- публичный код приложения и Docker Compose;
- self-hosted deployment profile;
- ключ LLM клиента или локальный LLM endpoint;
- license consumer и проверка offline/online лицензии;
- `SELF_HOSTED_DEFAULT_PLAN_ID=read_only` до активации;
- срок ручной лицензии по умолчанию 1 месяц, максимум 3 месяца;
- отсутствие hosted billing, Stripe и приватных ключей issuer.

## Этапы

### 1. Границы и инвентаризация

- определить файлы и env-переменные, допустимые для public self-hosted;
- разделить hosted-only маршруты и компоненты;
- проверить отсутствие ключей, production-конфигурации и клиентских данных;
- закрепить правило: hosted-планы не бесплатны, `null` цена означает `unpriced`.

**Статус:** manifest и правила сборки подготовлены в
[`self-hosted-public-manifest.md`](self-hosted-public-manifest.md); локальные `.env.*` игнорируются,
а автоматический audit проверяет границы Compose и tracked secrets.

**Выход:** manifest публичной поставки и список запрещённых файлов.

### 2. Чистый self-hosted Compose

- отдельный профиль Compose для self-hosted;
- `.env.example` без секретов;
- PostgreSQL, API, Web, worker и optional monitoring;
- автоматический startup после reboot;
- понятные команды install, upgrade, rollback и backup;
- startup/preflight seed для rubricator и обязательных справочников.

**Выход:** установка на чистый Ubuntu-сервер без ручного запуска внутренних Python-команд.

**Статус:** изолированный Ubuntu/Docker smoke-run пройден 30 августа 2026 года; evidence находится в
[`self-hosted-ubuntu-acceptance-2026-08-30.md`](self-hosted-ubuntu-acceptance-2026-08-30.md).

### 3. License Control Plane

- перенести issuer из переходного CLI в отдельный закрытый сервис;
- endpoints для issue/list/renew/revoke;
- ручное подтверждение выпуска;
- срок 1 месяц по умолчанию и жёсткий максимум 3 месяца;
- аудит, idempotency и защита от повторной выдачи;
- публикация только public keys и revocation format для клиента.

**Статус:** базовый закрытый Python-сервис реализован в `apps/license_control_plane`. Он хранит
собственный SQLite ledger, принимает отдельные operator/activation tokens, выпускает, продлевает и
отзывает подписанные лицензии, сохраняет аудит и не повторно показывает activation code. Приватный
Ed25519-ключ передаётся только монтированием в issuer container.

**Выход:** оператор может выдать, продлить и отозвать лицензию, не имея доступа к клиентским данным.

### 4. Чистая установка и лицензирование

На отдельной Ubuntu-машине проверить:

- запуск с нулевой базой;
- регистрацию и создание workspace;
- локальный/self-hosted LLM credential;
- offline activation на 1 месяц;
- продление на 3 месяца;
- отказ лицензии на 4 месяца;
- истечение и переход в read-only/grace;
- отзыв и сохранение только чтения/backup;
- отсутствие hosted billing и Stripe endpoints.

### 5. Тестирование

- smoke Playwright без LLM-токенов;
- agent/n8n тесты только через Compose mock profile;
- отдельный каталог видео и trace для каждого прогона;
- закрытие рекомендаций OpenCode: rubric seed, worker/runtime profiles, mock network и cleanup;
- ручная проверка пяти режимов из тестового пакета.

Подробные рекомендации зафиксированы в [`test-strategy-recommendations.md`](test-strategy-recommendations.md).

### 6. Security review публичной поставки

- secret scan истории Git и текущего дерева;
- проверка `.gitignore` и `.env.example`;
- проверка Docker images, ports, default passwords и CORS;
- проверка лицензирования и trust store;
- проверка backup на отсутствие секретов;
- проверка README на воспроизводимость установки;
- SBOM/dependency audit и фиксация известных ограничений.

### 7. Публичный репозиторий и release

Публичный репозиторий создаётся только после этапов 1–6. В него входят код, Compose, миграции,
документация, schemas, fixtures и release notes. Не входят hosted billing implementation details,
issuer secrets, production deployment files, реальные ключи, клиентские проекты и внутренние отчёты.

Первый релиз должен иметь:

- version tag;
- installation guide;
- upgrade/rollback guide;
- license activation guide;
- security policy;
- known limitations;
- checksum для release artifacts;
- проверенный smoke report.

## Release gates

Публичный release запрещён, если:

- чистая установка требует ручного seed базы;
- self-hosted может случайно обратиться к hosted billing;
- приватный ключ issuer попадает в Docker image или public repository;
- лицензия длиннее трёх месяцев принимается клиентом;
- тесты используют реальный LLM или внешний runtime;
- backup содержит секреты;
- не сохранены видео и отчёт полного smoke-прогона.

## Текущий статус

- базовый self-hosted license consumer готов;
- ограничение лицензии 1–3 месяца реализовано;
- закрытый License Control Plane с issue/list/renew/revoke/activation/revocation API реализован;
- отдельный self-hosted Compose overlay задаёт `read_only` до активации и не передаёт hosted LLM/billing настройки;
- clean Docker Compose drill подтверждает seed рубрикатора, отключённый service LLM и `read_only` для нового workspace;
- self-hosted overlay явно очищает service LLM, Stripe и E2E-ключи даже при их наличии в локальном
  `.env.compose`; release audit закрепляет это проверкой;
- hosted Stripe/webhook, subscription, invoice-reconciliation and pricing modules moved under
  `process_architect_api.hosted`; the API loads hosted billing and service-admin routes only when their
  modules are present, allowing the public self-hosted tree to omit them physically;
- подготовлены public manifest и `SECURITY.md`;
- release-boundary Compose drill с намеренно переданными hosted-значениями пройден и оформлен в
  [`self-hosted-release-check-2026-08-30.md`](self-hosted-release-check-2026-08-30.md);
- комментарии OpenCode оформлены;
- изолированный Ubuntu installation smoke-run, licensing contract acceptance и восстановление из
  backup после изменения лицензии пройдены; остаются dependency/SBOM review и публикация отдельного
  self-hosted репозитория с устанавливаемой поставкой;
- публичный целевой репозиторий
  [AI_Process_Architect_SelfHosted](https://github.com/SoldatovAlexander/AI_Process_Architect_SelfHosted)
  инициализирован статусной документацией; до release gates он намеренно не содержит приложение;
- текущий основной репозиторий остаётся исходным репозиторием до прохождения release gates.
