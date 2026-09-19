import os
from pathlib import Path

import pytest

# Tests must run with no env vars set: force the offline mode regardless of a local .env
os.environ["SF_ENABLED"] = "false"
os.environ["AI_ENABLED"] = "false"
os.environ["ANTHROPIC_API_KEY"] = ""

from src.config import PROJECT_ROOT  # noqa: E402
from src.policy import get_policy  # noqa: E402


@pytest.fixture(scope="session")
def policy():
    return get_policy()


@pytest.fixture(scope="session")
def pipeline_db(tmp_path_factory):
    """Run the full pipeline once against a temporary DuckDB file and a temporary mock Salesforce store."""
    from src import config
    tmp = tmp_path_factory.mktemp("db")
    config.settings.duckdb_path = str(tmp / "test.duckdb")
    config.settings.mock_sf_path = str(tmp / "mock_salesforce.json")
    from src.main import run_all
    run_all()
    yield config.settings.duckdb_file


@pytest.fixture
def products():
    from src.cpq.models import Product
    return {
        "PRD-API-STARTER": Product(product_id="PRD-API-STARTER", product_name="Starter API Commitment", pricing_model="usage",
                                   list_price_monthly=5000, included_units=5_000_000, overage_price_per_unit=0.0000012),
        "PRD-API-BASE": Product(product_id="PRD-API-BASE", product_name="Base API Commitment", pricing_model="usage",
                                list_price_monthly=10000, included_units=10_000_000, overage_price_per_unit=0.0000012),
        "PRD-ENT-PLATFORM": Product(product_id="PRD-ENT-PLATFORM", product_name="Enterprise Platform", pricing_model="usage",
                                    list_price_monthly=50000, included_units=50_000_000, overage_price_per_unit=0.0000012),
        "PRD-SUPPORT-PREM": Product(product_id="PRD-SUPPORT-PREM", product_name="Premium Support", pricing_model="subscription",
                                    list_price_monthly=2000),
    }
