#!/usr/bin/env bash
# Prueba las migraciones de supabase/ en un PostgreSQL temporal, sin Docker
# ni red: crea un clúster en una carpeta temporal, carga la imitación mínima
# de Supabase, aplica las migraciones en orden y ejecuta las pruebas pgTAP.
# El clúster se borra al terminar.
#
# Requisitos: PostgreSQL (initdb, pg_ctl, psql), pgTAP y pg_prove.
#   Debian/Ubuntu: apt install postgresql-16 postgresql-16-pgtap
#
# La prueba de referencia sigue siendo `supabase test db` con la CLI oficial.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

bindir="${PG_BINDIR:-}"
if [[ -z "$bindir" ]]; then
    for candidate in /usr/lib/postgresql/*/bin; do
        [[ -x "$candidate/initdb" ]] && bindir="$candidate"
    done
fi
if [[ -z "$bindir" || ! -x "$bindir/initdb" ]]; then
    echo "No se encuentra initdb; define PG_BINDIR" >&2
    exit 2
fi
command -v pg_prove >/dev/null || { echo "Falta pg_prove (pgTAP)" >&2; exit 2; }

work="$(mktemp -d)"
cleanup() {
    "$bindir/pg_ctl" -D "$work/data" -m immediate stop >/dev/null 2>&1 || true
    rm -rf "$work"
}
trap cleanup EXIT

"$bindir/initdb" -D "$work/data" -U postgres -A trust --no-sync >/dev/null
"$bindir/pg_ctl" -D "$work/data" -l "$work/log" -w \
    -o "-k $work -c listen_addresses='' -c fsync=off" start >/dev/null

export PGHOST="$work" PGUSER=postgres PGDATABASE=postgres
psql_run() { psql -X -q -v ON_ERROR_STOP=1 "$@"; }

psql_run -c "alter database postgres set search_path = \"\$user\", public, extensions"
psql_run -f "$repo/scripts/db/supabase_minimo.sql"
for migration in "$repo"/supabase/migrations/*.sql; do
    echo "Migración: $(basename "$migration")"
    psql_run --single-transaction -f "$migration"
done

pg_prove --ext .sql -r "$repo/supabase/tests"
