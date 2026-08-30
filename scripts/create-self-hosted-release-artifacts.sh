#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT="${1:-}"
REVISION="${2:-HEAD}"

if [[ -z "$OUTPUT" ]]; then
  printf 'usage: %s OUTPUT_DIRECTORY [GIT_REVISION]\n' "$0" >&2
  exit 2
fi

REVISION="$(git -C "$ROOT" rev-parse --verify "$REVISION^{commit}")"
mkdir -p "$OUTPUT"
OUTPUT="$(cd "$OUTPUT" && pwd)"
PACKAGE="$OUTPUT/ai-process-architect-self-hosted"
ARCHIVE="$OUTPUT/ai-process-architect-self-hosted-${REVISION}.tar.gz"

if [[ -e "$PACKAGE" || -e "$ARCHIVE" ]]; then
  printf 'release artifact path already exists in %s\n' "$OUTPUT" >&2
  exit 2
fi

"$ROOT/scripts/assemble-self-hosted-public.sh" "$PACKAGE" "$REVISION"
"$PACKAGE/scripts/audit-self-hosted-release.sh"
"$PACKAGE/scripts/generate-self-hosted-sbom.py" --root "$PACKAGE" --output "$OUTPUT/self-hosted-sbom.cdx.json"
tar -C "$OUTPUT" -czf "$ARCHIVE" "$(basename "$PACKAGE")"
(cd "$OUTPUT" && sha256sum "$(basename "$ARCHIVE")" self-hosted-sbom.cdx.json > SHA256SUMS)

printf 'self-hosted-artifacts=%s\n' "$OUTPUT"
