# chore/deploy-docs

Everything needed to run this on a machine that is not the laptop it was
written on, plus the documentation a judge and a teammate each need.

## What was built

**A production image.** `api/Dockerfile` now installs `libgomp1` for LightGBM,
copies the source, creates a normal user `app` at uid 1000 and switches to it.
Nothing runs as root. uid 1000 is deliberate: it matches the usual first host
account, so the development bind mount stays writable and `train_pressure.py`
can still save an artefact.

**One bootstrap for both environments.** `bootstrap.sh` waits for Postgres,
applies migrations, loads the dataset, creates the authority account if a
password is configured, trains a model if one is missing and there is enough
history, then starts gunicorn with uvicorn workers. Steps 1 to 3 abort the
start if they fail, because an API serving from an unmigrated database is worse
than one that does not start. Steps 4 and 5 only warn: the API is still useful
without a dashboard login or a trained model.

**A production compose file.** `docker-compose.prod.yml` runs the same images
with no host mounts, no published database or Redis ports, a named volume for
model artefacts so a retrain survives a rebuild, restart policies, and a
container healthcheck that polls `/health`.

## The bug the fresh-clone test found

The first fresh-clone run returned `HTTP 200` from `/health` — and the database
had **zero tables**.

`docker-compose.yml` overrode the image's command with
`uvicorn --reload`, so `bootstrap.sh` never ran. Anyone following the README
would have got a healthy-looking API on an empty database, and every real
endpoint would have failed on first use. `/health` passing is exactly what made
it easy to miss.

The fix was to stop having two start paths. `bootstrap.sh` now takes a
`RELOAD=1` switch, set only by the development compose file, which makes it
finish with a reloading uvicorn instead of gunicorn. Development and production
run the same migrate-seed-train sequence. A clean clone cannot come up against
an unmigrated database any more.

Re-verified afterwards: 8 tables, 3 destinations loaded, `/api/recommend`
returning real scored results, and `id` inside the container reporting
`uid=1000(app)`.

## How the verification was done

`git clone` would not have proved anything, because nothing on this branch is
committed yet — a clone would have contained only `CLAUDE.md`. Instead the test
copied exactly the files a clone *will* contain, `git ls-files -co
--exclude-standard`, into an empty directory: 105 files, no `.env`, no `.venv`,
no artefacts. Then the README steps were followed literally.

Both stacks were verified from that copy:

- **Development**: `cp .env.example .env` then `docker compose up --build`.
  `/health` returned 200, 8 tables existed, the dataset was loaded, and
  `/api/recommend` returned real scores with explanations.
- **Production**: `ENVIRONMENT=production` with a real secret and an `https://`
  origin, then `docker compose -f docker-compose.prod.yml up --build -d`.
  gunicorn booted two uvicorn workers, the container healthcheck went green,
  the authority account was created by bootstrap and logged in successfully,
  and neither Postgres nor Redis published a host port. A restart re-ran
  bootstrap cleanly and reported the account as *updated*, not duplicated.

## Licences: checked, not guessed

Every licence in `THIRD_PARTY.md` was read from the installed package's own
metadata rather than from memory, and the command that does it is in the file
so it can be re-run after any dependency change.

Two results worth knowing:

- **psycopg 3 is LGPL-3.0**, the only copyleft licence in the runtime list.
  Using it as an unmodified library imported at runtime is exactly what LGPL
  permits, and it imposes nothing on this project's code. But "they were all
  MIT" would have been a wrong answer to a fair question, and this is the sort
  of thing Guidelines 7.3 exists for.
- **email-validator is Unlicense**, effectively public domain.

Base images and `libgomp1` are listed too. `libgomp1` is GPL-3.0 but carries
the GCC Runtime Library Exception, which exists precisely so linking against it
does not impose the GPL on the program using it.

## Documentation

`README.md` was rewritten: what the project is, the exact-versus-estimated
distinction it turns on, a mermaid architecture diagram, prerequisites, clone
to running in three commands, a full environment variable table, how to run
tests, how to retrain, and where the model card lives and why it is gitignored.

`docs/DEMO.md` is the click path, timed at six to seven minutes, with the exact
form values, what to say at each screen, the questions to have answers ready
for, and what to do when something breaks on stage.

**The demo destination was measured, not chosen.** A sweep of all three
destinations across all twelve months put **Ella, month 8** at the top:
pressure 81.0, band high, with alternatives returning Belihuloya at 54%
similarity and low pressure. Ella is also the honest choice because it is the
one destination with a genuinely poor crowd score. The sweep command is in
`DEMO.md` so it can be re-run once the real SLTDA series lands, because the
busiest destination will very likely move.

## Left open

**The dataset is still three example rows.** Everything above works, but the
numbers in it are invented and every `source_ref` says so. Bootstrap tells you
loudly that it cannot train, and the four model-dependent endpoints return 503
until real history is loaded. That is the single biggest remaining item, and it
is N's dataset work rather than anything in this branch.

**Dev and test dependencies are in the production image.** pytest, httpx and
ruff get installed because there is one `requirements.txt` and `THIRD_PARTY.md`
is meant to mirror it exactly. Splitting into `requirements-dev.txt` would trim
the image; it was left alone to keep the licence table and the requirements
file in step.

**Rate limiting is still per-process.** Two gunicorn workers means two
independent counters, so the effective limit is roughly double what `.env`
says. slowapi takes a Redis URI for shared storage and Redis is already
running, so this is a one-line change when it matters.
