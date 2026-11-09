#!/usr/bin/env bash
# A throwaway Postgres, for the migration tests. Start, test, stop.
#
#   scripts/pg-test.sh start     # initdb + start on port 55432
#   scripts/pg-test.sh stop
#
# Why this exists: `tests/test_migrations_pg.py` caught a runner that executed SQL and never recorded the
# version — a bug no fake cursor could show, because the fault was in what was NOT executed. A database in
# a temp directory makes that test runnable on any machine, in seconds, with nothing installed but postgres.
set -uo pipefail

PGDATA="${PGDATA:-/tmp/pgvision}"
PGPORT="${PGPORT:-55432}"
DB="${DB:-llmtest}"
CMD="${1:-start}"

case "$CMD" in
  start)
    if [ -d "$PGDATA" ]; then
      pg_ctl -D "$PGDATA" status >/dev/null 2>&1 && pg_ctl -D "$PGDATA" stop -m fast >/dev/null 2>&1
      rm -rf "$PGDATA"
    fi
    initdb -D "$PGDATA" -U postgres --auth=trust -E UTF8 >/dev/null 2>&1 || {
      echo "initdb failed; is postgres installed?" >&2; exit 1; }
    pg_ctl -D "$PGDATA" -o "-p $PGPORT -k /tmp" -l "$PGDATA.log" start >/dev/null 2>&1 || {
      echo "could not start postgres on $PGPORT" >&2; exit 1; }
    sleep 2
    psql -h /tmp -p "$PGPORT" -U postgres -c "CREATE DATABASE $DB;" >/dev/null 2>&1
    echo "postgres ready: host=/tmp port=$PGPORT dbname=$DB"
    echo "run: TEST_PG_DSN='host=/tmp port=$PGPORT user=postgres dbname=$DB' pytest tests/test_migrations_pg.py"
    ;;
  stop)
    pg_ctl -D "$PGDATA" stop -m fast >/dev/null 2>&1 || true
    rm -rf "$PGDATA" "$PGDATA.log"
    echo "stopped and removed $PGDATA"
    ;;
  *)
    echo "usage: $0 {start|stop}" >&2; exit 2 ;;
esac
