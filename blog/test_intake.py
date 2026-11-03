import email.message
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from blog.intake import (
    IntakeError,
    authenticate_token,
    create_agent_token,
    parse_digest_email,
    publish_digest,
    submit_digest,
    unpublish_digest,
)
from blog.models import AgentToken, Digest, FeedItem, Series

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=TEST_STORAGES)
class IntakeTestBase(TestCase):
    def setUp(self):
        self.series = Series.objects.create(
            slug="github-trending", name="GitHub Trending"
        )
        self.agent, self.key = create_agent_token("Muse")

    def post(self, payload, key=None):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {key or self.key}"}
        return self.client.post(
            reverse("blog:intake_api"),
            data=json.dumps(payload),
            content_type="application/json",
            **headers,
        )

    def payload(self, **over):
        data = {
            "series": "github-trending",
            "title": "Week 45",
            "date": "2026-11-06",
            "items": [
                {"title": "repo/a", "url": "https://github.com/a/a", "summary": "hot"}
            ],
        }
        data.update(over)
        return data


class TokenTests(IntakeTestBase):
    def test_only_hash_is_stored_and_auth_works(self):
        self.assertNotIn(self.key, self.agent.key_hash)
        self.assertEqual(authenticate_token(self.key), self.agent)
        self.assertIsNone(authenticate_token("wlg_wrong"))

    def test_revoked_token_rejected(self):
        AgentToken.objects.filter(pk=self.agent.pk).update(is_active=False)
        self.assertEqual(self.post(self.payload()).status_code, 401)


class ApiTests(IntakeTestBase):
    def test_requires_token_and_post(self):
        resp = self.client.post(
            reverse("blog:intake_api"), data="{}", content_type="application/json"
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(self.client.get(reverse("blog:intake_api")).status_code, 405)

    def test_lands_as_draft_with_provenance(self):
        resp = self.post(self.payload())
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["status"], "draft")
        digest = Digest.objects.get()
        self.assertEqual((digest.source, digest.agent), ("api", self.agent))
        self.assertFalse(FeedItem.objects.exists())
        self.assertIn("[repo/a](https://github.com/a/a)", digest.body_md)

    def test_draft_is_not_public(self):
        self.post(self.payload())
        digest = Digest.objects.get()
        self.assertEqual(self.client.get(digest.get_absolute_url()).status_code, 404)

    def test_resubmission_updates_same_item(self):
        self.post(self.payload(external_id="w45"))
        resp = self.post(self.payload(external_id="w45", title="Week 45 v2"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Digest.objects.count(), 1)
        self.assertEqual(Digest.objects.get().title, "Week 45 v2")

    def test_validation_errors(self):
        for bad in (
            self.payload(series="nope"),
            self.payload(title=""),
            self.payload(date="yesterday"),
            self.payload(items=None, body=""),
            self.payload(items=[{"url": "https://x.y"}]),
            self.payload(items=[{"title": "t", "url": "javascript:alert(1)"}]),
        ):
            self.assertEqual(self.post(bad).status_code, 400, bad)
        self.assertFalse(Digest.objects.exists())

    def test_inactive_series_rejected(self):
        Series.objects.update(is_active=False)
        self.assertEqual(self.post(self.payload()).status_code, 400)

    def test_bad_json(self):
        resp = self.client.post(
            reverse("blog:intake_api"),
            data="not json",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.key}",
        )
        self.assertEqual(resp.status_code, 400)


class PipelineTests(IntakeTestBase):
    def test_cleaning_strips_private_links_and_emails(self):
        body = (
            "Mail me at rohan@example.com\n"
            "[x](https://www.google.com/url?q=https://real.example/a&sa=D&usg=AOv_1)\n"
            "[y](https://mail.google.com/mail/u/0/#inbox/abc)"
        )
        digest, _ = submit_digest(
            series=self.series, title="t", digest_date="2026-11-06", body=body
        )
        self.assertNotIn("rohan@example.com", digest.body_md)
        self.assertNotIn("mail.google.com", digest.body_md)
        self.assertIn("(https://real.example/a)", digest.body_md)

    def test_body_markdown_is_sanitized_on_render(self):
        digest, _ = submit_digest(
            series=self.series,
            title="t",
            digest_date="2026-11-06",
            body="<script>alert(1)</script>hello",
        )
        publish_digest(digest)
        page = self.client.get(digest.get_absolute_url())
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "<script>alert(1)</script>")

    def test_same_date_different_external_id_gets_unique_slug(self):
        a, _ = submit_digest(
            series=self.series,
            title="a",
            digest_date="2026-11-06",
            body="x",
            external_id="1",
        )
        b, _ = submit_digest(
            series=self.series,
            title="b",
            digest_date="2026-11-06",
            body="y",
            external_id="2",
        )
        self.assertNotEqual(a.slug, b.slug)

    def test_auto_publish_series_publishes_and_mirrors(self):
        Series.objects.update(auto_publish=True)
        digest, _ = submit_digest(
            series="github-trending", title="t", digest_date="2026-11-06", body="hello"
        )
        self.assertEqual(digest.status, "published")
        self.assertEqual(FeedItem.objects.count(), 1)
        self.assertEqual(self.client.get(digest.get_absolute_url()).status_code, 200)

    def test_resubmit_never_republishes_an_unpublished_draft(self):
        Series.objects.update(auto_publish=True)
        d, _ = submit_digest(
            series="github-trending", title="t", digest_date="2026-11-06", body="x"
        )
        unpublish_digest(d)
        d, _ = submit_digest(
            series="github-trending", title="t2", digest_date="2026-11-06", body="x"
        )
        self.assertEqual(d.status, "draft")

    def test_publish_and_unpublish_manage_feed_card(self):
        digest, _ = submit_digest(
            series=self.series, title="t", digest_date="2026-11-06", body="hello"
        )
        publish_digest(digest)
        digest.refresh_from_db()
        self.assertEqual(digest.status, "published")
        self.assertTrue(FeedItem.objects.filter(url=digest.get_absolute_url()).exists())
        unpublish_digest(digest)
        self.assertFalse(FeedItem.objects.exists())
        digest.refresh_from_db()
        self.assertEqual(digest.status, "draft")

    def test_rejects_oversize_body(self):
        with self.assertRaises(IntakeError):
            submit_digest(
                series=self.series,
                title="t",
                digest_date="2026-11-06",
                body="x" * 200_001,
            )


