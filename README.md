# AI Process Architect Self-Hosted

> Release preparation repository. This is **not yet an installable product release**.

AI Process Architect turns a business-process interview, a template, an n8n workflow, or an interview
transcript into a versioned Process IR. From it, the product can prepare BPMN/draw.io diagrams,
AI-development specifications, n8n workflows, and governed Agent-ready packages.

This repository will contain the customer-operated distribution. It will not contain hosted billing,
service-owned LLM credentials, customer data, or the private licence-issuer key.

## Current status

The separate public delivery is being assembled from an allowlist and is not ready for installation yet.
The first release requires a clean Ubuntu acceptance run, self-hosted licensing evidence, a security
review, and a source-boundary audit. See [PUBLICATION_STATUS.md](PUBLICATION_STATUS.md).

Do not run deployment commands copied from the main product repository against a production server until
the first tagged self-hosted release is published here.

## Planned customer boundaries

- Your deployment uses your own LLM credential or an approved local endpoint.
- New workspaces remain read-only until a signed licence is activated.
- Project backup export stays available in read-only mode.
- The closed licence issuer stays with the service operator; a customer deployment receives only public
  verification keys and signed licence data.
- Hosted billing, Stripe integration, operator tools, service LLM keys, and production customer data are
  not part of this repository.

## Planned first-release contents

- Docker Compose deployment for API, web application, worker, PostgreSQL, and optional monitoring.
- Installation, update, rollback, backup, restore, LLM, and licence-activation guides.
- Process IR schemas, safe fixtures, automated checks, and source archive checksums.
- A supported security-reporting process and known limitations.

## Security

Never commit `.env` files, licence envelopes, activation codes, private keys, database dumps, customer
projects, transcripts, or captured browser artifacts. See [SECURITY.md](SECURITY.md).

---

# AI Process Architect Self-Hosted

> Репозиторий подготовки релиза. Это **ещё не устанавливаемый релиз продукта**.

AI Process Architect превращает интервью о бизнес-процессе, шаблон, workflow n8n или текстовую
транскрипцию в версионируемый Process IR. На его основе формируются BPMN/draw.io, ТЗ для AI-разработки,
workflow n8n и управляемые Agent-ready пакеты.

Здесь будет находиться самостоятельная клиентская поставка. В неё не войдут hosted billing,
LLM-ключи сервиса, клиентские данные и приватный ключ издателя лицензий.

## Текущий статус

Публичная поставка собирается из разрешённого набора файлов и пока не готова к установке. До первого
релиза нужны чистая приёмка на Ubuntu, проверка self-hosted лицензирования, security review и аудит
границы исходного кода. Подробности: [PUBLICATION_STATUS.md](PUBLICATION_STATUS.md).

Не используйте в production команды установки из основного репозитория до появления здесь первого
помеченного self-hosted релиза.

## Границы будущей поставки

- Владелец установки использует свой LLM-ключ или разрешённый локальный endpoint.
- Новые пространства остаются в режиме чтения до активации подписанной лицензии.
- Экспорт резервной копии проекта доступен и в режиме чтения.
- Закрытый issuer лицензий остаётся у оператора сервиса; клиент получает только публичные ключи
  проверки и подписанные данные лицензии.
- Hosted billing, Stripe, операторские инструменты, LLM-ключи сервиса и production-данные клиентов не
  публикуются в этом репозитории.

## Безопасность

Никогда не коммитьте `.env`, licence envelope, activation code, приватные ключи, дампы БД, проекты
клиентов, транскрипции и браузерные артефакты. См. [SECURITY.md](SECURITY.md).
