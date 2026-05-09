"""
score_calculator.py — Computes weighted audit scores from extracted data.
Weights: Performance 30%, SEO 30%, Marketing 20%, UX 20%
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class ScoreBreakdown:
    performance: float
    seo: float
    marketing: float
    ux: float
    total: float
    grade: str     # A+ / A / B / C / D / F
    color: str     # CSS color for UI


def calculate_scores(
    seo: dict,
    performance: dict,
    marketing: dict,
    schema: dict,
    geo: dict,
    semantic: dict | None = None,
) -> ScoreBreakdown:
    perf = _score_performance(performance, geo)
    seo_s = _score_seo(seo, schema, geo)
    mkt = _score_marketing(marketing)
    ux = _score_ux(seo, schema, marketing, geo, semantic)

    total = round(perf * 0.30 + seo_s * 0.30 + mkt * 0.20 + ux * 0.20, 1)

    return ScoreBreakdown(
        performance=round(perf, 1),
        seo=round(seo_s, 1),
        marketing=round(mkt, 1),
        ux=round(ux, 1),
        total=total,
        grade=_grade(total),
        color=_color(total),
    )


# ── Sub-scorers ───────────────────────────────────────────────────────────────

def _score_performance(p: dict, geo: dict) -> float:
    score = 100.0

    # LCP (weight 35)
    lcp_r = p.get("lcp_rating", "unknown")
    if lcp_r == "poor": score -= 35
    elif lcp_r == "needs_improvement": score -= 15

    # CLS (weight 25)
    cls_r = p.get("cls_rating", "unknown")
    if cls_r == "poor": score -= 25
    elif cls_r == "needs_improvement": score -= 10

    # INP (weight 20)
    inp_r = p.get("inp_rating", "unknown")
    if inp_r == "poor": score -= 20
    elif inp_r == "needs_improvement": score -= 8

    # TTFB (weight 10)
    ttfb_r = p.get("ttfb_rating", "unknown")
    if ttfb_r == "poor": score -= 10
    elif ttfb_r == "needs_improvement": score -= 5

    # JS bundle size (weight 10)
    js_kb = p.get("total_js_kb", 0)
    if js_kb > 800: score -= 10
    elif js_kb > 400: score -= 5

    return max(0, score)


def _score_seo(s: dict, schema: dict, geo: dict) -> float:
    score = 100.0

    if not s.get("title"): score -= 15
    elif not s.get("title_ok"): score -= 7

    if not s.get("meta_description"): score -= 12
    elif not s.get("meta_description_ok"): score -= 5

    if s.get("h1_count", 0) == 0: score -= 15
    elif not s.get("has_single_h1"): score -= 8

    if not s.get("has_canonical"): score -= 8
    if s.get("is_noindex"): score -= 25   # huge penalty
    
    # Check X-Robots-Tag from geo
    x_robots = (geo.get("x_robots_tag") or "").lower()
    if "noindex" in x_robots: score -= 25
    
    if not s.get("has_viewport"): score -= 10

    # Images
    img_missing = s.get("images_missing_alt_count", 0)
    img_total = s.get("image_count", 1)
    alt_ratio = img_missing / max(img_total, 1)
    if alt_ratio > 0.5: score -= 10
    elif alt_ratio > 0.2: score -= 5

    # Schema
    if not schema.get("has_any_schema"): score -= 8
    if not s.get("content_ok"): score -= 5

    # Robots & Sitemap (from geo)
    if geo.get("has_robots_txt") is False: score -= 5
    elif geo.get("robots_txt_ok") is False: score -= 15 # Severe issue, blocking indexing
    
    if geo.get("has_sitemap") is False: score -= 5

    return max(0, score)


def _score_marketing(m: dict) -> float:
    score = 0.0

    # Each critical tool = 25 pts
    if m.get("has_gtm"): score += 25
    if m.get("has_ga4"): score += 25

    # Advertising
    if m.get("has_fb_pixel"): score += 15
    if m.get("has_google_ads"): score += 10
    if m.get("has_tiktok_pixel"): score += 5

    # UX tools
    if m.get("has_hotjar") or m.get("has_microsoft_clarity"): score += 10
    if m.get("has_live_chat"): score += 5
    if m.get("has_cookie_consent"): score += 5

    return min(100, score)


def _score_ux(s: dict, schema: dict, m: dict, geo: dict, semantic: dict | None) -> float:
    score = 100.0

    # Mobile-friendliness (viewport)
    if not s.get("has_viewport"): score -= 20

    # Trust signals
    if not schema.get("has_aggregate_rating"): score -= 10
    if not m.get("has_phone"): score -= 8
    if not m.get("has_reviews"): score -= 7
    if not m.get("has_privacy_link"): score -= 5

    # SSL
    if geo.get("ssl_valid") is False: score -= 20
    ssl_days = geo.get("ssl_expiry_days")
    if ssl_days is not None and ssl_days < 30: score -= 10

    # Security headers
    sec_score = geo.get("security_headers_score", 0)
    if sec_score < 2: score -= 10
    elif sec_score < 4: score -= 5

    # HTTP→HTTPS redirect
    if geo.get("http_to_https") is False: score -= 10

    # Semantic AI scores
    if semantic and not semantic.get("parse_error"):
        eeat = semantic.get("eeat_score", 70)
        cro = semantic.get("cro_score", 70)
        rel = semantic.get("heading_relevance_score", 70)
        # Blend AI scores (max ±15 pts influence)
        avg_ai = (eeat + cro + rel) / 3
        ai_adj = (avg_ai - 70) / 70 * 15
        score += ai_adj

    return max(0, min(100, score))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _grade(score: float) -> str:
    if score >= 90: return "A+"
    if score >= 80: return "A"
    if score >= 70: return "B"
    if score >= 60: return "C"
    if score >= 45: return "D"
    return "F"


def _color(score: float) -> str:
    if score >= 80: return "#22c55e"   # green
    if score >= 60: return "#f59e0b"   # amber
    if score >= 40: return "#f97316"   # orange
    return "#ef4444"                   # red
