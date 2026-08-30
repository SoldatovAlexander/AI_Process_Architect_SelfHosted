# AI Process Architect Self-Hosted

AI Process Architect turns a process interview, text transcript, or existing workflow into Process IR and exports BPMN/draw.io, n8n, implementation specifications, and agent-ready packages.

## Quick Start

```bash
cp .env.self-hosted.example .env.compose
# Replace every placeholder in .env.compose.
docker compose --env-file .env.compose up -d --build
```

Open `http://127.0.0.1:5173`. A new installation is read-only until a signed self-hosted license is activated. Each user provides their own encrypted LLM credential or permitted local endpoint.

Read [installation](03_delivery/self-hosted-installation.md), [licensing](03_delivery/self-hosted-licensing.md), and [security](SECURITY.md) before production use.

## Boundary

This repository contains no hosted billing, Stripe code, service administrator API, service-owned LLM credentials, License Control Plane, issuer key, or customer data. The private issuer provides only signed envelopes, public keys, and revocation lists.

## Release Evidence

Assembled from upstream revision `2f0651b86c07a48dc6aceca238be2fa6e11d7c28`. The CycloneDX SBOM is [here](release/self-hosted-sbom.cdx.json).

## Русский

AI Process Architect Self-Hosted собирает Process IR из интервью, текстовой расшифровки или готового workflow и выгружает BPMN/draw.io, n8n, ТЗ и Agent-ready пакеты.

Скопируйте `.env.self-hosted.example` в `.env.compose`, замените placeholders и выполните команду выше. Новая установка работает в read-only до активации подписанной лицензии. Каждый пользователь задаёт собственный зашифрованный ключ LLM или разрешённый локальный endpoint.

В поставке отсутствуют hosted billing, Stripe, серверный LLM-ключ, Admin API, License Control Plane, приватный ключ issuer и клиентские данные.
