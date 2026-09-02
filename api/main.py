"""FastAPI application: CORS, the error shape, and /health.

Every route is registered here. The exception handlers are what keep the
promise that bad input never returns a 500 (CLAUDE.md hard rule 2).
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.config import settings
from api.envelope import envelope
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

app = FastAPI(
    title="CeylonTour API",
    version="0.1.0",
    description="Sustainable travel decision support. Skeleton: mock data only.",
)

# The Next.js dev server. Origins come from settings so production does not
# need a code change.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    """Build the {"error": {...}} body every failure returns."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Bad input is a 422 with a readable message, never a 500.
    first = exc.errors()[0]
    field = ".".join(str(part) for part in first["loc"][1:]) or "body"
    return _error(422, "validation_error", f"{field}: {first['msg']}")


@app.exception_handler(InvalidInput)
async def invalid_input_handler(request: Request, exc: InvalidInput) -> JSONResponse:
    # Input a schema cannot check on its own, such as a preference word that
    # is not in config/weights.yaml. Still the caller's mistake, so 422 and
    # the same code as any other validation failure, never a 500.
    return _error(422, "validation_error", str(exc))


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
    code = str(exc.status_code)
    return _error(exc.status_code, code, str(exc.detail))


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Last resort. The detail stays out of the response so nothing internal
    # leaks to the client.
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
