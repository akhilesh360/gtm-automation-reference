from fastapi import APIRouter

from api.models import HealthResponse
from src.config import settings
from src.db import session
from src.policy import get_policy

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["operational"])
def health() -> HealthResponse:
    db_ok = False
    try:
        with session() as con:
            con.execute("SELECT 1")
            db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    return HealthResponse(status="ok", db_ok=db_ok, policy_version=get_policy().version,
                          sf_enabled=settings.sf_enabled, ai_enabled=settings.ai_enabled)
