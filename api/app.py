"""FastAPI service. Three routes only: GET /health (operational), POST /score-account, POST /evaluate-quote."""
from fastapi import FastAPI

from api.routes import evaluate_quote, health, score_account

app = FastAPI(
    title="GTM Revenue Operations Engine",
    description="Deterministic CPQ-style pricing/approval evaluation and signal-based account scoring. "
                "Commercial policy comes from config/policy.yaml.",
    version="1.0.0",
)
app.include_router(health.router)
app.include_router(score_account.router)
app.include_router(evaluate_quote.router)
