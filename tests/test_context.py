from meetingkb.config import Settings
from meetingkb.context import AppContext
from meetingkb.search.storage import init_db


def test_context_provides_wired_services(tmp_path):
    # opensearch_url pinned to a closed port (127.0.0.1:59999): this dev box always
    # has an unrelated OpenSearch container occupying the default 9200, so relying
    # on "nothing running on the default port" would be environment-dependent. Same
    # convention as tests/test_opensearch_backend.py::test_available_false_when_unreachable.
    ctx = AppContext(Settings(data_dir=tmp_path, opensearch_url="http://127.0.0.1:59999"))
    init_db(ctx.sqlite())
    assert ctx.sqlite() is ctx.sqlite()  # cached singleton
    assert ctx.search_backend().url.startswith("http")
    assert ctx.opensearch_available() is False  # nothing running in test


class _FakeAlwaysAvailableBackend:
    """Stand-in for OpenSearchClient whose `.available()` reports True."""

    def available(self) -> bool:
        return True


def test_opensearch_available_false_when_disabled_even_if_backend_reachable(tmp_path):
    # KB_OPENSEARCH_ENABLED=false must force SQLite-only serving even when an
    # OpenSearch instance is actually reachable -- e.g. right after
    # `kb index --no-opensearch`, so a stale pre-existing OpenSearch index
    # can't override the freshly-rebuilt SQLite data.
    ctx = AppContext(Settings(data_dir=tmp_path, opensearch_enabled=False))
    ctx._search_backend = _FakeAlwaysAvailableBackend()  # inject fake: reachable
    assert ctx.search_backend().available() is True  # sanity: backend says available
    assert ctx.opensearch_available() is False  # but the toggle still forces False
