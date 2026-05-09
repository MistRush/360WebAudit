"""
audit_runner.py — Orchestrates the full audit pipeline:
Scrape → Extract → Score → AI Analysis → Generate Report
Called from FastAPI background tasks or Celery worker.
"""
from __future__ import annotations
import asyncio
from datetime import datetime
from pathlib import Path

from database import AsyncSessionLocal, Audit, AuditLog, AuditStatus, AuditIssue, IssueSeverity
from scraper.playwright_engine import PlaywrightEngine
from scraper.seo_extractor import extract_seo
from scraper.performance_metrics import analyze_performance, fetch_pagespeed
from scraper.marketing_stack import detect_marketing_stack
from scraper.schema_extractor import extract_schema
from scraper.geo_checker import check_geo
from ai.gap_analyzer import analyze_gaps_and_fixes
from report.score_calculator import calculate_scores
from report.html_generator import generate_html_report
from config import settings


async def run_audit(audit_id: int):
    """Main audit pipeline. Updates audit record in DB at each step."""

    async def log(level: str, msg: str):
        async with AsyncSessionLocal() as db:
            db.add(AuditLog(audit_id=audit_id, level=level, message=msg))
            await db.commit()

    async with AsyncSessionLocal() as db:
        audit: Audit = await db.get(Audit, audit_id)
        if not audit:
            return
        url = audit.url
        audit.status = AuditStatus.RUNNING
        await db.commit()

    try:
        # ── STEP 1: Playwright scrape ────────────────────────
        engine = PlaywrightEngine(log_callback=log)
        raw = await engine.scrape_full(url)

        desktop_html = raw["desktop"].get("html", "")
        mobile_html = raw["mobile"].get("html", "")
        final_url = raw["desktop"].get("final_url", url)
        ttfb_ms = raw["desktop"].get("ttfb_ms")
        resource_sizes = raw["desktop"].get("resource_sizes", [])
        perf_raw = raw.get("performance_raw", {})
        dom_nodes = raw["desktop"].get("dom_nodes", 0)
        screenshot_desktop = raw.get("screenshot_desktop")

        # ── STEP 2: Extract data ─────────────────────────────
        await log("info", "Extrahuji SEO data...")
        seo = extract_seo(desktop_html, final_url)

        await log("info", "Analyzuji performance metriky...")
        performance = analyze_performance(perf_raw, resource_sizes)
        performance["ttfb_ms"] = performance.get("ttfb_ms") or ttfb_ms
        performance["dom_nodes"] = dom_nodes

        # Optionally enrich with PageSpeed API
        psi = await fetch_pagespeed(url)
        if psi.get("mobile") and not psi["mobile"].get("error"):
            # Override with more accurate PSI data where available
            m = psi["mobile"]
            if m.get("lcp_ms") and not performance.get("lcp_ms"):
                performance["lcp_ms"] = round(m["lcp_ms"])
                from scraper.performance_metrics import _rating, LCP_GOOD, LCP_POOR
                performance["lcp_rating"] = _rating(m["lcp_ms"], LCP_GOOD, LCP_POOR)

        await log("info", "Detekcuji marketing stack...")
        marketing = detect_marketing_stack(desktop_html)

        await log("info", "Extrahuji Schema.org strukturovaná data...")
        schema = extract_schema(desktop_html)

        await log("info", "Kontroluji GEO / SSL / server...")
        geo = await check_geo(url, ttfb_ms=ttfb_ms)

        # ── STEP 3: AI Analysis ──────────────────────────────
        async with AsyncSessionLocal() as db:
            audit = await db.get(Audit, audit_id)
            audit.status = AuditStatus.ANALYZING
            await db.commit()

        await log("info", "Spouštím AI analýzu (Gemini)...")
        ai_result = await analyze_gaps_and_fixes(seo, performance, marketing, schema, geo, url)
        semantic = ai_result.get("semantic", {})

        # ── STEP 4: Score ────────────────────────────────────
        await log("info", "Počítám skóre...")
        scores = calculate_scores(seo, performance, marketing, schema, geo, semantic)

        # ── STEP 5: Generate report ──────────────────────────
        async with AsyncSessionLocal() as db:
            audit = await db.get(Audit, audit_id)
            audit.status = AuditStatus.REPORTING
            await db.commit()

        await log("info", "Generuji HTML report...")
        html_content = generate_html_report(
            audit_id=audit_id, url=url, scores=scores,
            seo=seo, performance=performance, marketing=marketing,
            schema=schema, geo=geo, ai_result=ai_result,
            screenshot_desktop_b64=screenshot_desktop,
        )

        # Save HTML
        report_path = settings.reports_dir / f"audit_{audit_id}.html"
        report_path.write_text(html_content, encoding="utf-8")

        # ── STEP 6: Persist results ──────────────────────────
        async with AsyncSessionLocal() as db:
            audit = await db.get(Audit, audit_id)
            audit.status = AuditStatus.DONE
            audit.completed_at = datetime.utcnow()
            audit.score_performance = scores.performance
            audit.score_seo = scores.seo
            audit.score_marketing = scores.marketing
            audit.score_ux = scores.ux
            audit.score_total = scores.total
            audit.set_raw("raw_seo", seo)
            audit.set_raw("raw_performance", performance)
            audit.set_raw("raw_marketing", marketing)
            audit.set_raw("raw_schema", schema)
            audit.set_raw("raw_geo", geo)
            audit.ai_summary = ai_result.get("executive_summary", "")
            audit.report_html_path = str(report_path)
            await db.commit()

        await log("success", f"Audit dokončen! Skóre: {scores.total}/100 ({scores.grade})")

    except Exception as e:
        import traceback
        err = f"Chyba auditu: {e}\n{traceback.format_exc()[:2000]}"
        await log("error", err)
        async with AsyncSessionLocal() as db:
            audit = await db.get(Audit, audit_id)
            if audit:
                audit.status = AuditStatus.FAILED
                audit.error_message = str(e)[:500]
                await db.commit()
