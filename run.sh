#!/usr/bin/env bash
# =============================================================================
# ka11y — restart the stack.
#
#   ./run.sh            stop + rebuild + start. Audit history, users, sessions,
#                       manual verdicts, assets and reports are all kept: every
#                       stateful path is a bind mount under ./output/ (see
#                       docker-compose.yml).
#   ./run.sh --wipe     DESTRUCTIVE. Also deletes ./output/* (PostgreSQL data,
#                       the SQLite run store, assets, artifacts, logs, crawled
#                       images) and the model-cache volumes, for a clean slate.
#                       Asks for confirmation first.
#   ./run.sh -d         pass extra flags to `docker compose up` (e.g. detach).
#
# The previous version of this script ran `docker rm -f $(docker ps -aq)`,
# `docker volume prune -f`, `docker system prune -af` and `docker compose down
# -v` on EVERY start — that is what wiped the history each time (PostgreSQL
# was on a named volume). None of that runs any more unless --wipe is given,
# and even then only this project's containers/volumes are touched.
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

WIPE=0
UP_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --wipe) WIPE=1 ;;
    *) UP_ARGS+=("$arg") ;;
  esac
done

if [[ "$WIPE" == "1" ]]; then
  echo "This deletes ALL audit history, users, sessions, verdicts, assets and reports under ./output/,"
  echo "plus the model-cache volumes. Type 'wipe' to continue:"
  read -r answer
  [[ "$answer" == "wipe" ]] || { echo "aborted"; exit 1; }
  docker compose down -v --remove-orphans
  # PostgreSQL's data dir is root/postgres-owned inside the bind mount.
  sudo rm -rf output/pg output/db output/assets output/artifacts
  rm -rf output/crawled_images output/logs
else
  docker compose down --remove-orphans
fi

docker compose up --build "${UP_ARGS[@]}"
