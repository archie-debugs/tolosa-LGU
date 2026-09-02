import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from dotenv import load_dotenv
from sqlalchemy import inspect

# Load .env early so core.py picks up environment overrides
load_dotenv()

from alembic import command
from alembic.config import Config

from .database import engine, get_database_info
from . import models
from .core import ensure_default_super_admin_account
from .routes.auth import router as auth_router
from .routes.status import router as status_router
from .routes.audit import router as audit_router
from .routes.registration import router as registration_router
from .routes.documents import router as documents_router
from .routes.analytics import router as analytics_router


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
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
]

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


def run_database_migrations() -> None:
    table_names = inspect(engine).get_table_names()
    alembic_cfg = Config(os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini"))

    if not table_names:
        models.Base.metadata.create_all(bind=engine)
        command.stamp(alembic_cfg, "head")
        return

    if "alembic_version" not in table_names:
        command.stamp(alembic_cfg, "head")
        return

    command.upgrade(alembic_cfg, "head")


try:
    run_database_migrations()
    ensure_default_super_admin_account()
except Exception as exc:
    raise RuntimeError(f"Startup initialization failed: {exc}") from exc

app.include_router(status_router)
app.include_router(auth_router)
app.include_router(registration_router)
app.include_router(audit_router)
app.include_router(documents_router)
app.include_router(analytics_router)


@app.on_event("startup")
def log_database_info():
    info = get_database_info()
    print(f"Database dialect: {info['dialect']}, URL: {info['url']}")


@app.get("/health")
def health():
    info = get_database_info()
    return {"status": "ok", "database": {"dialect": info['dialect'], "url": info['url']}}
