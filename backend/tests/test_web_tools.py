"""Keyless web tools (workspace/functions/function_calling/web.py), tested offline."""

import base64
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

WEB_PY = Path(__file__).resolve().parents[2] / "workspace" / "functions" / "function_calling" / "web.py"


@pytest.fixture()
def web():
    spec = importlib.util.spec_from_file_location("web_tools_under_test", WEB_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_api_key_is_read(web):
    source = WEB_PY.read_text(encoding="utf-8")
    assert "API_KEY" not in source and "getenv" not in source


def test_search_uses_ddgs_with_paging(web, monkeypatch):
    calls = []

    def ddgs(query, page, language, country):
        calls.append(page)
        return [("Title", f"https://example.com/{page}", "snippet")]

    monkeypatch.setattr(web, "_search_ddgs", ddgs)
    monkeypatch.setattr(web, "_search_bing", lambda *a: pytest.fail("bing not needed"))
    out = web.web_search("python", page=2)
    assert calls == [2] and "https://example.com/2" in out and "(page 2)" in out


def test_first_page_falls_back_to_bing(web, monkeypatch):
    def broken(*args):
        raise RuntimeError("blocked")

    monkeypatch.setattr(web, "_search_ddgs", broken)
    monkeypatch.setattr(web, "_search_bing", lambda *a: [("B", "https://b.example", "")])
    assert "https://b.example" in web.web_search("python")
    # later pages have no fallback and say so instead of repeating page 1
    assert "not available" in web.web_search("python", page=3)


def test_search_reports_failures_and_empty_query(web, monkeypatch):
    def broken(*args):
        raise RuntimeError("down")

    monkeypatch.setattr(web, "_search_ddgs", broken)
    monkeypatch.setattr(web, "_search_bing", broken)
    assert web.web_search("python").startswith("Error: web search failed")
    assert web.web_search("   ").startswith("Error: the search query is empty")


def test_bing_redirect_links_are_decoded(web):
    target = "https://realpython.com/async-io-python/"
    encoded = base64.urlsafe_b64encode(target.encode()).decode().rstrip("=")
    assert web._clean_bing_link(f"https://www.bing.com/ck/a?!&&p=abc&u=a1{encoded}&ntb=1") == target
    assert web._clean_bing_link("javascript:alert(1)") == ""


@pytest.mark.parametrize(
    "url",
    ["http://localhost:6400/api", "http://127.0.0.1/", "http://192.168.1.10/", "http://[::1]/", "file:///etc/passwd",
     "http://user:pass@example.com/"],
)
def test_reader_refuses_local_and_unsafe_addresses(web, url, monkeypatch):
    import requests

    monkeypatch.setattr(requests, "get", lambda *a, **k: pytest.fail("must not fetch"))
    assert web.read_webpage_content(url).startswith("Error:")


def test_reader_extracts_text_and_follows_safe_redirects(web, monkeypatch):
    import requests

    monkeypatch.setattr(web, "_is_public_host", lambda host: host != "internal.example")
    html = "<html><head><title>Trang thử</title></head><body><nav>menu</nav><main><h1>Xin chào</h1><p>Nội dung chính</p></main></body></html>"
    pages = {
        "https://a.example/": SimpleNamespace(is_redirect=True, headers={"location": "/final"}),
        "https://a.example/final": SimpleNamespace(
            is_redirect=False, headers={"content-type": "text/html; charset=utf-8"}, encoding="utf-8",
            raw=SimpleNamespace(read=lambda n, decode_content=True: html.encode("utf-8")),
        ),
        "https://b.example/": SimpleNamespace(is_redirect=True, headers={"location": "https://internal.example/admin"}),
    }
    for page in pages.values():
        page.close = lambda: None
        page.raise_for_status = lambda: None
    monkeypatch.setattr(requests, "get", lambda url, **k: pages[url])

    text = web.read_webpage_content("https://a.example/")
    assert "Xin chào" in text and "Nội dung chính" in text and "menu" not in text
    # a redirect into a private host is refused, not followed
    assert web.read_webpage_content("https://b.example/").startswith("Error: local or private")
