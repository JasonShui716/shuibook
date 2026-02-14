from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from readability import Document
import trafilatura
import httpx

from app.config import settings
from app.utils.http import fetch_url, is_medium_url


@dataclass
class ExtractResult:
    text: str | None
    excerpt: str | None
    image_url: str | None
    site_name: str | None


def _resolve_url(base_url: str, link: str) -> str:
    return urljoin(base_url, link)


def _extract_og_image(soup: BeautifulSoup, base_url: str) -> str | None:
    for prop in ["og:image", "og:image:url", "twitter:image"]:
        tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            return _resolve_url(base_url, tag["content"].strip())
    return None


def _extract_site_name(soup: BeautifulSoup, base_url: str) -> str | None:
    tag = soup.find("meta", attrs={"property": "og:site_name"})
    if tag and tag.get("content"):
        return tag["content"].strip()
    parsed = urlparse(base_url)
    return parsed.netloc


def _extract_first_image(soup: BeautifulSoup, base_url: str) -> str | None:
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if not src:
            continue
        if src.startswith("data:"):
            continue
        width = img.get("width")
        height = img.get("height")
        if width and height:
            try:
                if int(width) < 120 or int(height) < 120:
                    continue
            except ValueError:
                pass
        return _resolve_url(base_url, src)
    return None


def extract_article(url: str) -> ExtractResult:
    html = None
    base_url = url
    is_medium = is_medium_url(url)

    if html is None:
        resp = fetch_url(url)
        if resp is not None:
            html = resp.text
            base_url = str(resp.url)
            if _looks_blocked(html):
                html = None

    if html is None:
        if not is_medium:
            firecrawl_text = _firecrawl_extract(url)
            if firecrawl_text:
                excerpt = firecrawl_text.strip()[: settings.excerpt_max_chars]
                site_name = urlparse(url).netloc
                return ExtractResult(text=firecrawl_text, excerpt=excerpt, image_url=None, site_name=site_name)
        return ExtractResult(None, None, None, None)

    soup = BeautifulSoup(html, "lxml")

    og_image = _extract_og_image(soup, base_url)
    site_name = _extract_site_name(soup, base_url)

    text = None
    try:
        text = trafilatura.extract(html, include_comments=False, include_tables=False)
    except Exception:
        text = None

    if not text:
        try:
            doc = Document(html)
            summary_html = doc.summary()
            summary_soup = BeautifulSoup(summary_html, "lxml")
            text = summary_soup.get_text("\n", strip=True)
            if not og_image:
                og_image = _extract_first_image(summary_soup, base_url)
        except Exception:
            text = None

    if _looks_blocked(text):
        text = None

    if (not text or len(text.strip()) < 200) and not is_medium:
        firecrawl_text = _firecrawl_extract(url)
        if firecrawl_text:
            text = firecrawl_text

    if not og_image:
        og_image = _extract_first_image(soup, base_url)

    excerpt = None
    if text:
        excerpt = text.strip()[: settings.excerpt_max_chars]

    return ExtractResult(text=text, excerpt=excerpt, image_url=og_image, site_name=site_name)


def _firecrawl_extract(url: str) -> str | None:
    if not settings.firecrawl_api_key:
        return None
    try:
        headers = {"Authorization": f"Bearer {settings.firecrawl_api_key}"}
        payload = {
            "url": url,
            "onlyMainContent": True,
            "formats": ["markdown"],
            "blockAds": True,
            "removeBase64Images": True,
            "storeInCache": False,
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.post("https://api.firecrawl.dev/v1/scrape", json=payload, headers=headers)
            if resp.status_code >= 400:
                return None
            data = resp.json()
        if data.get("success") is False:
            return None
        content = data.get("data", {}).get("markdown") or data.get("data", {}).get("content")
        return content.strip() if content else None
    except Exception:
        return None


def _looks_blocked(html: str | None) -> bool:
    if not html:
        return False
    lower = html.lower()
    return (
        "just a moment" in lower
        or "cf-browser-verification" in lower
        or "cf-chl" in lower
        or "challenge-platform" in lower
        or "attention required" in lower
        or "access denied" in lower
        or "verify you are human" in lower
        or "enable javascript" in lower
        or "security check" in lower
        or "ddos protection" in lower
        or "检测到异常流量" in lower
        or "请完成验证" in lower
        or "安全验证" in lower
        or "人机验证" in lower
        or "访问受限" in lower
    )
