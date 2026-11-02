import email.message
import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from blog.briefings import ingest_briefing_html, sync_briefing_from_gmail
from blog.models import DailyBriefing, FeedItem, ProductUpdate
from blog.product_updates import sync_gumroad_products

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def _github_sig(secret, body_bytes):
    digest = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@override_settings(
    GITHUB_WEBHOOK_SECRET="test-secret",
    GITHUB_OWNER="acme",
    PRODUCTS_FEED_MIRROR=True,
    STORAGES=TEST_STORAGES,
)
class GitHubWebhookTests(TestCase):
    def _payload(self):
        return {
            "action": "published",
            "repository": {
                "name": "ml-platform",
                "owner": {"login": "acme"},
                "html_url": "https://github.com/acme/ml-platform",
            },
            "release": {
                "id": 12345,
                "name": "v1.2.3",
                "tag_name": "v1.2.3",
                "body": "Fixes and improvements.",
                "html_url": "https://github.com/acme/ml-platform/releases/tag/v1.2.3",
                "published_at": "2026-03-08T20:00:00Z",
            },
        }

    def test_github_webhook_creates_product_update_and_feed_item(self):
        payload = self._payload()
        body = json.dumps(payload).encode("utf-8")
        response = self.client.post(
            reverse("blog:github_webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="release",
            HTTP_X_HUB_SIGNATURE_256=_github_sig("test-secret", body),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProductUpdate.objects.count(), 1)
        self.assertEqual(FeedItem.objects.count(), 1)

        update = ProductUpdate.objects.get()
        self.assertEqual(update.source, "github")
        self.assertEqual(update.repo, "ml-platform")
        self.assertIsNotNone(update.mirrored_feed_item)

    def test_github_webhook_is_idempotent_for_same_release(self):
        payload = self._payload()
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "content_type": "application/json",
            "HTTP_X_GITHUB_EVENT": "release",
            "HTTP_X_HUB_SIGNATURE_256": _github_sig("test-secret", body),
        }

        self.client.post(reverse("blog:github_webhook"), data=body, **headers)
        self.client.post(reverse("blog:github_webhook"), data=body, **headers)

        self.assertEqual(ProductUpdate.objects.count(), 1)
        self.assertEqual(FeedItem.objects.count(), 1)

    def test_github_webhook_rejects_bad_signature(self):
        payload = self._payload()
        body = json.dumps(payload).encode("utf-8")
        response = self.client.post(
            reverse("blog:github_webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="release",
            HTTP_X_HUB_SIGNATURE_256="sha256=bad",
        )
        self.assertEqual(response.status_code, 403)


@override_settings(
    GUMROAD_ACCESS_TOKEN="gum-token",
    PRODUCTS_FEED_MIRROR=True,
    STORAGES=TEST_STORAGES,
)
class GumroadSyncTests(TestCase):
    @patch("blog.product_updates._fetch_gumroad_products")
    def test_sync_gumroad_products_creates_updates_and_feed_items(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "id": "prod_1",
                "name": "Clinical Trial AI Starter",
                "description": "Templates and workflows for AI-enabled clinical trial ops.",
                "short_url": "https://gum.co/ctaistarter",
                "currency": "usd",
                "price": 4900,
                "published": True,
                "published_at": "2026-03-01T10:00:00Z",
            }
        ]

        stats = sync_gumroad_products()

        self.assertEqual(stats["created"], 1)
        self.assertEqual(ProductUpdate.objects.count(), 1)
        self.assertEqual(FeedItem.objects.count(), 1)
        update = ProductUpdate.objects.get()
        self.assertEqual(update.source, "gumroad")
        self.assertIn("USD", update.price)

    @patch("blog.product_updates._fetch_gumroad_products")
    def test_sync_command_runs(self, mock_fetch):
        mock_fetch.return_value = []
        call_command("sync_gumroad_products")
        self.assertEqual(ProductUpdate.objects.count(), 0)


