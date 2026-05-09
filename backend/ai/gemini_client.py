"""
gemini_client.py — Rate-limited async wrapper around Google Generative AI SDK.
Implements token bucket rate limiter to stay under Gemini API quotas.
"""
from __future__ import annotations
import asyncio
import time
import google.generativeai as genai
from config import settings

import httpx
import json


class RateLimiter:
    """Simple token bucket rate limiter."""
    def __init__(self, rpm: int):
        self.rpm = rpm
        self._tokens = float(rpm)
        self._max_tokens = float(rpm)
        self._refill_rate = rpm / 60.0
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._max_tokens, self._tokens + elapsed * self._refill_rate)
            self._last_refill = now
            if self._tokens < 1:
                wait = (1 - self._tokens) / self._refill_rate
                await asyncio.sleep(wait)
                self._tokens = 0
            else:
                self._tokens -= 1

_limiter = RateLimiter(rpm=settings.rate_limit_gemini_rpm)

# Initialize direct Gemini if key is provided
if settings.gemini_api_key:
    genai.configure(api_key=settings.gemini_api_key)
    _model = genai.GenerativeModel(settings.gemini_model)
else:
    _model = None


async def gemini_generate(prompt: str, temperature: float = 0.3) -> str:
    """
    Send a prompt to AI (OpenRouter or direct Gemini) and return text response.
    """
    await _limiter.acquire()

    # Priority 1: OpenRouter (only if key is real)
    if settings.openrouter_api_key and not settings.openrouter_api_key.startswith("your_"):
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "HTTP-Referer": "https://webauditor2026.local",
            "X-Title": "AI Web Auditor 2026",
            "Content-Type": "application/json"
        }
        payload = {
            "model": settings.openrouter_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]
                # If 401/403, we might want to fall back to Gemini instead of failing
            except Exception as e:
                print(f"OpenRouter Error: {e}, trying fallback...")

    # Priority 2: Direct Gemini
    if settings.gemini_api_key:
        # Re-initialize or use cached model with the current setting
        model_name = settings.gemini_model
        print(f"DEBUG: Spouštím AI audit s modelem: {model_name}")
        model = genai.GenerativeModel(model_name)
        
        for attempt in range(3):
            try:
                response = await asyncio.to_thread(
                    model.generate_content,
                    prompt,
                    generation_config=genai.GenerationConfig(
                        temperature=temperature,
                        max_output_tokens=4096,
                    ),
                )
                return response.text
            except Exception as e:
                print(f"Gemini Error (Attempt {attempt+1}): {e}")
                if attempt == 2: raise e
                await asyncio.sleep(2 ** attempt)

    raise Exception("Není nakonfigurován žádný AI poskytovatel (OpenRouter nebo Gemini API Key)")
