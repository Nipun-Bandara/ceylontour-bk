# feat/f5-alternatives

**What was built:** `GET /api/alternatives/{id}` answers "this one is busy,
where else could I go that feels the same?". `api/services/similarity.py`
decides what "feels the same" means; the router combines that with the F4
forecast so every suggestion is genuinely under less pressure.

**Why this feature matters more than its stretch ranking suggests.** It is the
only thing that connects the two AI features. Without it the index and the
pressure model sit side by side doing nothing for each other, and one of the
proposal's innovation claims goes unbacked.

**The attribute vector** is four blocks joined together: landscape type as a
one-hot, activities as a multi-hot, cost band as one scaled number, and
closeness to the selected destination. Distance is haversine, scaled against
the furthest candidate and then inverted, so near means a large value —
cosine rewards agreement on large components, so closeness has to point the
same way as everything else. Vectors are rebuilt per request because the
distance block is measured from whichever destination the user picked.

**Cost band does not start at zero.** It is scaled from the budgets already in
`config/cost_bands.yaml` rather than invented again, and the lowest band maps
to 0.167 rather than 0. A zero component contributes nothing to a cosine, so
"both of these are cheap" would have counted as no resemblance at all.

**Vocabularies are sorted**, so the vector layout is identical on every
request. Two destinations must never score differently because a set iterated
in a different order.

**Filters come first, similarity second.** If `budget_lkr` or `duration_days`
are given, anything failing them is dropped before any scoring happens. F5 is
explicit that an alternative must never break the user's original filters, and
doing it in this order makes that true by construction rather than by
remembering to check later.

**Then pressure, strictly.** A candidate is only offered if its forecast is
*below* the selected destination's. Equal is not an improvement, so two
destinations in the same region never suggest each other — they share a
regional forecast. That falls straight out of the comparison, and there is a
test for it.

**Empty is a real answer.** If nothing qualifies, the response is a 200 with an
empty list and a message saying so. Padding three slots with poor matches would
be worse than useless: it would teach a user the suggestions are noise. The
message says as much in plain words.

**One bad region does not sink the request.** If a candidate's region has too
little history to forecast, it is skipped — it cannot be compared, so it is not
offered. If the *selected* destination cannot be forecast there is nothing to
be lower than, and that is a genuine 503.

**Verified before merge:** 111 tests pass and `ruff check` is clean. Over HTTP
against a temporarily loaded six-year series, Ella (the busiest region) returned
Belihuloya at 54% and Meemure at 23%, both under its pressure; `duration_days=2`
dropped Belihuloya, which needs three; `budget_lkr=10000` emptied the list and
returned the message; Belihuloya, already the quietest, returned the message
with no alternatives; and the source id never appeared in its own results. The
synthetic data and every artefact were removed afterwards.

**Known problem, not fixed here.** The reason template says "Similar
{landscape_type} setting", naming the *alternative's* landscape and assuming it
matches the one the user picked. When it does not, the sentence overclaims:
Meemure came back as "Similar forest setting" against a mountain destination,
at 23% similarity. The fix is a second template for when the landscapes differ.
That changes user-facing wording, so it wants agreeing first. This is the same
shape of problem as the "Ranked below" sentence in F3 and should probably be
settled at the same time.

**Two gaps worth naming.** features.md F5 lists climate as a similarity
attribute; there is no climate column in the schema, so cost band stands in.
And the endpoint compares pressure for the *current* month, because the
contract gives it no month parameter — if a user is planning for September, the
alternatives should be compared in September. Adding an optional `month` query
parameter would fix it and would not break any existing caller.
