# AI Web Auditor & Sales Engine 2026

> Automatizovaný auditor webů s AI analýzou (Gemini) a stylizovaným prodejním reportem.
> Postaven na: FastAPI · Playwright · Gemini 1.5 · SQLite/PostgreSQL · Railway

---

## 🚀 Rychlý start (lokálně)

### 1. Požadavky
- Python 3.11+
- Git

### 2. Instalace

```bash
git clone <repo-url>
cd 360WebTest

# Zkopíruj env
cp .env.example .env
# → Vyplň GEMINI_API_KEY v .env

# Vytvoř virtualenv
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # Linux/Mac

# Nainstaluj deps
pip install -r requirements.txt

# Nainstaluj Playwright browsers (Chromium)
playwright install chromium --with-deps

# Spusť server
cd backend
python main.py
```

Server běží na: **http://localhost:8000**
API dokumentace: **http://localhost:8000/docs**

### 3. Test auditu

```bash
# Spustit audit
curl -X POST http://localhost:8000/audits \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# Sledovat live log (SSE)
curl http://localhost:8000/audits/1/stream

# Zobrazit report
# → Otevři v prohlížeči: http://localhost:8000/audits/1/report
```

---

## ☁️ Nasazení na Railway (doporučeno)

### Proč Railway?
- ✅ Podporuje Docker (Playwright + Chromium)
- ✅ PostgreSQL a Redis jako pluginy (zdarma v základu)
- ✅ Automatické nasazení z GitHub
- ✅ Persistent storage pro reporty
- ✅ Custom domény

### Kroky

1. **Vytvoř Railway projekt** na [railway.app](https://railway.app)

2. **Přidej PostgreSQL plugin** v Railway dashboardu
   - Railway automaticky nastaví `DATABASE_URL` env var

3. **Přidej Redis plugin**
   - Railway automaticky nastaví `REDIS_URL`

4. **Nastav environment variables** v Railway:
   ```
   GEMINI_API_KEY=...
   GEMINI_MODEL=gemini-1.5-flash
   GOOGLE_PAGESPEED_API_KEY=...  (volitelné)
   REPORT_BRAND_NAME=Tvoje Agentura
   REPORT_BRAND_COLOR=#6366f1
   ```
   > `DATABASE_URL` a `REDIS_URL` Railway nastaví automaticky z pluginů.

5. **Deploy z GitHub:**
   ```bash
   git add .
   git commit -m "Initial deploy"
   git push
   ```
   Railway automaticky builduje z Dockerfile.

6. **Migrace DB** (první spuštění):
   - DB tabulky se vytvoří automaticky při startu (`init_db()`)

### URL po nasazení
```
https://your-app.railway.app/
https://your-app.railway.app/docs
https://your-app.railway.app/audits
```

---

## 🗂️ Struktura projektu

```
360WebTest/
├── backend/
│   ├── main.py                    # FastAPI app + API endpoints + SSE
│   ├── config.py                  # Env vars (pydantic-settings)
│   ├── database.py                # SQLAlchemy modely (Audit, AuditIssue, AuditLog)
│   ├── audit_runner.py            # Pipeline orchestrátor
│   │
│   ├── scraper/
│   │   ├── playwright_engine.py   # Core scraper (Desktop + Mobile Googlebot)
│   │   ├── seo_extractor.py       # Title, Meta, H1-H6, Alt, Canonical, OG
│   │   ├── performance_metrics.py # LCP, CLS, INP, FCP, TTFB + PageSpeed API
│   │   ├── marketing_stack.py     # GTM, GA4, Pixels, Chat, Consent detekce
│   │   ├── schema_extractor.py    # JSON-LD / Schema.org extrakce
│   │   └── geo_checker.py         # IP, SSL, Security headers, TTFB
│   │
│   ├── ai/
│   │   ├── gemini_client.py       # Rate-limited Gemini API wrapper
│   │   └── gap_analyzer.py        # Business gap analysis + E-E-A-T + fixes
│   │
│   └── report/
│       ├── score_calculator.py    # Vážené skóre (Výkon 30% + SEO 30% + ...)
│       ├── html_generator.py      # Jinja2 HTML report s issue cards
│       ├── pdf_exporter.py        # Playwright PDF export (+ WeasyPrint fallback)
│       └── templates/
│           └── report_full.html   # Stylizovaná HTML šablona (Tailwind + Chart.js)
│
├── Dockerfile                     # Playwright + Python image pro Railway
├── railway.json                   # Railway konfigurace
├── docker-compose.yml             # Lokální development (Redis)
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🔑 API klíče

| Klíč | Kde získat | Nutný? |
|------|-----------|--------|
| `GEMINI_API_KEY` | [aistudio.google.com](https://aistudio.google.com) | ✅ Ano |
| `GOOGLE_PAGESPEED_API_KEY` | [Google Cloud Console](https://console.cloud.google.com) | Volitelný (25 req/den zdarma) |

---

## 📊 Co audit měří

### SEO (váha 30%)
- Title tag (délka, přítomnost)
- Meta description (délka, přítomnost)
- H1–H6 hierarchie
- Canonical URL
- Hreflang tagy
- Alt texty obrázků
- Open Graph / Twitter Cards
- Schema.org JSON-LD
- Noindex detekce

### Performance (váha 30%)
- **LCP** (Largest Contentful Paint) — cíl < 2.5s
- **CLS** (Cumulative Layout Shift) — cíl < 0.1
- **INP** (Interaction to Next Paint) — cíl < 200ms
- **FCP** (First Contentful Paint)
- **TTFB** (Time to First Byte)
- JS / CSS / Image bundle size
- Render-blocking resources

### Marketing Stack (váha 20%)
- Google Tag Manager
- Google Analytics 4
- Meta Pixel / TikTok Pixel / Google Ads
- Hotjar / Microsoft Clarity
- Live chat nástroje
- Cookie consent (GDPR)

### UX / Bezpečnost (váha 20%)
- SSL certifikát (platnost, zbývající dny)
- HTTP → HTTPS redirect
- Security headers (HSTS, CSP, X-Frame-Options...)
- Mobilní viewport
- Telefonní číslo, recenze, privacy link
- AI E-E-A-T hodnocení obsahu

---

## 📄 Report výstupy

1. **HTML report** — stylizovaný, interaktivní, s radagovým grafem a screenshotem
2. **PDF export** — přes Playwright print-to-PDF (A4 formát)
3. **JSON API** — strukturovaná data pro vlastní zpracování

---

## 🛣️ Roadmap

- [ ] Frontend dashboard (Next.js)
- [ ] Scheduled re-audits (cron)
- [ ] Competitor analysis
- [ ] Email doručení reportu
- [ ] White-label konfigurace
- [ ] Accessibility (WCAG 2.1) audit
- [ ] Carbon footprint score
