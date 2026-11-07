from django.core.management.base import BaseCommand
from hackerstack.ranking import rerank


class Command(BaseCommand):
    help = "Refresh HackerStack's time-sensitive scores without network requests"

    def handle(self, *args, **options):
        self.stdout.write(f"Ranked {rerank()} resources")
