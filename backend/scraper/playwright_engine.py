"""
playwright_engine.py — Core scraping engine.
Launches Playwright with Googlebot-Desktop and Googlebot-Mobile user agents,
waits for full JS hydration (networkidle), and orchestrates all extractors.
"""
import asyncio
import time
from typing import Callable, Awaitable
from playwright.async_api import async_playwright, Browser, Page, BrowserContext

from config import settings


# ── User Agents ──────────────────────────────────────────────────────────────

GOOGLEBOT_DESKTOP_UA = (
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)
GOOGLEBOT_MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36 "
    "(compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)

CHROME_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


# ── Viewport configs ──────────────────────────────────────────────────────────

DESKTOP_VIEWPORT = {"width": 1440, "height": 900}
MOBILE_VIEWPORT = {"width": 375, "height": 812}


LogCallback = Callable[[str, str], Awaitable[None]]


class PlaywrightEngine:
    """
    Manages a Playwright browser instance and provides high-level page loading
    with proper JS hydration waiting, performance timing, and screenshot capture.
    """

    def __init__(self, log_callback: LogCallback | None = None):
        self._log = log_callback or self._default_log

    async def _default_log(self, level: str, msg: str):
        print(f"[{level.upper()}] {msg}")

    # ── Public API ────────────────────────────────────────────────────────────

    async def scrape_full(self, url: str) -> dict:
        """
        Full audit scrape: desktop + mobile pass, returns merged data dict.
        This is the main entry point called by the audit job.
        """
        await self._log("info", f"START: Scraper pro: {url}")
        start_total = time.monotonic()

        # Check loop type on Windows
        import sys
        if sys.platform == 'win32':
            loop = asyncio.get_event_loop()
            loop_name = type(loop).__name__
            if 'Proactor' not in loop_name:
                await self._log("warning", f"DEBUG: Loop je {loop_name} (ne ProactorEventLoop). Playwright muze selhat!")
            else:
                await self._log("info", f"DEBUG: OK - loop je {loop_name}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ]
            )

            try:
                # ── Desktop pass ─────────────────────────────────────────────
                await self._log("info", "Desktop pass (Googlebot-Desktop UA)...")
                desktop_data = await self._load_page(
                    browser, url,
                    user_agent=GOOGLEBOT_DESKTOP_UA,
                    viewport=DESKTOP_VIEWPORT,
                    is_mobile=False,
                )

                # ── Mobile pass ──────────────────────────────────────────────
                await self._log("info", "Mobile pass (Googlebot-Mobile UA)...")
                mobile_data = await self._load_page(
                    browser, url,
                    user_agent=GOOGLEBOT_MOBILE_UA,
                    viewport=MOBILE_VIEWPORT,
                    is_mobile=True,
                )

                # ── Performance metrics pass (real Chrome UA for accurate CWV) ─
                await self._log("info", "Performance metrics pass...")
                perf_data = await self._load_page(
                    browser, url,
                    user_agent=CHROME_DESKTOP_UA,
                    viewport=DESKTOP_VIEWPORT,
                    is_mobile=False,
                    collect_performance=True,
                )

            finally:
                await browser.close()

        elapsed = round(time.monotonic() - start_total, 2)
        await self._log("success", f"DONE: Scraping dokončen za {elapsed}s")

        return {
            "url": url,
            "desktop": desktop_data,
            "mobile": mobile_data,
            "performance_raw": perf_data.get("performance_raw", {}),
            "screenshot_desktop": desktop_data.get("screenshot"),
            "screenshot_mobile": mobile_data.get("screenshot"),
            "scrape_duration_s": elapsed,
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _load_page(
        self,
        browser: Browser,
        url: str,
        user_agent: str,
        viewport: dict,
        is_mobile: bool,
        collect_performance: bool = False,
    ) -> dict:
        """
        Load a single page with the given UA / viewport.
        Waits for 'networkidle' to ensure JS frameworks have hydrated.
        """
        context: BrowserContext = await browser.new_context(
            user_agent=user_agent,
            viewport=viewport,
            is_mobile=is_mobile,
            java_script_enabled=True,
            ignore_https_errors=True,
        )

        # Inject performance observer before navigation
        if collect_performance:
            await context.add_init_script(PERFORMANCE_OBSERVER_SCRIPT)

        page: Page = await context.new_page()

        # Track network requests for resource analysis
        resource_sizes: list[dict] = []
        page.on("response", lambda r: resource_sizes.append({
            "url": r.url,
            "status": r.status,
            "content_type": r.headers.get("content-type", ""),
            "size": int(r.headers.get("content-length", 0)),
        }))

        t_start = time.monotonic()

        try:
            await self._log("info", f"Naviguji na {url} ({user_agent[:20]}...)")
            response = await page.goto(
                url,
                wait_until="load",
                timeout=45000, # 45s hard timeout for navigation
            )
            # Short wait for any late-loading JS
            await asyncio.sleep(2)
            ttfb = round((time.monotonic() - t_start) * 1000)  # ms
        except Exception as e:
            await context.close()
            return {"error": str(e), "screenshot": None}

        # Additional wait for React/Next.js hydration
        await asyncio.sleep(1.5)

        # Grab HTML after full render
        html_content = await page.content()

        # Screenshot (base64 PNG)
        screenshot_bytes = await page.screenshot(full_page=False, type="png")
        import base64
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode()

        # Collect performance metrics if requested
        perf_raw = {}
        if collect_performance:
            perf_raw = await page.evaluate("() => window.__AUDIT_PERF__ || {}")

        # Collect all cookies (for privacy/GDPR signal)
        cookies = await context.cookies()

        # DOM node count
        dom_nodes = await page.evaluate("() => document.querySelectorAll('*').length")

        await context.close()

        return {
            "html": html_content,
            "status_code": response.status if response else None,
            "final_url": page.url,
            "ttfb_ms": ttfb,
            "resource_sizes": resource_sizes,
            "cookies": [{"name": c["name"], "domain": c["domain"]} for c in cookies],
            "screenshot": screenshot_b64,
            "performance_raw": perf_raw,
            "is_mobile": is_mobile,
            "dom_nodes": dom_nodes,
        }


# ── Performance Observer script injected before page load ─────────────────────

PERFORMANCE_OBSERVER_SCRIPT = """
(function() {
  window.__AUDIT_PERF__ = {
    lcp: null, cls: 0, inp: null, fcp: null, ttfb: null,
    long_tasks: [], resource_timing: []
  };

  // LCP
  const lcpObs = new PerformanceObserver((list) => {
    const entries = list.getEntries();
    if (entries.length) {
      window.__AUDIT_PERF__.lcp = entries[entries.length - 1].startTime;
    }
  });
  try { lcpObs.observe({ type: 'largest-contentful-paint', buffered: true }); } catch(e) {}

  // CLS
  let clsValue = 0;
  const clsObs = new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
      if (!entry.hadRecentInput) clsValue += entry.value;
    }
    window.__AUDIT_PERF__.cls = clsValue;
  });
  try { clsObs.observe({ type: 'layout-shift', buffered: true }); } catch(e) {}

  // FCP
  const fcpObs = new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
      if (entry.name === 'first-contentful-paint') {
        window.__AUDIT_PERF__.fcp = entry.startTime;
      }
    }
  });
  try { fcpObs.observe({ type: 'paint', buffered: true }); } catch(e) {}

  // Long tasks (INP proxy)
  const ltObs = new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
      window.__AUDIT_PERF__.long_tasks.push(entry.duration);
    }
  });
  try { ltObs.observe({ type: 'longtask', buffered: true }); } catch(e) {}

  // Navigation timing (TTFB)
  window.addEventListener('load', () => {
    const nav = performance.getEntriesByType('navigation')[0];
    if (nav) {
      window.__AUDIT_PERF__.ttfb = nav.responseStart - nav.requestStart;
    }
    // Resource timing
    const resources = performance.getEntriesByType('resource');
    window.__AUDIT_PERF__.resource_timing = resources.map(r => ({
      name: r.name,
      duration: Math.round(r.duration),
      transfer_size: r.transferSize || 0,
      initiator_type: r.initiatorType,
    }));
  });
})();
"""
