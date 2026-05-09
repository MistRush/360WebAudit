"""
config.py — Centralized application settings loaded from environment variables.
Uses pydantic-settings for validation and type coercion.
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    # ── AI ────────────────────────────────────────────────
    gemini_api_key: str = Field("", env="GEMINI_API_KEY")
    gemini_model: str = Field("gemini-1.5-flash", env="GEMINI_MODEL")
    
    openrouter_api_key: str = Field("", env="OPENROUTER_API_KEY")
    openrouter_model: str = Field("google/gemini-flash-1.5", env="OPENROUTER_MODEL")

    # ── PageSpeed (optional) ──────────────────────────────
    google_pagespeed_api_key: str = Field("", env="GOOGLE_PAGESPEED_API_KEY")

    # ── Database ──────────────────────────────────────────
    database_url: str = Field(
        "sqlite+aiosqlite:///./webauditor.db", env="DATABASE_URL"
    )

    # ── Redis / Celery ────────────────────────────────────
    redis_url: str = Field("redis://localhost:6379/0", env="REDIS_URL")

    # ── App ───────────────────────────────────────────────
    app_secret_key: str = Field("dev-secret-change-me", env="APP_SECRET_KEY")
    max_concurrent_audits: int = Field(3, env="MAX_CONCURRENT_AUDITS")
    audit_timeout_seconds: int = Field(120, env="AUDIT_TIMEOUT_SECONDS")
    rate_limit_gemini_rpm: int = Field(55, env="RATE_LIMIT_GEMINI_RPM")

    # ── Report ────────────────────────────────────────────
    report_brand_name: str = Field("AI Web Auditor", env="REPORT_BRAND_NAME")
    report_brand_color: str = Field("#6366f1", env="REPORT_BRAND_COLOR")
    reports_dir: Path = Field(Path("./reports"), env="REPORTS_DIR")

    # ── Email ─────────────────────────────────────────────
    smtp_host: str = Field("", env="SMTP_HOST")
    smtp_port: int = Field(587, env="SMTP_PORT")
    smtp_user: str = Field("", env="SMTP_USER")
    smtp_pass: str = Field("", env="SMTP_PASS")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
settings.reports_dir.mkdir(parents=True, exist_ok=True)
