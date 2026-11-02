from django.core.management.base import BaseCommand

from blog.briefings import sync_briefing_from_gmail


class Command(BaseCommand):
    help = "Check Gmail Drafts/Inbox via IMAP for BRIEFING_AUTO_PUBLISH and ingest new daily briefings."

    def handle(self, *args, **options):
        stats = sync_briefing_from_gmail()
        if not stats.get("checked"):
            self.stdout.write(
                "Skipped Gmail briefing sync (GMAIL_USER / GMAIL_APP_PASSWORD not configured)."
            )
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"Gmail briefing sync complete: created={stats['created']} updated={stats['updated']}"
            )
        )
