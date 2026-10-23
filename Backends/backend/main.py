import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from dotenv import load_dotenv
from sqlalchemy import text

# Load .env early so core.py picks up environment overrides
load_dotenv()

from .lan import refresh_development_public_urls
from .database import engine, get_database_info
from .core import ensure_default_super_admin_account
from .schema import run_database_migrations
from .routes.auth import router as auth_router
from .routes.status import router as status_router
from .routes.audit import router as audit_router
from .routes.documents import router as documents_router, public_qr_router
from .routes.analytics import _storage_information, router as analytics_router
from .routes.public_documents import router as public_documents_router, stats_router as public_stats_router
from .routes.settings import router as settings_router
from .routes.storage import router as storage_router
from .routes.offices import router as offices_router
from .routes.todays_documents import router as todays_documents_router
from .routes.notifications import router as notifications_router
from .routes.council import router as council_router
from .routes.council_sessions import router as council_sessions_router
from .routes.order_of_business import router as order_of_business_router
from .routes.measure_stages import router as measure_stages_router

refresh_development_public_urls()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        # HSTS over plain-HTTP development would pin browsers to HTTPS for this host for a year.
        if force_https:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-XSS-Protection", "1; mode=block")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self';")
        return response


app = FastAPI(title="LGU Tolosa SB Legislative Tracking Backend")

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8550",
    "http://127.0.0.1:8550",
    "http://localhost:8551",
    "http://127.0.0.1:8551",
]
configured_frontend_url = os.getenv("FRONTEND_PUBLIC_URL", "").strip().rstrip("/")
if configured_frontend_url and configured_frontend_url not in CORS_ALLOWED_ORIGINS:
    CORS_ALLOWED_ORIGINS.append(configured_frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

dev_http = os.getenv("DEV_HTTP", "0").lower() in ("1", "true", "yes")
force_https = not dev_http and os.getenv("FORCE_HTTPS", "1").lower() not in ("0", "false", "no")
if force_https:
    app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(SecurityHeadersMiddleware)


try:
    run_database_migrations()
    ensure_default_super_admin_account()
except Exception as exc:
    raise RuntimeError(f"Startup initialization failed: {exc}") from exc

app.include_router(status_router)
app.include_router(auth_router)
app.include_router(audit_router)
app.include_router(documents_router)
app.include_router(public_qr_router)
app.include_router(analytics_router)
app.include_router(public_documents_router)
app.include_router(public_stats_router)
app.include_router(settings_router)
app.include_router(storage_router)
app.include_router(offices_router)
app.include_router(todays_documents_router)
app.include_router(notifications_router)
app.include_router(council_router)
app.include_router(council_sessions_router)
app.include_router(order_of_business_router)
app.include_router(measure_stages_router)


@app.on_event("startup")
def log_database_info():
    info = get_database_info()
    print(f"Database dialect: {info['dialect']}, URL: {info['url']}")


@app.get("/health")
def health():
    info = get_database_info()
    database_status = "operational"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        database_status = "unavailable"

    storage = _storage_information()
    maintenance_mode = False
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT value FROM system_settings WHERE key = 'maintenance_mode' LIMIT 1")).fetchone()
            if result is not None:
                maintenance_mode = str(result[0]).strip().lower() == "true"
    except Exception:
        maintenance_mode = False

    return {
        "status": "ok",
        "backend": {"status": "operational"},
        "database": {
            "status": database_status,
            "dialect": info["dialect"],
        },
        "document_storage": storage["document_storage"],
        "temporary_upload_storage": storage["temporary_upload_storage"],
        "storage": storage,
        "maintenance_mode": maintenance_mode,
    }
