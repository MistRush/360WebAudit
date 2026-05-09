"""
gap_analyzer.py + fix_explainer.py combined.
Generates business gap analysis and "why it costs you money" explanations via Gemini.
"""
from __future__ import annotations
import json
from ai.gemini_client import gemini_generate


async def analyze_gaps_and_fixes(
    seo: dict, performance: dict, marketing: dict, schema: dict, geo: dict, url: str
) -> dict:
    """
    Call Gemini to produce:
    1. Business gap analysis (co klient přichází)
    2. Fix explanations per critical issue (pro laika)
    3. Executive summary text
    4. Estimated conversion uplift
    """

    # ── Build context summary for Gemini ──────────────────
    context = _build_context(seo, performance, marketing, schema, geo, url)

    # ── Prompt 1: Gap analysis + executive summary ────────
    summary_prompt = f"""
Jsi expert na webový marketing a UX. Analyzuješ výsledky technického auditu webu.
Odpovídej VŽDY v češtině. Buď konkrétní, stručný a zaměřený na obchodní dopad.

URL: {url}

=== DATA Z AUDITU ===
{context}

=== ÚKOL ===
Vrať JSON objekt s těmito klíči:

{{
  "executive_summary": "2-3 věty shrnující celkový stav webu pro netechnického ředitele/majitele firmy",
  "top_3_threats": [
    {{"title": "...", "description": "...", "business_impact": "...", "solution": "jak to vyřešíme novým webem", "severity": "critical|warning"}}
  ],
  "estimated_conversion_uplift_pct": "Odhadované zvýšení konverzí po opravě všech kritických problémů (číslo nebo rozsah, např. '15-25')",
  "estimated_revenue_impact": "Stručný popis potenciálního dopadu na tržby v lidské řeči",
  "gaps": [
    {{"area": "seo|performance|marketing|ux", "gap": "popis problému", "money_impact": "proč to stojí peníze", "fix_in_new_web": "jak moderní stack (Next.js, Headless CMS) to řeší nativně"}}
  ],
  "strengths": ["seznam všech silných stránek webu"],
  "tech_assessment": "Odborné hodnocení technické úrovně webu (pro prodejní argument)"
}}

Vrať POUZE validní JSON, bez markdown bloků.
""".strip()

    raw = await gemini_generate(summary_prompt, temperature=0.4)
    result = _parse_json_safe(raw)

    # ── Prompt 2: Semantic content analysis ───────────────
    semantic_prompt = f"""
Jsi expert na E-E-A-T (Experience, Expertise, Authoritativeness, Trustworthiness) a UX copywriting.
Odpovídej v češtině.

Web: {url}
Title: {seo.get('title', 'N/A')}
Meta description: {seo.get('meta_description', 'N/A')}
H1: {', '.join(seo.get('h1_texts', [])) or 'Chybí'}
Počet slov: {seo.get('word_count', 0)}
Má recenze/hodnocení: {schema.get('has_aggregate_rating', False)}
Má FAQ strukturu: {schema.get('has_faq', False)}

Zhodnoť:
1. Odpovídá obsah (title/nadpisy/meta) tomu co firma reálně nabízí? Jsou nadpisy RELEVANTNÍ k byznysu?
2. Působí web důvěryhodně a odborně (E-E-A-T)?
3. Motivuje obsah k akci (konverzi)?

Vrať JSON:
{{"semantic_score": 0-100, "eeat_score": 0-100, "cro_score": 0-100, "heading_relevance_score": 0-100, "content_assessment": "2-3 věty", "heading_assessment": "Zhodnocení relevace nadpisů", "content_recommendations": ["max 3 konkrétní doporučení"]}}

Vrať POUZE validní JSON.
""".strip()

    semantic_raw = await gemini_generate(semantic_prompt, temperature=0.3)
    semantic = _parse_json_safe(semantic_raw)

    return {**result, "semantic": semantic}


