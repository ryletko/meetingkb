from meetingkb.search.opensearch_backend import OpenSearchClient


def test_url_is_trimmed():
    c = OpenSearchClient("http://host:9200/")
    assert c.url == "http://host:9200"


def test_available_false_when_unreachable():
    c = OpenSearchClient("http://127.0.0.1:59999")  # nothing listening
    assert c.available() is False
