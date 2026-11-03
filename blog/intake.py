"""
Single intake pipeline for agent-submitted content.

Every channel (HTTP API, Gmail draft, Django admin) funnels through
``submit_digest``. Agents never publish directly: items land as drafts unless
the target Series has ``auto_publish`` turned on.
"""

import email
import email.header
import email.utils
import hashlib
import imaplib
import logging
import re
import secrets
from datetime import date, datetime

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .briefings import _unwrap_gmail_redirect
from .models import AgentToken, Digest, FeedItem, Series, Tag

logger = logging.getLogger(__name__)

MAX_BODY_CHARS = 200_000
MAX_TITLE_CHARS = 255
MAX_TAGS = 10

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
GMAIL_REDIRECT_RE = re.compile(
    r'https?://(?:www\.)?google\.com/url\?q=([^&"\'\s<>)]+)'
    r"(?:(?:&amp;|&)(?:sa|source|ust|usg|ved)=[A-Za-z0-9_.\-]*)*",
    re.IGNORECASE,
)
PRIVATE_URL_RES = (
    re.compile(r"https?://mail\.google\.com/[^\s\"'<>)]*", re.IGNORECASE),
    re.compile(r"https?://(?:www\.)?readwise\.io/review/[^\s\"'<>)]*", re.IGNORECASE),
    re.compile(
        r"https?://[^\s\"'<>)]*[?&](?:authuser|token|unsubscribe|session_id)=[^\s\"'<>)]*",
        re.IGNORECASE,
    ),
)


class IntakeError(ValueError):
    """Raised for invalid submissions; message is safe to return to the caller."""


# --- tokens ---------------------------------------------------------------


def hash_key(key):
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def create_agent_token(name):
    """Create a token and return (AgentToken, plaintext_key). Key is shown once."""
    key = "wlg_" + secrets.token_urlsafe(32)
    token = AgentToken.objects.create(name=name, prefix=key[:8], key_hash=hash_key(key))
    return token, key


def authenticate_token(key):
    """Return the active AgentToken for a plaintext key, or None."""
    if not key:
        return None
    token = AgentToken.objects.filter(key_hash=hash_key(key), is_active=True).first()
    if token:
        AgentToken.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
    return token


# --- checks ---------------------------------------------------------------


def clean_body(text):
    """Strip Gmail redirect wrappers, private links and email addresses."""
    cleaned = GMAIL_REDIRECT_RE.sub(_unwrap_gmail_redirect, text or "")
    for pattern in PRIVATE_URL_RES:
        cleaned = pattern.sub("", cleaned)
    return EMAIL_RE.sub("", cleaned).strip()


def items_to_markdown(items):
    """Turn [{title, url, summary}] into a markdown list."""
    lines = []
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict) or not item.get("title"):
            raise IntakeError(f"items[{i - 1}] needs a 'title'")
        title = str(item["title"]).strip()
        url = str(item.get("url") or "").strip()
        if url and not re.match(r"^https?://", url, re.IGNORECASE):
            raise IntakeError(f"items[{i - 1}].url must be http(s)")
        heading = f"[{title}]({url})" if url else title
        lines.append(f"{i}. **{heading}**")
        summary = str(item.get("summary") or "").strip()
        if summary:
            lines.append(f"   {summary}")
        lines.append("")
    return "\n".join(lines)


def _parse_date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        raise IntakeError("'date' must be YYYY-MM-DD")


# --- pipeline -------------------------------------------------------------


@transaction.atomic
def submit_digest(
    *,
    series,
    title,
    digest_date,
    body="",
    items=None,
    external_id="",
    tags=None,
    source_url="",
    source="api",
    agent=None,
):
    """
    Validate, clean and upsert a Digest. Returns (digest, created).

    Resubmitting the same (series, external_id) updates the existing item and
    never silently re-publishes something that was a draft.
    """
    if isinstance(series, str):
        series_obj = Series.objects.filter(slug=series, is_active=True).first()
        if not series_obj:
            raise IntakeError(f"unknown or inactive series '{series}'")
    else:
        series_obj = series

    title = (title or "").strip()
    if not title:
        raise IntakeError("'title' is required")
    if len(title) > MAX_TITLE_CHARS:
        raise IntakeError(f"'title' exceeds {MAX_TITLE_CHARS} characters")

    parsed_date = _parse_date(digest_date)

    if items:
        if not isinstance(items, list):
            raise IntakeError("'items' must be a list")
        body = (body + "\n\n" if body else "") + items_to_markdown(items)
    if not (body or "").strip():
        raise IntakeError("provide 'body' or 'items'")
    if len(body) > MAX_BODY_CHARS:
        raise IntakeError(f"content exceeds {MAX_BODY_CHARS} characters")

    if source_url and not re.match(r"^https?://", source_url, re.IGNORECASE):
        raise IntakeError("'source_url' must be http(s)")

    tag_list = [t.strip() for t in (tags or []) if str(t).strip()][:MAX_TAGS]
    external_id = (external_id or parsed_date.isoformat())[:255]
    body = clean_body(body)
    title = clean_body(title)[:MAX_TITLE_CHARS]

    digest = Digest.objects.filter(series=series_obj, external_id=external_id).first()
    created = digest is None
    if created:
        digest = Digest(series=series_obj, external_id=external_id)
    digest.title = title
    digest.digest_date = parsed_date
    digest.body_md = body
    digest.source_url = source_url
    digest.source = source
    digest.agent = agent
    digest.save()

    names = list(dict.fromkeys([series_obj.slug, *tag_list]))
    digest.tags.set([Tag.objects.get_or_create(name=n)[0] for n in names])

    if series_obj.auto_publish and (
        created or digest.status == Digest.STATUS_PUBLISHED
    ):
        publish_digest(digest)
    elif digest.status == Digest.STATUS_PUBLISHED:
        mirror_digest_to_feed(digest)  # keep the feed card in sync with edits
    return digest, created


