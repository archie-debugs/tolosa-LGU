import os

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv
from sqlalchemy import inspect

load_dotenv()

from alembic import command
from alembic.config import Config

from Backends.backend.database import engine
from Backends.backend import models
from Backends.backend.routes.status import router as status_router
from Backends.backend.routes.documents import router as documents_router
from Backends.backend.routes.analytics import router as analytics_router
from Backends.backend.routes.audit import router as audit_router
from Backends.backend.routes.auth import login_user


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


app = FastAPI(title="LGU Tolosa - Employee Backend")

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
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    alembic_cfg = Config(os.path.join(project_root, "alembic.ini"))

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
except Exception as exc:
    raise RuntimeError(f"Startup initialization failed: {exc}") from exc

auth_router = APIRouter()
auth_router.post("/auth/login")(login_user)

app.include_router(status_router)
app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(analytics_router)
app.include_router(audit_router)


@app.get("/health")
def health():
    return {"status": "ok"}

