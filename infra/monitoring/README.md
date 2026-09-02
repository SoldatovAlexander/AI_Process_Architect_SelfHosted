# Monitoring / Мониторинг

## Русский

Поддерживаются два режима мониторинга:

- **Встроенный:** профиль `monitoring` добавляет Prometheus, PostgreSQL exporter и Grafana.
- **Внешний:** если у клиента уже есть Prometheus, Grafana или совместимое хранилище метрик, профиль `monitoring` запускать не нужно. Существующий коллектор опрашивает защищённый `/metrics`, а готовая панель импортируется в имеющуюся Grafana.

Обычный запуск приложения остаётся прежним: встроенные сервисы мониторинга стартуют только с явным `--profile monitoring`, поэтому второй экземпляр Grafana или Prometheus самопроизвольно не поднимается.

1. Укажите сильный `GRAFANA_ADMIN_PASSWORD` в `.env.compose`.
2. Запустите приложение вместе с мониторингом:

```bash
docker compose --profile monitoring up --build -d
```

3. Откройте Grafana на `http://127.0.0.1:3000` и Prometheus на `http://127.0.0.1:9090`. Порты меняются через `GRAFANA_PORT` и `PROMETHEUS_PORT`.
4. В Grafana уже подключён Prometheus и загружена панель `AI Process Architect / Operations`.

API публикует Prometheus-метрики по `/metrics`. Авторизованная точка `/api/v1/ops/diagnostics` возвращает безопасный снимок состояния БД, очереди и конфигурационных флагов. Отключить их можно через `METRICS_ENABLED=false` и `SUPPORT_DIAGNOSTICS_ENABLED=false`.

Метрики не содержат email, текст сообщений и интервью, Process IR, токены, credentials, project ID или фактические URL запросов. HTTP label `route` использует только объявленный шаблон FastAPI, например `/api/v1/projects/{project_id}`. Метки операций имеют закрытый набор значений.

В комплект входят одиннадцать правил для недоступности API/БД/exporter, доли ошибок, p95 latency, застрявшей очереди, dead-letter jobs, ошибок LLM, аномального объёма токенов и месячного бюджета LLM. Предупреждение о бюджете срабатывает на 80%, критическое — на 100%. Пороги являются стартовыми и должны быть настроены под тариф и реальную нагрузку. Alertmanager и каналы доставки уведомлений намеренно не включены: production-инсталляция должна подключить свой Alertmanager или существующую систему оповещений.

Для внешнего Prometheus используйте target `api:8000` внутри Compose-сети либо защищённый адрес `/metrics` через вашу инфраструктуру. Внешняя Grafana может импортировать [`grafana/dashboards/overview.json`](grafana/dashboards/overview.json). Grafana не принимает метрики напрямую: у неё должен быть настроен существующий Prometheus или другой совместимый datasource.

В плане развития предусмотрены отдельные панели и alert rules для опционально устанавливаемых рядом n8n,
OpenClaw и Hermes. Они будут работать в обоих режимах: через встроенный monitoring-профиль или через
экспорт scrape targets и dashboard JSON в существующую инфраструктуру клиента. Тексты workflow,
промпты, Process IR и credentials в runtime-метрики не попадут.

## English

Two monitoring modes are supported:

- **Bundled:** the `monitoring` profile adds Prometheus, PostgreSQL exporter, and Grafana.
- **External:** when the customer already operates Prometheus, Grafana, or a compatible metrics backend, do not start the `monitoring` profile. The existing collector scrapes the protected `/metrics` endpoint and the bundled dashboard is imported into the existing Grafana.

The regular application startup remains unchanged. Bundled monitoring services run only when `--profile monitoring` is explicitly selected, so the installation never starts a duplicate Grafana or Prometheus instance by itself.

1. Set a strong `GRAFANA_ADMIN_PASSWORD` in `.env.compose`.
2. Start the application and monitoring stack:

```bash
docker compose --profile monitoring up --build -d
```

3. Open Grafana at `http://127.0.0.1:3000` and Prometheus at `http://127.0.0.1:9090`. Override these ports with `GRAFANA_PORT` and `PROMETHEUS_PORT`.
4. Grafana starts with the Prometheus datasource and the `AI Process Architect / Operations` dashboard provisioned.

The API exposes Prometheus metrics at `/metrics`. The authenticated `/api/v1/ops/diagnostics` endpoint returns a safe database, queue, and configuration-flags snapshot. Disable them with `METRICS_ENABLED=false` and `SUPPORT_DIAGNOSTICS_ENABLED=false`.

Metrics never contain email addresses, messages or interview text, Process IR, tokens, credentials, project IDs, or raw request URLs. The HTTP `route` label uses only the declared FastAPI template, such as `/api/v1/projects/{project_id}`. Operation labels use bounded value sets.

Eleven bundled rules cover API/database/exporter availability, error ratio, p95 latency, stalled queues, dead-letter jobs, LLM errors, abnormal token volume, and the monthly LLM budget. Budget alerts fire at 80 and 100 percent. These thresholds are starting points and must be calibrated against the deployment plan and real traffic. Alertmanager and notification delivery are intentionally not bundled; production deployments should connect their own Alertmanager or existing incident system.

An external Prometheus can scrape `api:8000` inside the Compose network or a protected `/metrics` address exposed by deployment infrastructure. An external Grafana can import [`grafana/dashboards/overview.json`](grafana/dashboards/overview.json). Grafana does not ingest metrics directly, so it must use the customer's existing Prometheus or another compatible datasource.

The roadmap includes dedicated dashboards and alert rules for optionally co-located n8n, OpenClaw, and
Hermes runtimes. They will support both modes: the bundled monitoring profile or exported scrape targets
and dashboard JSON for the customer's existing platform. Workflow content, prompts, Process IR, and
credentials will never be runtime metric labels.
