# CeylonTour — Feature Specification

Eight features. **F1 to F4 are committed.** F5 to F8 are built in priority order only after the core path works end to end.

A feature is not done until every acceptance criterion is checked, on the deployed build, not on localhost.

| ID | Feature | Priority | Owner |
|---|---|---|---|
| F1 | Home page | Core | D |
| F2 | Destination recommendation | Core | N + D |
| F3 | XAI explanation panel | Core | N + D |
| F4 | Overtourism risk | Core | N + D |
| F5 | Alternative destinations | Stretch 1 | N + D |
| F6 | What-if simulator | Stretch 2 | D |
| F7 | Destination map | Stretch 3 | D |
| F8 | Authority dashboard | Stretch 4 | D |

---

## F1 — Home page

**Priority:** Core · **Endpoint:** none · **Depends on:** nothing

A landing page explaining the purpose of the system: discover Sri Lanka while helping protect its environment and support local communities.

Two buttons: *Find a Sustainable Destination* leads to F2, *Explore Tourism Sustainability* leads to the information pages.

**Acceptance criteria**

- [ ] Loads in under 2 seconds on a normal connection
- [ ] Both buttons navigate correctly
- [ ] Readable on a phone screen at 375px wide
- [ ] States in one sentence what the system does, without jargon

**Note:** build this last within the Sept 3–5 block. It is the easiest thing to polish and the least important thing to get right early.

---

## F2 — Sustainable destination recommendation

**Priority:** Core · **Endpoint:** `POST /api/recommend` · **Depends on:** dataset (M1), Sustainability Index

The main feature. The user submits budget, trip duration, interest, crowd preference and sustainability preference. The system scores every destination and returns a ranked list. The top result shows its total Sustainability Score and the five factor scores behind it.

### The Sustainability Index

Not a learned model. A transparent weighted sum, with weights in `config/weights.yaml` and version-tracked.

| Factor | Base weight |
|---|---|
| Environmental condition | 0.30 |
| Crowd level | 0.25 |
| Community benefit | 0.20 |
| Tourist suitability | 0.15 |
| Infrastructure | 0.10 |

The user's `sustainability_weight` input shifts the balance between the sustainability group (environmental, crowd, community) and the personal-fit group (suitability, infrastructure). Weights are renormalised to sum to 1.0 after any shift.

Budget and duration act as **filters before scoring**, not as scored factors. A destination that does not fit the budget is excluded rather than penalised.

**Acceptance criteria**

- [ ] All five inputs collected and validated client-side and server-side
- [ ] Weights load from config, never hardcoded
- [ ] Weights sum to 1.0 after any user adjustment — asserted in a test
- [ ] Every destination in the dataset gets scored, no silent drops
- [ ] Ranked list renders with total score and all five factor scores
- [ ] Response returns in under 2 seconds for 20 destinations
- [ ] Out-of-range and malformed inputs rejected with a clear message, never a 500

---

## F3 — XAI explanation panel

**Priority:** Core · **Endpoint:** included in `POST /api/recommend` · **Depends on:** F2

The most important feature in the project. No result is shown without a reason.

For each recommendation the panel answers *"Why was this recommended?"* with horizontal contribution bars and a plain-language sentence beneath them.

### Two kinds of explanation, labelled differently

| Kind | Where from | How shown |
|---|---|---|
| **Exact** | Index contributions, computed directly from weights | Solid bars |
| **Estimated** | TreeSHAP on the pressure forecast | Hatched or outlined bars, with a tooltip saying it is a model estimate |

This distinction is stated in the proposal. Presenting an exact calculation and a model estimate as equally certain would defeat the point of building an explainable system, and a judge on an XAI theme will check for it.

### Sentence templates

Fixed templates filled from the top two contributing factors. No free-text generation.

> "Recommended mainly because of {factor_1} and {factor_2}."
> "Ranked below {higher_destination} mainly because of {deciding_factor}."

**Acceptance criteria**

- [ ] Contribution percentages sum to 100, asserted in a test
- [ ] Bars visually sum to the total score
- [ ] Exact and estimated contributions are visually distinguishable without reading the tooltip
- [ ] Sentence generates correctly for every destination in the dataset, including edge cases where two factors tie
- [ ] Top five factors shown, no more. Longer lists stop being explanations
- [ ] Panel readable by someone with no technical background — test this on somebody outside the team

---

## F4 — Overtourism risk

**Priority:** Core · **Endpoint:** `GET /api/risk/{id}?month=` · **Depends on:** `region_pressure_history`

The second AI feature, and the only genuine machine learning in the system.

A LightGBM regressor forecasts visitor pressure for a region in a given month. Training data is SLTDA monthly occupancy, arrivals and guest nights across multiple years. Features: month, region, recent occupancy history, arrival trend, holiday indicators. Target: the region's occupancy rate that month.

Output maps to bands: **low** (green), **medium** (yellow), **high** (red). The SHAP breakdown shows where the pressure comes from.

### Evaluation

MAE on held-out data, most recent full year as the test set, compared against a seasonal-average baseline.

