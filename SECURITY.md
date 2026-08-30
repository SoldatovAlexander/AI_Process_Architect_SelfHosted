# Security policy

## Supported delivery paths

Security fixes are prepared on the current main source repository and included in the next supported
self-hosted release tag. The hosted service and the self-hosted package have different operational
boundaries; do not include customer data, access tokens, licence envelopes, or private keys in a report.

## Reporting a vulnerability

Use a private security advisory in the repository where the affected release is published. If that is
not available, contact the service operator through the deployment's documented support channel. Include:

- affected version or image digest;
- reproducible steps and expected versus actual behavior;
- impact and whether the report concerns hosted, self-hosted, or the closed licence issuer;
- a safe reproduction that uses synthetic data only.

Do not open a public issue for a vulnerability before a fix or mitigation is available.

## Self-hosted operator responsibilities

- keep Docker, the operating system, container images, and the application release current;
- use unique values for database, authentication, encryption, Grafana, runtime, and licence-server
  credentials;
- keep `.env.compose`, backups, and the LLM credential-encryption key outside the repository and under
  access control;
- expose the web application, Prometheus, Grafana, and the licence issuer only through an authenticated
  reverse proxy or private network as appropriate;
- keep the issuer Ed25519 private key only in the protected issuer environment. Customer installations
  require the public key only.

## Design limits

The first self-hosted release supports a signed offline licence and optional HTTPS online activation.
Revocation data must be updated by the operator. The licence issuer is intentionally not distributed to
customers.
