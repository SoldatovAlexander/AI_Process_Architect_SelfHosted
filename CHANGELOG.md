# Changelog

## Unreleased

## 0.2.0-rc.1 - 2026-08-20

### Русский

- Добавлены иерархический рубрикатор и библиотека из 296 шаблонов с личными коллекциями, избранным и сохранением проекта как шаблона.
- Реализованы импорт n8n как AS-IS, интервью для TO-BE и обратный экспорт без потери неподдерживаемых узлов для n8n `2.30`–`2.32`.
- Добавлены полный переносимый архив истории проекта и проверяемое восстановление.
- Текстовые интервью теперь принимаются из текста, офисных файлов и разрешённых ссылок, проходят проверку, анализ доказательств и объединение нескольких источников.
- Agent-ready контур включает управляемые контракты, пилотные проверки, очередь запусков, инциденты, OpenClaw/Hermes и Python-адаптеры.
- Добавлены проверяемый Python для Code node и внешних сервисов, SBOM и ограниченный TypeScript fallback.
- Реализованы проверяемые профили подключений, выключенная публикация в n8n и сохранение Agent-ready пакетов без запуска.
- Добавлен воспроизводимый release-check и CI для backend, frontend, Playwright, миграций и Compose-конфигурации.
- Добавлены privacy-safe метрики Prometheus, support diagnostics, PostgreSQL exporter, готовая Grafana-панель и девять базовых alert rules в опциональном Compose-профиле.

### English

- Added the hierarchical rubric and 296-template library with personal collections, favorites, and project-to-template saving.
- Added n8n AS-IS import, TO-BE completion interviews, and source-preserving round trips for n8n `2.30`–`2.32`.
- Added complete portable project-history archive validation and restore.
- Text interviews now support pasted text, office files, and allowlisted links with review, evidence analysis, and multi-source composition.
- The Agent-ready layer now includes governed contracts, pilot gates, dispatch queues, incidents, OpenClaw/Hermes, and Python adapters.
- Added reviewed Python for Code nodes and external services, SBOM output, and a constrained TypeScript fallback.
- Added verified runtime profiles, inactive n8n publication, and non-running Agent-ready package storage.
- Added a reproducible release check and CI for backend, frontend, Playwright, migrations, and Compose configuration.
- Added privacy-safe Prometheus metrics, support diagnostics, PostgreSQL exporter, a provisioned Grafana dashboard, and nine baseline alert rules in an optional Compose profile.

## 2026-08-12

- Added explicit AS-IS and TO-BE revision perspectives for imported n8n workflows.
- Added a localized AS-IS completion interview whose accepted changes create separate TO-BE revisions.
- Made Playwright start from a clean database migrated through Alembic `head`.
- Added source-preserving n8n round-trip packages for `2.30`, `2.31`, and `2.32`, including exact AS-IS return and TO-BE overlays.

- Added n8n `2.30`–`2.32` JSON import into immutable AS-IS projects with source provenance, diagnostics, credential references, and inline-secret rejection.
- Added private per-user template collections, a required Favorites collection, and catalog favorites.
- Added saving the current project revision as an immutable personal Process IR template and reusing it to create projects.
- Added Prometheus and Grafana observability to the commercial self-hosted roadmap.
- Added localized rubric facets to the template library for business domain, automation mode, process role, and risk.
- Added server-side AND filtering through repeatable `rubricEntryId` parameters.
- Added rubric-aware template search and optional rubric constraints for interview-time suggestions.

## 0.1.0-mvp - 2026-08-12

### Русский

- Завершён основной цикл: авторизация, проекты, интервью, подтверждаемые изменения Process IR, история и откат ревизий.
- Добавлена библиотека из 296 шаблонов: 20 готовых схем и 276 интервью-черновиков, включая 28 Agent-ready процессов.
- Реализованы экспорты ТЗ для AI-сред разработки, редактируемого BPMN/draw.io, n8n 2.32/2.31/2.30 и Agent-ready пакетов OpenClaw/Hermes.
- Пройдены три сквозных сценария и матрица из 21 сценария экспорта.
- Все девять созданных workflow импортированы в n8n 2.32.7, 2.31.7 и 2.30.8.
- Исправлены ложное завершение интервью без изменения схемы, повторное предложение применённого шаблона и дубли имён узлов n8n.

### English

- Completed the primary flow: authentication, projects, interviews, reviewable Process IR changes, revision history, and rollback.
- Added a library of 296 templates: 20 ready diagrams and 276 interview drafts, including 28 Agent-ready processes.
- Added exports for AI development specifications, editable BPMN/draw.io, n8n 2.32/2.31/2.30, and OpenClaw/Hermes Agent-ready packages.
- Completed three end-to-end scenarios and the 21-case export matrix.
- Imported all nine generated workflows into n8n 2.32.7, 2.31.7, and 2.30.8.
- Fixed false interview completion without a diagram change, repeated suggestions of an applied template, and duplicate n8n node names.
