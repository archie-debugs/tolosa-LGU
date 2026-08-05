from fastapi import FastAPI
from dotenv import load_dotenv

# Load .env early so core.py picks up environment overrides
load_dotenv()
from fastapi.middleware.cors import CORSMiddleware

from .database import engine
from . import models
from .core import ensure_user_role_column, ensure_current_location_column
from .core import ensure_source_filename_column
from .routes.auth import router as auth_router
from .routes.status import router as status_router
from .routes.workflow import router as workflow_router
from .routes.documents import router as documents_router
from .routes.tracking import router as tracking_router
from .secretariat.documents import router as secretariat_router

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
except Exception:
    pass

try:
    ensure_current_location_column()
except Exception:
    pass

try:
    ensure_source_filename_column()
except Exception:
    pass

app.include_router(status_router)
app.include_router(auth_router)
app.include_router(workflow_router)
app.include_router(documents_router)
app.include_router(tracking_router)
app.include_router(secretariat_router)


@app.get("/health")
def health():
    return {"status": "ok"}
