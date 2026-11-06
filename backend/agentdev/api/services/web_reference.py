"""Web pages and web searches the user adds to a message (composer "Add web link" / "Search the web").

The page or the search results are read on the server with the keyless web tools
(workspace/functions/function_calling/web.py: public addresses only, size and redirect limits) and
saved as a Markdown attachment, so every agent of any workflow receives the content, also one
without web tools.
"""

from __future__ import annotations

import importlib.util
import re
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from urllib.parse import urlparse

from agentdev.utils.exceptions import ValidationError
from agentdev.utils.function_manager import FUNCTION_CALLING_DIR

MAX_QUERY_CHARS = 300
MAX_URL_CHARS = 2000


@lru_cache(maxsize=1)
def _web_tools() -> ModuleType:
    path = Path(FUNCTION_CALLING_DIR) / "web.py"
    spec = importlib.util.spec_from_file_location("agentdev_web_reference_tools", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("web tools are not available")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _failure(text: str) -> str:
    """The tools answer failures as text starting with "Error:"; '' when the text is a result."""
    return text[len("Error:"):].strip() if text.startswith("Error:") else ""


def _slug(text: str, limit: int = 40) -> str:
    slug = re.sub(r"[^\w.-]+", "-", text, flags=re.UNICODE).strip("-.")
    return slug[:limit] or "web"


def normalize_url(raw: str) -> str:
    url = (raw or "").strip()
    if not url:
        raise ValidationError("The web address is empty", field="url")
    if len(url) > MAX_URL_CHARS:
        raise ValidationError("The web address is too long", field="url")
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValidationError("Only http(s) web addresses can be added", field="url")
    return url


def read_page(raw_url: str) -> tuple[str, str, str]:
    """(display name, markdown, url) for one web page; ValidationError when it cannot be read."""
    url = normalize_url(raw_url)
    text = _web_tools().read_webpage_content(url)
    problem = _failure(text)
    if problem:
        raise ValidationError(problem, field="url")
    host = urlparse(url).hostname or "web"
    markdown = "\n".join(
        [
            f"# Web page: {url}",
            "",
            "The user added this web page to the message. Its readable text was fetched for you below",
            "(scripts, navigation and images are left out). Use it as the reference the user means,",
            "e.g. to answer questions about it or to build something similar.",
            "",
            text,
        ]
    )
    return f"web-{_slug(host)}.md", markdown, url


def search(raw_query: str, *, language: str = "en") -> tuple[str, str]:
    """(display name, markdown) with the first page of web results for a query."""
    query = " ".join((raw_query or "").split())
    if not query:
        raise ValidationError("The search query is empty", field="query")
    if len(query) > MAX_QUERY_CHARS:
        raise ValidationError("The search query is too long", field="query")
    lang = (language or "en").lower()
    text = _web_tools().web_search(query, language=lang, country=lang)
    problem = _failure(text)
    if problem:
        raise ValidationError(problem, field="query")
    markdown = "\n".join(
        [
            f"# Web search: {query}",
            "",
            "The user asked to look this up on the web. These are the search results (title, link,",
            "snippet). Read a result in full with a web tool when you have one and need more detail.",
            "",
            text,
        ]
    )
    return f"search-{_slug(query)}.md", markdown
