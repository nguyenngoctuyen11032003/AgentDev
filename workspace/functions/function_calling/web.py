"""Web tools that need no API key: metasearch (ddgs, Bing fallback) and direct page reading."""

import ipaddress
import socket
from urllib.parse import parse_qs, urljoin, urlparse

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36"
)
_TIMEOUT = 20
_MAX_REDIRECTS = 5
_MAX_BYTES = 3 * 1024 * 1024
_MAX_CHARS = 20000
_RESULTS_PER_PAGE = 10
# (language, country) -> DuckDuckGo region code
_REGIONS = {
    "en": "us-en", "us": "us-en", "vi": "vn-vi", "vn": "vn-vi",
    "zh-cn": "cn-zh", "cn": "cn-zh", "zh-tw": "tw-tzh", "tw": "tw-tzh",
    "ja": "jp-jp", "jp": "jp-jp", "ko": "kr-kr", "kr": "kr-kr",
}


def web_search(query: str, page: int = 1, language: str = "en", country: str = "us") -> str:
    """
    Performs a web search based on the user-provided query with pagination.

    Args:
        query (str): The keyword(s) to search for.
        page (int): The page number of the results to return. Defaults to 1.
        language (str): The language of the search results. Defaults to "en", can be "en", "vi", "zh-cn", "zh-tw", "ja", "ko".
        country (str): The country of the search results. Defaults to "us", can be "us", "vn", "cn", "jp", "kr".

    Returns:
        str: A formatted string containing the title, link, and snippet of the search results for the specified page.
    """
    query = (query or "").strip()
    if not query:
        return "Error: the search query is empty."
    try:
        page = max(1, int(page or 1))
    except (TypeError, ValueError):
        page = 1
    language = (language or "en").lower()
    country = (country or "us").lower()

    # ddgs queries several keyless engines and pages through results; scraping Bing directly
    # backs it up for the first page (Bing serves only that page to scripts).
    engines = (_search_ddgs, _search_bing) if page == 1 else (_search_ddgs,)
    errors = []
    for engine in engines:
        try:
            results = engine(query, page, language, country)
        except Exception as exc:  # noqa: BLE001 - try the next engine
            errors.append(f"{engine.__name__[8:]}: {type(exc).__name__}")
            continue
        if results:
            lines = [f"## Search results for: {query} (page {page})"]
            for index, (title, link, snippet) in enumerate(results, 1):
                lines.append(f"{index}. **[{title or link}]({link})**")
                if snippet:
                    lines.append(f"   {snippet}")
            return "\n".join(lines)
    if page > 1:
        return (
            f"Page {page} of the results is not available right now. "
            "Use the first page or try a more specific query instead."
        )
    if errors:
        return f"Error: web search failed ({', '.join(errors)})."
    return f"No results found for: {query}"


