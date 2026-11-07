"""Polite, SSRF-safe page metadata fetcher. Standard library only; no LLM involved.

Every connection (including each redirect hop) resolves the host itself and refuses
non-public addresses, so a submitted link cannot make this process reach internal
services. robots.txt is honoured, requests to one host are spaced out, and only the
first bytes of an HTML response are read.
"""

import codecs
import http.client
import ipaddress
import re
import socket
import ssl
import threading
import time
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import (
    HTTPDefaultErrorHandler,
    HTTPErrorProcessor,
    HTTPHandler,
    HTTPRedirectHandler,
    HTTPSHandler,
    OpenerDirector,
    Request,
    UnknownHandler,
)
from urllib.robotparser import RobotFileParser

ROBOTS_TOKEN = "HackerStack"
USER_AGENT = "HackerStack/1.0 (+https://rohansweblog.com/hackerstack/)"
MAX_BYTES = 150_000
RETRYABLE = ("error", "http_429", "http_500", "http_502", "http_503", "http_504")


class UnsafeHost(OSError):
    pass


def is_public(address):
    ip = ipaddress.ip_address(address.split("%")[0])
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global


def safe_create_connection(address, timeout=None, source_address=None):
    host, port = address
    last = None
    for family, kind, proto, _, sockaddr in socket.getaddrinfo(
        host, port, type=socket.SOCK_STREAM
    ):
        if not is_public(sockaddr[0]):
            last = last or UnsafeHost(f"{host} resolves to a non-public address")
            continue
        sock = socket.socket(family, kind, proto)
        try:
            sock.settimeout(timeout)
            sock.connect(sockaddr)
            return sock
        except OSError as exc:
            sock.close()
            last = exc
    raise last or OSError(f"No addresses for {host}")


