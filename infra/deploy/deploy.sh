#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

release_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
DEPLOY_ROOT="$(cd -- "$release_dir/../.." && pwd -P)"
export DEPLOY_ROOT
[[ "$release_dir" == "$DEPLOY_ROOT/releases/"* ]] || { echo 'Run from DEPLOY_ROOT/releases/<release>/deploy.sh'; exit 1; }
for file in "$DEPLOY_ROOT/.env" "$DEPLOY_ROOT/backend.env" "$release_dir/release.env"; do
  [[ -s "$file" ]] || { echo "Missing configuration: $file"; exit 1; }
done

# Protect manual deployments as well as Actions runs.
exec 9>"$DEPLOY_ROOT/.deploy.lock"
flock -n 9 || { echo 'Another deployment is running.'; exit 1; }
compose_files=(-f "$release_dir/compose.yaml")
if [[ -f "$DEPLOY_ROOT/compose.override.yaml" ]]; then
  compose_files+=(-f "$DEPLOY_ROOT/compose.override.yaml")
fi
dc() {
  docker compose --project-name zhigenews-prod \
    --env-file "$DEPLOY_ROOT/.env" --env-file "$release_dir/release.env" \
    "${compose_files[@]}" "$@"
}
on_error() {
  echo 'Deployment failed; current still identifies the last successful release.' >&2
  echo 'Services may be stopped or partly updated. Inspect status and follow docs/deployment.md.' >&2
  dc ps >&2 || true
}
trap on_error ERR

dc config --quiet
mkdir -p "$DEPLOY_ROOT/data" "$DEPLOY_ROOT/backups"
dc pull mysql redis api worker beat web sandbox
# Validate keys before interrupting the active services. No values are printed.
dc run --rm --no-deps api python -c '
from cryptography.fernet import Fernet
from zhigenews.settings import get_settings
s = get_settings()
Fernet(s.secret_encryption_key.encode())
assert len(s.ip_hash_key) >= 32, "IP_HASH_KEY must be at least 32 characters"
assert len(s.admin_password) >= 12, "ADMIN_PASSWORD must be at least 12 characters"
assert s.openai_model and s.openai_api_key and s.tavily_api_key, "Configure model and Tavily credentials"
'

# Drain worker while the old API and scheduler no longer accept/create work.
dc stop beat api
dc stop worker
dc up -d --wait --wait-timeout 300 mysql redis
if [[ -f "$DEPLOY_ROOT/.initialized" ]]; then
  backup="$DEPLOY_ROOT/backups/$(date -u +%Y%m%dT%H%M%SZ)-$(basename "$release_dir").sql.gz"
  # Expand the database password inside the container, not on the host.
  # shellcheck disable=SC2016
  dc exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -u root --single-transaction --routines --triggers --events --no-tablespaces --set-gtid-purged=OFF zhigenews' | gzip > "$backup"
  echo "Database backup: $backup"
fi
dc run --rm --no-deps api alembic upgrade head
# init also seeds sources, so it must NOT run on every deployment.
if [[ ! -f "$DEPLOY_ROOT/.initialized" ]]; then
  dc run --rm --no-deps api python -m zhigenews.cli init
  touch "$DEPLOY_ROOT/.initialized"
fi
dc run --rm --no-deps api python -m zhigenews.cli migrate-news
dc up -d --wait --wait-timeout 240 api worker beat web

for key in USER_DOMAIN ADMIN_DOMAIN; do
  domain="$(dc exec -T web printenv "$key")"
  curl --fail --silent --show-error --retry 12 --retry-all-errors --retry-delay 5 \
    --connect-timeout 10 --max-time 20 "https://$domain/healthz"
  curl --fail --silent --show-error --output /dev/null \
    --connect-timeout 10 --max-time 20 "https://$domain/"
done

previous="$(readlink "$DEPLOY_ROOT/current" || true)"
if [[ -n "$previous" && "$previous" != "$release_dir" ]]; then
  ln -sfn "$previous" "$DEPLOY_ROOT/previous"
fi
ln -sfn "$release_dir" "$DEPLOY_ROOT/current"
dc ps
echo "Deployment complete: $(basename "$release_dir")"
