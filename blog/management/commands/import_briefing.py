from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from blog.briefings import ingest_briefing_html


class Command(BaseCommand):
    help = (
        "Import and sanitize one or more Gemini Daily Intelligence Briefing HTML files."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "path",
            help="Path to an HTML briefing file or a directory of HTML briefing files.",
        )
        parser.add_argument(
            "--date",
            default=None,
            help="Optional YYYY-MM-DD override when importing a single file.",
        )

    def handle(self, *args, **options):
        target = Path(options["path"]).expanduser().resolve()
        if not target.exists():
            raise CommandError(f"Path does not exist: {target}")

        if target.is_dir():
            files = sorted(target.glob("*.html"))
        else:
            files = [target]

        if not files:
            raise CommandError(f"No .html files found at: {target}")

        for html_path in files:
            raw_html = html_path.read_text(encoding="utf-8", errors="replace")
            briefing, created = ingest_briefing_html(
                raw_html,
                briefing_date=options["date"] if len(files) == 1 else None,
                filename=html_path.name,
            )
            action = "Created" if created else "Updated"
            self.stdout.write(
                self.style.SUCCESS(
                    f"{action} briefing [{briefing.slug}] ({briefing.signal_count} signals): {briefing.title}"
                )
            )
