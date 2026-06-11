"""
Xenia CRM – FastAPI Application Entry Point
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.config import settings
from app.database import engine, Base

# ── Import all models (registers with metadata) ───────────────────────────────
import app.models  # noqa: F401

# ── Routers (imported here; implemented in later phases) ──────────────────────
# from app.routers import customers, opportunities, campaigns, planner, analytics, briefing, webhooks


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────
from app.scheduler import start_scheduler, stop_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    print(f"STARTING UP {settings.app_name} (env={settings.app_env})")

    # Create tables if they don't exist (Alembic handles production migrations)
    if settings.debug:
        Base.metadata.create_all(bind=engine)

    # Start background scheduler
    start_scheduler()

    yield  # App runs here

    # Shutdown
    print(f"SHUTTING DOWN {settings.app_name}")
    stop_scheduler()


# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Xenia CRM API",
    description=(
        "AI-Native Shopper CRM powered by Xenia AI. "
        "Understand shoppers, discover opportunities, plan campaigns, measure impact."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
def health_check():
    """Service health probe."""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": "1.0.0",
        "ai_layer": "Xenia AI (Gemini 2.5 Flash)",
    }


@app.get("/", tags=["System"])
def root():
    return {
        "message": f"Welcome to {settings.app_name} API",
        "docs": "/docs",
        "health": "/health",
    }


# ── Register Routers ──────────────────────────────────────────────────────────
from app.routers import customers, opportunities, campaigns, planner, analytics, briefing, webhooks, promotions

app.include_router(customers.router)
app.include_router(opportunities.router)
app.include_router(campaigns.router)
app.include_router(planner.router)
app.include_router(analytics.router)
app.include_router(briefing.router)
app.include_router(webhooks.router)
app.include_router(promotions.router)


