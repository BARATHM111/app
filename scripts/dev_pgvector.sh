#!/usr/bin/env bash
# Local PostgreSQL 15 + pgvector 0.8.0 for verifying the Prisma migrations and the pgvector store.
# Neon supports pgvector 0.8.0 on Postgres 14-17, so this mirrors the production target.
# Usage: bash /app/scripts/dev_pgvector.sh   (idempotent; DB at postgresql://postgres@127.0.0.1:54329/barterx_dev)
set -euo pipefail
PGBIN=/usr/lib/postgresql/15/bin
DATA=${PGDEV_DATA:-/var/lib/barterx-pgdev/data}
CLI=${PGDEV_CLI:-/root/pgdev/prisma}
URL="postgresql://postgres@127.0.0.1:54329/barterx_dev"

if [ ! -x "$PGBIN/postgres" ]; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq postgresql-15 postgresql-server-dev-15 build-essential git >/dev/null
fi
if [ ! -f "$(sudo -u postgres $PGBIN/pg_config --sharedir 2>/dev/null || echo /usr/share/postgresql/15)/extension/vector.control" ] && [ ! -f /usr/share/postgresql/15/extension/vector.control ]; then
  rm -rf /tmp/pgvector && git clone -q --branch v0.8.0 --depth 1 https://github.com/pgvector/pgvector.git /tmp/pgvector
  (cd /tmp/pgvector && make -s >/dev/null && sudo make -s install >/dev/null)
fi
sudo mkdir -p "$DATA" && sudo chown -R postgres:postgres "$(dirname "$DATA")"
[ -f "$DATA/PG_VERSION" ] || sudo -u postgres $PGBIN/initdb -D "$DATA" -A trust >/dev/null
sudo -u postgres $PGBIN/pg_ctl -D "$DATA" -o "-p 54329 -k /tmp" -l "$(dirname "$DATA")/pg.log" status >/dev/null 2>&1 \
  || sudo -u postgres $PGBIN/pg_ctl -D "$DATA" -o "-p 54329 -k /tmp" -l "$(dirname "$DATA")/pg.log" start >/dev/null
sleep 2
psql -h 127.0.0.1 -p 54329 -U postgres -tc "select 1 from pg_database where datname='barterx_dev'" | grep -q 1 \
  || psql -h 127.0.0.1 -p 54329 -U postgres -qc "create database barterx_dev"

mkdir -p "$CLI" && cd "$CLI"
[ -f package.json ] || yarn init -y >/dev/null 2>&1
[ -x node_modules/.bin/prisma ] || yarn add -s prisma@6.19.0 >/dev/null 2>&1
export DATABASE_URL="$URL" DIRECT_URL="$URL"
npx prisma validate --schema /app/prisma/schema.prisma
npx prisma migrate deploy --schema /app/prisma/schema.prisma | tail -2
npx prisma migrate diff --from-url "$URL" --to-schema-datamodel /app/prisma/schema.prisma --exit-code >/dev/null \
  && echo "No drift: migrated database matches schema.prisma"
psql -h 127.0.0.1 -p 54329 -U postgres -d barterx_dev -tc "select 'pgvector ' || extversion from pg_extension where extname='vector'"
