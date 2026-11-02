import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import db
from app.api.auth import router as auth_router, ensure_bootstrap_admin
from app.api.documents import router as documents_router
from app.api.dashboard import router as dashboard_router
from app.api.search import router as search_router
from app.api.security import router as security_router, ensure_default_rules
from app.api.chat import router as chat_router

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("docintel")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting DocIntel AI backend...")
    await db.connect()
    await ensure_default_rules()
    await ensure_bootstrap_admin()
    yield
    # Shutdown
    logger.info("Shutting down DocIntel AI backend...")
    await db.disconnect()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Enterprise Document Intelligence & Secure Data Extraction Platform API",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# CORS Middleware
# Only explicitly configured origins are permitted; the wildcard is never
# combined with credentials (an invalid and insecure combination).
_allowed_origins = sorted({o.strip() for o in (settings.CORS_ORIGINS + [settings.FRONTEND_URL]) if o and o.strip()})
if "*" in _allowed_origins:
    # Never allow credentialed wildcard origins; drop the wildcard.
    _allowed_origins = [o for o in _allowed_origins if o != "*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# Global Exception Handler to ensure clean user-facing error messages without stack trace leak
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please contact system administrator."},
    )


# Liveness probe: process is up. Intentionally minimal and never leaks
# infrastructure details (no database host, mode, or credentials).
@app.get("/api/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
    }


# Readiness probe: reports whether dependencies required to serve requests are
# actually available, without exposing backend internals.
@app.get("/api/ready", tags=["Health"])
async def readiness_check():
    return {
        "ready": bool(db.is_connected),
        "status": "ready" if db.is_connected else "unavailable",
    }


# Include Routers under /api
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(documents_router, prefix=settings.API_V1_STR)
app.include_router(dashboard_router, prefix=settings.API_V1_STR)
app.include_router(search_router, prefix=settings.API_V1_STR)
app.include_router(security_router, prefix=settings.API_V1_STR)
app.include_router(chat_router, prefix=settings.API_V1_STR)
