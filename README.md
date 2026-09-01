# CeylonTour — Backend

Sustainable travel decision support for Sri Lanka. FastAPI service behind
Postgres 16 and Redis 7.

**Status: skeleton.** Every endpoint returns hardcoded mock data that matches
the API contract in `plan.md` section 7. There is no Sustainability Index, no
pressure model and no SHAP yet. The frontend can build against this today.

## Requirements

Docker and Docker Compose. Nothing else needs to be installed to run the API.

## Run it

```bash
cp .env.example .env
```

```bash
docker compose up --build
```

Then create the tables:

```bash
docker compose exec api alembic upgrade head
```

Then load the dataset:

```bash
docker compose exec api python -m ml.seed
```

The API is on <http://localhost:8000>, interactive docs on
<http://localhost:8000/docs>.

```bash
curl http://localhost:8000/health
```

## Dataset

The three CSVs in `ml/data/` are the dataset. `python -m ml.seed` validates all
three, and only writes to the database if every row passes. On a failure it
prints each problem with its file and line number and writes nothing.

Re-running is safe: destinations are matched by name and the other two tables
upsert on their primary keys, so a re-run updates rather than duplicates.

See `ml/data/README.md` for the column formats and where each value comes from.
**The rows currently committed are examples with invented numbers**, kept only
so the loader has something to run against.

### If a port is already taken

`DB_PORT`, `REDIS_PORT` and `API_PORT` in `.env` set the **host** ports only.
Containers always talk to each other on 5432, 6379 and 8000, so changing these
is safe. Set `DB_PORT=5433` and `REDIS_PORT=6380` if another project on your
machine already holds the defaults.

## Hot reload

`docker compose` mounts the repo into the api container and runs uvicorn with
`--reload`. Editing a `.py` file restarts the server. No rebuild needed unless
`requirements.txt` changes.

## Tests

Inside the container:

```bash
docker compose exec api pytest
```

Or on the host, without Docker, because nothing in the tests touches the
database:

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pytest
```

## Lint

```bash
.venv/bin/ruff check .
```

## Migrations

Alembic config is `alembic.ini`, versions live in `api/migrations/versions/`.

```bash
docker compose exec api alembic revision --autogenerate -m "what changed"
```

```bash
docker compose exec api alembic upgrade head
```

`alembic check` reports whether the models and the migrations still agree.

## Endpoints

Every successful response is wrapped:

```json
{ "data": {}, "meta": { "model_version": "...", "index_version": "..." } }
```

Every failure returns the matching HTTP status plus:

```json
{ "error": { "code": "...", "message": "..." } }
```

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness check |
| POST | `/api/recommend` | Ranked destinations with scores and contributions |
| GET | `/api/destinations` | All destinations with coordinates and current band |
| GET | `/api/destinations/{id}` | Single destination detail |
| GET | `/api/risk/{id}?month=` | Pressure forecast, band, SHAP breakdown |
| GET | `/api/alternatives/{id}` | Similar destinations with lower pressure |
| POST | `/api/simulate` | Recomputed score from adjusted inputs |
| GET | `/api/dashboard/summary` | Authority overview (auth not enforced yet) |
| POST | `/api/auth/login` | JWT issue for authority users (mock token) |

## Layout

```
api/
├── main.py          # app, CORS, error handlers, /health
├── config.py        # settings from the environment
├── envelope.py      # the {"data", "meta"} helper
├── database.py      # engine and session factory
├── routers/         # one module per endpoint group, mocks only
├── schemas/         # Pydantic request and response models
├── models/          # SQLAlchemy tables
├── migrations/      # Alembic
└── tests/
ml/
├── seed.py          # validate the CSVs, then load them
├── data/            # the dataset, plus where each value came from
└── tests/
```

## Secrets

`.env` is gitignored. `.env.example` is committed and lists every variable the
app reads. `JWT_SECRET` must be changed before anything is deployed.
