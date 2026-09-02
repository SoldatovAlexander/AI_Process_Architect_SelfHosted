# Deployment profiles / Профили установки

## Русский

- `hosted`: облачный сервис использует ключ владельца сервиса. Пользователь не видит и не вводит ключ или модель.
- `default`: обычная self-hosted установка. Каждый пользователь подключает собственный DeepSeek, OpenAI или совместимый API; ключ шифруется перед записью в БД.
- `restricted`: self-hosted с ограниченным списком внешних провайдеров и сетевых адресов.
- `fully-local`: только локальный OpenAI-совместимый API, например Ollama; внешний сетевой доступ LLM запрещён.

Для облака задайте `DEPLOYMENT_PROFILE=hosted` и `SYSTEM_LLM_PROVIDER`, `SYSTEM_LLM_API_KEY`, `SYSTEM_LLM_BASE_URL`, `SYSTEM_LLM_MODEL`. Для старой конфигурации DeepSeek по-прежнему поддерживается `AI_PROCESS_API`.

Для self-hosted задайте отдельный постоянный `LLM_CREDENTIAL_ENCRYPTION_KEY`. Его потеря делает сохранённые пользовательские ключи нечитаемыми. Не меняйте его при обновлении и храните в резервной копии секретов, отдельно от БД.

Раздел `administration` отделяет hosted control plane от локальной админки без отдельной ветки кода. В
`hosted` разрешены биллинг и режим издателя лицензий. В `default`, `restricted` и `fully-local` биллинг
выключен, установка только активирует подписанные лицензии и не может вручную назначать коммерческий план.
Старый кастомный профиль без этого раздела получает безопасные self-hosted значения по умолчанию.

## English

- `hosted`: the hosted service uses a service-owned key. Users neither see nor enter a key or model.
- `default`: standard self-hosted deployment. Each user connects DeepSeek, OpenAI, or a compatible API; the key is encrypted before it reaches the database.
- `restricted`: self-hosted deployment with constrained providers and network destinations.
- `fully-local`: local OpenAI-compatible API only, such as Ollama; remote LLM egress is blocked.

For hosted operation set `DEPLOYMENT_PROFILE=hosted` and the `SYSTEM_LLM_*` variables. The legacy `AI_PROCESS_API` DeepSeek configuration remains supported.

For self-hosted operation set a separate, stable `LLM_CREDENTIAL_ENCRYPTION_KEY`. Losing it makes stored user keys unreadable. Keep it unchanged across upgrades and back it up separately from the database.

The `administration` section separates the hosted control plane from local administration without a
separate source branch. `hosted` enables billing and license-issuer mode. `default`, `restricted`, and
`fully-local` disable billing, consume signed licenses, and cannot manually assign a commercial plan.
Older custom profiles without this section receive fail-closed self-hosted defaults.
