import hashlib
import hmac
import json
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from blog.models import FeedItem, ProductUpdate
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
