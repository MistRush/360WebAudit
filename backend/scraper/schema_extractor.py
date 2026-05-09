"""
schema_extractor.py — Extracts and validates all JSON-LD structured data blocks.
Supports: LocalBusiness, Product, Article, FAQPage, BreadcrumbList, WebSite, Organization.
"""
from __future__ import annotations
import re, json
from typing import Any


VALUABLE_TYPES = {
    "LocalBusiness", "Restaurant", "Store", "MedicalBusiness",
    "Product", "Offer",
    "Article", "BlogPosting", "NewsArticle",
    "FAQPage", "HowTo",
    "BreadcrumbList",
    "WebSite", "WebPage",
    "Organization", "Corporation",
    "Person",
    "Event",
    "Review", "AggregateRating",
    "Service",
}


def extract_schema(html_content: str) -> dict[str, Any]:
    """Extract and categorize all JSON-LD blocks from the page."""
    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.DOTALL | re.IGNORECASE
    )

    schemas: list[dict] = []
    parse_errors: list[str] = []
    found_types: list[str] = []

    for match in pattern.finditer(html_content):
        raw = match.group(1).strip()
        try:
            data = json.loads(raw)
            # Handle both single objects and arrays (@graph)
            items = data if isinstance(data, list) else [data]
            for item in items:
                if "@graph" in item:
                    items.extend(item["@graph"])
                    continue
                schema_type = item.get("@type", "Unknown")
                if isinstance(schema_type, list):
                    schema_type = schema_type[0]
                found_types.append(schema_type)
                schemas.append({
                    "type": schema_type,
                    "is_valuable": schema_type in VALUABLE_TYPES,
                    "data": _truncate_schema(item),
                })
        except json.JSONDecodeError as e:
            parse_errors.append(str(e)[:100])

    # ── Presence flags ────────────────────────────────────
    has_local_business = any(
        s["type"] in ("LocalBusiness", "Restaurant", "Store", "MedicalBusiness")
        for s in schemas
    )
    has_product = any(s["type"] in ("Product", "Offer") for s in schemas)
    has_article = any(s["type"] in ("Article", "BlogPosting", "NewsArticle") for s in schemas)
    has_faq = any(s["type"] == "FAQPage" for s in schemas)
    has_breadcrumb = any(s["type"] == "BreadcrumbList" for s in schemas)
    has_organization = any(s["type"] in ("Organization", "Corporation") for s in schemas)
    has_aggregate_rating = any(s["type"] == "AggregateRating" for s in schemas)

    # ── Missing opportunities ─────────────────────────────
    missing_suggestions: list[str] = []
    if not has_local_business and not has_organization:
        missing_suggestions.append("Organization / LocalBusiness — základní identita firmy")
    if not has_faq:
        missing_suggestions.append("FAQPage — zvyšuje CTR v Google (rich results)")
    if not has_breadcrumb:
        missing_suggestions.append("BreadcrumbList — lepší navigace v SERP")
    if not has_aggregate_rating:
        missing_suggestions.append("AggregateRating — hvězdičky v Google výsledcích")

    return {
        "schemas": schemas,
        "schema_count": len(schemas),
        "types_found": found_types,
        "parse_errors": parse_errors,
        "has_local_business": has_local_business,
        "has_product": has_product,
        "has_article": has_article,
        "has_faq": has_faq,
        "has_breadcrumb": has_breadcrumb,
        "has_organization": has_organization,
        "has_aggregate_rating": has_aggregate_rating,
        "missing_suggestions": missing_suggestions,
        "has_any_schema": len(schemas) > 0,
    }


def _truncate_schema(data: dict, max_str_len: int = 200) -> dict:
    """Recursively truncate long string values to keep storage manageable."""
    result = {}
    for k, v in data.items():
        if isinstance(v, str) and len(v) > max_str_len:
            result[k] = v[:max_str_len] + "…"
        elif isinstance(v, dict):
            result[k] = _truncate_schema(v, max_str_len)
        elif isinstance(v, list):
            result[k] = [_truncate_schema(i, max_str_len) if isinstance(i, dict) else i for i in v[:5]]
        else:
            result[k] = v
    return result
