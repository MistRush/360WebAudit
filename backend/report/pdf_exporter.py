"""
pdf_exporter.py — Export HTML report to PDF.
Primary: Playwright (Chromium) — works on Railway/Linux and Windows.
Fallback: WeasyPrint if Playwright unavailable.
"""
from __future__ import annotations
import asyncio
from pathlib import Path


async def export_pdf(html_path: str, output_path: str) -> None:
    """Convert HTML report to PDF using Playwright's Chromium print-to-PDF."""
    try:
        await _playwright_pdf(html_path, output_path)
    except Exception as e:
        # Fallback to WeasyPrint
        try:
            _weasyprint_pdf(html_path, output_path)
        except Exception as e2:
            raise RuntimeError(f"PDF export selhal. Playwright: {e} | WeasyPrint: {e2}")


async def _playwright_pdf(html_path: str, output_path: str):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page()
        await page.goto(f"file:///{Path(html_path).absolute().as_posix()}")
        await page.wait_for_timeout(2000)  # Let Chart.js render
        await page.pdf(
            path=output_path,
            format="A4",
            print_background=True,
            margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"},
        )
        await browser.close()


def _weasyprint_pdf(html_path: str, output_path: str):
    from weasyprint import HTML
    HTML(filename=html_path).write_pdf(output_path)
