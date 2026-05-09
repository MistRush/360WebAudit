"""
geo_checker.py — Checks hosting, IP, SSL certificate, DNS, and server response time.
Uses httpx for HTTP checks and dnspython for DNS resolution.
"""
from __future__ import annotations
import asyncio
import ssl
import socket
import time
from datetime import datetime, timezone
from typing import Any
import httpx
import tldextract


async def check_geo(url: str, ttfb_ms: int | None = None) -> dict[str, Any]:
    """
    Perform geo/server checks:
    - IP address and reverse DNS
    - HTTPS / SSL certificate validity + expiry
    - HTTP → HTTPS redirect
    - Security headers
    - TTFB (from Playwright or measured here)
    - Server header / technology hints
    """
    result: dict[str, Any] = {
        "url": url,
        "ip": None,
        "reverse_dns": None,
        "ssl_valid": None,
        "ssl_expiry_days": None,
        "ssl_issuer": None,
        "https_redirect": None,
        "http_to_https": None,
        "server_header": None,
        "powered_by": None,
        "ttfb_ms": ttfb_ms,
        "security_headers": {},
        "has_robots_txt": None,
        "robots_txt_ok": None,
        "has_sitemap": None,
        "errors": [],
    }

    # ── Domain extraction ─────────────────────────────────
    extracted = tldextract.extract(url)
    hostname = f"{extracted.subdomain}.{extracted.domain}.{extracted.suffix}".lstrip(".")
    result["hostname"] = hostname
    result["domain"] = f"{extracted.domain}.{extracted.suffix}"

    # ── IP resolution ─────────────────────────────────────
    try:
        ip = socket.gethostbyname(hostname)
        result["ip"] = ip
        try:
            rdns = socket.gethostbyaddr(ip)[0]
            result["reverse_dns"] = rdns
        except Exception:
            pass
    except Exception as e:
        result["errors"].append(f"DNS: {e}")

    # ── SSL certificate check ─────────────────────────────
    if url.startswith("https"):
        try:
            ctx = ssl.create_default_context()
            conn = ctx.wrap_socket(
                socket.socket(socket.AF_INET), server_hostname=hostname
            )
            conn.settimeout(10)
            conn.connect((hostname, 443))
            cert = conn.getpeercert()
            conn.close()

            # Expiry date
            exp_str = cert.get("notAfter", "")
            if exp_str:
                exp_dt = datetime.strptime(exp_str, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
                days_left = (exp_dt - datetime.now(timezone.utc)).days
                result["ssl_expiry_days"] = days_left
                result["ssl_valid"] = days_left > 0
            else:
                result["ssl_valid"] = True

            # Issuer
            issuer = dict(x[0] for x in cert.get("issuer", []))
            result["ssl_issuer"] = issuer.get("organizationName", "")

        except ssl.SSLError as e:
            result["ssl_valid"] = False
            result["errors"].append(f"SSL: {e}")
        except Exception as e:
            result["errors"].append(f"SSL check: {e}")

    # ── HTTP headers + redirect check ────────────────────
    try:
        async with httpx.AsyncClient(
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; WebAuditor/1.0)"},
        ) as client:
            # Measure TTFB if not provided by Playwright
            if ttfb_ms is None:
                t0 = time.monotonic()
                resp = await client.get(url)
                result["ttfb_ms"] = round((time.monotonic() - t0) * 1000)
            else:
                resp = await client.get(url)

            result["status_code"] = resp.status_code
            result["final_url"] = str(resp.url)
            result["redirect_count"] = len(resp.history)

            # Server fingerprinting
            h = resp.headers
            result["server_header"] = h.get("server", "")
            result["powered_by"] = h.get("x-powered-by", "")
            result["content_type"] = h.get("content-type", "")

            # ── Security headers ──────────────────────────
            security_headers = {
                "Strict-Transport-Security": h.get("strict-transport-security", ""),
                "Content-Security-Policy": h.get("content-security-policy", ""),
                "X-Frame-Options": h.get("x-frame-options", ""),
                "X-Content-Type-Options": h.get("x-content-type-options", ""),
                "Referrer-Policy": h.get("referrer-policy", ""),
                "Permissions-Policy": h.get("permissions-policy", ""),
                "X-Robots-Tag": h.get("x-robots-tag", ""),
            }
            result["x_robots_tag"] = h.get("x-robots-tag", "")
            result["security_headers"] = {k: v for k, v in security_headers.items()}
            result["security_headers_score"] = sum(1 for v in security_headers.values() if v)
            result["hsts_enabled"] = bool(h.get("strict-transport-security"))

        # ── HTTP → HTTPS redirect check ───────────────────
        if url.startswith("https"):
            http_url = url.replace("https://", "http://", 1)
            try:
                async with httpx.AsyncClient(timeout=10, follow_redirects=False) as c2:
                    r2 = await c2.get(http_url)
                    result["http_to_https"] = (
                        r2.status_code in (301, 302, 308)
                        and "https" in r2.headers.get("location", "")
                    )
            except Exception:
                result["http_to_https"] = None

        # ── Robots.txt and Sitemap.xml check ──────────────────
        base_url = f"https://{hostname}" if url.startswith("https") else f"http://{hostname}"
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c_robots:
                # Robots.txt
                r_robots = await c_robots.get(f"{base_url}/robots.txt")
                if r_robots.status_code == 200:
                    result["has_robots_txt"] = True
                    text = r_robots.text.lower()
                    
                    # Safer parsing: check if there's an exact match for "disallow: /" right after a newline or start
                    # To avoid matching "Disallow: /admin/"
                    import re
                    # Look for "user-agent: *" followed eventually by "disallow: /" on its own line
                    has_ua_star = "user-agent: *" in text
                    blocks_all = bool(re.search(r"disallow:\s*/\s*(?:$|\n|\r)", text))
                    
                    result["robots_txt_ok"] = not (has_ua_star and blocks_all)
                else:
                    result["has_robots_txt"] = False
                    result["robots_txt_ok"] = False
                
                # Sitemap.xml
                # Try standard /sitemap.xml
                r_sitemap = await c_robots.head(f"{base_url}/sitemap.xml")
                if r_sitemap.status_code == 200:
                    result["has_sitemap"] = True
                else:
                    # Fallback to sitemap_index.xml
                    r_sitemap_idx = await c_robots.head(f"{base_url}/sitemap_index.xml")
                    result["has_sitemap"] = (r_sitemap_idx.status_code == 200)

        except Exception as e:
            result["has_robots_txt"] = False
            result["robots_txt_ok"] = False
            result["has_sitemap"] = False
            result["errors"].append(f"Robots/Sitemap check: {e}")

    except Exception as e:
        result["errors"].append(f"HTTP: {e}")

    # ── Technology detection from headers ─────────────────
    result["tech_hints"] = _detect_tech_from_headers(result)

    return result


def _detect_tech_from_headers(data: dict) -> list[str]:
    hints = []
    server = (data.get("server_header") or "").lower()
    powered = (data.get("powered_by") or "").lower()
    final_url = data.get("final_url", "")

    if "nginx" in server: hints.append("Nginx")
    if "apache" in server: hints.append("Apache")
    if "cloudflare" in server: hints.append("Cloudflare")
    if "php" in powered: hints.append("PHP")
    if "asp.net" in powered: hints.append("ASP.NET")
    if "vercel" in server or "vercel" in final_url: hints.append("Vercel")
    if "netlify" in server: hints.append("Netlify")
    if "shopify" in server or "myshopify" in final_url: hints.append("Shopify")
    if "wordpress" in server: hints.append("WordPress (hosting)")

    return hints
