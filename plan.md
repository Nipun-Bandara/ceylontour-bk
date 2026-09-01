# CeylonTour — Build Plan

**Team:** Blind Bandits, University of Moratuwa
**Competition:** CodeSplash '26 University Phase, Theme 01 (Decision Support System Using Explainable AI)
**Development window:** 1 September to 10 September 2026

---

## 1. Ground rules

These are not suggestions. Breaking any of them costs marks.

| Rule | Source |
|---|---|
| Build only what the proposal declared. The declared stack is the primary reference at the Grand Finale, and any change must be justified in the demo | Guidelines 5.3.6 |
| Both members must be able to explain every part of the system. Purely AI-generated work with no understanding is disqualified | Guidelines 7.2 |
| Every open-source library used gets recorded with its licence in `THIRD_PARTY.md` | Guidelines 7.3 |
| Nothing is "done" until it runs on the demo machine, not just the developer's laptop | Learned the hard way by every hackathon team ever |

**Working agreement:** if either of us writes something the other cannot explain, it gets explained the same day or removed.

---

## 2. Who owns what

| Owner | Area |
|---|---|
| **N** (Nipun) | Sustainability Index, visitor pressure model, SHAP layer, similarity module, dataset compilation, model evaluation |
| **D** (Dananjana) | Next.js frontend, FastAPI service layer, database schema, Docker, deployment, auth |
| **Both** | API contract, testing, documentation, demo rehearsal |

The split only works if the API contract in section 7 is agreed on **day one** and neither side changes it without telling the other. D builds against mock responses until N's real ones land.

---

## 3. Before 1 September

The development phase opens on 1 September. Ask the organisers whether compiling the dataset before that date is permitted, since it is research rather than development. Do not assume either way.

If it is permitted, this is the highest-value prep work available, because the dataset is the longest lead-time item in the whole project and nothing else can be tested without it.

- [ ] Confirm with organisers what counts as development
- [ ] Download SLTDA annual statistical reports for the last 5 years
- [ ] Check Open-Meteo covers all candidate destination coordinates
- [ ] **Check OpenAQ actually has sensors near the smaller destinations.** Coverage outside Colombo is thin. If Belihuloya and Meemure have nothing, decide now whether air quality becomes a proxy estimate or gets dropped
- [ ] Agree the final list of 15 to 20 destinations
- [ ] Both members read `features.md` end to end

---

## 4. Day-by-day plan

This follows the roadmap declared in the proposal. Do not drift from it without a written reason, because the proposal is what the judges will hold the demo against.

### Sept 1 – 3 · Foundations

| Owner | Task |
|---|---|
| D | Repo created, branch protection on `main`, `.env.example` committed |
| D | `docker-compose.yml` running Postgres 16 + PostGIS + Redis + API + web |
| D | Database schema created and migrated (section 8) |
| D | FastAPI skeleton with all endpoints returning hardcoded mock data matching the contract |
| N | Destination table compiled: 15 to 20 rows, all five factor values, every value carrying a source reference and a confidence flag |
| N | SLTDA monthly occupancy and arrivals extracted into `region_pressure_history` |
| N | Open-Meteo historical pull script written and run |
| Both | API contract signed off. After this point, changes require agreement |

**Gate: end of Sept 3.** D can develop the whole frontend against mocks. N can develop models against real data. Neither is blocked.

### Sept 3 – 5 · Core path

| Owner | Task |
|---|---|
| N | Sustainability Index implemented, weights in `config/weights.yaml`, contributions returned alongside the score |
| N | Index unit tests: weights sum to 1.0, contributions sum to the score, each factor moves the score in the expected direction |
| D | Home page |
| D | Recommendation form with all five inputs |
| D | Results page rendering the ranked list and five factor scores |
| D | Real index wired into `POST /api/recommend`, mocks removed |

**Gate: end of Sept 5. M2 reached.** Form to scored result works end to end with real data.

### Sept 5 – 7 · The XAI layer and the model

