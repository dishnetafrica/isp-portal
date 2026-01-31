"""
ISP Customer Portal - Main FastAPI Application
Supports: Starlink, MikroTik, TR-069 (D-Link/TP-Link), UISP Integration
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import structlog
from prometheus_client import make_asgi_app

from app.core.config import settings
from app.core.database import init_db
from app.api import auth, devices, starlink, mikrotik, tr069, billing, hotspot

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting ISP Portal API", environment=settings.ENVIRONMENT)
    await init_db()
    yield
    # Shutdown
    logger.info("Shutting down ISP Portal API")


# Create FastAPI app
app = FastAPI(
    title="ISP Customer Portal API",
    description="Manage Starlink, MikroTik, and TR-069 devices with UISP billing integration",
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    lifespan=lifespan,
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "isp-portal-api",
        "version": "1.0.0"
    }


# Include API routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(devices.router, prefix="/api/devices", tags=["Devices"])
app.include_router(starlink.router, prefix="/api/starlink", tags=["Starlink"])
app.include_router(mikrotik.router, prefix="/api/mikrotik", tags=["MikroTik"])
app.include_router(tr069.router, prefix="/api/tr069", tags=["TR-069"])
app.include_router(billing.router, prefix="/api/billing", tags=["Billing"])
app.include_router(hotspot.router, prefix="/api/hotspot", tags=["Hotspot"])


@app.get("/")
async def root():
    return {
        "message": "ISP Customer Portal API",
        "docs": "/docs",
        "health": "/health"
    }
