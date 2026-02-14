import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from cachetools import TTLCache
from app.config import settings
from app.utils.remote_fetch import remote_fetch_html


ROBOTS_CACHE = TTLCache(maxsize=256, ttl=24 * 3600)
RESPONSE_CACHE = TTLCache(maxsize=512, ttl=3600)
HOST_LAST_REQUEST: dict[str, float] = {}
MEDIUM_DOMAINS = {"medium.com"}


def _get_robot_parser(base_url: str) -> RobotFileParser:
    if base_url in ROBOTS_CACHE:
        return ROBOTS_CACHE[base_url]

    robots_url = f"{base_url}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        with httpx.Client(timeout=10.0, headers={"User-Agent": settings.user_agent}) as client:
            resp = client.get(robots_url)
            if resp.status_code == 200:
                parser.parse(resp.text.splitlines())
            else:
                parser.parse([])
    except Exception:
        parser.parse([])

    ROBOTS_CACHE[base_url] = parser
    return parser


def is_allowed(url: str) -> bool:
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    parser = _get_robot_parser(base_url)
    return parser.can_fetch(settings.user_agent, url)


def is_medium_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc
    return any(host.endswith(domain) for domain in MEDIUM_DOMAINS)


def rate_limit(url: str) -> None:
    parsed = urlparse(url)
    host = parsed.netloc
    sleep_seconds = settings.rate_limit_seconds
    if any(host.endswith(domain) for domain in MEDIUM_DOMAINS):
        sleep_seconds = max(sleep_seconds, settings.medium_rate_limit_seconds)
    last = HOST_LAST_REQUEST.get(host)
    now = time.time()
    if last is not None:
        elapsed = now - last
        if elapsed < sleep_seconds:
            time.sleep(sleep_seconds - elapsed)
    HOST_LAST_REQUEST[host] = time.time()


def fetch_url(url: str) -> httpx.Response | None:
    if url in RESPONSE_CACHE:
        return RESPONSE_CACHE[url]

    if not is_allowed(url):
        return None

    rate_limit(url)
    try:
        # For Medium, ALWAYS prefer the remote-browser fetch path (CDP on the remote host).
        # This is the standard Medium tool: login state lives on the remote machine, not in this container.
        if is_medium_url(url):
            remote_html = remote_fetch_html(url)
            if remote_html:
                req = httpx.Request("GET", url)
                resp = httpx.Response(200, request=req, content=remote_html.encode("utf-8"))
                RESPONSE_CACHE[url] = resp
                return resp
            # Do not fall back to direct HTTP for Medium. If the remote browser isn't available,
            # we treat it as unavailable content instead of triggering challenges locally.
            return None

        headers = {"User-Agent": settings.user_agent}
        with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            if resp.status_code in (403, 429):
                remote_html = remote_fetch_html(url)
                if remote_html:
                    req = httpx.Request("GET", url)
                    resp = httpx.Response(200, request=req, content=remote_html.encode("utf-8"))
                else:
                    return None
            if resp.status_code >= 400:
                return None
            RESPONSE_CACHE[url] = resp
            return resp
    except Exception:
        return None
