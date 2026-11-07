from pathlib import Path

from django.core.management.base import BaseCommand

from hackerstack.snapshot import export_snapshot

DEFAULT = Path(__file__).resolve().parents[2] / "data" / "snapshot.jsonl.gz"


class Command(BaseCommand):
    help = "Write the index (resources, evidence, backfill coverage) to a gzip JSONL snapshot"

    def add_arguments(self, parser):
        parser.add_argument("--out", default=str(DEFAULT))

    def handle(self, *args, **options):
        counts = export_snapshot(options["out"])
        size = Path(options["out"]).stat().st_size
        self.stdout.write(f"Wrote {options['out']} ({size / 1e6:.1f} MB): {counts}")
