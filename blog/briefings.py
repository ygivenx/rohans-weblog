import email
import email.utils
import html
import imaplib
import logging
import re
from datetime import date, datetime
from urllib.parse import unquote

from django.conf import settings
from django.db import transaction
from django.urls import reverse

from .models import DailyBriefing, FeedItem, Tag

logger = logging.getLogger(__name__)


MONTH_DATE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})",
    re.IGNORECASE,
)
ISO_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
EMAIL_ATTR_RE = re.compile(r'\s+title="[^"]*@[^"]*"', re.IGNORECASE)
GMAIL_URL_RE = re.compile(r'https?://mail\.google\.com/[^\s"\'<>]*', re.IGNORECASE)
EMAIL_TEXT_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def _strip_tags(raw_fragment):
    """Strip HTML tags and normalize whitespace."""
    if not raw_fragment:
        return ""
    no_tags = re.sub(r"<[^>]+>", "", raw_fragment)
    return " ".join(html.unescape(no_tags).split())


def parse_briefing_date(raw_html, filename="", fallback_date=None):
    """Extract briefing date from HTML title, masthead, or filename."""
    if isinstance(fallback_date, date):
        return fallback_date
    if isinstance(fallback_date, str) and fallback_date.strip():
        iso_match = ISO_DATE_RE.search(fallback_date.strip())
        if iso_match:
            try:
                return date(
                    int(iso_match.group(1)),
                    int(iso_match.group(2)),
                    int(iso_match.group(3)),
                )
            except ValueError:
                pass

    title_match = re.search(
        r"<title>(.*?)</title>", raw_html or "", re.IGNORECASE | re.DOTALL
    )
    search_targets = []
    if title_match:
        search_targets.append(_strip_tags(title_match.group(1)))

    masthead_match = re.search(
        r'<div class="masthead-meta">(.*?)</div>',
        raw_html or "",
        re.IGNORECASE | re.DOTALL,
    )
    if masthead_match:
        search_targets.append(_strip_tags(masthead_match.group(1)))

    kicker_match = re.search(
        r'<div class="kicker">(.*?)</div>',
        raw_html or "",
        re.IGNORECASE | re.DOTALL,
    )
    if kicker_match:
        search_targets.append(_strip_tags(kicker_match.group(1)))

    if filename:
        search_targets.append(filename.replace("_", " ").replace("-", " "))

    for target in search_targets:
        m = MONTH_DATE_RE.search(target)
        if m:
            try:
                dt = datetime.strptime(
                    f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y"
                )
                return dt.date()
            except ValueError:
                pass
        iso = ISO_DATE_RE.search(target)
        if iso:
            try:
                return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
            except ValueError:
                pass

    return date.today()


