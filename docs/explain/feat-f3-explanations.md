# feat/f3-explanations

**What was built:** the explanation layer. `api/services/explain.py` turns a
destination's factor values into contribution bars and one plain-language
sentence, and `POST /api/recommend` now fills both fields. No result comes back
without a reason, which is the point of F3.

**Nothing here generates text.** Two fixed templates, with factor labels
slotted in. A template cannot say something the numbers do not support, and it
means both of us can point at any word in the output and say where it came
from. That matters more here than anywhere else in the project: the whole
theme is explainable AI, and an explanation nobody can account for is worse
than no explanation.

**Contributions.** `contributions(factor_scores, weights)` asks the index for
the percentages, rounds them, and sorts them largest first. `top_n` caps the
list at five, because F3 says longer lists stop being explanations.

**Why largest-remainder rounding.** The contract types `percent` as a whole
number. Rounding each value on its own gives bars that add up to 99 or 101, and
F3 promises they sum to 100 and that the bars visually sum to the score. So
every value is floored and the leftover points go to the largest fractional
parts. This code moved out of `index.py`, where F2 had left it: scoring and
presenting a score are different jobs, and only one module should own the
rounding.

**Ties break on the factor name**, everywhere. Two factors contributing 12 each
always come out in the same order, so the same request always renders the same
bars and the same sentence. There is a test that runs the same input five times
and compares.

**Labels** are the five plain-language phrases: `crowd` becomes "low visitor
pressure", not "crowd: 25%". A tourist reads this panel, not a developer.

**Position decides the sentence.** The top result gets "Recommended mainly
because of {factor_1} and {factor_2}", filled from its two largest
contributors. Everything below gets "Ranked below {higher_destination} mainly
because of {deciding_factor}", compared against the result directly above it,
with the deciding factor being its weakest contributor. Because the sentence
depends on rank, it can only be written after the list is sorted, so the router
scores everything, sorts, then makes a second pass for the sentences.

**Verified before merge:** 61 tests pass against real Postgres inside docker
compose, `ruff check` is clean, and over HTTP every seeded destination returns
five contributions summing to exactly 100 at every preference setting, with
repeated identical requests returning byte-identical results.

**Known problem, not fixed here.** The "Ranked below" template reads wrongly.
Its deciding factor is the destination's weakest contributor, but every label
is phrased as a strength, so Ella, which has a crowd score of 38, comes back
saying "Ranked below Meemure mainly because of low visitor pressure" — the
opposite of what its own data says. The fix is a second label map phrased as
weaknesses, used only by that template. It changes user-facing wording, so it
needs agreeing rather than slipping in. Until then, do not put the second and
third results on screen in the demo.

**Also left open:** the sentence compares against the destination directly
above rather than the top result, and it never sees the higher destination's
contributions, so it cannot name the factor the two actually differ on. It
names this destination's own weak spot instead.
