import hashlib
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

TRACKING_PARAMS_PREFIXES = (
    "utm_",
)
TRACKING_PARAMS = {
    "gclid",
    "fbclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "mkt_tok",
    "ref",
    "spm",
    "si",
}


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()

    if ":" in netloc:
        host, port = netloc.split(":", 1)
        if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
            netloc = host

    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        key_lower = key.lower()
        if key_lower in TRACKING_PARAMS:
            continue
        if any(key_lower.startswith(prefix) for prefix in TRACKING_PARAMS_PREFIXES):
            continue
        query_items.append((key, value))

    query_items.sort()
    query = urlencode(query_items, doseq=True)

    normalized = urlunparse((scheme, netloc, path, "", query, ""))
    return normalized


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