def extract_briefing_metadata(raw_html, briefing_date=None, filename=""):
    """Extract structured metadata (title, date, counts, summary, metrics) from raw HTML."""
    parsed_date = parse_briefing_date(
        raw_html, filename=filename, fallback_date=briefing_date
    )

    title_match = re.search(
        r"<title>(.*?)</title>", raw_html or "", re.IGNORECASE | re.DOTALL
    )
    title = (
        _strip_tags(title_match.group(1))
        if title_match
        else f"Daily Intelligence Briefing • {parsed_date.strftime('%B %d, %Y')}"
    )

    # Extract edition meta (e.g., "Vol. XLIV • No. 304")
    edition_meta = ""
    masthead_spans = re.findall(
        r'<div class="masthead-meta">.*?<span>(.*?)</span>\s*<span>(.*?)</span>\s*<span>(.*?)</span>',
        raw_html or "",
        re.IGNORECASE | re.DOTALL,
    )
    if masthead_spans:
        edition_meta = _strip_tags(masthead_spans[0][1])
    else:
        vol_match = re.search(
            r"(Vol\.[A-Za-z0-9\s•·.\-]+No\.\s*\d+)",
            raw_html or "",
            re.IGNORECASE,
        )
        if vol_match:
            edition_meta = _strip_tags(vol_match.group(1))

    # Extract signal count (supports both static <article class="briefing-card"> and JS-rendered ITEMS)
    card_ids = re.findall(
        r'<article[^>]+class="[^"]*briefing-card[^"]*"',
        raw_html or "",
        re.IGNORECASE,
    )
    signal_count = len(card_ids)
    if not signal_count:
        for pattern in (
            r'<div class="badge-processed">\s*<strong>(\d+)</strong>',
            r"(\d+)\s+Synthesized Briefings",
            r">All\s*\((\d+)\)<",
        ):
            m_count = re.search(pattern, raw_html or "", re.IGNORECASE | re.DOTALL)
            if m_count:
                signal_count = int(m_count.group(1))
                break

    # Extract 3-bullet executive summary
    signal_items = re.findall(
        r'<div class="signal-item">\s*<div class="signal-label">(.*?)</div>\s*<div class="signal-text">(.*?)</div>\s*</div>',
        raw_html or "",
        re.IGNORECASE | re.DOTALL,
    )
    summary_lines = []
    for label_raw, text_raw in signal_items:
        label = _strip_tags(label_raw)
        text = _strip_tags(text_raw)
        if label and text:
            # Escape currency/ticker $ signs so MathJax does not treat "$40B ... $25B" as LaTeX math
            safe_label = re.sub(r"\$(?=[0-9A-Za-z])", r"\\$", label)
            safe_text = re.sub(r"\$(?=[0-9A-Za-z])", r"\\$", text)
            summary_lines.append(f"- **{safe_label}** — {safe_text}")
    executive_summary_md = "\n\n".join(summary_lines)

    # Extract metric cards
    metric_cards = re.findall(
        r'<div class="metric-card[^"]*">\s*<div class="metric-value">(.*?)</div>\s*<div class="metric-desc">(.*?)</div>\s*</div>',
        raw_html or "",
        re.IGNORECASE | re.DOTALL,
    )
    metrics_json = []
    for val_raw, desc_raw in metric_cards:
        val = _strip_tags(val_raw)
        desc = _strip_tags(desc_raw)
        if val or desc:
            metrics_json.append({"value": val, "desc": desc})

    return {
        "title": title,
        "briefing_date": parsed_date,
        "edition_meta": edition_meta,
        "signal_count": signal_count,
        "executive_summary_md": executive_summary_md,
        "metrics_json": metrics_json,
    }


