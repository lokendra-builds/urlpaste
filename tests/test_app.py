"""End-to-end tests for the Streamlit app using Streamlit's own test harness."""

from __future__ import annotations

from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")

from urlpaste import TextItem, decode, encode, payload_from_link  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")


def run_app(query: dict | None = None):
    at = st_testing.AppTest.from_file(APP, default_timeout=30)
    for key, value in (query or {}).items():
        at.query_params[key] = value
    return at.run()


def test_create_page_renders_without_errors():
    at = run_app()
    assert not at.exception
    assert at.subheader[0].value == "Your link"
    assert "How it works" in [s.value for s in at.subheader]


def test_typing_a_note_produces_a_working_link():
    at = run_app()
    at.text_area[0].input("hello from the app").run()
    assert not at.exception
    link = at.code[0].value
    assert "?n=" in link
    assert decode(payload_from_link(link)) == TextItem("hello from the app")


def test_password_produces_an_encrypted_link():
    at = run_app()
    at.text_area[0].input("secret")
    at.text_input[0].input("pw").run()
    payload = payload_from_link(at.code[0].value)
    assert decode(payload, password="pw") == TextItem("secret")


def test_opening_a_text_link_shows_the_note():
    at = run_app({"n": encode(TextItem("shared note"))})
    assert not at.exception
    assert at.code[0].value == "shared note"


def test_markdown_link_escapes_html():
    at = run_app({"n": encode(TextItem("# Hi\n\n<script>alert(1)</script>", kind="markdown"))})
    assert not at.exception
    rendered = [m.value for m in at.markdown]
    assert any("# Hi" in v for v in rendered)
    assert all(m.allow_html is False for m in at.markdown if "<script>" in m.value)


def test_encrypted_link_asks_for_password_then_unlocks():
    at = run_app({"n": encode(TextItem("locked"), password="pw")})
    assert "password protected" in at.title[0].value
    at.text_input[0].input("pw")
    at.button[0].click().run()
    assert not at.exception
    assert at.code[0].value == "locked"


def test_wrong_password_shows_error():
    at = run_app({"n": encode(TextItem("locked"), password="pw")})
    at.text_input[0].input("nope")
    at.button[0].click().run()
    assert "Wrong password" in at.error[0].value


def test_broken_link_shows_friendly_error():
    at = run_app({"n": "AAAA"})
    assert not at.exception
    assert "broken" in at.error[0].value
