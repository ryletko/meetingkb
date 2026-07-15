from meetingkb.search.storage import connect, init_db


def test_schema_creates_expected_tables(tmp_path):
    conn = connect(tmp_path / "sub" / "kb.sqlite")   # parent auto-created
    init_db(conn)
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
    assert {"meetings", "segments", "terms", "segment_fts"} <= names
    # dead tables removed in the restructure
    assert "aliases" not in names
    assert "meeting_summaries" not in names


def test_fts_is_queryable(tmp_path):
    conn = connect(tmp_path / "kb.sqlite")
    init_db(conn)
    conn.execute(
        "INSERT INTO segment_fts (segment_id, meeting_id, title, text, terms) "
        "VALUES ('s1','m1','T','hello world','[]')")
    rows = conn.execute(
        "SELECT segment_id FROM segment_fts WHERE segment_fts MATCH 'hello'").fetchall()
    assert rows[0][0] == "s1"
