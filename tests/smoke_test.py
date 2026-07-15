import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.integration  # needs indexed sample data + running services


def test_app_runs_without_exception():
    at = AppTest.from_file("src/meetingkb/web/app.py", default_timeout=30).run()
    assert not at.exception
    assert any(
        "Meeting Knowledge Base" in (m.value if hasattr(m, "value") else "")
        for m in at.markdown + at.title
    )
