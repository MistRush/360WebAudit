"""
html_generator.py — Generates styled HTML audit report using Jinja2.
Produces a self-contained file with inlined Tailwind (CDN) and Chart.js.
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import settings
from report.score_calculator import ScoreBreakdown

TEMPLATE_DIR = Path(__file__).parent / "templates"


def generate_html_report(
    audit_id: int,
    url: str,
    scores: ScoreBreakdown,
    seo: dict,
    performance: dict,
    marketing: dict,
    schema: dict,
    geo: dict,
    ai_result: dict,
    screenshot_desktop_b64: str | None = None,
) -> str:
    """Render the full HTML report and return as string."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["score_color"] = _score_color
    env.filters["rating_badge"] = _rating_badge
    env.filters["format_ms"] = lambda v: f"{v:,.0f} ms" if v else "N/A"
    env.filters["format_kb"] = lambda v: f"{v:,.0f} KB" if v else "N/A"

    template = env.get_template("report_full.html")

    # Build issues list
    issues = _build_issues(seo, performance, marketing, schema, geo)

    context = {
        "audit_id": audit_id,
        "url": url,
        "domain": url.replace("https://", "").replace("http://", "").split("/")[0],
        "generated_at": datetime.utcnow().strftime("%d. %m. %Y %H:%M UTC"),
        "brand_name": settings.report_brand_name,
        "brand_color": settings.report_brand_color,
        "scores": scores,
        "seo": seo,
        "performance": performance,
        "marketing": marketing,
        "schema": schema,
        "geo": geo,
        "ai": ai_result,
        "issues": issues,
        "radar_data": json.dumps({
            "labels": ["Výkon", "SEO", "Marketing", "UX/Důvěra"],
            "datasets": [{
                "label": "Skóre",
                "data": [scores.performance, scores.seo, scores.marketing, scores.ux],
                "backgroundColor": "rgba(99,102,241,0.2)",
                "borderColor": "rgba(99,102,241,1)",
                "pointBackgroundColor": "rgba(99,102,241,1)",
            }]
        }),
        "screenshot_desktop": screenshot_desktop_b64,
        "top_threats": (ai_result.get("top_3_threats") or [])[:3],
        "gaps": ai_result.get("gaps") or [],
        "strengths": ai_result.get("strengths") or [],
    }

    return template.render(**context)


# ── Issue builder ─────────────────────────────────────────────────────────────

