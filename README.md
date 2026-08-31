# AI Process Architect Self-Hosted

AI Process Architect Community Self-Hosted turns a process interview, text transcript, or existing workflow into Process IR. Community export is limited to BPMN/draw.io diagrams and process descriptions.

## Quick Start

```bash
cp .env.self-hosted.example .env.compose
# Replace every placeholder in .env.compose.
docker compose --env-file .env.compose up -d --build
```

Open `http://127.0.0.1:5173`. The Community installation is ready to use without activation. Each user provides their own encrypted LLM credential or permitted local endpoint.

Read [installation](03_delivery/self-hosted-installation.md) and [security](SECURITY.md) before production use.

## Boundary

This repository contains no hosted billing, Stripe code, service administrator API, service-owned LLM credentials, License Control Plane, issuer key, or customer data.

## Release Evidence

Assembled from upstream revision `2f0651b86c07a48dc6aceca238be2fa6e11d7c28`. The CycloneDX SBOM is [here](release/self-hosted-sbom.cdx.json).

## Русский

Community Self-Hosted собирает Process IR из интервью, текстовой расшифровки или готового workflow. В Community доступны экспорт BPMN/draw.io и текстовое описание процесса.

Скопируйте `.env.self-hosted.example` в `.env.compose`, замените placeholders и выполните команду выше. Community-установка готова к работе без активации. Каждый пользователь задаёт собственный зашифрованный ключ LLM или разрешённый локальный endpoint.

В поставке отсутствуют hosted billing, Stripe, серверный LLM-ключ, Admin API, License Control Plane, приватный ключ issuer и клиентские данные.
