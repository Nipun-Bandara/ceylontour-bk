# Demo script

Rehearse this three times before the 12th, and time it. Have screenshots ready
in case the network fails.

Target length: **6 to 7 minutes**, leaving time for questions.

---

## Before you start

Everything below assumes a trained model. Without one, half the demo returns
503.

```bash
docker compose up --build -d
```

```bash
docker compose exec api python ml/train_pressure.py && docker compose exec api python ml/evaluate.py && docker compose restart api
```

Confirm all four in this order. If any fails, stop and fix it before demoing.

```bash
curl -s localhost:8000/health
```

```bash
curl -s "localhost:8000/api/risk/3?month=8" | head -c 120
```

```bash
curl -s localhost:8000/api/destinations | head -c 120
```

```bash
curl -s -X POST localhost:8000/api/auth/login -H 'content-type: application/json' -d '{"email":"authority@ceylontour.lk","password":"'"$AUTHORITY_PASSWORD"'"}' | head -c 120
```

Have the model card open in a tab: `ml/artifacts/model_card.md`. You will be
asked about it.

## Confirming which destination to use

**Re-run this after loading the real SLTDA data.** The numbers below were
measured against the current dataset, and the busiest destination may move once
real history lands.

```bash
for id in 1 2 3; do for m in $(seq 1 12); do echo -n "id=$id month=$m "; curl -s "localhost:8000/api/risk/$id?month=$m" | grep -o '"predicted_pressure":[0-9.]*'; done; done | sort -t: -k2 -rn | head -5
```

Use the destination and month at the top of that list. It must come back
`"band":"high"`, and its `/api/alternatives/{id}` must return at least one
lower-pressure option, or the middle of the demo has nothing to show.

**Currently that is Ella, id 3, month 8 (August)** — pressure 81.0, band high.
Its alternatives return Belihuloya at 54% similarity and low pressure. Ella is
the right choice for a second reason: it is the one destination in the set with
a genuinely poor crowd score (38), so the story is honest rather than staged.

---

## The click path

### 1. Home — 20 seconds

Open the home page. One sentence: *"This helps someone visiting Sri Lanka pick
a destination that is good for them and good for the place, and it shows its
working."*

Click **Find a Sustainable Destination**.

### 2. The recommendation form — 30 seconds

Fill in:

| Field | Value |
|---|---|
| Budget | 50,000 LKR |
| Duration | 4 days |
| Interest | Nature |
| Crowd preference | Low |
| Sustainability weight | **High** |
| Travel month | **August** |

Say why the month matters: August is one of Sri Lanka's two peak windows, so it
is when overtourism actually bites.

Submit.

### 3. Results and the explanation panel — 90 seconds

**This is the most important screen. Do not rush it.**

Belihuloya comes top. Point at the five factor scores, then the contribution
bars.

Say: *"These bars are exact. Environmental contributes 35% because its weight
is 0.30 and its value is 92 — you can do that arithmetic yourself from
`config/weights.yaml`. They sum to exactly 100."*

Read the generated sentence aloud: *"Recommended mainly because of strong
environmental conditions and low visitor pressure."* Note that it comes from a
fixed template, not a language model, so it cannot say anything the numbers do
not support.

Then move the **sustainability weight** to Low and resubmit. Ella climbs, the
quieter places fall. Say: *"The user's preference shifts weight between the
sustainability group and the personal-fit group, and the weights are
renormalised to 1.0 every time."*

### 4. The risk view — 90 seconds

Open **Ella**, month **August**.

The band is **high**, around 81.

Three things to say, in this order:

1. *"This is the only real machine learning in the system: a LightGBM model
   trained on SLTDA monthly occupancy."*
2. Point at the SHAP bars. *"These are labelled estimated, not exact. They are
   the model explaining itself, and we render them differently from the index
   contributions for exactly that reason."*
3. Point at the scope line: *"regional indicator, not site-specific". "SLTDA
   publishes occupancy by province. We will not claim a number for a single
   site that the data cannot support."*

If asked how good the model is, open the model card and read the two MAE
figures out. **If the model lost to the seasonal-average baseline, say so.** A
team that knows its model underperformed reads as competent.

### 5. Alternatives — 60 seconds

Still on Ella, open **alternatives**.

Belihuloya comes back at 54% similarity, low pressure, with a one-line reason.

Say: *"This is the link between the two AI features. The recommender knows what
is similar, the model knows what is busy, and this is where they talk to each
other. If nothing similar were quieter we would say so rather than pad the
list."*

### 6. The what-if simulator — 45 seconds

Open the simulator for Belihuloya.

Drag **expected tourists** to the top and **waste management** to the bottom.
The score falls from 89 to 31 and a warning appears.

Say: *"This is not a separate model. It is the same index with different
inputs, so the number here means the same thing as the number on the results
page. Put the sliders back and you get exactly 89 again."*

Put them back. Show it returns to 89.

### 7. The map — 30 seconds

Open the map. Markers are coloured by pressure band, matching the risk screen
exactly because both read the same thresholds from `config/bands.yaml`.

Click Ella's marker. The panel shows its score, its band and its factor values.

### 8. The authority dashboard — 60 seconds

Log in as the authority account.

Show: destinations monitored, the split across bands, the highest-pressure list,
and the recommended action — which is generated from the counts, not written in
advance.

Then show the **global SHAP importance** chart: *"That is mean absolute SHAP
across the whole history, so it is the same measure as the per-destination bars,
aggregated."*

Finish by logging out and logging in as a tourist-role account to show the
**403**. *"Wrong role gets a clear refusal, not a blank page."*

---

## Questions to have answers ready for

| Question | Short answer |
|---|---|
| Where does each factor value come from? | `source_ref` on every row, shown on the destination panel. `ml/data/README.md` lists the sources. |
| Which values are estimates? | Every row carries `measured` or `estimated`; it is on the results and the detail panel. |
| Why is the Index not a learned model? | So every contribution is exact and reproducible. A model there would destroy the distinction the whole project rests on. |
| Did the model beat the baseline? | Read the number off the model card. Do not guess, and do not soften it. |
| What happens when a destination has almost no data? | The seed refuses to load a factor row with no `source_ref`. A region with under 13 months cannot be forecast and returns 503 rather than a made-up number. |
| Which parts did AI tools help write? | Answer honestly, and be ready to explain any file you are asked about. |
| Why trust this over Google? | Google ranks by popularity, which is what causes overtourism. This ranks by sustainability and shows its arithmetic. |

## If something breaks mid-demo

- **503 on risk, alternatives, destinations or the dashboard** → the model is
  not loaded. You skipped the training step, or the API was not restarted after
  training.
- **429** → you hit the rate limit by clicking repeatedly. Wait a minute, or
  raise `RATE_LIMIT_RECOMMEND` in `.env` before the demo.
- **Empty recommendation list** → the budget or duration filter excluded
  everything. Raise the budget to 50,000 and the duration to 4.
- **Anything else** → fall back to the screenshots. Do not debug on stage.
