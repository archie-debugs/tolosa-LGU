from fastapi import FastAPI
from dotenv import load_dotenv

# Load .env early so core.py picks up environment overrides
load_dotenv()
from fastapi.middleware.cors import CORSMiddleware

from .database import engine
from . import models
from .core import ensure_schema_columns, ensure_user_role_column
from .routes.auth import router as auth_router
from .routes.user_roles import router as user_roles_router
from .routes.status import router as status_router
from .routes.audit import router as audit_router
from .routes.registration import router as registration_router

app = FastAPI(title="LGU Tolosa SB Legislative Tracking Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

models.Base.metadata.create_all(bind=engine)

try:
    ensure_user_role_column()
    ensure_schema_columns()
except Exception:
    pass

app.include_router(status_router)
app.include_router(auth_router)
app.include_router(user_roles_router)
app.include_router(registration_router)
app.include_router(audit_router)


@app.get("/health")
def health():
    return {"status": "ok"}
