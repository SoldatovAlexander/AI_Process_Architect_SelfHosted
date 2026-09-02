# Self-hosted licensing / Лицензирование self-hosted

## Русский

Коммерческая установка должна задать `SELF_HOSTED_DEFAULT_PLAN_ID=read_only`. До активации
пользователь может читать проекты и выгружать резервные архивы, но не может создавать новые
проекты, выполнять агентов или экспортировать рабочие артефакты.

### Выдача и ручное управление лицензиями

Приватный ключ издателя не должен находиться в основном приложении или на сервере клиента. Выпуском
управляет отдельный закрытый Python-сервис License Control Plane с собственным SQLite ledger,
idempotency, журналом операций и отдельными operator/activation tokens. Он запускается только в
операторской среде через `compose.license-control.yml`, а не в составе self-hosted поставки.

Оператор использует `POST /v1/licenses`, `GET /v1/licenses`, `POST /v1/licenses/{licenseId}/renew`
и `POST /v1/licenses/{licenseId}/revoke`. Выпуск без `months` создаёт лицензию на один месяц;
допустимы только один, два или три календарных месяца. Запрос на четыре месяца отклоняется.
Клиенту передаются только подписанный envelope или одноразовый activation code, а также public key
и portable revocation list. Ledger, ключ подписи и operator token всегда остаются вне репозитория и
за пределами клиентского сервера.

На Hosted-сервере control plane подключается к внутренней Docker-сети приложения и слушает только
`127.0.0.1:8090`. API обращается к нему по имени `http://license-control:8090`; для этого в
`.env.compose` задаются `LICENSE_CONTROL_PLANE_URL` и `LICENSE_CONTROL_PLANE_OPERATOR_TOKEN`, а
операторские ключ и токены хранятся в отдельном `.env.license-control` вне Git.
Любой другой адрес control plane должен использовать HTTPS.

1. Владелец workspace запрашивает `GET /api/v1/workspaces/{workspaceId}/license` и получает
   стабильный `deploymentId` и `workspaceId`.
2. Издатель формирует payload по `license-envelope-v1.schema.json`, подписывает канонический JSON
   приватным Ed25519-ключом и передаёт envelope клиенту. Приватный ключ никогда не устанавливается
   на сервер клиента.
3. Public key издателя добавляется в `LICENSE_TRUSTED_KEYS_PATH`.
4. Offline-файл активируется через `POST /api/v1/workspaces/{workspaceId}/license/offline` с телом
   `{"envelope": {...}}`.
5. Для online-активации задаётся `LICENSE_SERVER_URL`, после чего activation code отправляется в
   `POST /api/v1/workspaces/{workspaceId}/license/online`.

Online-запрос содержит только activation code, идентификаторы установки и workspace и имя продукта.
Процессы, интервью, пользовательские данные и credentials не отправляются. Отзыв выполняется обновлением
`config/licensing/revocations.json` (или файла из `LICENSE_REVOCATIONS_PATH`); этот каталог read-only
монтируется в API и читается без пересборки образа. Истёкшая или отозванная лицензия сохраняет чтение и
backup export.

Проверка на стороне клиента также отклоняет envelope, у которого срок между `notBefore` и `expiresAt`
превышает три календарных месяца.

## English

A commercially licensed installation should set `SELF_HOSTED_DEFAULT_PLAN_ID=read_only`. Before
activation, users can read projects and export portable backups, but cannot create projects, execute
agents, or export working artifacts.

Issuance is handled by the separate private License Control Plane, not by the customer installation.
The operator service keeps its signing key, SQLite ledger, audit trail, operator token, and activation
token in the operator environment. `POST /v1/licenses` defaults to one calendar month and accepts no
more than three; renew and revoke use dedicated operator endpoints. The customer receives only a signed
envelope or activation code, the public key, and the portable revocation-list format.

On the hosted server the control plane joins the application's internal Docker network while listening
only on `127.0.0.1:8090`. The API reaches `http://license-control:8090` using its private operator
token; issuer keys and control-plane tokens remain in a separate `.env.license-control` outside Git.
Any other control-plane address must use HTTPS.

1. A workspace owner calls `GET /api/v1/workspaces/{workspaceId}/license` to obtain the stable
   `deploymentId` and `workspaceId`.
2. The issuer creates a payload conforming to `license-envelope-v1.schema.json`, signs its canonical
   JSON with an Ed25519 private key, and supplies the envelope. The private key is never installed on
   the customer server.
3. Add the issuer public key to `LICENSE_TRUSTED_KEYS_PATH`.
4. Activate an offline envelope through `POST /api/v1/workspaces/{workspaceId}/license/offline` with
   `{"envelope": {...}}`.
5. For online activation, configure `LICENSE_SERVER_URL` and send the activation code to
   `POST /api/v1/workspaces/{workspaceId}/license/online`.

The online request contains only the activation code, deployment and workspace identifiers, and product
name. Process data, interviews, user content, and credentials are never sent. Revoke a license by updating
`config/licensing/revocations.json` (or `LICENSE_REVOCATIONS_PATH`); the API reads the mounted customer
directory without rebuilding its image. Expired or revoked licenses retain read and backup access.
