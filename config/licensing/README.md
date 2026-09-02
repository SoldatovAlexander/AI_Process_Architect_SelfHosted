# Licensing trust configuration

`trusted-public-keys.json` contains Ed25519 public keys only. A key entry has the form
`{"keyId":"issuer-2026-01","publicKey":"<base64url raw 32-byte key>"}`.
Private signing keys must never be placed in this repository or on customer installations.

Issuer operations belong to a separate License Control Plane. The repository contains only the
customer-side trust store and revocation format plus the guarded MVP CLI at `tools/license_control.py`.
Manual self-hosted licenses default to one calendar month and cannot exceed three calendar months.

`revocations.json` is a deployment-owned deny list of signed `licenseId` values. Updating the
file and restarting the API applies revocation without contacting the licensing service.
