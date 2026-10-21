from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.v1.router import api_v1_router
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: instrument Prometheus metrics
    yield
    # Shutdown


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    description=(
        "High-Throughput Distributed Financial Transaction & Double-Entry Ledger Engine "
        "providing sub-10ms ACID writes, zero double-spending, and distributed idempotency."
    ),
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Prometheus Metrics Instrumentator
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# Mount API Routers
app.include_router(api_v1_router, prefix=settings.API_V1_STR)


@app.get("/", include_in_schema=False)
async def root():
    """Redirect root path to Swagger UI documentation."""
    return RedirectResponse(url="/docs")


@app.get(f"{settings.API_V1_STR}/docs", include_in_schema=False)
async def api_docs_alias():
    """Redirect legacy /api/v1/docs path to /docs."""
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["Health"])
async def health_check():
    """Liveness probe verifying that the API is running."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
    }
