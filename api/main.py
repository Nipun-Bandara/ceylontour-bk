"""FastAPI application: CORS, rate limits, the error shape, and /health.

Every route is registered here. The exception handlers are what keep the
promise that bad input never returns a 500 (CLAUDE.md hard rule 2), and that
an unexpected failure never returns a stack trace to the caller.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.config import settings
from api.envelope import envelope
from api.rate_limit import limiter
from api.routers import (
    alternatives,
    auth,
    dashboard,
    destinations,
    recommend,
    risk,
    simulate,
)
from api.schemas.common import Envelope, ErrorResponse
from api.services.forecast import ForecastUnavailable
from api.services.index import InvalidInput

logger = logging.getLogger("ceylontour.api")

app = FastAPI(
    title="CeylonTour API",
    version="0.1.0",
    description="Sustainable travel decision support.",
)

# slowapi finds the limiter here.
app.state.limiter = limiter

# The deployed frontend origin, from the environment. Never "*": with
# allow_credentials on, a wildcard would let any site read an authenticated
# response. config.py refuses to start in production if it is set to one.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    """Build the {"error": {...}} body every failure returns."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


@app.middleware("http")
async def limit_body_size(request: Request, call_next: Any) -> Any:
    """Reject oversized bodies before anything tries to parse them.

    Every endpoint here takes a small JSON object, so a large body is either a
    mistake or an attempt to spend our memory. Checked on the declared length,
    which is what a JSON client always sends.
    """
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            length = int(declared)
        except ValueError:
            return _error(400, "bad_request", "Invalid Content-Length header")
        if length > settings.max_request_bytes:
            return _error(
                413,
                "payload_too_large",
                f"Request body exceeds {settings.max_request_bytes} bytes",
            )
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Bad input is a 422 with a readable message, never a 500. Covers body,
    # query and path parameters alike.
    first = exc.errors()[0]
    field = ".".join(str(part) for part in first["loc"][1:]) or "body"
    return _error(422, "validation_error", f"{field}: {first['msg']}")


@app.exception_handler(InvalidInput)
async def invalid_input_handler(request: Request, exc: InvalidInput) -> JSONResponse:
    # Input a schema cannot check on its own, such as a preference word that
    # is not in config/weights.yaml. Still the caller's mistake, so 422 and
    # the same code as any other validation failure, never a 500.
    return _error(422, "validation_error", str(exc))


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    # features.md, Rate limiting. The same error shape as everything else, so
    # the frontend has one thing to parse.
    logger.warning(
        "Rate limit hit on %s by %s", request.url.path, request.client
    )
    return _error(
        429,
        "rate_limit_exceeded",
        "Too many requests. Please wait a moment and try again.",
    )


@app.exception_handler(ForecastUnavailable)
async def forecast_unavailable_handler(
    request: Request, exc: ForecastUnavailable
) -> JSONResponse:
    # The model is not trained, or a region has too little history. Nothing
    # the caller did wrong, and not a crash either, so 503 with a message
    # saying what is missing rather than a 500 or a made-up number.
    return _error(503, "forecast_unavailable", str(exc))


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    # Reuses the status FastAPI already chose (404, 403, and so on).
    return _error(exc.status_code, str(exc.status_code), str(exc.detail))


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """The last resort. Nothing gets past this.

    The traceback goes to the server log where the two of us can read it; the
    caller gets a fixed sentence. An exception message can carry a table name,
    a file path or a fragment of a query, and none of that belongs in a
    response.
    """
    logger.exception(
        "Unhandled error on %s %s", request.method, request.url.path
    )
    return _error(500, "internal_error", "An unexpected error occurred.")


@app.get("/health", response_model=Envelope[dict[str, str]], tags=["health"])
def health() -> dict[str, Any]:
    """Liveness check. Uses the envelope like every other route."""
    return envelope({"status": "ok"})


app.include_router(recommend.router)
app.include_router(destinations.router)
app.include_router(risk.router)
app.include_router(alternatives.router)
app.include_router(simulate.router)
app.include_router(dashboard.router)
app.include_router(auth.router)

# Referenced so the error shape appears in the OpenAPI schema the frontend
# generates its client from.
__all__ = ["ErrorResponse", "app"]
