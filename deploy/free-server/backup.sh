#!/bin/sh
# Database backups to Cloudflare R2 (or any S3-compatible store) for the free server.
#
#   (no argument)   run forever: one backup a day at BACKUP_HOUR (UTC), keep BACKUP_KEEP_DAYS days
#   now             one backup now:   docker compose run --rm backup now
#   list            list backups:     docker compose run --rm backup list
#   restore FILE    restore one:      docker compose run --rm backup restore afe-20261001-0100.dump
#                   (stop api and worker first: docker compose stop api worker)
set -eu

apk add --no-cache rclone >/dev/null

export RCLONE_CONFIG_R2_TYPE=s3
export RCLONE_CONFIG_R2_PROVIDER=Cloudflare
export RCLONE_CONFIG_R2_ACCESS_KEY_ID="${R2_ACCESS_KEY_ID:?set R2_ACCESS_KEY_ID in .env}"
export RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="${R2_SECRET_ACCESS_KEY:?set R2_SECRET_ACCESS_KEY in .env}"
export RCLONE_CONFIG_R2_ENDPOINT="${R2_ENDPOINT:?set R2_ENDPOINT in .env}"
export RCLONE_CONFIG_R2_NO_CHECK_BUCKET=true
DEST="r2:${R2_BACKUP_BUCKET:?set R2_BACKUP_BUCKET in .env}/db"

backup() {
  name="afe-$(date -u +%Y%m%d-%H%M).dump"
  pg_dump --format=custom --file="/tmp/$name"
  rclone copyto "/tmp/$name" "$DEST/$name"
  rm -f "/tmp/$name"
  rclone delete --min-age "${BACKUP_KEEP_DAYS:-30}d" "$DEST/"
  echo "{\"event\":\"backup_done\",\"file\":\"$name\"}"
}

case "${1:-}" in
  now) backup; exit 0 ;;
  list) rclone lsl "$DEST/"; exit 0 ;;
  restore)
    file="${2:?name the backup to restore, e.g. afe-20261001-0100.dump}"
    rclone copyto "$DEST/$file" "/tmp/$file"
    pg_restore --clean --if-exists --no-owner --dbname="$PGDATABASE" "/tmp/$file"
    echo "{\"event\":\"restore_done\",\"file\":\"$file\"}"
    exit 0 ;;
esac

hour="${BACKUP_HOUR:-1}"
while true; do
  now=$(date -u +%s)
  wait=$(( (hour * 3600 - now % 86400 + 86400) % 86400 ))
  [ "$wait" -eq 0 ] && wait=86400
  sleep "$wait"
  if ! backup; then
    echo "{\"event\":\"backup_failed\"}"
  fi
done
