"""Bounded HN ingestion. Never fetches arbitrary submitted URLs."""

import hashlib
import json
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Evidence, Resource
from .ranking import HALF_LIVES

PLACEHOLDER_DESCRIPTION = (
    "Community submission. Open the discussion for context and competing views."
)

QUERIES = [
    ("agents", "LLM agents"),
    ("agents", "agent harness"),
    ("llms", "language model"),
    ("rl", "reinforcement learning"),
    ("evals", "LLM evaluation"),
    ("retrieval", "retrieval augmented generation"),
    ("inference", "LLM inference"),
    ("data", "fine tuning"),
    ("production", "LLM production"),
    ("safety", "mechanistic interpretability"),
    ("multimodal", "vision language model"),
    ("research", "AI research"),
]


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = set()

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            try:
                url = canonical_url(href)
                if urlsplit(url).hostname not in ("news.ycombinator.com", "lobste.rs"):
                    self.links.add(url)
            except ValueError:
                pass


def ingest_comment(hit, category, thread_id):
    source_id = str(hit.get("objectID", ""))
    if not source_id.isdigit() or str(hit.get("story_id")) != thread_id:
        raise ValueError("Invalid comment or parent thread")
    parser = LinkParser()
    parser.feed(hit.get("comment_text") or "")
    date = parse_datetime(hit.get("created_at", ""))
    if date and timezone.is_naive(date):
        date = timezone.make_aware(date)
    if date and date > timezone.now():
        raise ValueError("Comment date is in the future")
    discussion = "https://news.ycombinator.com/item?id=" + source_id
    title = str(hit.get("story_title") or "HN discussion")[:400]
    for url in sorted(parser.links):
        with transaction.atomic():
            resource, _ = Resource.objects.get_or_create(
                url=url,
                defaults=dict(
                    title=urlsplit(url).netloc + urlsplit(url).path[:250],
                    description=f"Link mentioned in “{title}”. Read the comment to assess its context; a mention is not an endorsement.",
                    category=category,
                    kind="article",
                    provenance=discussion,
                ),
            )
            Evidence.objects.update_or_create(
                resource=resource,
                source="hn",
                source_id=source_id,
                defaults=dict(
                    thread_id=thread_id,
                    discussion_url=discussion,
                    title=title,
                    kind="mention",
                    points=None,
                    published_at=date,
                ),
            )
    return len(parser.links)


def canonical_url(value):
    if not isinstance(value, str) or len(value) > 2000:
        raise ValueError("URL must be a string of at most 2000 characters")
    p = urlsplit(value.strip())
    if (
        p.scheme.lower() not in ("https", "http")
        or not p.hostname
        or p.username
        or p.password
    ):
        raise ValueError("Only public HTTP(S) URLs without credentials are supported")
    port = p.port  # Validate malformed ports.
    host = p.hostname.lower().encode("idna").decode("ascii")
    if ":" in host:
        host = "[" + host + "]"
    if port and not (
        (p.scheme == "https" and port == 443) or (p.scheme == "http" and port == 80)
    ):
        host += ":" + str(port)
    query = [
        (k, v)
        for k, v in parse_qsl(p.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid")
    ]
    # Keep query ordering, meaningful parameters and hash routes intact.
    return urlunsplit(
        (p.scheme.lower(), host, p.path or "/", urlencode(query), p.fragment)
    )


class BudgetExceeded(Exception):
    pass


class CachedHNClient:
    def __init__(self, budget=24, delay=1.0, cache_dir=None):
        self.budget = budget
        self.requests = 0
        self.cache_hits = 0
        self.delay = delay
        self.last_request = 0
        self.cache_dir = Path(cache_dir or settings.BASE_DIR / ".cache" / "hackerstack")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        for old in self.cache_dir.glob("*.json"):
            if time.time() - old.stat().st_mtime > 7 * 86400:
                old.unlink(missing_ok=True)

    def get(self, endpoint, params):
        url = "https://hn.algolia.com/api/v1/" + endpoint + "?" + urlencode(params)
        cache = self.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".json")
        if cache.exists() and time.time() - cache.stat().st_mtime < 86400:
            try:
                result = json.loads(cache.read_text())
                self.cache_hits += 1
                return result
            except (OSError, ValueError):
                pass
        for attempt in range(2):
            if self.requests >= self.budget:
                raise BudgetExceeded("Network request budget reached; progress saved")
            time.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
            self.requests += 1
            self.last_request = time.monotonic()
            try:
                req = Request(
                    url,
                    headers={
                        "User-Agent": "HackerStack/1.0 (+https://rohansweblog.com/hackerstack/)"
                    },
                )
                with urlopen(req, timeout=15) as response:
                    raw = response.read(4_000_001)
                if len(raw) > 4_000_000:
                    raise ValueError("HN response exceeded 4 MB")
                result = json.loads(raw)
                if not isinstance(result, dict) or not isinstance(
                    result.get("hits"), list
                ):
                    raise ValueError("Unexpected HN response schema")
                temporary = cache.with_suffix(".tmp")
                temporary.write_bytes(raw)
                temporary.replace(cache)
                return result
            except HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt:
                    raise
                try:
                    delay = min(30, max(2, float(exc.headers.get("Retry-After", "2"))))
                except ValueError:
                    delay = 2
                time.sleep(delay)
            except (URLError, TimeoutError):
                if attempt:
                    raise
                time.sleep(2)


def ingest_story(hit, category, source="hn"):
    if source == "hn":
        source_id = str(hit.get("objectID", ""))
        if not source_id.isdigit():
            raise ValueError("Invalid HN ID")
        points = hit.get("points")
        comments = hit.get("num_comments", 0)
        created = hit.get("created_at")
        discussion = "https://news.ycombinator.com/item?id=" + source_id
    else:
        source_id = str(hit.get("short_id", ""))
        if not source_id.isalnum() or len(source_id) > 20:
            raise ValueError("Invalid Lobsters ID")
        points = hit.get("score")
        comments = hit.get("comment_count", 0)
        created = hit.get("created_at")
        discussion = "https://lobste.rs/s/" + source_id
    if points is not None and (not isinstance(points, int) or isinstance(points, bool)):
        raise ValueError("Points must be an integer or null")
    if not isinstance(comments, int) or comments < 0:
        raise ValueError("Comment count must be nonnegative")
    title = hit.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Missing title")
    url = canonical_url(hit.get("url"))
    date = parse_datetime(created) if created else None
    if date and timezone.is_naive(date):
        date = timezone.make_aware(date)
    if created and date is None:
        raise ValueError("Invalid submission date")
    if date and date > timezone.now():
        raise ValueError("Submission date is in the future")
    kind = "article"
    if urlsplit(url).hostname in ("arxiv.org", "openreview.net"):
        kind = "paper"
    elif title.lower().startswith(("show hn:", "launch hn:")):
        kind = "tool"
    with transaction.atomic():
        resource, _ = Resource.objects.get_or_create(
            url=url,
            defaults=dict(
                title=title[:400],
                category=category,
                kind=kind,
                description=PLACEHOLDER_DESCRIPTION,
                half_life_days=HALF_LIVES[kind],
                provenance=discussion,
            ),
        )
        Evidence.objects.update_or_create(
            resource=resource,
            source=source,
            source_id=source_id,
            defaults=dict(
                thread_id=source_id,
                discussion_url=discussion,
                title=title[:400],
                points=points,
                comments=comments,
                published_at=date,
            ),
        )
    return resource