def _clean_ledger_row(match):
    """Sanitize a single <tr>...</tr> row inside the Verification Ledger tbody."""
    row_html = match.group(0)
    num_match = re.search(r'<td class="ledger-num">(\d+)</td>', row_html)
    row_num = num_match.group(1) if num_match else "1"

    # 1. Remove sender email span
    row_html = re.sub(
        r'\s*<span class="ledger-sender-email">.*?</span>',
        "",
        row_html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # 2. Rewrite subject cell link from mail.google.com to #card-<row_num>
    row_html = re.sub(
        r'<a\s+href="https?://mail\.google\.com/[^"]*"\s+target="_blank"\s+rel="noopener noreferrer"\s+class="ledger-link">',
        f'<a href="#card-{row_num}" class="ledger-link">',
        row_html,
        flags=re.IGNORECASE,
    )

    # 3. Clean verification cell: remove "View Email" link & pipe separator
    row_html = re.sub(
        r'<a\s+href="https?://mail\.google\.com/[^"]*"[^>]*class="ledger-verify-btn"[^>]*>\s*View Email[^<]*</a>\s*\|\s*',
        "",
        row_html,
        flags=re.IGNORECASE,
    )

    # 4. If the remaining Web link also points to mail.google.com, point it to #card-<row_num>
    row_html = re.sub(
        r'<a\s+href="https?://mail\.google\.com/[^"]*"[^>]*class="ledger-verify-btn"[^>]*>\s*Web[^<]*</a>',
        f'<a href="#card-{row_num}" class="ledger-verify-btn">Card #{row_num} ↑</a>',
        row_html,
        flags=re.IGNORECASE,
    )

    return row_html


def _unwrap_gmail_redirect(match):
    """
    Unwrap Gmail redirect links (https://www.google.com/url?q=...) injected when Gmail
    saves a draft. Also restores bare JS identifiers like card.id or DAIR.AI that Gmail
    mistakenly prefixed with http://.
    """
    raw_q = html.unescape(match.group(1))
    decoded = unquote(raw_q)
    # If Gmail turned a bare token like card.id or DAIR.AI into http://card.id (no slash after host)
    bare_match = re.match(r"^http://([A-Za-z0-9_-]+\.[A-Za-z]{2,4})$", decoded)
    if bare_match and not decoded.lower().startswith("http://www."):
        return bare_match.group(1)
    return decoded


def sanitize_briefing_html(raw_html):
    """
    Sanitize a Daily Intelligence Briefing HTML artifact for public publishing:
    - Unwrap Gmail redirect URLs (https://www.google.com/url?q=...) and restore JS identifiers like card.id
    - Strip all private Gmail links (mail.google.com), Readwise private review links, and email addresses
    - Replace location with 'Generated with ❤️ from Seattle, WA'
    - Inject Rohan Singh's Weblog top navigation bar, branding, and 1-click Share buttons
    """
    cleaned = raw_html or ""

    # 0. Unwrap Gmail redirect URLs (https://www.google.com/url?q=...)
    cleaned = re.sub(
        r'https?://(?:www\.)?google\.com/url\?q=([^&"\'\s<>]+)'
        r"(?:(?:&amp;|&)(?:sa|source|ust|usg|ved)=[A-Za-z0-9_.\-]*)*",
        _unwrap_gmail_redirect,
        cleaned,
        flags=re.IGNORECASE,
    )
    # Strip private account/investor/review URLs (Readwise, InvPortal, Fundrise, etc.)
    for private_pattern in (
        r'https?://(?:www\.)?readwise\.io/review/[^\s"\'<>]*',
        r'https?://[^\s"\'<>]*invportal\.com[^\s"\'<>]*',
        r'https?://(?:www\.)?fundrise\.com/property-update/[^\s"\'<>]*',
        r'https?://[^\s"\'<>]*[?&](?:authuser|token|unsubscribe|session_id)=[^\s"\'<>]*',
    ):
        cleaned = re.sub(private_pattern, "#", cleaned, flags=re.IGNORECASE)

    # In JS-rendered card templates, avoid rendering dead href="#" links
    cleaned = cleaned.replace(
        '<a href="${it[5]}" target="_blank" rel="noopener noreferrer">Open Primary Source ↗</a>',
        '${it[5] && it[5] !== "#" ? `<a href="${it[5]}" target="_blank" rel="noopener noreferrer">Open Primary Source ↗</a>` : `<span style="color:var(--muted)">Curated Dispatch</span>`}',
    )

    # 1. Strip email addresses in title="..." attributes (e.g. .card-source-badge)
    cleaned = EMAIL_ATTR_RE.sub("", cleaned)

    # 2. Remove .card-gmail-link buttons ("✉️ Email ↗")
    cleaned = re.sub(
        r'\s*<a\s+[^>]*class="card-gmail-link"[^>]*>.*?</a>',
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # 3. Replace primary .card-link anchors that point to mail.google.com with a clean label
    cleaned = re.sub(
        r'<a\s+href="https?://mail\.google\.com/[^"]*"[^>]*class="card-link"[^>]*>(.*?)</a>',
        r'<span class="card-time">Curated Dispatch</span>',
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # 4. Add a 1-click "🔗 Share" button next to every card's "🔊 Listen" button
    cleaned = re.sub(
        r'(<button\s+type="button"\s+class="card-listen-btn"\s+data-listen-card="(card-\d+)"[^>]*>.*?</button>)',
        r'\1\n<button type="button" class="card-listen-btn card-share-btn" data-share-card="\2" title="Copy direct link &amp; takeaway for this signal">🔗 Share</button>',
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # 5. Clean the Verification Ledger headers, subtitle, and rows
    cleaned = cleaned.replace(
        "<th>Publication &amp; Sender</th>", "<th>Publication</th>"
    )
    cleaned = cleaned.replace(
        "<th>Synthesized Headline &amp; Thread Link</th>",
        "<th>Synthesized Headline</th>",
    )
    cleaned = cleaned.replace("<th>Verification</th>", "<th>Source</th>")
    cleaned = re.sub(
        r'<p class="ledger-sub">.*?</p>',
        '<p class="ledger-sub">Every synthesized briefing card above is grounded in a curated dispatch. Click any headline to jump to its synthesis card or open the original publisher source.</p>',
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Clean each row inside <tbody>...</tbody>
    tbody_match = re.search(
        r"(<tbody>)(.*?)(</tbody>)", cleaned, flags=re.IGNORECASE | re.DOTALL
    )
    if tbody_match:
        tbody_cleaned = re.sub(
            r"<tr>.*?</tr>",
            _clean_ledger_row,
            tbody_match.group(2),
            flags=re.IGNORECASE | re.DOTALL,
        )
        cleaned = (
            cleaned[: tbody_match.start(2)]
            + tbody_cleaned
            + cleaned[tbody_match.end(2) :]
        )

    # 6. Strip any remaining sender email spans or Gmail URLs anywhere in the document
    cleaned = re.sub(
        r'\s*<span class="ledger-sender-email">.*?</span>',
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = GMAIL_URL_RE.sub("#", cleaned)
    cleaned = EMAIL_TEXT_RE.sub("", cleaned)

    # 7. Brand the Masthead & Footer and replace location with "Generated with ❤️ from Seattle, WA"
    cleaned = re.sub(
        r"<span>\s*The Daily Intelligence Desk\s*</span>",
        "<span>Rohan Singh • Daily Intelligence Desk</span>",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r'<div class="footer-title">.*?</div>',
        '<div class="footer-title">Rohan Singh • The Daily Intelligence Desk</div>',
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(
        r'<p class="footer-text">.*?</p>',
        '<p class="footer-text">Published daily on <a href="/" style="color: inherit; text-decoration: underline;">rohansweblog.com</a> by Rohan Singh\'s autonomous Gemini intelligence agent. Strict editorial separation of frontier AI breakthroughs, capital catalysts, operational systems, and macro intelligence.</p>',
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Replace city/location in footer-copy (e.g., "Sammamish, Washington") with "Generated with ❤️ from Seattle, WA"
    def _replace_footer_copy(m):
        inner = m.group(1)
        if "Sammamish" in inner:
            inner = re.sub(
                r"Sammamish,\s*Washington",
                "Generated with ❤️ from Seattle, WA",
                inner,
                flags=re.IGNORECASE,
            )
        elif "Generated with" not in inner:
            parts = [p.strip() for p in inner.split("•") if p.strip()]
            if len(parts) >= 3:
                parts[-2] = "Generated with ❤️ from Seattle, WA"
                inner = " • ".join(parts)
            else:
                inner = f"{inner} • Generated with ❤️ from Seattle, WA"
        return f'<p class="footer-copy">{inner}</p>'

    cleaned = re.sub(
        r'<p class="footer-copy">(.*?)</p>',
        _replace_footer_copy,
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(
        r"Sammamish,\s*Washington",
        "Generated with ❤️ from Seattle, WA",
        cleaned,
        flags=re.IGNORECASE,
    )

    # 8. Strip any legacy inline top-ribbon (rendered outside the sandboxed iframe in briefing_viewer.html)
    cleaned = re.sub(
        r"/\* Rohan's Weblog Integration Ribbon \*/[\s\S]*?\.weblog-ribbon-badge\s*\{[^}]*\}\s*",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r'<div class="weblog-top-ribbon"[\s\S]*?</div>\s*</div>\s*</div>\s*',
        "",
        cleaned,
    )

    share_script = """
<script>
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.card-share-btn').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            var cardId = this.getAttribute('data-share-card');
            var card = document.getElementById(cardId);
            if (!card) return;
            var headline = (card.querySelector('.card-headline') || {}).textContent || '';
            var why = (card.querySelector('.why-matters-text') || {}).textContent || '';
            var baseUrl = (window.parent && window.parent.location) ? (window.parent.location.origin + window.parent.location.pathname) : '';
            var shareUrl = (baseUrl || 'https://rohansweblog.com/briefings/') + '#' + cardId;
            var payload = headline.trim() + (why ? '\\n\\nWhy It Matters: ' + why.trim() : '') + '\\n\\n' + shareUrl;
            var self = this;
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(payload).then(function() {
                    self.textContent = '✓ Copied';
                    setTimeout(function() { self.textContent = '🔗 Share'; }, 1400);
                });
            }
        });
    });
});
</script>
"""
    if "card-share-btn" in cleaned and "navigator.clipboard" not in cleaned:
        cleaned = cleaned.replace("</body>", share_script + "\n</body>", 1)

    return cleaned


def _feed_payload_for_briefing(briefing):
    """Build FeedItem title, url, and markdown body for a DailyBriefing."""
    url = reverse("blog:briefing_detail", kwargs={"slug": briefing.slug})
    date_label = briefing.briefing_date.strftime("%b %d, %Y")
    signal_suffix = (
        f" ({briefing.signal_count} Signals)" if briefing.signal_count else ""
    )
    title = f"Daily Intelligence Briefing — {date_label}{signal_suffix}"

    lines = [
        f"🎙️ **[Open Interactive Briefing & Voice Studio →]({url})**",
        "",
    ]
    if briefing.metrics_json:
        top_metrics = briefing.metrics_json[:3]
        metric_parts = [
            f"`{m.get('value')}` {m.get('desc')}"
            for m in top_metrics
            if m.get("value") and m.get("desc")
        ]
        if metric_parts:
            lines.append("**Key Metrics:** " + " · ".join(metric_parts))
            lines.append("")

    if briefing.executive_summary_md:
        lines.append(briefing.executive_summary_md)
        lines.append("")

    lines.append(
        "*Generated with ❤️ from Seattle, WA · [Always-On Latest Briefing](/briefing/) · [Archive](/briefings/)*"
    )
    return {
        "title": title,
        "url": url,
        "body": "\n".join(lines),
    }


def mirror_briefing_to_feed(briefing):
    """Create or update mirrored FeedItem on the main tumblelog feed."""
    if not getattr(settings, "BRIEFINGS_FEED_MIRROR", True):
        return None
    if not briefing.is_published:
        return None

    payload = _feed_payload_for_briefing(briefing)

    if briefing.mirrored_feed_item_id:
        item = briefing.mirrored_feed_item
        item.content_type = "link"
        item.title = payload["title"]
        item.url = payload["url"]
        item.body = payload["body"]
        item.save()
    else:
        item = FeedItem.objects.create(
            content_type="link",
            title=payload["title"],
            url=payload["url"],
            body=payload["body"],
        )
        briefing.mirrored_feed_item = item
        briefing.save(update_fields=["mirrored_feed_item", "updated_date"])

    tag_names = ["briefing", "ai", "markets"]
    tags = []
    for name in tag_names:
        tag, _ = Tag.objects.get_or_create(name=name)
        tags.append(tag)
    item.tags.set(tags)
    briefing.tags.set(tags)
    return item


@transaction.atomic
def ingest_briefing_html(raw_html, briefing_date=None, filename="", is_published=True):
    """
    Parse, sanitize, and upsert a DailyBriefing record from a Gemini HTML artifact,
    and mirror its executive summary to the main Feed.
    """
    # Unwrap <!DOCTYPE html>...</html> if wrapped in markdown fences or Gmail draft text
    doctype_match = re.search(
        r"<!DOCTYPE\s+html>[\s\S]*</html>", raw_html or "", re.IGNORECASE
    )
    if doctype_match:
        raw_html = doctype_match.group(0)

    meta = extract_briefing_metadata(
        raw_html, briefing_date=briefing_date, filename=filename
    )
    sanitized = sanitize_briefing_html(raw_html)
    parsed_date = meta["briefing_date"]
    slug = parsed_date.isoformat()

    briefing, created = DailyBriefing.objects.update_or_create(
        briefing_date=parsed_date,
        defaults={
            "title": meta["title"],
            "slug": slug,
            "edition_meta": meta["edition_meta"],
            "signal_count": meta["signal_count"],
            "executive_summary_md": meta["executive_summary_md"],
            "metrics_json": meta["metrics_json"],
            "sanitized_html": sanitized,
            "is_published": is_published,
        },
    )

    mirror_briefing_to_feed(briefing)
    return briefing, created


def _extract_html_from_email_message(msg):
    """
    Extract raw <!DOCTYPE html>...</html> from a parsed email.message.Message.
    Handles both text/plain and HTML-escaped text/html Gmail draft bodies.
    """
    candidates = []
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type in ("text/plain", "text/html"):
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    text = payload.decode(charset, errors="replace")
                    if content_type == "text/plain":
                        candidates.insert(0, text)
                    else:
                        candidates.append(text)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            candidates.append(payload.decode(charset, errors="replace"))

    for raw in candidates:
        match = re.search(r"<!DOCTYPE\s+html>[\s\S]*</html>", raw, re.IGNORECASE)
        if match:
            return match.group(0)
        # In case Gmail rich-text draft escaped the HTML tags (&lt;!DOCTYPE html&gt;)
        unescaped = html.unescape(re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE))
        unescaped = re.sub(r"</?(div|p)[^>]*>", "\n", unescaped, flags=re.IGNORECASE)
        unescaped = html.unescape(unescaped)
        match = re.search(r"<!DOCTYPE\s+html>[\s\S]*</html>", unescaped, re.IGNORECASE)
        if match:
            return match.group(0)

    return None


def sync_briefing_from_gmail():
    """
    Connect to Gmail via IMAP using GMAIL_USER and GMAIL_APP_PASSWORD,
    search ONLY [Gmail]/Drafts for BRIEFING_EMAIL_SUBJECT (never INBOX, preventing
    external sender spoofing), verify sender matches GMAIL_USER if present,
    ingest any matching HTML briefing, and delete the processed draft.
    """
    gmail_user = getattr(settings, "GMAIL_USER", "").strip()
    gmail_password = (
        getattr(settings, "GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    )
    subject_filter = getattr(
        settings, "BRIEFING_EMAIL_SUBJECT", "BRIEFING_AUTO_PUBLISH"
    ).strip()

    if not gmail_user or not gmail_password:
        return {"created": 0, "updated": 0, "checked": False}

    created_count = 0
    updated_count = 0

    imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    try:
        imap.login(gmail_user, gmail_password)
        status, _ = imap.select('"[Gmail]/Drafts"')
        if status == "OK":
            status, data = imap.search(None, f'(SUBJECT "{subject_filter}")')
            if status == "OK" and data and data[0]:
                msg_ids = data[0].split()
                for msg_id in msg_ids:
                    fetch_status, msg_data = imap.fetch(msg_id, "(RFC822)")
                    if fetch_status != "OK" or not msg_data:
                        continue

                    raw_bytes = None
                    for item in msg_data:
                        if isinstance(item, tuple) and len(item) >= 2:
                            raw_bytes = item[1]
                            break
                    if not raw_bytes:
                        continue

                    msg = email.message_from_bytes(raw_bytes)
                    sender_addr = email.utils.parseaddr(msg.get("From", ""))[1].lower()
                    if sender_addr and sender_addr != gmail_user.lower():
                        logger.warning(
                            "Skipping draft with mismatched From address: %s",
                            sender_addr,
                        )
                        continue

                    extracted_html = _extract_html_from_email_message(msg)
                    if not extracted_html:
                        continue

                    _, created = ingest_briefing_html(extracted_html)
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

                    # Delete processed draft so it is not re-processed
                    imap.store(msg_id, "+FLAGS", "\\Deleted")

                imap.expunge()
    finally:
        try:
            imap.logout()
        except Exception:
            pass

    return {"created": created_count, "updated": updated_count, "checked": True}