def _search_bing(query, page, language, country):
    import requests
    from bs4 import BeautifulSoup

    lang = language.split("-")[0]
    response = requests.get(
        "https://www.bing.com/search",
        params={"q": query, "first": (page - 1) * _RESULTS_PER_PAGE + 1, "setlang": lang, "cc": country},
        headers={"User-Agent": _USER_AGENT, "Accept-Language": f"{lang},en;q=0.8"},
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    results = []
    for item in soup.select("li.b_algo"):
        anchor = item.select_one("h2 a")
        if anchor is None:
            continue
        link = _clean_bing_link(anchor.get("href") or "")
        if not link:
            continue
        snippet = item.select_one(".b_caption p") or item.select_one("p")
        results.append((anchor.get_text(" ", strip=True), link, snippet.get_text(" ", strip=True) if snippet else ""))
    return results[:_RESULTS_PER_PAGE]


def _clean_bing_link(href: str) -> str:
    """Bing wraps result links as /ck/a?...&u=a1<base64url(target)>."""
    import base64

    parsed = urlparse(href)
    if parsed.netloc.endswith("bing.com") and parsed.path.startswith("/ck/"):
        encoded = parse_qs(parsed.query).get("u", [""])[0]
        if encoded.startswith("a1"):
            encoded = encoded[2:]
            try:
                href = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                return ""
    return href if urlparse(href).scheme in ("http", "https") else ""


def _search_ddgs(query, page, language, country):
    from ddgs import DDGS

    region = _REGIONS.get(country) or _REGIONS.get(language) or "us-en"
    items = DDGS(timeout=_TIMEOUT).text(query, region=region, max_results=_RESULTS_PER_PAGE, page=page)
    results = []
    for item in items or []:
        link = item.get("href") or ""
        if urlparse(link).scheme in ("http", "https"):
            results.append((item.get("title") or "", link, item.get("body") or ""))
    return results[:_RESULTS_PER_PAGE]


def _is_public_host(host: str) -> bool:
    """True when every address the host resolves to is a public internet address."""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return False
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%", 1)[0])
        if not address.is_global or address.is_multicast:
            return False
    return bool(infos)


def _check_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return "only http(s) web addresses can be read"
    if parsed.username or parsed.password:
        return "addresses with embedded credentials are not allowed"
    if not _is_public_host(parsed.hostname):
        return "local or private network addresses cannot be read"
    return ""


def read_webpage_content(url: str) -> str:
    """
    Reads the content of a webpage and returns it as a string.
    """
    import requests
    from bs4 import BeautifulSoup

    url = (url or "").strip()
    response = None
    try:
        for _ in range(_MAX_REDIRECTS + 1):
            problem = _check_url(url)
            if problem:
                return f"Error: {problem}: {url}"
            response = requests.get(
                url,
                headers={"User-Agent": _USER_AGENT, "Accept": "text/html,text/plain;q=0.9,*/*;q=0.5"},
                timeout=_TIMEOUT,
                allow_redirects=False,
                stream=True,
            )
            if response.is_redirect and response.headers.get("location"):
                url = urljoin(url, response.headers["location"])
                response.close()
                continue
            break
        else:
            return "Error: too many redirects."
        response.raise_for_status()
        raw = response.raw.read(_MAX_BYTES + 1, decode_content=True)
    except requests.RequestException as exc:
        return f"Error: could not read the page ({type(exc).__name__})."
    finally:
        if response is not None:
            response.close()

    content_type = (response.headers.get("content-type") or "").lower()
    raw = raw[:_MAX_BYTES]
    head = raw[:200].decode("ascii", errors="ignore").lstrip().lower()
    if "html" in content_type or head.startswith(("<!doctype", "<html")):
        # Hand the bytes to BeautifulSoup so it honours <meta charset> (requests assumes latin-1)
        declared = "charset=" in content_type and response.encoding or None
        text = _html_to_text(BeautifulSoup(raw, "html.parser", from_encoding=declared))
    else:
        text = raw.decode(response.encoding or "utf-8", errors="replace")
    if content_type and "html" not in content_type and not content_type.startswith(("text/", "application/json", "application/xml")):
        return f"Error: unsupported content type '{content_type}' at {url}"

    text = text.strip()
    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS] + "\n\n[... content truncated ...]"
    return f"URL: {url}\n\n{text}" if text else f"The page at {url} has no readable text."


def _html_to_text(soup) -> str:
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "form", "nav", "footer", "header", "aside"]):
        tag.decompose()
    for tag in soup.select('[role="navigation"], [role="banner"], [role="contentinfo"], .sidebar, .sphinxsidebar, .related'):
        tag.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    root = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.find("article") or soup.body or soup
    lines = []
    for element in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "pre", "td", "blockquote"]):
        chunk = element.get_text(" ", strip=True)
        if not chunk:
            continue
        if element.name in ("h1", "h2", "h3", "h4"):
            lines.append("#" * int(element.name[1]) + " " + chunk)
        elif element.name == "li":
            lines.append(f"- {chunk}")
        else:
            lines.append(chunk)
    body = "\n\n".join(dict.fromkeys(lines)) or root.get_text("\n", strip=True)
    return f"# {title}\n\n{body}" if title else body


if __name__ == "__main__":
    pass
