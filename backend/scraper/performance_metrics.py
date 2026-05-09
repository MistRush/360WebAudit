"""
performance_metrics.py — Interprets raw performance data from Playwright
and optionally enriches it via Google PageSpeed Insights API.
"""
from __future__ import annotations
import httpx
from config import settings


# ── Thresholds (Core Web Vitals 2024) ─────────────────────────────────────────
# Source: web.dev/articles/vitals
LCP_GOOD = 2500        # ms
LCP_POOR = 4000        # ms

CLS_GOOD = 0.1
CLS_POOR = 0.25

INP_GOOD = 200         # ms
INP_POOR = 500         # ms

FCP_GOOD = 1800        # ms
FCP_POOR = 3000        # ms

TTFB_GOOD = 800        # ms
TTFB_POOR = 1800       # ms


def _rating(value: float | None, good: float, poor: float, lower_is_better=True) -> str:
    if value is None:
        return "unknown"
    if lower_is_better:
        if value <= good: return "good"
        if value <= poor: return "needs_improvement"
        return "poor"
    else:
        if value >= good: return "good"
        if value >= poor: return "needs_improvement"
        return "poor"


def analyze_performance(perf_raw: dict, resource_sizes: list[dict]) -> dict:
    """
    Process raw performance data collected by the Performance Observer
    and resource timing from Playwright network interception.
    """
    lcp = perf_raw.get("lcp")
    cls = perf_raw.get("cls")
    fcp = perf_raw.get("fcp")
    ttfb = perf_raw.get("ttfb")
    long_tasks: list[float] = perf_raw.get("long_tasks", [])
    resource_timing: list[dict] = perf_raw.get("resource_timing", [])

    # INP estimation from long tasks (proxy — real INP needs interaction)
    inp_estimate = max(long_tasks) if long_tasks else None

    # ── Resource analysis ─────────────────────────────────
    js_resources = [r for r in resource_sizes if "javascript" in r.get("content_type", "").lower()
                    or r.get("url", "").endswith(".js")]
    css_resources = [r for r in resource_sizes if "css" in r.get("content_type", "").lower()
                     or r.get("url", "").endswith(".css")]
    image_resources = [r for r in resource_sizes if "image" in r.get("content_type", "").lower()]

    total_js_kb = round(sum(r.get("size", 0) for r in js_resources) / 1024, 1)
    total_css_kb = round(sum(r.get("size", 0) for r in css_resources) / 1024, 1)
    total_img_kb = round(sum(r.get("size", 0) for r in image_resources) / 1024, 1)
    total_transfer_kb = round(sum(r.get("size", 0) for r in resource_sizes) / 1024, 1)

    # Resources from resource_timing (richer data)
    rt_js_kb = round(sum(r.get("transfer_size", 0) for r in resource_timing
                         if r.get("initiator_type") == "script") / 1024, 1)
    rt_css_kb = round(sum(r.get("transfer_size", 0) for r in resource_timing
                          if r.get("initiator_type") == "link") / 1024, 1)
    rt_img_kb = round(sum(r.get("transfer_size", 0) for r in resource_timing
                          if r.get("initiator_type") == "img") / 1024, 1)

    # Detect unminified JS (heuristic: file >100KB that doesn't contain .min.)
    # Note: resource_timing uses 'name' key (from PerformanceObserver), not 'url'
    large_js = [r.get("name", "") for r in resource_timing
                if r.get("initiator_type") == "script"
                and r.get("transfer_size", 0) > 100 * 1024
                and ".min." not in r.get("name", "")]

    # Third-party requests
    from urllib.parse import urlparse
    third_party_count = 0

    # Detect render-blocking resources (simplified: sync scripts in head)
    render_blocking_scripts = [r.get("name", "") for r in resource_timing
                                if r.get("initiator_type") == "script"
                                and r.get("duration", 0) > 200]

    return {
        # Core Web Vitals
        "lcp_ms": round(lcp) if lcp is not None else None,
        "lcp_rating": _rating(lcp, LCP_GOOD, LCP_POOR),
        "cls": round(cls, 4) if cls is not None else None,
        "cls_rating": _rating(cls, CLS_GOOD, CLS_POOR),
        "inp_ms": round(inp_estimate) if inp_estimate is not None else None,
        "inp_rating": _rating(inp_estimate, INP_GOOD, INP_POOR),
        "fcp_ms": round(fcp) if fcp is not None else None,
        "fcp_rating": _rating(fcp, FCP_GOOD, FCP_POOR),
        "ttfb_ms": round(ttfb) if ttfb is not None else None,
        "ttfb_rating": _rating(ttfb, TTFB_GOOD, TTFB_POOR),

        # Resource budgets
        "total_js_kb": max(total_js_kb, rt_js_kb),
        "total_css_kb": max(total_css_kb, rt_css_kb),
        "total_img_kb": max(total_img_kb, rt_img_kb),
        "total_transfer_kb": total_transfer_kb,
        "js_ok": max(total_js_kb, rt_js_kb) < 400,
        "img_ok": max(total_img_kb, rt_img_kb) < 1000,

        # Issues
        "large_unminified_js": large_js[:5],
        "render_blocking_scripts": render_blocking_scripts[:5],
        "long_tasks_count": len(long_tasks),
        "resource_count": len(resource_sizes),
    }


async def fetch_pagespeed(url: str) -> dict:
    """
    Fetch PageSpeed Insights data for both mobile and desktop.
    Returns empty dict if API key is missing or request fails.
    """
    if not settings.google_pagespeed_api_key:
        return {}

    results = {}
    async with httpx.AsyncClient(timeout=30) as client:
        for strategy in ("mobile", "desktop"):
            try:
                resp = await client.get(
                    "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
                    params={
                        "url": url,
                        "strategy": strategy,
                        "key": settings.google_pagespeed_api_key,
                        "category": ["performance", "seo", "accessibility", "best-practices"],
                    }
                )
                data = resp.json()
                cats = data.get("lighthouseResult", {}).get("categories", {})
                audits = data.get("lighthouseResult", {}).get("audits", {})

                results[strategy] = {
                    "performance_score": round((cats.get("performance", {}).get("score", 0) or 0) * 100),
                    "seo_score": round((cats.get("seo", {}).get("score", 0) or 0) * 100),
                    "accessibility_score": round((cats.get("accessibility", {}).get("score", 0) or 0) * 100),
                    "best_practices_score": round((cats.get("best-practices", {}).get("score", 0) or 0) * 100),
                    "lcp_ms": _psi_metric(audits, "largest-contentful-paint"),
                    "cls": _psi_metric(audits, "cumulative-layout-shift"),
                    "fcp_ms": _psi_metric(audits, "first-contentful-paint"),
                    "ttfb_ms": _psi_metric(audits, "server-response-time"),
                    "speed_index": _psi_metric(audits, "speed-index"),
                }
            except Exception as e:
                results[strategy] = {"error": str(e)}

    return results


def _psi_metric(audits: dict, key: str) -> float | None:
    audit = audits.get(key, {})
    return audit.get("numericValue")
