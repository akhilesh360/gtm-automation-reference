"""FastAPI service. Core routes: GET /health (operational), POST /score-account, POST /evaluate-quote.
POST /webhooks/clay is registered only when CLAY_ENABLED=true."""
from fastapi import FastAPI

from api.routes import evaluate_quote, health, score_account
from src.config import settings

app = FastAPI(
    title="GTM Revenue Operations Engine",
    description="Deterministic CPQ-style pricing/approval evaluation and signal-based account scoring. "
                "Commercial policy comes from config/policy.yaml.",
    version="1.0.0",
)
app.include_router(health.router)
app.include_router(score_account.router)
app.include_router(evaluate_quote.router)

if settings.clay_enabled:  # optional connector route; absent unless switched on
    from api.routes import clay_webhook

    app.include_router(clay_webhook.router)
