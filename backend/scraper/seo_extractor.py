"""
seo_extractor.py — Extracts SEO data from rendered HTML using stdlib HTMLParser.
"""
from __future__ import annotations
import re, html
from html.parser import HTMLParser
from typing import Any


class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self._in_title = False
        self.meta: list[dict] = []
        self.links: list[dict] = []
        self.headings: list[dict] = []
        self._cur_heading: str | None = None
        self._heading_buf: list[str] = []
        self.images: list[dict] = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs); t = tag.lower()
        if t == "title": self._in_title = True
        elif t == "meta": self.meta.append(d)
        elif t == "link": self.links.append(d)
        elif t in ("h1","h2","h3","h4","h5","h6"):
            self._cur_heading = t; self._heading_buf = []
        elif t == "img":
            self.images.append({"src": d.get("src",""), "alt": d.get("alt"),
                                 "width": d.get("width"), "height": d.get("height"),
                                 "loading": d.get("loading","")})

    def handle_endtag(self, tag):
        t = tag.lower()
        if t == "title": self._in_title = False
        elif t in ("h1","h2","h3","h4","h5","h6") and self._cur_heading:
            self.headings.append({"level": t,
                                   "text": html.unescape(" ".join(self._heading_buf).strip())})
            self._cur_heading = None

    def handle_data(self, data):
        if self._in_title: self.title += data
        if self._cur_heading: self._heading_buf.append(data.strip())


def extract_seo(html_content: str, final_url: str = "") -> dict[str, Any]:
    p = _MetaParser()
    p.feed(html_content)

    meta_dict: dict[str, str] = {}
    og: dict[str, str] = {}
    twitter: dict[str, str] = {}

    for m in p.meta:
        name = m.get("name", "").lower()
        prop = m.get("property", "").lower()
        content = m.get("content", "")
        if name: meta_dict[name] = content
        if prop.startswith("og:"): og[prop[3:]] = content
        if prop.startswith("twitter:") or name.startswith("twitter:"):
            key = prop[8:] if prop.startswith("twitter:") else name[8:]
            twitter[key] = content
        if m.get("charset"): meta_dict["charset"] = m["charset"]

    canonical = next((l.get("href","") for l in p.links if "canonical" in l.get("rel","").lower()), "")
    hreflang = [{"lang": l.get("hreflang",""), "href": l.get("href","")}
                for l in p.links if "alternate" in l.get("rel","").lower() and l.get("hreflang")]

    title = p.title.strip()
    meta_desc = meta_dict.get("description", "")
    meta_robots = meta_dict.get("robots", "")
    h1_list = [h["text"] for h in p.headings if h["level"] == "h1"]

    images_missing_alt = [i for i in p.images if i["alt"] is None]
    images_no_lazy = [i for i in p.images if i.get("loading","").lower() != "lazy"]
    jsonld_count = len(re.findall(r'<script[^>]+type=["\']application/ld\+json["\']', html_content, re.I))
    word_count = len(re.sub(r'<[^>]+>', ' ', html_content).split())

    return {
        "title": title, "title_length": len(title), "title_ok": 30 <= len(title) <= 60,
        "meta_description": meta_desc, "meta_description_length": len(meta_desc),
        "meta_description_ok": 120 <= len(meta_desc) <= 160,
        "meta_robots": meta_robots, "is_noindex": "noindex" in meta_robots.lower(),
        "is_nofollow": "nofollow" in meta_robots.lower(),
        "viewport": meta_dict.get("viewport",""), "has_viewport": bool(meta_dict.get("viewport")),
        "charset": meta_dict.get("charset",""),
        "canonical": canonical, "has_canonical": bool(canonical),
        "canonical_matches_url": canonical.rstrip("/") == final_url.rstrip("/") if canonical and final_url else None,
        "hreflang": hreflang, "has_hreflang": len(hreflang) > 0,
        "headings": p.headings,
        "h1_count": len(h1_list), "h1_texts": h1_list, "has_single_h1": len(h1_list) == 1,
        "image_count": len(p.images),
        "images_missing_alt_count": len(images_missing_alt),
        "images_no_lazy_count": len(images_no_lazy),
        "images_missing_alt_urls": [i["src"] for i in images_missing_alt[:50]],
        "og": og, "og_complete": all(k in og for k in ("title","description","image","type")),
        "twitter": twitter, "twitter_complete": all(k in twitter for k in ("card","title","description")),
        "jsonld_count": jsonld_count,
        "word_count": word_count, "content_ok": word_count >= 300,
    }
