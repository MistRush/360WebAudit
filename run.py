"""
run.py — Windows-compatible entry point for the FastAPI backend.

On Windows, Playwright requires `WindowsProactorEventLoopPolicy` to be able
to launch subprocesses via asyncio. However, when uvicorn uses `reload=True`,
it spawns a separate child worker process that does NOT inherit the policy
set in main.py. This script solves that by:

  1. Setting WindowsProactorEventLoopPolicy BEFORE importing uvicorn.
  2. Passing `loop="none"` to uvicorn so it doesn't override our loop policy.
"""
import sys

if sys.platform == "win32":
    import asyncio
    from asyncio import WindowsProactorEventLoopPolicy
    if not isinstance(asyncio.get_event_loop_policy(), WindowsProactorEventLoopPolicy):
        asyncio.set_event_loop_policy(WindowsProactorEventLoopPolicy())
        print("INFO: WindowsProactorEventLoopPolicy set successfully.")

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,   # reload=True is broken on Windows with Playwright
        app_dir="backend",
    )
