from meetingkb.search.query import fuzzy_match_query, highlight_fuzzy, query_variants


def test_variants_transliterate_not_translate():
    variants = query_variants("семафор")
    assert "semafor" in variants
    assert "semaphore" not in variants


def test_fuzzy_typos_and_translit_match():
    for text in ("симафор", "симмофорами", "semafor", "semaphore"):
        matched, score, _ = fuzzy_match_query("семафор", text)
        assert matched, text
        assert score > 0


def test_fuzzy_no_false_positive():
    matched, _, _ = fuzzy_match_query("семафор", "Семенов")
    assert not matched


def test_empty_query_matches_trivially():
    assert fuzzy_match_query("", "anything") == (True, 0, [])


def test_highlight_escapes_and_marks():
    out = highlight_fuzzy("a <b> семафор", ["семафор"])
    assert "&lt;b&gt;" in out
    assert "<mark>" in out
