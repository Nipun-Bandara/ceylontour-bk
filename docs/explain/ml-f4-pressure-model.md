# ml/f4-pressure-model

**What was built:** the training pipeline for the visitor pressure model.
Three files: `ml/features.py` turns the raw monthly series into a feature
frame, `ml/train_pressure.py` trains a LightGBM regressor, and
`ml/evaluate.py` measures it and writes the model card. Nothing under `api/`
changed; wiring the model into `GET /api/risk/{id}` is a later branch.

**What it predicts:** a region's occupancy rate for a calendar month, 0 to 100.
That number becomes the traffic-light band the risk endpoint returns.

**Every feature is known before the month starts.** Lagged occupancy at 1, 2
and 12 months, a rolling mean of the three months before, the direction of
arrivals over the two previous months, the month as both a raw number and a
sin/cos pair so December sits next to January, a peak-season flag for
December-March and July-August, and the region as a category. The current
month's arrivals and guest nights are deliberately left out. They are known
in the historical table but would not be known in a real forecast, and using
them would make the evaluation look good and the model useless.

**Gaps in the series are handled properly.** Each region is reindexed onto a
gap-free monthly index before the lags are computed. Without that, a missing
month would quietly shift everything, and "occupancy last month" could mean
three months ago. Months that were invented by the reindex have no target, so
they never reach the model.

**No NaN reaches the model.** `build_features` leaves NaNs where a lag does not
exist yet; `model_frame` is what drops them. Keeping the two apart means the
caller can see how many rows were lost rather than having them disappear. The
first twelve months of every region always go, because lag-12 does not exist
for them yet.

**The split is by time and nothing else.** The test set is the most recent full
calendar year; training is everything strictly before it. A part-finished year
after the test year is dropped from both sides so the split stays a clean line.
`time_split` raises rather than returns if training ever overlaps the held-out
year — a raise, not an assert, because asserts vanish under `python -O` and
this is the guarantee the whole evaluation rests on.

**Training and evaluation are separate commands on purpose.** Training never
prints an accuracy number. The only number that counts is the one measured on
the year the model has not seen, and keeping the steps apart makes it harder
to drift into tuning against the test set. The hyperparameters are fixed in the
source and the model card says they were not adjusted after seeing the results.

**The model card cannot flatter the model.** It prints both MAE figures side by
side and states plainly which won. The losing sentence is as prominent as the
winning one: "The model's MAE is 1.81 points *worse* than the seasonal average.
The simple baseline is the better predictor on this data, and the demo should
say so."

**Verified before merge:** 24 ml tests pass and `ruff check` is clean. Against
the real database the pipeline refuses to train, exits 1 and writes nothing,
because one month of history cannot produce a single complete feature row.
Against a synthetic seven-year series it trained on 240 rows, held out 48, and
produced a full card. A deliberately noisy series made the model lose, and the
card reported the loss rather than hiding it. A 31-month series produced the
loud warning and the short-series banner in the card.

**Artifacts are gitignored.** A model card is only true of the data it was
generated from. Committing one produced from example rows would put fabricated
accuracy numbers in the repository, which is the exact opposite of what a model
card is for. `ml/artifacts/README.md` explains how to regenerate them.

**One thing the Dockerfile needed:** LightGBM links against the OpenMP runtime,
which `python:3.11-slim` does not ship, so `import lightgbm` failed inside the
container with a missing `libgomp.so.1`. The image now installs `libgomp1`.
This would have shown up on the demo machine and nowhere else.

**Left open on purpose:** SHAP is not here. F4 needs a TreeSHAP breakdown on
the risk endpoint, but that is API work and this branch is `ml/` only. The
model version is `pressure-v1.0` while `MODEL_VERSION` in `.env` still says
`pressure-v1.2` from the skeleton; they need reconciling when the risk endpoint
is wired up, since the contract promises the returned version identifies the
model that produced the number.
