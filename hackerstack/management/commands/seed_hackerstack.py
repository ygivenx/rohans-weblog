import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from hackerstack.ingestion import canonical_url
from hackerstack.models import Resource
from hackerstack.ranking import HALF_LIVES, rerank


class Command(BaseCommand):
    help = "Add the researched directory without replacing subsequent editorial changes"

    def handle(self, *args, **options):
        path = Path(__file__).resolve().parents[2] / "data" / "resources.json"
        count = 0
        with transaction.atomic():
            for row in json.loads(path.read_text()):
                url = canonical_url(row.pop("url"))
                _, created = Resource.objects.get_or_create(
                    url=url,
                    defaults={
                        **row,
                        "curated": True,
                        "provenance": url,
                        "half_life_days": HALF_LIVES[row["kind"]],
                    },
                )
                count += created
        rerank()
        self.stdout.write(f"Added {count} curated resources")