def _build_issues(seo, perf, mkt, schema, geo) -> list[dict]:
    issues = []

    def add(category, key, label, severity, value, expected=None, desc=None, fix=None, money=None):
        issues.append({
            "category": category, "key": key, "label": label,
            "severity": severity, "value": str(value) if value is not None else "N/A",
            "expected": expected or "", "description": desc or "",
            "fix_proposal": fix or "", "money_impact": money or "",
        })

    # ── SEO Issues ────────────────────────────────────────
    if not seo.get("title"):
        add("seo","missing_title","Chybí Title tag","critical","Chybí",
            "30–60 znaků",
            "Title tag je první věc, kterou Google zobrazí ve výsledcích.",
            "Next.js <Head> + automatická generace title z CMS pro každou stránku.",
            "Bez title Google vybírá vlastní text — typicky špatný. Přicházíte o CTR.")
    elif not seo.get("title_ok"):
        sev = "warning" if seo["title_length"] < 30 else "warning"
        add("seo","title_length","Délka Title tagu",sev,
            f"{seo['title_length']} znaků","30–60 znaků",
            "Příliš krátký nebo dlouhý title Google ořezává.",
            "CMS bude hlídat délku title a upozorní editora.","Nižší CTR = méně návštěvníků zdarma.")

    if not seo.get("meta_description"):
        add("seo","missing_meta_desc","Chybí Meta Description","critical","Chybí","120–160 znaků",
            "Google zobrazuje meta description jako popis ve výsledcích hledání.",
            "Automatické generování z prvního odstavce + manuální přepsání v CMS.",
            "Bez popisu Google generuje náhodný výňatek. CTR klesá o 5–10 %.")
    elif not seo.get("meta_description_ok"):
        add("seo","meta_desc_length","Délka Meta Description","warning",
            f"{seo['meta_description_length']} znaků","120–160 znaků",
            "Příliš krátký popis nevyužívá prostor, příliš dlouhý je ořezán.",
            "CMS editor bude mít live počítadlo znaků s barevnou signalizací.","")

    if seo.get("h1_count", 0) == 0:
        add("seo","missing_h1","Chybí H1 nadpis","critical","0","1",
            "H1 je hlavní nadpis stránky — klíčový signál pro Google o tématu obsahu.",
            "Next.js komponenty budou mít H1 jako povinný prop, CMS bude vyžadovat H1.",
            "Google může stránku považovat za méně relevantní pro cílové klíčové slovo.")
    elif not seo.get("has_single_h1"):
        add("seo","multiple_h1","Více H1 nadpisů","warning",
            f"{seo['h1_count']}x H1","1x H1",
            "Více H1 na stránce mate Google i čtenáře — kdo je šéf?",
            "Architektura komponent zabrání vícenásobnému H1 na úrovni kódu.","")

    if not seo.get("has_canonical"):
        add("seo","missing_canonical","Chybí Canonical URL","warning","Chybí","Přítomen",
            "Bez canonical mohou různé URL (www vs. non-www, http vs. https) způsobit duplicitu.",
            "Next.js automaticky přidá canonical na každou stránku.","Duplikace obsahu = penalizace Google.")

    if seo.get("is_noindex"):
        add("seo","noindex","Stránka je nastavena NOINDEX","critical","noindex","index",
            "Tato stránka říká Googlu: 'Nezahrnuj mě do výsledků!' Je to záměr?",
            "Audit a nastavení robots meta tagů přes CMS s vizuálním varováním.","Stránka není viditelná v Google = nulová organická návštěvnost.")

    if seo.get("images_missing_alt_count", 0) > 0:
        add("seo","missing_alt","Obrázky bez alt textu","warning",
            f"{seo['images_missing_alt_count']}/{seo.get('image_count',0)}","0",
            "Alt text pomáhá Googlu pochopit obrázek a je klíčový pro přístupnost (WCAG).",
            "CMS bude vyžadovat alt text při nahrávání obrázků. AI bude navrhovat popis.",
            "Ztráta z image search + EU accessibility zákon (EAA 2025).")

    if not seo.get("og_complete"):
        add("seo","og_incomplete","Neúplné Open Graph tagy","warning","Nekompletní","Kompletní",
            "Open Graph určuje, jak se web zobrazí při sdílení na Facebooku, LinkedIn a dalších.",
            "Automatické OG tagy generované z CMS pro každou stránku.",
            "Sdílení na sociálních sítích bez obrázku = nižší engagement a dosah.")

    if geo.get("has_robots_txt") is False:
        add("seo","missing_robots","Chybí robots.txt","warning","Chybí","Přítomen",
            "Soubor robots.txt řídí, kam smí vyhledávací roboti přistupovat.",
            "Next.js sitemap a robots generátor zajistí automatické vytvoření na správné URL.",
            "Ztrácíte kontrolu nad crawl budgetem a indexací webu.")
    elif geo.get("robots_txt_ok") is False:
        add("seo","bad_robots","Robots.txt blokuje celý web","critical","Blokováno","Povoleno",
            "Soubor robots.txt obsahuje direktivu Disallow: / pro všechny agenty. Google web vůbec nenaindexuje!",
            "Správné nastavení robots.txt s povolenou indexací.",
            "Web není a nebude ve výsledcích hledání. Extrémní ztráta návštěvnosti.")

    if geo.get("has_sitemap") is False:
        add("seo","missing_sitemap","Chybí sitemap.xml","warning","Chybí","Nalezena",
            "Sitemapa říká Googlu o všech důležitých stránkách, které má indexovat.",
            "Automatická dynamická sitemap.xml generovaná z databáze článků a produktů.",
            "Pomalé objevování nových stránek vyhledávačem.")

    # ── Performance Issues ────────────────────────────────
    lcp_ms = perf.get("lcp_ms")
    if lcp_ms and lcp_ms > 4000:
        add("performance","lcp_poor","LCP — Načtení hlavního obsahu (KRITICKÉ)","critical",
            f"{lcp_ms:,} ms","< 2 500 ms",
            "LCP měří, jak rychle se načte největší viditelný prvek (hero obrázek, nadpis). Google ho používá jako hlavní rychlostní metriku.",
            "Next.js Image optimalizace (WebP/AVIF, lazy loading), CDN, server-side rendering = LCP typicky < 2s.",
            f"Web se načítá pomalu → {round((lcp_ms-2500)/1000,1)}s nad limitem → Google snižuje pozice → méně návštěvníků.")
    elif lcp_ms and lcp_ms > 2500:
        add("performance","lcp_warning","LCP — Načtení hlavního obsahu (VAROVÁNÍ)","warning",
            f"{lcp_ms:,} ms","< 2 500 ms",
            "LCP je mírně nad Google limitem. Na hraně — jeden špatný den a propadne.","","")

    cls = perf.get("cls")
    if cls is not None and cls > 0.25:
        add("performance","cls_poor","CLS — Vizuální stabilita stránky (KRITICKÉ)","critical",
            f"{cls:.3f}","< 0.10",
            "CLS měří, jak moc se obsah 'skáče' při načítání. Frustruje uživatele — omylem kliknou na špatný prvek.",
            "Rezervace prostoru pro obrázky a reklamy, font-display: swap, skeleton loaders.",
            "Špatné UX → opouštění stránky → ztracené konverze.")

    ttfb = perf.get("ttfb_ms")
    if ttfb and ttfb > 1800:
        add("performance","ttfb_poor","TTFB — Odezva serveru (KRITICKÉ)","critical",
            f"{ttfb:,} ms","< 800 ms",
            "TTFB je čas od kliknutí do prvního bajtu ze serveru. Pomalý server = vše ostatní je taky pomalé.",
            "Next.js na Vercel/Railway s edge caching = TTFB < 200ms. Serverless funkce blíže uživateli.",
            "Pomalý server trestá Google ranking přímo. Hosting stojí víc než výkon přináší.")

    js_kb = perf.get("total_js_kb", 0)
    if js_kb > 500:
        add("performance","large_js","Velký JavaScript bundle","warning",
            f"{js_kb:,} KB","< 400 KB",
            f"Web stahuje {js_kb:,.0f} KB JavaScriptu. To zpomaluje mobilní zařízení a slabé počítače.",
            "Next.js automaticky dělí kód na chunky (code splitting) — uživatel stáhne jen to, co potřebuje.",
            "Každých 100 KB navíc = ~1s navíc na mobilním 3G. V ČR má 20% uživatelů mobilní data.")

    # ── Marketing Issues ──────────────────────────────────
    if not mkt.get("has_gtm"):
        add("marketing","missing_gtm","Chybí Google Tag Manager","critical","Chybí","Přítomen",
            "GTM je 'řídící centrum' pro všechny marketingové skripty. Bez něj nelze měřit výsledky kampaní.",
            "Integrace GTM jako první krok při spuštění nového webu — 15 minut práce.",
            "Bez GTM nevíte, co funguje. Investice do reklamy = hod peněz do tmy.")

    if not mkt.get("has_ga4"):
        add("marketing","missing_ga4","Chybí Google Analytics 4","critical","Chybí","Přítomen",
            "GA4 je základ měření návštěvnosti a chování uživatelů. Povinná výbava každého webu.",
            "GA4 přes GTM + konfigurace klíčových konverzí ihned po spuštění.",
            "Nemáte data = nemůžete optimalizovat. Rozhodujete se naslepo.")

    if not mkt.get("has_fb_pixel"):
        add("marketing","missing_fb_pixel","Chybí Meta (Facebook) Pixel","warning","Chybí","Přítomen",
            "Meta Pixel umožňuje retargeting (oslovení lidí, kteří navštívili web) a měření konverzí z reklam.",
            "Implementace přes GTM — 10 minut. Nastavení retargetingových publik.",
            "Bez Pixelu nelze retargetovat ani měřit ROAS Facebook reklam. Plýtváte budgetem.")

    if not mkt.get("has_cookie_consent"):
        add("marketing","missing_consent","Chybí Cookie Consent Banner","warning","Chybí","Přítomen",
            "GDPR a ePrivacy směrnice vyžadují souhlas před spuštěním analytických/reklamních cookies.",
            "Implementace CookieYes nebo Cookiebot přes GTM. Automatická blokace tagů před souhlasem.",
            "Pokuta ÚOOÚ až 20M EUR nebo 4% ročního obratu za porušení GDPR.")

    # ── GEO/SSL Issues ────────────────────────────────────
    if geo.get("ssl_valid") is False:
        add("ux","invalid_ssl","Neplatný SSL certifikát","critical","Neplatný","Platný",
            "Prohlížeče zobrazují červené varování 'Nebezpečné'. Uživatelé okamžitě odcházejí.",
            "SSL automaticky přes Let's Encrypt nebo Cloudflare. Na Railway/Vercel zdarma.",
            "Přibližně 85% uživatelů okamžitě opustí stránku s SSL varováním.")

    ssl_days = geo.get("ssl_expiry_days")
    if ssl_days is not None and 0 < ssl_days < 30:
        add("ux","ssl_expiring","SSL certifikát brzy vyprší","warning",
            f"Za {ssl_days} dní","Obnoven",
            "SSL certifikát brzy skončí. Po vypršení web zobrazí chybové varování.",
            "Automatická obnova SSL přes certbot nebo platformní hosting.","Výpadek webu a ztráta důvěry.")

    if geo.get("http_to_https") is False:
        add("ux","no_https_redirect","Chybí HTTP→HTTPS přesměrování","warning","Chybí","301 redirect",
            "Web je dostupný přes nezabezpečené HTTP bez přesměrování na HTTPS.",
            "Konfigurace 301 redirect na úrovni serveru nebo CDN.",
            "Duplicitní obsah pro Google + bezpečnostní riziko.")

    if geo.get("security_headers_score", 0) < 3:
        add("ux","weak_security_headers","Chybějící bezpečnostní HTTP hlavičky","warning",
            f"{geo.get('security_headers_score',0)}/6","≥ 4/6",
            "Bezpečnostní hlavičky (CSP, HSTS, X-Frame-Options) chrání uživatele před XSS a clickjacking útoky.",
            "Konfigurace Next.js next.config.js headers() — 5 řádků kódu.",
            "Legislativní riziko + ztráta důvěry při bezpečnostním incidentu.")

    return issues


# ── Jinja filters ─────────────────────────────────────────────────────────────

def _score_color(score: float) -> str:
    if score >= 80: return "#22c55e"
    if score >= 60: return "#f59e0b"
    if score >= 40: return "#f97316"
    return "#ef4444"


def _rating_badge(rating: str) -> str:
    badges = {
        "good": '<span style="color:#22c55e;font-weight:700">✅ OK</span>',
        "needs_improvement": '<span style="color:#f59e0b;font-weight:700">⚠️ VAROVÁNÍ</span>',
        "poor": '<span style="color:#ef4444;font-weight:700">❌ KRITICKÉ</span>',
        "unknown": '<span style="color:#94a3b8">❓ Neměřeno</span>',
    }
    return badges.get(rating, rating)