**Report the number honestly.** If the model does not beat the baseline, say so in the model card and in the demo. A team that knows its model underperformed reads as competent. A team caught overstating does not.

**Acceptance criteria**

- [ ] Training script reproducible from raw data with one command
- [ ] MAE and baseline comparison recorded in `ml/artifacts/model_card.md`
- [ ] Model artefact versioned, and `model_version` returned in every response
- [ ] SHAP breakdown returned per destination and month
- [ ] Bands render in traffic-light colours with the percentage visible
- [ ] Response states clearly that pressure is a **regional** indicator, not per-site. The data does not support per-site claims
- [ ] Inference under 500ms

---

## F5 — Alternative destination suggestion

**Priority:** Stretch 1 · **Endpoint:** `GET /api/alternatives/{id}` · **Depends on:** F2, F4

Build this first among the stretch features. It is what connects the recommendation engine to the risk model, and that link is one of the four innovation claims in the proposal. Without it, the two AI features sit side by side doing nothing for each other.

When a user selects a high-pressure destination, the system warns them and offers similar destinations with lower pressure, each with a similarity percentage and a one-sentence reason.

Similarity is cosine similarity over attribute vectors: landscape type, activities, travel distance, climate.

**Acceptance criteria**

- [ ] Returns 3 alternatives, all with lower forecast pressure than the selected destination
- [ ] Similarity percentage shown for each
- [ ] One-sentence reason generated per alternative
- [ ] Handles the case where no lower-pressure similar destination exists — says so rather than returning a bad match
- [ ] Never suggests a destination outside the user's original budget or duration filter

---

## F6 — What-if simulator

**Priority:** Stretch 2 · **Endpoint:** `POST /api/simulate` · **Depends on:** F2

Three sliders: expected number of tourists, waste management level, infrastructure level. Moving a slider recalculates the sustainability score immediately.

This is not a simulation engine. It re-runs the same index calculation with changed inputs, which is enough to demonstrate decision support and is exactly what the proposal says it is.

**Acceptance criteria**

- [ ] Score updates within 300ms of a slider moving
- [ ] Score stays within 0 to 100 at every possible slider combination — test the corners
- [ ] Direction is always sensible: more visitors never raises the score, better waste management never lowers it
- [ ] Warning text appears when a change pushes the score down by more than 10 points
- [ ] Resetting sliders returns exactly the original score

---

## F7 — Sri Lanka destination map

**Priority:** Stretch 3 · **Endpoints:** `GET /api/destinations`, `GET /api/destinations/{id}` · **Depends on:** M1

Leaflet map with OpenStreetMap tiles, 10 to 15 destinations as coloured markers by pressure band. Clicking a marker opens a panel with that destination's sustainability score, risk, community score and environmental score.

No GIS work. Fixed coordinates, standard tile layer.

**Acceptance criteria**

- [ ] All destinations appear at correct coordinates
- [ ] Marker colours match the bands shown elsewhere in the app
- [ ] Panel opens on click and closes cleanly
- [ ] Map loads without blocking the rest of the page
- [ ] OpenStreetMap attribution displayed, as the licence requires

---

## F8 — Tourism authority dashboard

**Priority:** Stretch 4 · **Endpoints:** `GET /api/dashboard/summary`, `POST /api/auth/login` · **Depends on:** F4

An overview page for officials, behind a login. Shows how many destinations are monitored and their split across pressure bands, lists the highest-pressure destinations with risk values, and displays a recommended action.

Also shows the global SHAP feature importance view for the pressure model.

**Acceptance criteria**

- [ ] JWT login working, passwords hashed with bcrypt or argon2, never stored as text
- [ ] Tourist-role users get 403, not a blank page
- [ ] Counts match the destination table exactly
- [ ] Global feature importance chart renders
- [ ] Recommended action text is generated from the data, not hardcoded

**If time is short:** a static summary view with no login still demonstrates the two-audience idea. Cut the auth before cutting the dashboard.

---

## Cross-cutting requirements

These apply to every feature and are checked once, on Sept 9.

| Area | Requirement |
|---|---|
| Validation | Every endpoint validates with Pydantic. No unvalidated input reaches the database or a model |
| SQL | Parameterised queries only, via SQLAlchemy. No string interpolation anywhere |
| XSS | All user-facing output escaped |
| Rate limiting | Per-client limits on `/api/recommend` and `/api/risk` |
| Secrets | Everything in environment variables. `.env` in `.gitignore`, `.env.example` committed |
| HTTPS | Enforced in production |
| Traceability | `model_version` and `index_version` returned with every response, so any explanation shown to a user can be reproduced later |
| Confidence | Every score carries a `measured` or `estimated` label, surfaced in the UI |
| Attribution | Every open-source dependency listed with its licence in `THIRD_PARTY.md` |

---

## Definition of done

A feature is done when all of these are true:

1. Acceptance criteria all checked
2. Works on the deployed build, not just localhost
3. Fails gracefully with bad input, never a 500 or a blank screen
4. **Both team members can explain how it works.** This one is a competition rule, not a preference