| Owner | Task |
|---|---|
| D | Explanation panel with contribution bars (Recharts) |
| D | Plain-language sentence templates |
| D | Risk view with the traffic-light band and SHAP breakdown |
| N | LightGBM visitor pressure model trained on the SLTDA series |
| N | Evaluation: MAE on the most recent full year, held out, compared against a seasonal-average baseline. **Record the result whether or not it beats the baseline** |
| N | TreeSHAP wired into `GET /api/risk/{id}` |
| Both | Confirm the UI labels index contributions as exact and SHAP values as estimates. This distinction is in the proposal and judges will look for it |

**Gate: end of Sept 7. M3 and M4 reached.** All four core features work. **Everything after this point is optional.**

### Sept 7 – 9 · Stretch features, in this order

Build in priority order. Stop when time runs out rather than leaving several half-done.

1. Alternative destination suggestion (F5) — highest value, links the two AI features together
2. What-if simulator (F6) — strong demo moment, cheap to build
3. Destination map (F7) — visually impressive, low risk
4. Authority dashboard (F8) — the honest first cut for the demo

### Sept 9 – 10 · Ship

| Owner | Task |
|---|---|
| Both | End-to-end test on a clean machine from `git clone` |
| D | Deploy API and database, deploy frontend, verify HTTPS |
| D | Security pass: input validation on every endpoint, rate limiting live, no secrets in the repo |
| N | Model card: what it predicts, on what data, how well, with what limitations |
| Both | `README.md`, setup docs, `THIRD_PARTY.md` |
| Both | **Submit by 10 September.** Not on the evening of the 10th. That morning |

---

## 5. Milestones

| ID | Milestone | Done when |
|---|---|---|
| M1 | Dataset ready | 15+ destinations in Postgres, every factor value has a source and a confidence flag |
| M2 | Recommendation end to end | Form submits, real index scores, ranked list renders |
| M3 | XAI panel | Contributions displayed, bars sum exactly to the score, sentence generated |
| M4 | Risk and alternatives | Forecast returns with SHAP breakdown; alternatives return for a high-pressure destination |
| M5 | Stretch features | Simulator, map and dashboard as far as time allowed |
| M6 | Shipped | Deployed, tested from clean clone, documented, submitted |

---

## 6. Repository layout

```
ceylontour/
├── docker-compose.yml
├── README.md
├── THIRD_PARTY.md
├── plan.md
├── features.md
├── api/
│   ├── main.py
│   ├── routers/          # recommend, risk, alternatives, simulate, dashboard, auth
│   ├── schemas/          # Pydantic request and response models
│   ├── models/           # SQLAlchemy tables
│   ├── services/
│   │   ├── index.py      # Sustainability Index
│   │   ├── forecast.py   # LightGBM inference
│   │   ├── explain.py    # exact contributions + TreeSHAP
│   │   └── similarity.py
│   └── tests/
├── ml/
│   ├── data/             # raw SLTDA, Open-Meteo pulls
│   ├── notebooks/        # exploration only, never the source of truth
│   ├── train_pressure.py
│   ├── evaluate.py
│   └── artifacts/        # versioned model files
├── config/
│   └── weights.yaml      # index weights, version controlled
└── web/                  # Next.js app
```

**Rule:** notebooks are for exploring. Anything the API depends on lives in a `.py` file with a test.

---

## 7. API contract

Agreed 1 September. Both sides build against this. Changes need agreement from both members.

### Envelope

Every response:

```json
{
  "data": { },
  "meta": { "model_version": "pressure-v1.2", "index_version": "weights-v1" }
}
```

Errors return HTTP status plus `{"error": {"code": "...", "message": "..."}}`.

### Endpoints

| Method | Path | Purpose | Feature |
|---|---|---|---|
| POST | `/api/recommend` | Ranked destinations with scores and contributions | F2, F3 |
| GET | `/api/destinations` | All destinations with coordinates and current band | F7 |
| GET | `/api/destinations/{id}` | Single destination detail | F7 |
| GET | `/api/risk/{id}?month=` | Pressure forecast, band, SHAP breakdown | F4 |
| GET | `/api/alternatives/{id}` | Similar destinations with lower pressure | F5 |
| POST | `/api/simulate` | Recomputed score from adjusted inputs | F6 |
| GET | `/api/dashboard/summary` | Authority overview. **Auth required** | F8 |
| POST | `/api/auth/login` | JWT issue for authority users | F8 |

