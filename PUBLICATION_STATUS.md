# Self-hosted public release status

## Purpose

This repository is the public destination for the customer-operated distribution of AI Process Architect.
It is deliberately separate from the hosted service and from the closed licence issuer.

## Completed preparation

- Self-hosted deployment profile with a read-only default plan.
- Offline and online licence-consumer design with a one-month default and a three-month maximum manual
  licence duration.
- Compose boundary checks that clear service LLM, billing, Stripe, and end-to-end runtime credentials.
- Public-package manifest and a source-boundary audit in the main repository.

## Required before the first installable tag

- [ ] Remove or isolate hosted billing and service-administration implementation from the public source
      tree, not merely from runtime configuration.
- [ ] Assemble the application from the reviewed allowlist and run the public source-boundary audit.
- [ ] Run a clean Ubuntu installation with PostgreSQL, API, worker, web, and optional monitoring.
- [ ] Verify offline activation for one month, renewal for three months, rejection of four months,
      revocation, read-only/grace behaviour, and backup/restore.
- [ ] Review images, ports, CORS, dependencies/SBOM, customer backups, and documentation.
- [ ] Publish a smoke report, checksums, image digests, known limitations, and a signed release tag.

## Never publish here

- service-owned LLM credentials, hosted Stripe configuration, hosted subscription data, or production
  reverse-proxy configuration;
- private issuer keys, operator or activation tokens, issuer ledger/audit data, or revocation publishing
  operations;
- customer projects, database dumps, interview transcripts, browser recordings, screenshots, or any
  unreviewed research material.

Until the above checklist is complete, this repository intentionally contains documentation only.
