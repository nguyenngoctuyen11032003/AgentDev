"""Composer "Add web link" / "Search the web": the text becomes an attachment the agents receive."""

from types import SimpleNamespace

import pytest

from agentdev.api.services import web_reference
from agentdev.api.services.attachment_service import AttachmentService
from agentdev.utils.exceptions import ValidationError


@pytest.fixture()
def fake_web(monkeypatch):
    calls = {}

    def read(url):
        calls["url"] = url
        if "private" in url:
            return "Error: local or private network addresses cannot be read: " + url
        return "URL: " + url + "\n\n# Shop\n\nProducts and prices"

    def search(query, page=1, language="en", country="us"):
        calls["search"] = (query, language)
        return "1. Result\n   https://example.com\n   snippet"

    module = SimpleNamespace(read_webpage_content=read, web_search=search)
    monkeypatch.setattr(web_reference, "_web_tools", lambda: module)
    return calls


def test_page_is_read_and_scheme_is_added(fake_web):
    name, markdown, url = web_reference.read_page(" example.com/shop ")
    assert url == "https://example.com/shop" and fake_web["url"] == url
    assert name == "web-example.com.md"
    assert "Products and prices" in markdown and "build something similar" in markdown


def test_refused_page_and_bad_input_raise(fake_web):
    with pytest.raises(ValidationError, match="private"):
        web_reference.read_page("http://private.lan")
    with pytest.raises(ValidationError):
        web_reference.read_page("ftp://example.com")
    with pytest.raises(ValidationError):
        web_reference.read_page("   ")
    with pytest.raises(ValidationError):
        web_reference.search("  ")


def test_search_results_become_markdown(fake_web):
    name, markdown = web_reference.search("  máy pha   cà phê ", language="vi")
    assert fake_web["search"] == ("máy pha cà phê", "vi")
    assert name.startswith("search-") and "https://example.com" in markdown


def test_reference_is_a_registered_upload_of_the_session(tmp_path):
    service = AttachmentService(root=tmp_path)
    service.prepare_session_workspace("s1")
    record = service.register_web_reference(
        "s1", "# Web page", display_name="web-example.com.md", extra={"kind": "web", "url": "https://example.com"}
    )
    assert record.ref.name == "web-example.com.md"
    # accepted as an attachment of this session (and only this one)
    assert service.resolve_uploaded_paths("s1", [record.ref.attachment_id])
