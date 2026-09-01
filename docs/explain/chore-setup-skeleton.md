# chore/setup-skeleton

**What was built:** the empty shell of the backend. Every endpoint in the API
contract exists and answers with hardcoded mock data in the right shape. There
is no Sustainability Index, no LightGBM model and no SHAP in this branch. The
point is that D can build the whole frontend against real HTTP responses while
N is still compiling the dataset, so neither of us is blocked.

**Running it:** `docker compose up --build` starts Postgres 16, Redis 7 and the
API. The db and cache services have healthchecks and the API waits on them, so
it never starts against a database that cannot answer yet. The repo is mounted
into the API container and uvicorn runs with `--reload`, so edits restart the
server without a rebuild.

**The envelope.** `api/envelope.py` has one function that wraps a payload as
`{"data": ..., "meta": {...}}` and reads `model_version` and `index_version`
from settings. Every route calls it, so no route can forget the meta block and
the versions are defined in exactly one place. Traceability was promised in the
proposal: any explanation shown to a user can be matched back to the versions
that produced it.

**Errors.** `api/main.py` registers three exception handlers. Bad input becomes
a 422 with a readable message, HTTP errors keep the status FastAPI chose, and
anything unhandled becomes a 500 with the internal detail stripped out. All
three produce `{"error": {"code", "message"}}`. This is what keeps the promise
that malformed input never returns a raw 500.

**Schemas** (`api/schemas/`) are the contract in code. `recommend.py` uses the
field names from plan.md section 7 exactly. `common.py` holds the pieces that
repeat: the envelope, the five factor scores, and `Contribution`, which carries
a `type` of `"exact"` for index contributions or `"estimated"` for SHAP values.
Keeping those two labelled apart is the whole point of an explainable system.

**Models** (`api/models/`) are the seven tables from plan.md section 8, with a
single Alembic migration that creates them. Latitude and longitude are plain
float columns, not PostGIS, per cut 2 in the cut ladder: 15 to 20 fixed markers
do not need a GIS extension. Where a table has a natural key, such as region +
year + month in `region_pressure_history`, that is the primary key rather than
an invented id column.

**Tests** (`api/tests/`) are one per endpoint. Each asserts a 200 and then
validates the body against the same Pydantic model the route declares, so a
router that returns a field the schema does not know about, or drops one it
should have, fails the test. One extra test covers the bad-input path. Nothing
touches the database, so `pytest` runs without docker compose up.

**Verified before merge:** all 10 tests pass, `ruff check` is clean, the
migration applies to a real Postgres 16 and `alembic check` reports no drift
between the models and the migration, and all nine endpoints return 200 over
HTTP with the CORS header for `localhost:3000`.

**Left open on purpose:** `/api/dashboard/summary` is marked auth-required in
the contract but the JWT check is not built yet, and `/api/auth/login` returns
a mock token without hashing or verifying anything. Both land with F8.
