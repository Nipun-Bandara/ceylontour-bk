# CeylonTour Backend

Read `plan.md` and `features.md` in this repo before doing anything.
Section 7 of plan.md is the API contract. It is fixed. Never change a
response shape without being told to.

## Stack (declared in the competition proposal, cannot change)
Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, PostgreSQL 16,
LightGBM, SHAP, pandas, pytest, ruff, Docker Compose.

## Hard rules
1. Every response uses the envelope: {"data": ..., "meta": {"model_version", "index_version"}}.
2. Errors return {"error": {"code", "message"}} with the right HTTP status. Never a 500 for bad input.
3. Index weights load from config/weights.yaml. Never hardcode a weight.
4. Notebooks are for exploring only. Anything the API imports lives in a .py file with a test.
5. Parameterised queries only, through SQLAlchemy. No f-string SQL.
6. Every new third-party package gets added to THIRD_PARTY.md with its licence.
7. Two students must be able to explain this code to judges. Prefer plain,
   obvious code over clever code. Add short comments explaining *why*.
8. Do not add features that were not asked for.

## Layout
See plan.md section 6. Do not invent new top-level folders.

## After every task
Write or update `docs/explain/<branch-name>.md`: 10 to 15 lines in plain English
covering what was built, the main files, and how the logic works.