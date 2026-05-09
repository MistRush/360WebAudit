"""
database.py — SQLAlchemy async models and database initialization.
Tables: audits, audit_results, reports
"""
from datetime import datetime
from typing import Optional
import json

from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime,
    Boolean, ForeignKey, JSON, Enum as SAEnum
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship
import enum

from config import settings


# ── Engine & Session ──────────────────────────────────────────────────────────

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# ── Enums ─────────────────────────────────────────────────────────────────────

class AuditStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    ANALYZING = "analyzing"   # AI brain working
    REPORTING = "reporting"   # generating report
    DONE = "done"
    FAILED = "failed"


class IssueSeverity(str, enum.Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"


# ── Base ──────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Models ────────────────────────────────────────────────────────────────────

class Audit(Base):
    """One audit run for a given URL."""
    __tablename__ = "audits"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(2048), nullable=False, index=True)
    domain = Column(String(512), nullable=False)
    status = Column(SAEnum(AuditStatus), default=AuditStatus.PENDING, nullable=False)
    error_message = Column(Text, nullable=True)

    # Scores (0–100)
    score_performance = Column(Float, nullable=True)
    score_seo = Column(Float, nullable=True)
    score_marketing = Column(Float, nullable=True)
    score_ux = Column(Float, nullable=True)
    score_total = Column(Float, nullable=True)

    # Raw scraped data (stored as JSON text for SQLite compatibility)
    raw_seo = Column(Text, nullable=True)           # JSON
    raw_performance = Column(Text, nullable=True)   # JSON
    raw_marketing = Column(Text, nullable=True)     # JSON
    raw_schema = Column(Text, nullable=True)        # JSON
    raw_geo = Column(Text, nullable=True)           # JSON

    # AI analysis output
    ai_summary = Column(Text, nullable=True)
    ai_gaps = Column(Text, nullable=True)           # JSON list of gaps
    ai_fixes = Column(Text, nullable=True)          # JSON list of fixes

    # Report
    report_html_path = Column(String(512), nullable=True)
    report_pdf_path = Column(String(512), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    issues = relationship("AuditIssue", back_populates="audit", cascade="all, delete-orphan")
    logs = relationship("AuditLog", back_populates="audit", cascade="all, delete-orphan")

    # Helpers
    def get_raw(self, field: str) -> dict:
        val = getattr(self, field)
        return json.loads(val) if val else {}

    def set_raw(self, field: str, data: dict):
        setattr(self, field, json.dumps(data, ensure_ascii=False))


class AuditIssue(Base):
    """Individual issue found during audit (one row per check)."""
    __tablename__ = "audit_issues"

    id = Column(Integer, primary_key=True, index=True)
    audit_id = Column(Integer, ForeignKey("audits.id"), nullable=False)
    category = Column(String(64), nullable=False)   # seo | performance | marketing | ux
    key = Column(String(128), nullable=False)        # e.g. "lcp", "missing_h1"
    label = Column(String(256), nullable=False)      # Human-readable name
    severity = Column(SAEnum(IssueSeverity), nullable=False)
    value = Column(Text, nullable=True)             # Measured value
    expected = Column(Text, nullable=True)          # Expected value / benchmark
    description = Column(Text, nullable=True)       # Layman explanation
    fix_proposal = Column(Text, nullable=True)      # "Řešení v novém webu"
    money_impact = Column(Text, nullable=True)      # "Proč vás to stojí peníze"

    audit = relationship("Audit", back_populates="issues")


class AuditLog(Base):
    """Real-time log entries streamed to frontend via SSE."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    audit_id = Column(Integer, ForeignKey("audits.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    level = Column(String(16), default="info")      # info | warning | error | success
    message = Column(Text, nullable=False)

    audit = relationship("Audit", back_populates="logs")


# ── DB Init ───────────────────────────────────────────────────────────────────

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