class PublicViewTests(IntakeTestBase):
    def test_index_and_series_pages(self):
        d, _ = submit_digest(
            series=self.series, title="Week 45", digest_date="2026-11-06", body="hello"
        )
        self.assertEqual(self.client.get(reverse("blog:digest_index")).status_code, 200)
        publish_digest(d)
        self.assertContains(
            self.client.get(reverse("blog:digest_index")), "GitHub Trending"
        )
        self.assertContains(self.client.get(self.series.get_absolute_url()), "Week 45")
        self.assertContains(self.client.get(reverse("blog:index")), "Week 45")


class GmailAdapterTests(TestCase):
    def _msg(self, subject, body):
        msg = email.message.EmailMessage()
        msg["Subject"] = subject
        msg["Date"] = "Fri, 06 Nov 2026 10:00:00 +0000"
        msg.set_content(body)
        return msg

    def test_parse_subject_and_header_lines(self):
        kwargs = parse_digest_email(
            self._msg(
                "[Digest:github-trending] Week 45",
                "date: 2026-11-05\ntags: ai, tools\nid: w45\n\n# Hello\ntext",
            )
        )
        self.assertEqual(kwargs["series"], "github-trending")
        self.assertEqual(kwargs["title"], "Week 45")
        self.assertEqual(kwargs["digest_date"], "2026-11-05")
        self.assertEqual(kwargs["external_id"], "w45")
        self.assertEqual(kwargs["tags"], ["ai", "tools"])
        self.assertTrue(kwargs["body"].startswith("# Hello"))

    def test_date_defaults_to_draft_date(self):
        kwargs = parse_digest_email(self._msg("[Digest:x] T", "body"))
        self.assertEqual(kwargs["digest_date"], "2026-11-06")

    def test_non_digest_subject_ignored(self):
        self.assertIsNone(parse_digest_email(self._msg("hello", "body")))


@override_settings(STORAGES=TEST_STORAGES)
class AdminTests(IntakeTestBase):
    def setUp(self):
        super().setUp()
        self.admin_user = get_user_model().objects.create_superuser("a", "a@x.io", "pw")
        self.client.force_login(self.admin_user)

    def test_token_created_in_admin_shows_key_once(self):
        resp = self.client.post(
            reverse("admin:blog_agenttoken_add"),
            {"name": "Gemini", "is_active": "on"},
            follow=True,
        )
        token = AgentToken.objects.get(name="Gemini")
        self.assertContains(resp, "wlg_")
        self.assertEqual(len(token.key_hash), 64)

    def test_publish_action(self):
        d, _ = submit_digest(
            series=self.series, title="t", digest_date="2026-11-06", body="x"
        )
        self.client.post(
            reverse("admin:blog_digest_changelist"),
            {"action": "publish_selected", "_selected_action": [d.pk]},
        )
        d.refresh_from_db()
        self.assertEqual(d.status, "published")
        self.assertEqual(FeedItem.objects.count(), 1)

    def test_admin_edit_status_transitions(self):
        d, _ = submit_digest(
            series=self.series, title="t", digest_date="2026-11-06", body="x"
        )
        url = reverse("admin:blog_digest_change", args=[d.pk])

        def save(status):
            return self.client.post(
                url,
                {
                    "series": self.series.pk,
                    "title": "t",
                    "digest_date": "2026-11-06",
                    "external_id": d.external_id,
                    "slug": d.slug,
                    "body_md": "x",
                    "source_url": "",
                    "status": status,
                },
            )

        save("published")
        d.refresh_from_db()
        self.assertEqual((d.status, FeedItem.objects.count()), ("published", 1))
        save("draft")
        d.refresh_from_db()
        self.assertEqual((d.status, FeedItem.objects.count()), ("draft", 0))
