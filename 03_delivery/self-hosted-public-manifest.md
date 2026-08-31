# Self-hosted public package manifest

Status: release candidate inventory. This document is the source of truth when the separate public
repository is assembled from the main source repository.

## Included

- application source: `apps/api`, `apps/web`, migrations, Process IR schemas and neutral examples, and tests needed to run
  the self-hosted product;
- customer Docker configuration: `compose.yml`, `compose.self-hosted.yml`, `.env.self-hosted.example`,
  `infra/monitoring`, `infra/systemd`, and customer-facing scripts;
- deployment and entitlement configuration: `config/deployment_profiles`, `config/entitlements`;
- customer documentation: installation, upgrade/rollback, backup/restore, Community export limits, known
  limitations, `SECURITY.md`, and release notes;
- fixtures and schemas that demonstrate supported imports and exports, provided they contain no client
  data or credentials.

## Excluded

- `apps/license_control_plane`, `compose.license-control.yml`, `.env.license-control.example`, and all
  issuer private keys, operator tokens, activation tokens, issuer audit data, and revocation publishing
  operations;
- `apps/api/src/process_architect_api/hosted`, which contains Stripe webhooks, hosted subscriptions,
  invoice reconciliation, and hosted price calculation; `admin_routes.py` is likewise excluded from the
  customer API surface;
- hosted payment code and configuration, Stripe secrets, hosted subscription prices, service-owned LLM
  credentials, service administration deployment configuration, production reverse-proxy files, and
  internal monitoring credentials;
- real customer projects, database dumps, conversation transcripts, test-server reports, videos,
  screenshots, and unreviewed research files;
- any local `.env*` file other than explicitly reviewed `*.example` templates.

## Assembly rules

1. Build the public repository with `scripts/assemble-self-hosted-public.sh` in a clean working tree.
   The script selects only the paths from this allowlist; do not use a recursive copy of the monorepo.
2. Re-run `scripts/audit-self-hosted-release.sh` after assembly and before every tag.
3. Build the customer images from the public tree and run a clean Ubuntu acceptance scenario.
4. Publish SHA-256 checksums for the tagged source archive and container image digests.
5. Verify that the assembled tree starts with both `process_architect_api.hosted` and `admin_routes.py`
   absent; the API must not attempt to import either module under a self-hosted profile.

## Required evidence for the first public tag

- clean Ubuntu installation report, including successful BPMN and description export;
- server-side rejection evidence for n8n and Agent-ready package exports;
- smoke video/trace without external LLM or runtime credentials;
- dependency/SBOM review and known-limitations note;
- security review signed off by the release operator.
