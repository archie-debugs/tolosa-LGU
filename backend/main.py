import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from dotenv import load_dotenv

# Load .env early so core.py picks up environment overrides
load_dotenv()

from .database import engine
from . import models
from .core import ensure_schema_columns, ensure_user_role_column
from .routes.auth import router as auth_router
from .routes.status import router as status_router
from .routes.audit import router as audit_router
from .routes.registration import router as registration_router
from .routes.documents import router as documents_router


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

force_https = os.getenv("FORCE_HTTPS", "1").lower() not in ("0", "false", "no")
if force_https:
    app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

models.Base.metadata.create_all(bind=engine)

try:
    ensure_user_role_column()
    ensure_schema_columns()
except Exception:
    pass

app.include_router(status_router)
app.include_router(auth_router)
app.include_router(registration_router)
app.include_router(audit_router)
app.include_router(documents_router)


@app.get("/health")
def health():
    return {"status": "ok"}
