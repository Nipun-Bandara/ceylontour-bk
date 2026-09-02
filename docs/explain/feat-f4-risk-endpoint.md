# feat/f4-risk-endpoint

**What was built:** `GET /api/risk/{id}?month=` returns a real forecast.
`api/services/forecast.py` loads the trained LightGBM artefact, predicts an
occupancy rate for a region and month, and maps it to a traffic-light band.
`shap_breakdown()` in `api/services/explain.py` says which features drove that
prediction. The recommend endpoint was not touched.

**Bands come from config.** `config/bands.yaml` holds low 0-40 green, medium
41-70 yellow, high 71-100 red. Where "medium" stops and "high" starts is a
judgement someone will question, and it should be a line in a file anyone can
find rather than a number inside a function.

**SHAP is LightGBM's own TreeSHAP**, via `pred_contrib=True`. That is the same
exact algorithm as the `shap` package's TreeExplainer, so this is genuinely the
TreeSHAP the proposal promised, without pulling a heavy dependency into the API
or spending any of the 500ms budget on it.

**Every SHAP value is labelled `"estimated"`, never `"exact"`.** This is the
distinction the whole project turns on. Index contributions are a calculation
anyone can redo with a weight and a factor value. SHAP values are a model's
account of its own output. Presenting them as equally certain would defeat the
point of building an explainable system, and the UI renders them differently
because of it.

**Feature names are grouped into plain English.** `month`, `month_sin` and
`month_cos` all become "time of year": they are one idea split across three
columns for the model's benefit, and three bars all reading "time of year"
would be a broken panel. SHAP values are additive, so summing them into one bar
is legitimate. The percentages are shares of the top five drivers, so they sum
to 100 and fill the panel; features below the cut are left out rather than
folded in.

**Caching.** The booster loads once per process, and every `(region, month)`
answer is kept for the life of the process. A cold call including the model
load measured 98ms and a cached one 5ms, both well inside the 500ms the
acceptance criteria ask for. The cost is that **the API must be restarted after
retraining**, or it keeps serving the old model. That is written in the README.

**Failure modes, none of them a 500.** An unknown destination id is a 404, and
that check runs before the model is touched. A month outside 1-12 is a 422 from
the query validator. If the model has not been trained, or a region has too
little history to build features from, the endpoint answers 503 with a message
saying which — never a made-up number.

**That last case is the state the repo is in today.** There is no committed
artefact, because `region_pressure_history` holds one month and nothing can be
trained from it. Every risk request currently returns:

> `503 {"error": {"code": "forecast_unavailable", "message": "The pressure
> model has not been trained yet. Run \`python ml/train_pressure.py\` and
> restart the API."}}`

The endpoint starts working the moment real data is loaded and training is run.
Nothing else needs changing.

**Verified before merge:** 87 tests pass and `ruff check` is clean. The risk
tests train a real LightGBM model into a temp directory from a synthetic
series, so they do not depend on anyone having trained one. Over HTTP against a
temporarily loaded six-year series, July came back `75.4 high` and January
`44.8 medium` for Sabaragamuwa, Uva read higher than Sabaragamuwa in the same
month, breakdowns summed to exactly 100 with every entry `"estimated"`, and
meta reported `pressure-v1.0`. The synthetic data and every artefact it
produced were removed afterwards.

**Known limitation, and it is a real one.** At training time
`occupancy_lag_1` is the month immediately before the target. At inference the
target may be months ahead, so the most recent *observed* months are used
instead. `occupancy_lag_12` is the genuine article — the same calendar month
last year, which is why it dominates the breakdowns. Fixing this properly means
forecasting one month at a time up to the target. The `pressure_forecast` table
in the schema exists for precomputing exactly that, and nothing writes to it
yet.

**One inconsistency to settle:** the risk endpoint reports the loaded
artefact's version in `meta.model_version`, because the contract promises the
figure can be reproduced later. Every other endpoint still reports the
placeholder from `.env`, which currently says `pressure-v1.2` while the trainer
produces `pressure-v1.0`. Those should be unified, most likely by having
`meta_fields()` read the artefact version whenever one is loaded.