class SafeHTTPConnection(http.client.HTTPConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = safe_create_connection


class SafeHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = safe_create_connection


class _HTTP(HTTPHandler):
    def http_open(self, req):
        return self.do_open(SafeHTTPConnection, req)


class _HTTPS(HTTPSHandler):
    def https_open(self, req):
        return self.do_open(SafeHTTPSConnection, req, context=self._context)


class _Redirect(HTTPRedirectHandler):
    max_redirections = 5


def build_opener():
    # Explicit handler list: no file:, ftp:, data: or environment proxies.
    opener = OpenerDirector()
    for handler in (
        _HTTP(),
        _HTTPS(context=ssl.create_default_context()),
        _Redirect(),
        HTTPDefaultErrorHandler(),
        HTTPErrorProcessor(),
        UnknownHandler(),
    ):
        opener.add_handler(handler)
    return opener


def _clean(text, limit):
    return re.sub(r"\s+", " ", text or "").strip()[:limit]


class MetaParser(HTMLParser):
    """First <title>, first <h1>, and og/meta descriptions; ignores script/style/svg."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.h1 = [], []
        self.meta = {}
        self._mode = None
        self._skip = 0
        self._title_done = self._h1_done = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "svg", "noscript"):
            self._skip += 1
        elif self._skip:
            return
        elif tag == "title" and not self._title_done:
            self._mode = "title"
        elif tag == "h1" and not self._h1_done:
            self._mode = "h1"
        elif tag == "meta":
            a = {k: (v or "") for k, v in attrs}
            key = (a.get("property") or a.get("name") or "").lower()
            if key in ("og:title", "og:description", "description"):
                self.meta.setdefault(key, a.get("content", ""))

    def handle_endtag(self, tag):
        if tag in ("script", "style", "svg", "noscript"):
            self._skip = max(0, self._skip - 1)
        elif tag == "title" and self._mode == "title":
            self._mode, self._title_done = None, True
        elif tag == "h1" and self._mode == "h1":
            self._mode, self._h1_done = None, True

    def handle_data(self, data):
        if self._skip:
            return
        if self._mode == "title":
            self.title.append(data)
        elif self._mode == "h1":
            self.h1.append(data)


def _decode(raw, content_type):
    charset = None
    match = re.search(r"charset=([\w.-]+)", content_type or "", re.I)
    if match:
        charset = match.group(1)
    else:
        sniff = re.search(rb"<meta[^>]+charset=[\"']?([\w.-]+)", raw[:4096], re.I)
        charset = sniff.group(1).decode("ascii", "ignore") if sniff else None
    try:
        codecs.lookup(charset or "utf-8")
    except LookupError:
        charset = "utf-8"
    return raw.decode(charset or "utf-8", errors="replace")


def parse_metadata(html):
    parser = MetaParser()
    parser.feed(html)
    parser.close()
    title = _clean("".join(parser.title), 400) or _clean(
        parser.meta.get("og:title"), 400
    )
    description = _clean(
        parser.meta.get("og:description") or parser.meta.get("description"), 600
    )
    return dict(
        title=title, h1=_clean("".join(parser.h1), 400), description=description
    )


class Fetcher:
    def __init__(self, timeout=10, delay=1.0):
        self.timeout, self.delay = timeout, delay
        self._lock = threading.Lock()
        self._next = {}
        self._robots_cache = {}
        self._robots_locks = {}
        self._429 = {}
        self.blocked_hosts = set()

    def _pace(self, host):
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next.get(host, 0))
            self._next[host] = slot + self.delay
        if slot > now:
            time.sleep(slot - now)

    def _open(self, url):
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
                "Accept-Language": "en",
            },
        )
        return build_opener().open(request, timeout=self.timeout)

    def _robots(self, parts):
        origin = f"{parts.scheme}://{parts.netloc}"
        with self._lock:
            lock = self._robots_locks.setdefault(origin, threading.Lock())
        with lock:
            if origin in self._robots_cache:
                return self._robots_cache[origin]
            robots = RobotFileParser()
            try:
                self._pace(parts.hostname)
                with self._open(origin + "/robots.txt") as response:
                    body = response.read(500_001)[:500_000]
                    robots.parse(body.decode("utf-8", "replace").splitlines())
            except HTTPError as exc:
                if exc.code in (401, 403):
                    robots.disallow_all = True
                elif 400 <= exc.code < 500:
                    robots.allow_all = True
                else:
                    robots = None
            except (URLError, OSError, ValueError, http.client.HTTPException):
                robots = None
            self._robots_cache[origin] = robots
            return robots

    def fetch(self, url):
        """Returns dict(status, title, h1, description); status 'skipped' is not saved."""
        empty = dict(title="", h1="", description="")
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return dict(status="unsupported_url", **empty)
        if parts.hostname in self.blocked_hosts:
            return dict(status="skipped", **empty)
        robots = self._robots(parts)
        if robots is None:
            return dict(status="robots_unreachable", **empty)
        if not robots.can_fetch(ROBOTS_TOKEN, url):
            return dict(status="robots_blocked", **empty)
        try:
            self._pace(parts.hostname)
            with self._open(url) as response:
                kind = response.headers.get("Content-Type", "")
                if not re.match(r"\s*(text/html|application/xhtml)", kind, re.I):
                    return dict(status="not_html", **empty)
                raw = response.read(MAX_BYTES)
            meta = parse_metadata(_decode(raw, kind))
            ok = any(meta.values())
            return dict(status="ok" if ok else "no_metadata", **meta)
        except HTTPError as exc:
            if exc.code == 429:
                with self._lock:
                    self._429[parts.hostname] = self._429.get(parts.hostname, 0) + 1
                    if self._429[parts.hostname] >= 2:
                        self.blocked_hosts.add(parts.hostname)
            return dict(status=f"http_{exc.code}", **empty)
        except URLError as exc:
            unsafe = isinstance(exc.reason, UnsafeHost)
            return dict(status="unsafe_host" if unsafe else "error", **empty)
        except (OSError, ValueError, http.client.HTTPException):
            return dict(status="error", **empty)
