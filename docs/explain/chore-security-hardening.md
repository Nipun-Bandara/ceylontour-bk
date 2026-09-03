# chore/security-hardening

A sweep of the whole API against the Cross-cutting requirements table in
`features.md`. Everything below was changed, not just noted. 210 tests pass and
`ruff check` is clean.

## 1. Validation on every input

- [x] `interest` is now an `Interest` enum, `crowd_preference` a
      `CrowdPreference` enum. A typo is a 422 naming the allowed values instead
      of a string that quietly matches nothing.
- [x] `budget_lkr` is `gt=0`; a zero budget is not a budget.
- [x] `duration_days` is `1-30`.
- [x] `travel_month` and the risk `month` query stay `1-12`.
- [x] **Path parameters** now validated: every `destination_id` is `Path(gt=0)`.
      `/api/risk/-3` was previously a database lookup for a negative id.
- [x] **Query parameters** tightened on alternatives: `budget_lkr` `gt=0`,
      `duration_days` `1-30`.
- [x] `extra="forbid"` on every request body, so a misspelled field is a 422
      rather than a silently ignored value.
- [x] `password` bounded at 256 characters and `email` at 254, so login cannot
      be made to argon2-hash a megabyte.
- [x] `sustainability_weight` deliberately stays a plain string. Its allowed
      values are the shift keys in `config/weights.yaml`; an enum would hardcode
      them in a second place and break hard rule 3. The service validates it and
      returns 422.

Verified over HTTP: bad enum, `budget_lkr=0`, `duration_days=31`, `month=13`,
`destination_id=-1` and an unknown body field all returned 422 in the error
shape.

## 2. Rate limiting

- [x] `slowapi` on `POST /api/recommend` and `GET /api/risk/{id}`.
- [x] Limits from `RATE_LIMIT_RECOMMEND` and `RATE_LIMIT_RISK`, read through a
      callable so a change takes effect without a restart. That is also what
      lets the tests exercise the real limiter at a low limit rather than
      mocking it.
- [x] Exceeding one returns **429** as
      `{"error": {"code": "rate_limit_exceeded", ...}}`.
- [x] An autouse fixture clears the counters between tests, so the suite's own
      traffic cannot trip the limiter and make test order matter.

Verified over HTTP at `5/minute`: requests 1-5 returned 200, requests 6-8
returned 429 in the error shape.

## 3. One catch-all, no stack traces

- [x] The `Exception` handler now **logs the traceback server-side** and
      returns a fixed sentence. Previously it returned the generic message but
      logged nothing, so a real failure left no trace anywhere.
- [x] Specific handlers sit in front of it for validation (422), unknown
      preference (422), rate limit (429), forecast unavailable (503) and HTTP
      errors. Everything else falls through to the catch-all.
- [x] Tested by making a router raise an exception whose message contains a
      host address and a database password, then asserting the response is
      exactly the generic body and contains no `Traceback`, no `psycopg`, no
      address and no password.

## 4. Secrets

- [x] **`docker-compose.yml` no longer ships default credentials.**
      `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-ceylontour}` meant the repo
      contained a working password for any deployment that forgot to set one.
      Now `${POSTGRES_PASSWORD:?...}`, so compose refuses to start rather than
      standing up a database everyone knows the password to. Confirmed: compose
      fails with no `.env`.
- [x] **`config.py` default `DATABASE_URL` no longer carries `ceylontour:ceylontour@`.**
      The bare default fails to connect instead of quietly using a known
      credential.
- [x] `.env` is gitignored and untracked; only `.env.example` is committed.
      Confirmed with `git check-ignore` and `git ls-files`.
- [x] `.env.example` is current: every `Settings` field has a matching key.
- [x] Grepped the tracked tree for passwords, tokens, API keys and connection
      strings. The only remaining matches are test fixtures and field names.

## 5. SQL

- [x] Grepped for f-strings, `%`, `.format` and `+` near SQL keywords. **No
      interpolated SQL exists.** Every query goes through the ORM; the only
      `text()` calls are static strings in test teardown.
- [x] Tested end to end: a destination whose `name`, `district`, `source_ref`
      and `activities` are all `Robert'); DROP TABLE destinations;--` was
      stored, listed and returned verbatim, and the table survived.

## 6. CORS

- [x] Origins come from `CORS_ORIGINS` and default to the dev frontend only.
      Never `"*"` — with `allow_credentials=True` a wildcard would let any site
      read an authenticated dashboard response.
- [x] Methods narrowed from `*` to `GET, POST, OPTIONS`, headers from `*` to
      `Authorization, Content-Type`.
- [x] **Production refuses to start** on a placeholder `JWT_SECRET`, a `"*"`
      origin, or a plain `http://` origin. Verified: all three raise, and a
      correct configuration starts.

## 7. Request size

- [x] A middleware rejects any body over `MAX_REQUEST_BYTES` (64 KB default)
      with **413** in the error shape, before anything tries to parse it.
      Verified with a 100 KB body.

## 8. Tests

`api/tests/test_security.py`, 42 cases: bad enums, out-of-bounds body values,
unknown fields, twelve path/query permutations, the rate limit tripping on both
endpoints, oversized payload, SQL injection round-trip, the generic 500, error
shape consistency, and the production config guards.

---

## Two things left open

**The `Interest` enum values are invented.** `nature`, `culture`, `adventure`,
`wildlife`, `beach`, `relaxation`. Neither `plan.md` nor `features.md` lists
them, and `interest` still does not affect scoring. This is a narrowing: the
frontend must now send one of these six or get a 422. If the real set differs,
change `api/schemas/common.py` and tell D the same day.

**Rate limiting is per-process, in memory.** One API container is what the demo
runs, so this is fine. Behind two replicas each would keep its own counter and
the effective limit would double. slowapi takes a Redis URI for shared storage
and Redis is already in the compose file, so it is a one-line change if the
deployment ever grows a second instance.
