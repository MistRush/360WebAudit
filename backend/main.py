import sys
import asyncio

# ── Windows Subprocess Fix ──────────────────────────────────────────────────
if sys.platform == 'win32':
    import asyncio
    from asyncio import WindowsProactorEventLoopPolicy
    if not isinstance(asyncio.get_event_loop_policy(), WindowsProactorEventLoopPolicy):
        asyncio.set_event_loop_policy(WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
import tldextract
import os
import json
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from database import init_db, get_db, Audit, AuditLog, AuditStatus, AsyncSessionLocal
from audit_runner import run_audit
from config import settings


# ── Lifespan (startup/shutdown) ───────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    loop_name = type(loop).__name__
    print(f"DEBUG: Event loop = {loop_name}")
    if sys.platform == 'win32' and 'Proactor' not in loop_name:
        print(f"WARNING: Loop is {loop_name} (not ProactorEventLoop). Playwright subprocesses may fail!")
    await init_db()
    settings.reports_dir.mkdir(exist_ok=True, parents=True)
    yield


app = FastAPI(
    title="AI Web Auditor & Sales Engine 2026",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ───────────────────────────────────────────────────────────────────

class AuditRequest(BaseModel):
    url: str                 # e.g. "https://example.com"
    email: str | None = None


class AuditResponse(BaseModel):
    id: int
    url: str
    status: str
    score_total: float | None
    score_performance: float | None
    score_seo: float | None
    score_marketing: float | None
    score_ux: float | None
    created_at: str
    completed_at: str | None
    report_available: bool


# ── Helper ────────────────────────────────────────────────────────────────────

def _audit_to_response(audit: Audit) -> AuditResponse:
    return AuditResponse(
        id=audit.id,
        url=audit.url,
        status=audit.status.value,
        score_total=audit.score_total,
        score_performance=audit.score_performance,
        score_seo=audit.score_seo,
        score_marketing=audit.score_marketing,
        score_ux=audit.score_ux,
        created_at=audit.created_at.isoformat() if audit.created_at else "",
        completed_at=audit.completed_at.isoformat() if audit.completed_at else None,
        report_available=bool(audit.report_html_path),
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    dashboard = Path(__file__).parent.parent / "frontend" / "index.html"
    if dashboard.exists():
        return HTMLResponse(content=dashboard.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Dashboard nenalezen — umístěte frontend/index.html</h1>")


@app.post("/audits", response_model=AuditResponse, status_code=201)
async def create_audit(
    body: AuditRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Start a new web audit. Returns immediately with audit ID."""
    url = str(body.url).rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    ext = tldextract.extract(url)
    domain = f"{ext.domain}.{ext.suffix}"

    audit = Audit(url=url, domain=domain, status=AuditStatus.PENDING)
    db.add(audit)
    await db.commit()
    await db.refresh(audit)

    # Run audit in background
    background_tasks.add_task(run_audit, audit.id)

    return _audit_to_response(audit)


@app.get("/audits", response_model=list[AuditResponse])
async def list_audits(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List all audits, newest first."""
    result = await db.execute(
        select(Audit).order_by(desc(Audit.created_at)).offset(offset).limit(limit)
    )
    audits = result.scalars().all()
    return [_audit_to_response(a) for a in audits]


@app.get("/audits/{audit_id}", response_model=AuditResponse)
async def get_audit(audit_id: int, db: AsyncSession = Depends(get_db)):
    audit = await db.get(Audit, audit_id)
    if not audit:
        raise HTTPException(404, "Audit nenalezen")
    return _audit_to_response(audit)


@app.get("/audits/{audit_id}/report", response_class=HTMLResponse)
async def get_report_html(audit_id: int, db: AsyncSession = Depends(get_db)):
    """Serve the generated HTML report."""
    audit = await db.get(Audit, audit_id)
    if not audit or not audit.report_html_path:
        raise HTTPException(404, "Report nenalezen nebo audit ještě nebyl dokončen")
    from pathlib import Path
    path = Path(audit.report_html_path)
    if not path.exists():
        raise HTTPException(404, "Soubor reportu nenalezen")
    return HTMLResponse(content=path.read_text(encoding="utf-8"))


@app.get("/audits/{audit_id}/report/pdf")
async def get_report_pdf(audit_id: int, db: AsyncSession = Depends(get_db)):
    """Generate and serve PDF version of the report."""
    audit = await db.get(Audit, audit_id)
    if not audit or not audit.report_html_path:
        raise HTTPException(404, "Report nenalezen")

    from pathlib import Path
    html_path = Path(audit.report_html_path)
    pdf_path = html_path.with_suffix(".pdf")

    if not pdf_path.exists():
        try:
            from report.pdf_exporter import export_pdf
            await export_pdf(str(html_path), str(pdf_path))
        except Exception as e:
            raise HTTPException(500, f"PDF export selhal: {e}")

    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        filename=f"audit_{audit.domain}_{audit_id}.pdf",
    )


@app.get("/audits/{audit_id}/stream")
async def stream_audit_log(audit_id: int, db: AsyncSession = Depends(get_db)):
    """
    Server-Sent Events endpoint for live audit log streaming.
    Frontend connects and receives log messages as they are written.
    """
    audit = await db.get(Audit, audit_id)
    if not audit:
        raise HTTPException(404, "Audit nenalezen")

    async def event_generator() -> AsyncGenerator[str, None]:
        last_id = 0
        terminal_statuses = {AuditStatus.DONE, AuditStatus.FAILED}

        while True:
            # Use AsyncSessionLocal to get a fresh session for each check
            async with AsyncSessionLocal() as session:
                # Fetch new logs
                result = await session.execute(
                    select(AuditLog)
                    .where(AuditLog.audit_id == audit_id, AuditLog.id > last_id)
                    .order_by(AuditLog.id)
                )
                logs = result.scalars().all()
                for log_entry in logs:
                    last_id = log_entry.id
                    data = json.dumps({
                        "id": log_entry.id,
                        "level": log_entry.level,
                        "message": log_entry.message,
                        "timestamp": log_entry.timestamp.isoformat(),
                    })
                    yield f"data: {data}\n\n"

                # Check if audit is done
                current = await session.get(Audit, audit_id)
                if current and current.status in terminal_statuses:
                    final = json.dumps({"status": current.status.value, "score": current.score_total})
                    yield f"event: done\ndata: {final}\n\n"
                    break

            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.delete("/audits/{audit_id}", status_code=204)
async def delete_audit(audit_id: int, db: AsyncSession = Depends(get_db)):
    audit = await db.get(Audit, audit_id)
    if not audit:
        raise HTTPException(404)
    await db.delete(audit)
    await db.commit()


if __name__ == "__main__":
    import uvicorn
    # IMPORTANT: On Windows, reload=True spawns child processes that do NOT inherit
    # WindowsProactorEventLoopPolicy, which breaks Playwright (NotImplementedError).
    # Use reload=False for local dev, or use a run.py wrapper (see run.py).
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
