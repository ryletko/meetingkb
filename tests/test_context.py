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
