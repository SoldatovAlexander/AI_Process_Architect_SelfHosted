# Entitlement catalog / Каталог прав

`v1/catalog.json` is the server-authoritative capability and limit catalog shared by hosted subscriptions and self-hosted licenses. It contains no prices, payment-provider identifiers, secrets, or customer data.

`-1` means an unlimited integer limit. The `read_only` plan deliberately preserves `backup.export` so a commercial restriction cannot trap customer data.

`v1/catalog.json` — серверный источник возможностей и лимитов для hosted-подписок и self-hosted-лицензий. Здесь нет цен, идентификаторов платёжной системы, секретов и данных клиента.

Значение `-1` означает отсутствие числового ограничения. План `read_only` сохраняет `backup.export`, чтобы коммерческое ограничение не блокировало перенос данных клиента.
