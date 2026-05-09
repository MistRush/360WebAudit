"""
marketing_stack.py — Detects presence of analytics, advertising and UX tools
by scanning rendered HTML for known script patterns, DOM elements and cookies.
"""
from __future__ import annotations
import re
from typing import Any


# ── Detection patterns ────────────────────────────────────────────────────────
# Each tool: list of regex patterns checked against the full HTML source.

TOOL_PATTERNS: dict[str, dict] = {
    # Analytics
    "gtm": {
        "label": "Google Tag Manager",
        "category": "tag_manager",
        "patterns": [
            r"googletagmanager\.com/gtm\.js",
            r"GTM-[A-Z0-9]+",
        ],
    },
    "ga4": {
        "label": "Google Analytics 4",
        "category": "analytics",
        "patterns": [
            r"googletagmanager\.com/gtag/js",
            r"gtag\('config',\s*'G-",
            r"G-[A-Z0-9]{8,10}",
        ],
    },
    "ua": {
        "label": "Universal Analytics (GA3 — deprecated)",
        "category": "analytics",
        "patterns": [
            r"google-analytics\.com/analytics\.js",
            r"UA-\d{5,9}-\d",
        ],
    },

    # Advertising pixels
    "fb_pixel": {
        "label": "Meta (Facebook) Pixel",
        "category": "advertising",
        "patterns": [
            r"connect\.facebook\.net/.*fbevents\.js",
            r"fbq\('init'",
        ],
    },
    "tiktok_pixel": {
        "label": "TikTok Pixel",
        "category": "advertising",
        "patterns": [
            r"analytics\.tiktok\.com",
            r"ttq\.load\(",
        ],
    },
    "google_ads": {
        "label": "Google Ads (Conversion)",
        "category": "advertising",
        "patterns": [
            r"googleadservices\.com",
            r"gtag\('config',\s*'AW-",
            r"AW-\d{9,12}",
        ],
    },
    "linkedin_insight": {
        "label": "LinkedIn Insight Tag",
        "category": "advertising",
        "patterns": [
            r"snap\.licdn\.com/li\.lms-analytics",
            r"_linkedin_partner_id",
        ],
    },

    # Heatmaps & session recording
    "hotjar": {
        "label": "Hotjar",
        "category": "heatmap",
        "patterns": [
            r"static\.hotjar\.com",
            r"hjid:",
            r"hotjar\.com",
        ],
    },
    "microsoft_clarity": {
        "label": "Microsoft Clarity",
        "category": "heatmap",
        "patterns": [
            r"clarity\.ms/tag",
            r"clarity\('set'",
        ],
    },

    # Live chat / support
    "intercom": {
        "label": "Intercom",
        "category": "live_chat",
        "patterns": [r"widget\.intercom\.io", r"Intercom\("],
    },
    "drift": {
        "label": "Drift",
        "category": "live_chat",
        "patterns": [r"js\.driftt\.com", r"drift\.load\("],
    },
    "crisp": {
        "label": "Crisp Chat",
        "category": "live_chat",
        "patterns": [r"client\.crisp\.chat", r"\$crisp"],
    },
    "tawk": {
        "label": "Tawk.to",
        "category": "live_chat",
        "patterns": [r"embed\.tawk\.to"],
    },

    # CRO & A/B testing
    "google_optimize": {
        "label": "Google Optimize (deprecated)",
        "category": "cro",
        "patterns": [r"optimize\.google\.com"],
    },
    "vwo": {
        "label": "Visual Website Optimizer",
        "category": "cro",
        "patterns": [r"dev\.visualwebsiteoptimizer\.com"],
    },

    # Cookie consent
    "cookiebot": {
        "label": "Cookiebot",
        "category": "consent",
        "patterns": [r"consent\.cookiebot\.com"],
    },
    "onetrust": {
        "label": "OneTrust",
        "category": "consent",
        "patterns": [r"cdn\.cookielaw\.org", r"optanon"],
    },
    "cookie_yes": {
        "label": "CookieYes",
        "category": "consent",
        "patterns": [r"cdn-cookieyes\.com"],
    },
}

# Critical marketing tools that SHOULD be present
CRITICAL_TOOLS = {"gtm", "ga4", "fb_pixel"}
RECOMMENDED_TOOLS = {"hotjar", "microsoft_clarity", "google_ads"}


def detect_marketing_stack(html_content: str) -> dict[str, Any]:
    """
    Scan HTML for known marketing/analytics tool signatures.
    Returns detection results with business impact annotations.
    """
    detected: dict[str, bool] = {}
    detected_details: list[dict] = []

    for tool_key, tool_info in TOOL_PATTERNS.items():
        found = any(
            re.search(pattern, html_content, re.IGNORECASE)
            for pattern in tool_info["patterns"]
        )
        detected[tool_key] = found
        if found:
            detected_details.append({
                "key": tool_key,
                "label": tool_info["label"],
                "category": tool_info["category"],
            })

    # ── Missing critical tools ────────────────────────────
    missing_critical = [
        {"key": k, "label": TOOL_PATTERNS[k]["label"]}
        for k in CRITICAL_TOOLS if not detected.get(k)
    ]
    missing_recommended = [
        {"key": k, "label": TOOL_PATTERNS[k]["label"]}
        for k in RECOMMENDED_TOOLS if not detected.get(k)
    ]

    # ── CRO signals (non-tag-based) ───────────────────────
    has_live_chat = any(detected.get(t) for t in ("intercom", "drift", "crisp", "tawk"))
    has_cookie_consent = any(detected.get(t) for t in ("cookiebot", "onetrust", "cookie_yes"))

    # Detect CTA buttons heuristically
    cta_patterns = [r'<button[^>]*>', r'href=["\'][^"\']*kontakt', r'href=["\'][^"\']*objednat',
                    r'href=["\'][^"\']*poptavka', r'href=["\'][^"\']*contact', r'href=["\'][^"\']*order']
    has_cta = any(re.search(p, html_content, re.I) for p in cta_patterns)

    # Phone number presence
    has_phone = bool(re.search(r'tel:\+?\d[\d\s\-\(\)]{7,}', html_content))

    # Schema review presence
    has_reviews = bool(re.search(r'"@type"\s*:\s*"Review|AggregateRating"', html_content))

    # GDPR compliance indicators
    has_privacy_link = bool(re.search(
        r'href=["\'][^"\']*(?:privacy|ochrana|gdpr|soukromi)[^"\']*["\']',
        html_content, re.I
    ))

    return {
        "detected": detected,
        "detected_tools": detected_details,
        "missing_critical": missing_critical,
        "missing_recommended": missing_recommended,

        # Aggregates
        "has_gtm": detected.get("gtm", False),
        "has_ga4": detected.get("ga4", False),
        "has_ua": detected.get("ua", False),
        "has_fb_pixel": detected.get("fb_pixel", False),
        "has_tiktok_pixel": detected.get("tiktok_pixel", False),
        "has_google_ads": detected.get("google_ads", False),
        "has_hotjar": detected.get("hotjar", False),
        "has_microsoft_clarity": detected.get("microsoft_clarity", False),
        "has_live_chat": has_live_chat,
        "has_cookie_consent": has_cookie_consent,
        "has_cta": has_cta,
        "has_phone": has_phone,
        "has_reviews": has_reviews,
        "has_privacy_link": has_privacy_link,

        # Score (0–100): how equipped the marketing stack is
        "marketing_stack_count": len(detected_details),
        "critical_tools_count": sum(1 for k in CRITICAL_TOOLS if detected.get(k)),
    }
