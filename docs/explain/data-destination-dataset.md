# data/destination-dataset

**What was built:** the way data gets from a spreadsheet into Postgres. Three
CSV templates under `ml/data/`, and `ml/seed.py`, which checks them and loads
them. No API code changed on this branch. The API still returns mocks.

**Why CSV.** N is compiling the dataset by hand from SLTDA reports and
Open-Meteo pulls. A spreadsheet is what that work naturally produces, and a CSV
in git means every change to a factor value shows up in a diff and can be
argued about. Loading straight from the API would hide all of that.

**Run it with** `python -m ml.seed`, or `--data-dir` to point at a different
folder, which is how the tests and the failure demos run it.

**Validate first, load second.** The script reads all three files, collects
*every* problem across all of them, and only then decides whether to touch the
database. If there is even one problem it prints the whole list and exits 1
without opening a write. That ordering is the important part: a dataset that
loaded halfway is much harder to notice than one that did not load at all,
because the API will happily serve the half of it that made it in.

**What gets checked:** the five factor values are 0 to 100, `source_ref` is not
empty, `confidence` is exactly `measured` or `estimated`, lat/lon fall inside
Sri Lanka's bounding box, and no destination name is used twice. It also checks
every destination has a factor row, because M1 is not reached until every
factor value has a source and a confidence flag. Errors name the file and the
line number, so a message reads `destinations.csv line 3: lat 48.85 is outside
Sri Lanka (5.9 to 9.9)` and the fix is obvious without reading the script.

**Reading the CSVs.** pandas reads every column as a string with
`keep_default_na=False`, then numbers are converted explicitly. Without that,
pandas turns a blank `source_ref` into NaN and the empty check cannot see it,
and a typo in a number crashes instead of producing a readable message.

**Loading is a re-runnable upsert.** `destination_factors` and
`region_pressure_history` have natural primary keys, so those use Postgres
`ON CONFLICT DO UPDATE`. `destinations` has a surrogate id and nothing to
conflict on, so the script matches existing rows by name and updates them.
Running the seed twice in a row gives `0 inserted, 3 updated` and still three
rows, not six. That matters because fixing one wrong value should not mean
dropping the database.

**Tests** (`ml/tests/`) run the validator against small fixture CSVs and never
touch Postgres, so they run without docker compose up: a good file passes, a
blank `source_ref` fails, a factor value of 150 fails, plus coordinates outside
Sri Lanka, a duplicate name, a bad confidence word, and a missing factor row.
One test validates the real committed CSVs, which catches a bad hand-edit
before anyone tries to load it.

**Verified before merge:** 19 tests pass, `ruff check` is clean, and against a
real Postgres 16 the bad fixture exits 1 with `destinations` still empty, the
real CSVs load 3/3/3 with a measured-versus-estimated split of 2 and 1, and a
second run updates instead of duplicating.

**Left open on purpose:** the three rows in each CSV are examples with invented
numbers, and every `source_ref` says `EXAMPLE ROW - replace with a real
citation` so none of them can be mistaken for a real source. N replaces them
with the real 15 to 20 destinations. `destinations.name` has no unique
constraint in the database yet; the seed enforces uniqueness, but adding the
constraint would make it safe against any other write path too.