### `POST /api/recommend`

Request:

```json
{
  "budget_lkr": 50000,
  "duration_days": 4,
  "interest": "nature",
  "crowd_preference": "low",
  "sustainability_weight": "high",
  "travel_month": 9
}
```

Response `data`:

```json
{
  "results": [
    {
      "destination_id": 7,
      "name": "Belihuloya",
      "sustainability_score": 89,
      "factors": {
        "environmental": 92, "community": 88, "crowd": 91,
        "infrastructure": 76, "suitability": 90
      },
      "contributions": [
        { "factor": "environmental", "percent": 32, "type": "exact" },
        { "factor": "crowd", "percent": 25, "type": "exact" }
      ],
      "explanation": "Recommended mainly because of low visitor pressure and strong environmental conditions.",
      "confidence": "measured"
    }
  ]
}
```

`type` is `"exact"` for index contributions and `"estimated"` for SHAP values. The UI must render these differently. `confidence` is `"measured"` or `"estimated"` depending on whether the underlying factor values came from real data or proxies.

---

## 8. Database schema

| Table | Key columns |
|---|---|
| `destinations` | id, name, lat, lon, district, region, landscape_type, activities[], cost_band, typical_days |
| `destination_factors` | destination_id, environmental, community, crowd, infrastructure, suitability, source_ref, confidence |
| `region_pressure_history` | region, year, month, occupancy_rate, arrivals, guest_nights |
| `pressure_forecast` | region, month, predicted_pressure, band, model_version |
| `index_weights` | version, factor, weight, created_at |
| `users` | id, email, password_hash, role |
| `search_log` | id, ts, params_json, results_json, accepted_destination_id |

`source_ref` and `confidence` on every factor value are not optional. They power the confidence labels the proposal promised, and they are the answer when a judge asks where a number came from.

---

## 9. Cut ladder

When behind, cut from the bottom up. Decide by looking at this list, not by whoever is most attached to a feature.

| Order | Cut | Cost of cutting |
|---|---|---|
| 1 | Redis caching. Compute on request instead | None at demo scale |
| 2 | PostGIS. Plain lat/lon columns are enough for 15 markers | None |
| 3 | Authority dashboard (F8) | Loses the second-audience story |
| 4 | Map (F7) | Loses visual impact |
| 5 | What-if simulator (F6) | Loses a good demo moment |
| 6 | Alternative destinations (F5) | Loses the link between the two AI features. Painful |

**Never cut:** F2 recommendation, F3 explanation, F4 risk. Those three are the project. A polished core beats eight half-working features every time.

---

## 10. After submission

| Date | What |
|---|---|
| Sept 12 | Panel discussion, LCH 09. Prepare answers to the hard questions below |
| Sept 13 | Product pitching workshop |
| Sept 17 | Finalist announcement |
| Sept 18 | Final presentation due, 11:59 PM |
| Sept 19 | Grand Finale, Auditorium |

### Questions to have answers ready for

- Where does each factor value come from, and which are estimates?
- Why is the Sustainability Index not a learned model?
- Did the pressure model beat the seasonal-average baseline? By how much?
- What happens when a destination has almost no data?
- Which parts did AI tools help write, and can you explain them?
- Why should a tourist trust this over Google?

Rehearse the demo three times end to end before the 12th. Record how long it takes. Have screenshots ready in case the network fails.

---

## 11. Risks

| Risk | Likelihood | What we do |
|---|---|---|
| SLTDA data too coarse or too short a series to train on | Medium | Fall back to a seasonal-average model and say so openly. An honest simple baseline beats a fabricated complex one |
| OpenAQ has no coverage near small destinations | High | Decide before Sept 1. Either drop air quality or mark it as a proxy with a confidence flag |
| Dataset compilation eats into build days | High | Front-load it. It is the only task with no code dependency, so it can start earliest |
| Two people, ten days, eight features | High | The cut ladder exists for this. Use it early rather than at the last minute |
| One member falls sick or has exams | Medium | Keep the API contract stable so either can pick up basics on the other side |
