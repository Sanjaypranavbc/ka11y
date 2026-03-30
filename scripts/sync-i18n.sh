#!/usr/bin/env bash
# sync-i18n.sh — Copy the master i18n/ to both service directories.
# Run this after editing ka11y/i18n/rules.yml or any locale file.
#
# Usage: ./scripts/sync-i18n.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/i18n"

for dest in "$ROOT/ka11y-node/i18n" "$ROOT/ka11y-python/i18n"; do
  echo "Syncing $SRC → $dest"
  rsync -a --delete "$SRC/" "$dest/"
done

echo "Done. Both services are in sync with $SRC"
