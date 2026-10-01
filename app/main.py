import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app import models  # noqa: F401  (registers the tables)
from app.api import auth, bookings, centres, diagnostic_tests, payments
from app.core.exceptions import DomainError
from app.core.logging import setup_logging
from app.db.base import Base
from app.db.session import engine

setup_logging()
log = logging.getLogger("app.request")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(
    title="EVE Diagnostics Booking API",
    description="Diagnostic centres, test bookings and simulated payments.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def access_log(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("unhandled error", extra={"request_id": request_id, "path": request.url.path})
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "Something went wrong"}},
        )
    response.headers["x-request-id"] = request_id
    log.info(
        "request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": round((time.perf_counter() - started) * 1000, 1),
        },
    )
    return response


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, exc: DomainError):
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
        headers=headers,
    )


app.include_router(auth.router)
app.include_router(diagnostic_tests.router)
app.include_router(centres.router)
app.include_router(bookings.router)
app.include_router(payments.router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
