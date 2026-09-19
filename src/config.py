"""Environment settings only (paths, switches, credentials). Policy lives in config/policy.yaml."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    duckdb_path: str = "data/gtm.duckdb"
    mock_sf_path: str = "data/processed/mock_salesforce.json"
    random_seed: int = 42
    log_level: str = "INFO"

    sf_enabled: bool = False
    sf_username: str = ""
    sf_password: str = ""
    sf_security_token: str = ""
    sf_domain: str = "login"
    sf_auth: str = "cli"          # "cli" = reuse the Salesforce CLI session (no password); "password" = username/password/token
    sf_alias: str = "gtm-dev"     # CLI org alias used when sf_auth = "cli"

    ai_enabled: bool = False
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5"

    @property
    def duckdb_file(self) -> Path:
        p = Path(self.duckdb_path)
        return p if p.is_absolute() else PROJECT_ROOT / p

    @property
    def raw_dir(self) -> Path:
        return PROJECT_ROOT / "data" / "raw"

    @property
    def processed_dir(self) -> Path:
        return PROJECT_ROOT / "data" / "processed"

    @property
    def sql_dir(self) -> Path:
        return PROJECT_ROOT / "sql"

    @property
    def policy_file(self) -> Path:
        return PROJECT_ROOT / "config" / "policy.yaml"

    @property
    def log_file(self) -> Path:
        return PROJECT_ROOT / "logs" / "gtm_automation.log"

    @property
    def mock_sf_file(self) -> Path:
        p = Path(self.mock_sf_path)
        return p if p.is_absolute() else PROJECT_ROOT / p


settings = Settings()
