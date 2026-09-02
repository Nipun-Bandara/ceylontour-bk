# feat/f6-simulate

**What was built:** `POST /api/simulate` answers "what if this place got
busier, or cleaned up its waste, or built better roads?". The mock is gone.

**It is not a simulation engine, and that is the point.** The three sliders are
mapped onto three of the five factor values and the *same*
`api/services/index.py` is run again. No new scoring logic exists on this
branch. If the simulator computed a score any other way, the number on the
what-if screen would not be the number the recommendation was based on, and a
judge comparing the two screens would catch it.

**The mapping** is the only new logic, and it is input translation rather than
scoring:

| Slider | Factor | How |
|---|---|---|
| `expected_tourists` | crowd | inverted: `100 - slider` |
| `waste_management_level` | environmental | direct |
| `infrastructure_level` | infrastructure | direct |

`community` and `suitability` are left exactly as stored. No slider claims to
move them, so inventing movement would be dishonest.

**Why crowd is inverted.** The crowd factor scores *low visitor pressure*, so a
busy destination has a low crowd value: Belihuloya sits at 91, Ella at 38. More
expected tourists therefore has to produce a smaller number. Getting this
backwards would have made the simulator claim that crowding a place improves
it, which is the single most embarrassing bug this feature could have.

**Reset is exact, not approximately exact.** Sending `100 - stored_crowd`,
`stored_environmental` and `stored_infrastructure` puts all three values back
precisely where they started, so the score comes back identical and `delta` is
0. Verified on the seeded data: Belihuloya stores crowd 91, environmental 92,
infrastructure 76, and sliders of 9 / 92 / 76 return `base=89 new=89 delta=+0`.

**`delta`** is the new score minus the original, added to the response this
branch. `baseline_score` was already in the contract, so the UI can show both
the before and the size of the change without doing arithmetic the API has
already done.

**The warning** fires when `delta` is worse than minus ten points, as F6 asks.
The worst corner on Belihuloya returns `delta=-58` and the sentence "This
combination lowers the sustainability score by 58 points." It is a fixed
template, like every other user-facing string in this API.

**Score range is guaranteed, not hoped for.** The weights sum to 1.0 and every
factor value is 0 to 100, so the weighted sum cannot leave 0 to 100. The tests
still check all eight corner combinations rather than trusting the argument,
because the argument depends on the weights config staying valid.

**Verified before merge:** 135 tests pass and `ruff check` is clean. Over HTTP
against the seeded data: reset returned `delta=+0`; raising
`expected_tourists` from 0 to 100 moved the score 91 → 66 without ever rising;
raising `waste_management_level` from 0 to 100 moved it 61 → 91 without ever
falling; all 24 corner combinations across the three seeded destinations stayed
inside 0 to 100; contributions summed to exactly 100 every time; an unknown id
gave 404 and an out-of-range slider gave 422. A request took 3ms against the
300ms F6 allows.

**One contract change:** `expected_tourists` was `ge=0` and unbounded; it is now
`ge=0, le=100`, because the branch specifies all three sliders as 0-100. It is a
slider position meaning "how busy", not a headcount, and the schema comment now
says so. Anything sending a real visitor number would now get a 422.

**Left open on purpose.** The simulator scores with the neutral preference
weights, because the request carries no `sustainability_weight`. That is
self-consistent — baseline and simulated use the same weights, so `delta` is
always honest — but it means a user who asked for "high" sustainability on the
recommendation screen sees a slightly different baseline here than the score
they were shown there. Adding an optional `sustainability_weight` to the
request would close the gap and would not break any existing caller.

**Also:** a destination with no row in `destination_factors` has no baseline to
simulate against, so it returns 503 rather than 404. The destination exists;
what is missing is our data about it.