def _build_context(seo: dict, performance: dict, marketing: dict, schema: dict, geo: dict, url: str) -> str:
    lines = []

    # SEO
    lines.append("## SEO")
    lines.append(f"- Title: '{seo.get('title','')}' ({seo.get('title_length',0)} znaků, ok={seo.get('title_ok')})")
    lines.append(f"- Meta desc: {seo.get('meta_description_length',0)} znaků, ok={seo.get('meta_description_ok')}")
    lines.append(f"- H1: {seo.get('h1_count',0)}x — {seo.get('h1_texts','')}")
    lines.append(f"- Canonical: {seo.get('has_canonical')}, Hreflang: {seo.get('has_hreflang')}")
    lines.append(f"- Obrázky bez alt: {seo.get('images_missing_alt_count',0)}/{seo.get('image_count',0)}")
    lines.append(f"- Počet slov: {seo.get('word_count',0)}")
    lines.append(f"- Noindex: {seo.get('is_noindex')}, Schema.org bloků: {schema.get('schema_count',0)}")
    lines.append(f"- Robots.txt: {'OK' if geo.get('robots_txt_ok') else 'CHYBÍ nebo BLOKUJE'} (existuje: {geo.get('has_robots_txt')})")
    lines.append(f"- Sitemap.xml: {'Nalezena' if geo.get('has_sitemap') else 'CHYBÍ'}")
    
    # Headings
    lines.append("\n## Nadpisy (Heading Hierarchy)")
    for h in seo.get('headings', []):
        lines.append(f"- {h['level'].upper()}: {h['text']}")

    # Performance
    lines.append("\n## Performance")
    lines.append(f"- LCP: {performance.get('lcp_ms')} ms ({performance.get('lcp_rating')})")
    lines.append(f"- CLS: {performance.get('cls')} ({performance.get('cls_rating')})")
    lines.append(f"- INP: {performance.get('inp_ms')} ms ({performance.get('inp_rating')})")
    lines.append(f"- TTFB: {performance.get('ttfb_ms')} ms ({performance.get('ttfb_rating')})")
    lines.append(f"- JS: {performance.get('total_js_kb')} KB, CSS: {performance.get('total_css_kb')} KB")
    lines.append(f"- Celkový přenos: {performance.get('total_transfer_kb')} KB")

    # Marketing
    lines.append("\n## Marketing Stack")
    lines.append(f"- GTM: {marketing.get('has_gtm')}, GA4: {marketing.get('has_ga4')}")
    lines.append(f"- Meta Pixel: {marketing.get('has_fb_pixel')}, TikTok: {marketing.get('has_tiktok_pixel')}")
    lines.append(f"- Hotjar/Clarity: {marketing.get('has_hotjar') or marketing.get('has_microsoft_clarity')}")
    lines.append(f"- Live chat: {marketing.get('has_live_chat')}")
    lines.append(f"- Cookie consent: {marketing.get('has_cookie_consent')}")
    missing = [t['label'] for t in marketing.get('missing_critical', [])]
    if missing:
        lines.append(f"- CHYBÍ KRITICKÉ NÁSTROJE: {', '.join(missing)}")

    # GEO
    lines.append("\n## Server / GEO")
    lines.append(f"- SSL platný: {geo.get('ssl_valid')}, vyprší za: {geo.get('ssl_expiry_days')} dní")
    lines.append(f"- HTTP→HTTPS redirect: {geo.get('http_to_https')}")
    lines.append(f"- Security headers skóre: {geo.get('security_headers_score',0)}/6")
    lines.append(f"- Server: {geo.get('server_header','?')}")

    return "\n".join(lines)


def _parse_json_safe(text: str) -> dict:
    import re
    # Strip markdown code blocks if Gemini wrapped the response
    text = re.sub(r'^```(?:json)?\n?', '', text.strip(), flags=re.MULTILINE)
    text = re.sub(r'\n?```$', '', text.strip(), flags=re.MULTILINE)
    try:
        return json.loads(text.strip())
    except Exception:
        return {"raw_response": text, "parse_error": True}