def _excerpt(md, limit=300):
    text = re.sub(r"[#*_`>\[\]]|\(https?://[^)]*\)", "", md)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def mirror_digest_to_feed(digest):
    """Create or update the Feed card for a published digest."""
    if digest.status != Digest.STATUS_PUBLISHED:
        return None
    url = reverse(
        "blog:digest_detail",
        kwargs={"series_slug": digest.series.slug, "slug": digest.slug},
    )
    body = f"{_excerpt(digest.body_md)}\n\n[Read the full digest →]({url})"
    title = f"{digest.series.name}: {digest.title}"[:200]
    item = digest.mirrored_feed_item
    if item:
        item.title, item.url, item.body, item.content_type = title, url, body, "link"
        item.save()
    else:
        item = FeedItem.objects.create(
            content_type="link", title=title, url=url, body=body
        )
        digest.mirrored_feed_item = item
        digest.save(update_fields=["mirrored_feed_item", "updated_date"])
    item.tags.set(digest.tags.all())
    return item


def publish_digest(digest):
    """Mark a digest published and put a card on the Feed."""
    if digest.status != Digest.STATUS_PUBLISHED or not digest.published_at:
        digest.status = Digest.STATUS_PUBLISHED
        digest.published_at = digest.published_at or timezone.now()
        digest.save(update_fields=["status", "published_at", "updated_date"])
    return mirror_digest_to_feed(digest)


def unpublish_digest(digest):
    """Return a digest to draft and remove its Feed card."""
    item = digest.mirrored_feed_item
    digest.status = Digest.STATUS_DRAFT
    digest.mirrored_feed_item = None
    digest.save(update_fields=["status", "mirrored_feed_item", "updated_date"])
    if item:
        item.delete()


# --- Gmail adapter --------------------------------------------------------

DIGEST_SUBJECT_RE = re.compile(r"\[Digest:\s*([a-z0-9-]+)\]\s*(.*)", re.IGNORECASE)
HEADER_LINE_RE = re.compile(r"^(date|id|url|tags):\s*(.*)$", re.IGNORECASE)


def _plain_text_body(msg):
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if part.get_content_type() == "text/plain":
            payload = part.get_payload(decode=True)
            if payload:
                return payload.decode(part.get_content_charset() or "utf-8", "replace")
    return ""


def parse_digest_email(msg):
    """Return submit_digest kwargs parsed from a '[Digest:slug] Title' draft."""
    subject = str(
        email.header.make_header(email.header.decode_header(msg["Subject"] or ""))
    )
    match = DIGEST_SUBJECT_RE.search(subject)
    if not match:
        return None
    body_lines = _plain_text_body(msg).replace("\r\n", "\n").split("\n")
    meta = {}
    while body_lines and (m := HEADER_LINE_RE.match(body_lines[0].strip())):
        meta[m.group(1).lower()] = m.group(2).strip()
        body_lines.pop(0)
    when = meta.get("date")
    if not when:
        parsed = email.utils.parsedate_to_datetime(msg["Date"]) if msg["Date"] else None
        when = (parsed or timezone.now()).date().isoformat()
    return {
        "series": match.group(1).lower(),
        "title": match.group(2).strip(),
        "digest_date": when,
        "body": "\n".join(body_lines).strip(),
        "external_id": meta.get("id", ""),
        "source_url": meta.get("url", ""),
        "tags": [t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
    }


def sync_digests_from_gmail():
    """
    Pull '[Digest:<series>] Title' drafts from [Gmail]/Drafts only (never INBOX),
    submit them through the same pipeline, and delete drafts that were accepted.
    Rejected drafts are left in place so the problem can be inspected.
    """
    user = getattr(settings, "GMAIL_USER", "").strip()
    password = getattr(settings, "GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not user or not password:
        return {"submitted": 0, "rejected": 0, "checked": False}

    submitted = rejected = 0
    imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    try:
        imap.login(user, password)
        if imap.select('"[Gmail]/Drafts"')[0] == "OK":
            status, data = imap.search(None, '(SUBJECT "[Digest:")')
            for msg_id in (
                data[0].split() if status == "OK" and data and data[0] else []
            ):
                fetched, msg_data = imap.fetch(msg_id, "(RFC822)")
                raw = next(
                    (
                        i[1]
                        for i in msg_data or []
                        if isinstance(i, tuple) and len(i) >= 2
                    ),
                    None,
                )
                if fetched != "OK" or not raw:
                    continue
                msg = email.message_from_bytes(raw)
                sender = email.utils.parseaddr(msg.get("From", ""))[1].lower()
                if sender and sender != user.lower():
                    logger.warning("Skipping digest draft from %s", sender)
                    continue
                try:
                    kwargs = parse_digest_email(msg)
                    if not kwargs:
                        continue
                    submit_digest(source="gmail", **kwargs)
                except IntakeError as exc:
                    rejected += 1
                    logger.warning("Rejected digest draft: %s", exc)
                    continue
                submitted += 1
                imap.store(msg_id, "+FLAGS", "\\Deleted")
            imap.expunge()
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    return {"submitted": submitted, "rejected": rejected, "checked": True}
