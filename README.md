# CeylonTour — Backend

Sustainable travel decision support for Sri Lanka. FastAPI service behind
Postgres 16 and Redis 7.

**Status: F2 to F6 done.** `POST /api/recommend` runs the real Sustainability
Index with explanations, `GET /api/risk/{id}` returns a real LightGBM forecast
with a TreeSHAP breakdown, `GET /api/alternatives/{id}` suggests similar
destinations under less pressure, and `POST /api/simulate` re-runs the index
with adjusted inputs. Destinations, dashboard and auth still return hardcoded
mock data matching the API contract in `plan.md` section 7.

`GET /api/risk/{id}` and `GET /api/alternatives/{id}` need a trained model.
Until `ml/train_pressure.py` has been run they answer 503 with a message saying
so, rather than inventing a number.

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

## The Sustainability Index

A transparent weighted sum, not a learned model, so every contribution can be
shown exactly. `config/weights.yaml` holds the weights and the group shift;
`config/cost_bands.yaml` holds the budget a cost band needs. Neither is
hardcoded anywhere in the code. Editing a config file needs an app restart,
because the files are read once and cached.

Budget and duration are **filters applied before scoring**, not scored factors.
A destination the user cannot afford is left out rather than given a low score,
and `meta.excluded` on the response says how many went and why.

## The pressure model

Trains from the database, in two commands:

```bash
docker compose exec api python ml/train_pressure.py
```

```bash
docker compose exec api python ml/evaluate.py
```

Training writes the model to `ml/artifacts/`. Evaluation measures it on the
held-out year against a seasonal-average baseline and writes
`ml/artifacts/model_card.md`. The card reports whichever won, including when
the baseline did.

Both fail with a clear message and write nothing if there is not enough
history. Right now there is not: `region_pressure_history` holds one month, and
the model needs at least 13 consecutive months per region before any row has a
full set of features.

Artifacts are gitignored. A model card is only true of the data it came from,
so committing one would publish accuracy numbers nobody measured.

The API loads the model once at the first risk request and caches every
`(region, month)` answer for the life of the process, so **restart the API
after retraining** or it will keep serving the old model.

## Tests

Run them inside the container. The `/api/recommend` tests need Postgres:

```bash
docker compose exec api pytest
```

They also run on the host, but the database-backed ones **skip** rather than
fail if Postgres is not up, so a green run there does not mean everything
passed. Check the skip count.

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
├── routers/         # one module per endpoint group
├── services/        # index.py, explain.py, forecast.py, similarity.py
├── schemas/         # Pydantic request and response models
├── models/          # SQLAlchemy tables
├── migrations/      # Alembic
└── tests/
ml/
├── seed.py          # validate the CSVs, then load them
├── features.py      # feature engineering for the pressure model
├── train_pressure.py
├── evaluate.py      # metrics and the model card
├── data/            # the dataset, plus where each value came from
├── artifacts/       # generated model files, gitignored
└── tests/
config/
├── weights.yaml     # index weights and the preference shift
├── cost_bands.yaml  # budget each cost band needs
└── bands.yaml       # traffic-light thresholds for visitor pressure
```

## Secrets

`.env` is gitignored. `.env.example` is committed and lists every variable the
app reads. `JWT_SECRET` must be changed before anything is deployed.
