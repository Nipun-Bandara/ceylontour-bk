#!/usr/bin/env sh
#
# One command from a cold container to a serving API:
#
#   1. wait for Postgres
#   2. apply migrations
#   3. load the dataset from ml/data/*.csv
#   4. create the authority account, if a password is configured
#   5. make sure a model artefact exists
#   6. start gunicorn
#
# Every step is safe to repeat, so restarting a container is never a
# destructive act.
#
# Steps 1 to 3 are required and abort the start if they fail: an API serving
# from an unmigrated or empty database is worse than one that does not start.
# Steps 4 and 5 are optional and only warn, because the API is still useful
# without a dashboard login or a trained model.

set -eu

WORKERS="${GUNICORN_WORKERS:-2}"
BIND="${GUNICORN_BIND:-0.0.0.0:8000}"
TIMEOUT="${GUNICORN_TIMEOUT:-60}"

say() {
    echo "[bootstrap] $*"
}

say "1/5 waiting for the database"
python - <<'PYTHON'
import sys
import time

from sqlalchemy import text

from api.database import engine

DEADLINE = 60
started = time.monotonic()
while True:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        print("[bootstrap]     database is up")
        break
    except Exception as exc:  # noqa: BLE001 - any failure means "not ready"
        if time.monotonic() - started > DEADLINE:
            print(f"[bootstrap]     giving up after {DEADLINE}s: {exc}", file=sys.stderr)
            sys.exit(1)
        time.sleep(1)
PYTHON

say "2/5 applying migrations"
alembic upgrade head

say "3/5 loading the dataset"
python -m ml.seed

say "4/5 creating the authority account"
if [ -n "${AUTHORITY_PASSWORD:-}" ]; then
    python -m api.seed_user
else
    say "    AUTHORITY_PASSWORD is not set, skipping."
    say "    The dashboard will have no account to log in with."
fi

say "5/5 checking for a model artefact"
if [ -f ml/artifacts/pressure-v1.0.txt ]; then
    say "    found ml/artifacts/pressure-v1.0.txt"
else
    say "    no artefact; trying to train one from the loaded history"
    if python ml/train_pressure.py; then
        python ml/evaluate.py || say "    evaluation failed; the model card was not written"
    else
        say "    NOT ENOUGH HISTORY TO TRAIN."
        say "    The API will start, but /api/risk, /api/alternatives,"
        say "    /api/destinations and the dashboard will answer 503 until"
        say "    region_pressure_history has 13+ months per region and"
        say "    ml/train_pressure.py has been run."
    fi
fi

# RELOAD=1 is the development switch. Set only by docker-compose.yml, so a
# developer gets the same migrate-seed-train sequence as production and then a
# reloading server instead of gunicorn. Keeping one script means `docker
# compose up` on a clean machine cannot end up with an empty database.
if [ "${RELOAD:-0}" = "1" ]; then
    say "starting uvicorn with --reload on ${BIND}"
    exec uvicorn api.main:app --host "${BIND%:*}" --port "${BIND##*:}" --reload
fi

say "starting gunicorn on ${BIND} with ${WORKERS} uvicorn workers"
exec gunicorn api.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers "${WORKERS}" \
    --bind "${BIND}" \
    --timeout "${TIMEOUT}" \
    --access-logfile - \
    --error-logfile -
