# feat/f2-sustainability-index

**What was built:** the Sustainability Index, and `POST /api/recommend` wired
to it. The mock is gone. The endpoint now reads destinations out of Postgres,
filters them, scores them, and returns them ranked. `explanation` is still an
empty string; F3 fills it.

**Why it is not a learned model.** It is a weighted sum on purpose. Every
contribution can be traced back to a weight and a factor value, which is what
lets the UI label these `"exact"` while the SHAP values on the risk endpoint
are labelled `"estimated"`. That distinction is in the proposal, and a model
here would destroy it.

**Weights live in config** (`config/weights.yaml`), never in the code. The five
base weights come straight from features.md F2 and must sum to 1.0;
`load_weights()` refuses to start if they do not, if a factor is missing, or if
the two groups do not cover all five. It caches with `lru_cache`, so scoring 20
destinations reads the file once, not 20 times. Editing the file needs a
restart.

**The preference shift.** `apply_preference()` moves 0.10 of weight from the
personal-fit group (suitability, infrastructure) to the sustainability group
(environmental, crowd, community) when the user asks for `high`, and the other
way for `low`. Inside each group the split stays proportional, so the shift
changes how much the group matters without reordering the factors within it.
The result is renormalised so it sums to exactly 1.0 rather than 0.9999999.
On the seeded data the effect is visible: Ella, which is crowded but has good
infrastructure, drops from 70 to 65 going from `low` to `high`, while Meemure,
which is quiet but poorly served, rises from 84 to 88.

**Scoring.** `score()` returns the total and each factor's contribution as a
percent of it. Because the weights sum to 1.0 and factor values are 0 to 100,
the total is also 0 to 100. The API contract types `percent` as an integer, so
`round_percentages()` rounds them with the largest-remainder method, giving
leftover points to the biggest fractions. Rounding each one on its own would
produce bars adding to 99 or 101, and F3 promises they sum to 100.

**Filters, not penalties.** Budget and duration exclude a destination rather
than score it down, which is what features.md F2 asks for. The budget a cost
band needs lives in `config/cost_bands.yaml`. Because "every destination gets
scored, no silent drops" is an acceptance criterion, the response reports what
went: `meta.excluded` carries a total plus counts for `over_budget`,
`over_duration` and `missing_factors`. Scored plus excluded always accounts for
every row in the table, and there is a test that says so. Only `/api/recommend`
returns this richer meta; every other endpoint is unchanged.

**Bad input still never 500s.** A preference word that is not in the config is
something no Pydantic schema can catch, so the service raises `InvalidInput`
and the app turns that into a 422 with the usual error shape.

**Verified before merge:** 42 tests pass against real Postgres inside docker
compose, `ruff check` is clean, and over HTTP the endpoint ranks the three
seeded destinations correctly, returns contributions summing to exactly 100 in
every case, excludes Ella on a 20,000 budget with `over_budget: 1`, excludes
two destinations on a 2-day trip with `over_duration: 2`, and answers an
unknown preference word with a 422.

**Left open on purpose:** `interest` and `crowd_preference` are accepted and
validated but do not affect the score yet; nothing in F2 says how they should.
The figures in `config/cost_bands.yaml` are placeholders nobody has researched,
and they decide what a user is shown, so they need real numbers before the
demo. `meta.index_version` now comes from the weights file rather than the
environment, so it names the weights that actually produced the score.
