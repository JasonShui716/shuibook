from app.services.canonicalize import canonicalize_url


def test_canonicalize_url_removes_tracking():
    url = "https://example.com/path/?utm_source=abc&b=2&a=1#section"
    canon = canonicalize_url(url)
    assert canon == "https://example.com/path?a=1&b=2"


def test_canonicalize_url_default_port():
    url = "https://example.com:443/path/"
    canon = canonicalize_url(url)
    assert canon == "https://example.com/path"
