from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from hackerstack.models import CollectionCursor
from hackerstack.ranking import rerank
from hackerstack.snapshot import load_snapshot

DEFAULT = Path(__file__).resolve().parents[2] / "data" / "snapshot.jsonl.gz"


class Command(BaseCommand):
    help = "Load the committed snapshot once (per file version); safe to re-run with --force"

    def add_arguments(self, parser):
        parser.add_argument("--path", default=str(DEFAULT))
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.exists():
            self.stdout.write("No snapshot file; nothing to load")
            return
        # Marker is keyed by file size, so a re-exported (different) snapshot loads again.
        key = f"snapshot:{path.stat().st_size}"
        if CollectionCursor.objects.filter(key=key).exists() and not options["force"]:
            self.stdout.write("Snapshot already loaded")
            return
        try:
            stats = load_snapshot(path)
        except (OSError, ValueError) as exc:
            raise CommandError(
                f"Snapshot load failed and was rolled back: {exc}"
            ) from exc
        rerank()
        CollectionCursor.objects.get_or_create(key=key)
        self.stdout.write(f"Loaded snapshot: {stats}")
