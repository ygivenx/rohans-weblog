import signal
import threading
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlsplit

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from hackerstack.ingestion import PLACEHOLDER_DESCRIPTION
from hackerstack.models import CollectionRun, Resource
from hackerstack.pages import RETRYABLE, Fetcher


def interleave_by_host(resources):
    """Round-robin across hosts so one slow, rate-limited host cannot occupy every worker."""
    queues = defaultdict(deque)
    for resource in resources:
        queues[urlsplit(resource.url).hostname or ""].append(resource)
    ordered = []
    while queues:
        for host in list(queues):
            ordered.append(queues[host].popleft())
            if not queues[host]:
                del queues[host]
    return ordered


class Command(BaseCommand):
    help = (
        "Fetch each page's own <title>, <h1> and description (no LLM). Takes the best-scoring "
        "resources never tried before; safe to stop and resume."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=5000)
        parser.add_argument("--workers", type=int, default=16)
        parser.add_argument("--timeout", type=int, default=10)
        parser.add_argument(
            "--retry-failed",
            action="store_true",
            help="Also retry timeouts, 429s and 5xx from earlier runs",
        )

    def handle(self, *args, **options):
        limit, workers = options["limit"], options["workers"]
        if not 1 <= limit <= 25000 or not 1 <= workers <= 32:
            raise CommandError("--limit must be 1-25000 and --workers 1-32")
        statuses = [""] + (list(RETRYABLE) if options["retry_failed"] else [])
        resources = list(
            Resource.objects.filter(is_active=True, fetch_status__in=statuses).order_by(
                "-score", "id"
            )[:limit]
        )
        if not resources:
            self.stdout.write("Nothing to fetch")
            return
        stop = threading.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())
        fetcher = Fetcher(timeout=options["timeout"])
        run = CollectionRun.objects.create(source="page-fetch")
        counts = Counter()

        def work(resource):
            if stop.is_set():
                return resource, dict(status="skipped")
            return resource, fetcher.fetch(resource.url)

        done = 0
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(work, r) for r in interleave_by_host(resources)]
                for future in as_completed(futures):
                    resource, result = future.result()
                    done += 1
                    if result["status"] == "skipped":
                        counts["skipped"] += 1
                        continue
                    counts[result["status"]] += 1
                    resource.page_title = result["title"]
                    resource.page_h1 = result["h1"]
                    resource.page_description = result["description"]
                    resource.fetch_status = result["status"]
                    resource.fetched_at = timezone.now()
                    fields = [
                        "page_title",
                        "page_h1",
                        "page_description",
                        "fetch_status",
                        "fetched_at",
                    ]
                    if (
                        result["status"] == "ok"
                        and result["description"]
                        and resource.description == PLACEHOLDER_DESCRIPTION
                    ):
                        resource.description = result["description"]
                        fields.append("description")
                    resource.save(update_fields=fields)
                    if done % 250 == 0:
                        self.stdout.write(
                            f"{done}/{len(resources)} ok={counts['ok']}", ending="\n"
                        )
                        self.stdout.flush()
        finally:
            fetched = sum(v for k, v in counts.items() if k != "skipped")
            run.requests = fetched
            run.records = counts["ok"]
            run.status = "partial" if stop.is_set() or counts["skipped"] else "complete"
            run.finished_at = timezone.now()
            run.detail = (
                "Page <title>/<h1>/description fetched directly from each URL, robots.txt honoured. "
                + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
            )
            run.save()
        self.stdout.write(
            f"{run.status}: {fetched} fetched, {counts['ok']} with metadata; "
            + ", ".join(f"{k}={v}" for k, v in counts.most_common())
        )
        if fetcher.blocked_hosts:
            self.stdout.write(
                "Rate-limited hosts skipped: "
                + ", ".join(sorted(fetcher.blocked_hosts))
            )
