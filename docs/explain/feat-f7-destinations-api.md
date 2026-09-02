# feat/f7-destinations-api

**What was built:** the two endpoints behind the map. `GET /api/destinations`
returns everything needed to place and colour a marker;
`GET /api/destinations/{id}` returns everything the panel shows when one is
clicked. Both mocks are gone.

**Bands are imported, not recomputed.** The router calls `band_for` through the
same `api/services/forecast.forecast()` the risk endpoint uses, reading the
same `config/bands.yaml`. This matters more than it looks: F7 says marker
colours must match the bands shown elsewhere in the app, and the only way to
guarantee that is to have one implementation. A second copy of "41 to 70 is
medium" would drift the first time someone edited one and not the other. There
is a test that asks both endpoints for the same destination and compares.

**One forecast per region, not per destination.** The forecast service caches
on `(region, month)`, so twenty destinations spread across five regions cost
five predictions. Pressure is regional, so destinations in the same region get
the same band by construction.

**The split between list and detail** follows what each screen needs. The list
is eight fields, enough to drop a pin and colour it. The detail adds the five
factor scores, the confidence label, activities, cost band, typical days and
`source_ref`. `source_ref` is on the panel deliberately: the proposal promises
a reader can find out where a number came from, and this is the screen where
they would ask.

**Scores use the neutral preference weights.** These endpoints answer "what is
this place like", not "what is it like for me", so there is no
`sustainability_weight` to honour. That is the same choice the simulator makes,
for the same reason.

**Verified before merge:** 144 tests pass and `ruff check` is clean. Over HTTP
against a temporarily loaded six-year series and a trained model, all three
seeded destinations came back at their exact coordinates with scores 89, 86 and
67, and each one's band matched what `/api/risk` returned for the same
destination and month — low, medium, medium. An unknown id returned 404 with
the error shape. The synthetic data and the artefacts were removed afterwards.

**A contract narrowing worth knowing about.** The skeleton's mock returned
`landscape_type`, `cost_band` and `typical_days` in the *list*. The agreed field
list for this branch has none of them in the list, and only `cost_band` and
`typical_days` in the detail. So **`landscape_type` is no longer returned by
either endpoint**. It is still in the database and still used by the F5
similarity vectors; it just is not on these two responses any more. If the
frontend was reading it from the marker payload, that will break, and adding it
back to the detail is a one-line change.

**The fragile part.** A band needs a forecast, so if the model is untrained the
whole list is a 503, and if *any* single destination sits in a region with too
little history the whole list is a 503 too. That keeps the count honest — the
tests require the response to match the destinations table exactly, so a
destination can never be quietly dropped — but it means one thin region takes
the entire map down. With three seeded regions that is fine. With fifteen to
twenty destinations across more provinces than SLTDA covers well, it will not
be. The fix, when it bites, is to make `band` nullable and let the map render a
grey marker for a destination whose pressure is unknown. That is a contract
change, so it is flagged here rather than done quietly.

**Same for missing factors:** a destination with no `destination_factors` row
has no sustainability score, so it returns 503 rather than being skipped. The
seed validator already refuses to load a dataset where that is true, so this is
a guard against something reaching the table another way.
