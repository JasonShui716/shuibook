from app.services.canonicalize import content_hash


def test_content_hash_dedup():
    text = "hello world"
    assert content_hash(text) == content_hash(text)
    assert content_hash(text) != content_hash(text + "!")