@override_settings(STORAGES=TEST_STORAGES)
class ProductsPageTests(TestCase):
    def test_products_page_renders(self):
        ProductUpdate.objects.create(
            source="github",
            kind="release",
            external_id="r1",
            title="v0.1.0",
            summary="First release",
            url="https://github.com/acme/repo/releases/tag/v0.1.0",
            owner="acme",
            repo="repo",
            version="v0.1.0",
        )
        ProductUpdate.objects.create(
            source="gumroad",
            kind="product",
            external_id="g1",
            title="AI Health Toolkit",
            summary="A practical toolkit",
            url="https://gum.co/toolkit",
            price="USD 49.00",
        )

        response = self.client.get(reverse("blog:products_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "GitHub Releases")
        self.assertContains(response, "Gumroad Products")


SAMPLE_BRIEFING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<title>Daily Intelligence Briefing • October 31, 2026</title>
<style>body { color: #111; }</style>
</head>
<body>
<header class="masthead">
<div class="masthead-meta">
<span>The Daily Intelligence Desk</span>
<span>Vol. XLIV • No. 304</span>
<span>Saturday, October 31, 2026</span>
</div>
</header>
<div class="signal-grid" id="execSummaryGrid">
<div class="signal-item">
<div class="signal-label">Genie 4 World Model</div>
<div class="signal-text">Google debuts Genie 4 and boots orbital TPUs.</div>
</div>
</div>
<div class="metric-strip">
<div class="metric-card accent-blue">
<div class="metric-value">92% vs. 21.3%</div>
<div class="metric-desc">API gross margin vs sub break-even</div>
</div>
</div>
<article class="briefing-card" id="card-1" data-section-name="Priority 1">
<div>
<span class="card-source-badge" title="lspace@mail.beehiiv.com">AINews</span>
<button type="button" class="card-listen-btn" data-listen-card="card-1">🔊 Listen</button>
<h3 class="card-headline">Anthropic Launches Claude Ultra</h3>
<p class="card-synthesis">Synthesis text.</p>
<div class="why-matters-box"><span class="why-matters-text">Unit economics matter.</span></div>
</div>
<div class="card-footer">
<a href="https://www.google.com/url?q=https://readwise.io/review/rohan9/123&amp;source=gmail" class="card-link">Read →</a>
<a href="https://mail.google.com/mail/?authuser=rohanmyself@gmail.com#all/thread-f:123" class="card-gmail-link">✉️ Email ↗</a>
</div>
</article>
<script>https://www.google.com/url?q=http://card.id&source=gmail = "card-1";</script>
<table>
<tbody>
<tr>
<td class="ledger-num">1</td>
<td><span class="ledger-pub-name">AINews</span><span class="ledger-sender-email">lspace@mail.beehiiv.com</span></td>
<td class="ledger-subject-cell"><a href="https://mail.google.com/mail/?authuser=rohanmyself@gmail.com#all/thread-f:123" target="_blank" rel="noopener noreferrer" class="ledger-link">Headline 1</a></td>
<td><a href="https://mail.google.com/mail/?authuser=rohanmyself@gmail.com#all/thread-f:123" class="ledger-verify-btn">View Email ↗</a> | <a href="https://x.com/claudeai/status/1" class="ledger-verify-btn">Web ↗</a></td>
</tr>
</tbody>
</table>
<footer class="footer">
<div class="footer-title">The Daily Intelligence Desk</div>
<p class="footer-text">Original footer text.</p>
<p class="footer-copy">Volume XLIV • Edition 302 • Sammamish, Washington • Saturday, October 31, 2026</p>
</footer>
</body>
</html>"""


@override_settings(
    GMAIL_USER="rohanmyself@gmail.com",
    GMAIL_APP_PASSWORD="app-password-16ch",
    BRIEFINGS_FEED_MIRROR=True,
    STORAGES=TEST_STORAGES,
)
class DailyBriefingTests(TestCase):
    def test_ingest_strips_emails_and_replaces_location(self):
        briefing, created = ingest_briefing_html(SAMPLE_BRIEFING_HTML)
        self.assertTrue(created)
        self.assertEqual(briefing.slug, "2026-10-31")
        self.assertEqual(briefing.signal_count, 1)
        self.assertNotIn("rohanmyself", briefing.sanitized_html)
        self.assertNotIn("mail.google.com", briefing.sanitized_html)
        self.assertNotIn("google.com/url", briefing.sanitized_html)
        self.assertNotIn("readwise.io/review", briefing.sanitized_html)
        self.assertIn('card.id = "card-1";', briefing.sanitized_html)
        self.assertNotIn("lspace@mail.beehiiv.com", briefing.sanitized_html)
        self.assertNotIn("Sammamish", briefing.sanitized_html)
        self.assertIn("Generated with ❤️ from Seattle, WA", briefing.sanitized_html)
        self.assertIn("card-share-btn", briefing.sanitized_html)
        self.assertIsNotNone(briefing.mirrored_feed_item)

    @patch("blog.briefings.imaplib.IMAP4_SSL")
    def test_sync_briefing_from_gmail_and_routes(self, mock_imap_cls):
        msg = email.message.EmailMessage()
        msg["Subject"] = "BRIEFING_AUTO_PUBLISH"
        msg["From"] = "rohanmyself@gmail.com"
        msg["To"] = "rohanmyself@gmail.com"
        msg.set_content(f"```html\n{SAMPLE_BRIEFING_HTML}\n```")
        raw_bytes = msg.as_bytes()

        mock_imap = MagicMock()
        mock_imap_cls.return_value = mock_imap
        mock_imap.select.return_value = ("OK", [b"1"])
        mock_imap.search.return_value = ("OK", [b"1"])
        mock_imap.fetch.return_value = ("OK", [(b"1 (RFC822)", raw_bytes)])

        stats = sync_briefing_from_gmail()
        self.assertEqual(stats["created"], 1)
        self.assertEqual(DailyBriefing.objects.count(), 1)
        mock_imap.select.assert_called_once_with('"[Gmail]/Drafts"')
        mock_imap.store.assert_called_once_with(b"1", "+FLAGS", "\\Deleted")

        list_resp = self.client.get(reverse("blog:briefing_list"))
        self.assertEqual(list_resp.status_code, 200)
        self.assertContains(list_resp, "Daily Intelligence Briefing")
        self.assertContains(list_resp, "Generated with ❤️ from Seattle, WA")
        self.assertContains(
            list_resp,
            'sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"',
        )
        self.assertNotContains(list_resp, "allow-same-origin")

        archive_resp = self.client.get(reverse("blog:briefing_archive"))
        self.assertEqual(archive_resp.status_code, 200)
        self.assertContains(archive_resp, "Daily Intelligence Briefing")

        latest_resp = self.client.get(reverse("blog:briefing_latest"))
        self.assertEqual(latest_resp.status_code, 200)
        self.assertContains(latest_resp, "Generated with ❤️ from Seattle, WA")

        rss_resp = self.client.get(reverse("blog:briefing_rss"))
        self.assertEqual(rss_resp.status_code, 200)
        self.assertIn("application/rss+xml", rss_resp["Content-Type"])
