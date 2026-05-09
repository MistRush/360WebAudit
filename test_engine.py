import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path.cwd() / "backend"))

from scraper.playwright_engine import PlaywrightEngine

async def test_scrape():
    async def mock_log(level, msg):
        print(f"[{level}] {msg}")

    engine = PlaywrightEngine(log_callback=mock_log)
    url = "https://escapegame.cz"
    try:
        print(f"Starting scrape for {url}...")
        result = await engine.scrape_full(url)
        print("Scrape successful!")
        print(f"Keys in result: {result.keys()}")
        print(f"Status Desktop: {result['desktop'].get('status_code')}")
        print(f"Status Mobile: {result['mobile'].get('status_code')}")
    except Exception as e:
        import traceback
        print(f"Scrape failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(test_scrape())
