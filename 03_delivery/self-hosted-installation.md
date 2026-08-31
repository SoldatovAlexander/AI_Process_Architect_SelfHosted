# Self-hosted installation v1

This is the customer-operated product profile. It intentionally differs from hosted operation:

- no hosted billing, Stripe, service-owned LLM key, issuer private key, or hosted administrator controls;
- every user configures their own encrypted LLM credential or a permitted local endpoint;
- a new workspace starts ready for all Community work modes without activation;
- Community export is limited to BPMN/draw.io and a text process description.

## Install

1. Copy `.env.self-hosted.example` to `.env.compose` and replace every placeholder.
2. Start the customer stack:

```bash
docker compose -f compose.yml -f compose.self-hosted.yml --env-file .env.compose up -d --build
```

4. Verify `http://127.0.0.1:5173` and `/health` through the web proxy.
5. Register a user and create a workspace. No license activation is required. Verify that BPMN/draw.io
   and a text process description export successfully, while n8n and Agent-ready package exports are unavailable.

## Update and backup

Before every update, export project archives and back up PostgreSQL plus `.env.compose` separately.
For an update, pull the approved release, run the same Compose command with `--build`, then verify
health and a BPMN export. Rollback uses the preceding pinned release image or Git tag; never reuse a
database backup from a newer schema on an older application version.

## Boundaries

Community does not contain a license issuer or activation workflow. A future commercial licensing
service, if any, must be operated separately and must not add issuer keys or customer activation data
to this repository.

## Verified clean Compose drill

On 25 August 2026, an isolated clean Docker Compose stack was built with a new PostgreSQL volume and
the self-hosted overlay. API health reported the `default` self-hosted profile, rubric seeding was ready,
the service-owned LLM fallback was disabled, and a newly registered workspace received the Community
plan. The isolated containers, network, and volume were removed after the drill.

This is not yet the final Ubuntu acceptance gate. That gate must additionally cover successful BPMN and
description export plus server-side rejection of n8n and Agent-ready package exports.

The release-boundary Docker evidence and the remaining clean-Ubuntu checklist are recorded in
[`self-hosted-release-check-2026-08-30.md`](self-hosted-release-check-2026-08-30.md).
