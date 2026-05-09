import asyncio
import sys
import os

# Add the current directory to sys.path so we can import from scraper and config
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Windows Proactor fix
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from scraper.playwright_engine import PlaywrightEngine
from scraper.seo_extractor import extract_seo
from scraper.schema_extractor import extract_schema

async def main():
    url = "https://www.google.com"
    if len(sys.argv) > 1:
        url = sys.argv[1]
    
    print(f"--- Verifying DOM extraction for: {url} ---")
    
    engine = PlaywrightEngine()
    print("Step 1: Scraping with Playwright...")
    raw = await engine.scrape_full(url)
    
    if "error" in raw["desktop"]:
        print(f"Error: {raw['desktop']['error']}")
        return

    html_content = raw["desktop"]["html"]
    final_url = raw["desktop"]["final_url"]
    
    print(f"HTML Content Length: {len(html_content)}")
    print(f"HTML Snippet: {html_content[:500]}...")
    
    print(f"Resources found: {len(raw['desktop'].get('resource_sizes', []))}")
    if raw['desktop'].get('resource_sizes'):
        print(f"First few resources: {raw['desktop']['resource_sizes'][:3]}")
    
    print(f"Step 2: Extracting SEO data (Title, Headings, Meta)...")
    seo = extract_seo(html_content, final_url)
    
    print(f"Title: {seo['title']}")
    print(f"H1 Count: {seo['h1_count']}")
    if seo['h1_texts']:
        print(f"H1 Texts: {seo['h1_texts']}")
    
    print(f"Step 3: Extracting Schema.org data...")
    schema_res = extract_schema(html_content)
    print(f"Schema Types Found: {schema_res['types_found']}")
    if schema_res['parse_errors']:
        print(f"Schema Parse Errors: {schema_res['parse_errors']}")
    
    from scraper.performance_metrics import analyze_performance
    print(f"Step 4: Analyzing Performance Metrics...")
    performance = analyze_performance(raw.get("performance_raw", {}), raw["desktop"].get("resource_sizes", []))
    print(f"LCP: {performance['lcp_ms']} ms ({performance['lcp_rating']})")
    print(f"CLS: {performance['cls']} ({performance['cls_rating']})")
    print(f"Total Transfer: {performance['total_transfer_kb']} KB")
    
    print("\n--- DOM Verification Complete ---")

if __name__ == "__main__":
    asyncio.run(main())
