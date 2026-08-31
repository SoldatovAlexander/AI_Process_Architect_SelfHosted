# Self-hosted Public Release Status

The installable self-hosted source package is published from reviewed upstream revision `2f0651b86c07a48dc6aceca238be2fa6e11d7c28`.

It passed source-boundary audit, clean Ubuntu/Docker smoke acceptance, and backup-restore acceptance. It excludes hosted billing, payment adapters, service administration, license activation, issuer keys, and customer data.

Before tagging a numbered public release, run `scripts/audit-self-hosted-release.sh`, regenerate the SBOM, and publish fresh source-archive checksums.
