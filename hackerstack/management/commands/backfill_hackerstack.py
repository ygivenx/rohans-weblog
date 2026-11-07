from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from hackerstack.backfill import initialize_windows, process_window, window_params
from hackerstack.ingestion import BudgetExceeded, CachedHNClient
from hackerstack.models import BackfillWindow, CollectionRun
from hackerstack.ranking import rerank


class Command(BaseCommand):
    help = "Resume date-partitioned HN AI/engineering history without silently truncating capped searches"

    def add_arguments(self, parser):
        parser.add_argument("--max-requests", type=int, default=24)
        parser.add_argument(
            "--initialize",
            action="store_true",
            help="Queue history from 2006 through now; subsequent calls extend the horizon",
        )

    def handle(self, *args, **options):
        budget = options["max_requests"]
        if not 1 <= budget <= 120:
            raise CommandError("Request budget must be between 1 and 120")
        if options["initialize"]:
            self.stdout.write(
                f"Queued {initialize_windows(int(timezone.now().timestamp()))} date windows"
            )
        client = CachedHNClient(budget=budget)
        run = CollectionRun.objects.create(source="hn-backfill")
        try:
            # Limit cache-only work too. Newer intervals first; failed intervals can be inspected.
            for _ in range(budget * 2):
                window = (
                    BackfillWindow.objects.filter(status="pending")
                    .order_by("-end", "updated_at", "id")
                    .first()
                )
                if window is None:
                    break
                data = client.get("search_by_date", window_params(window))
                run.records += process_window(window, data)
            run.status = (
                "partial"
                if BackfillWindow.objects.exclude(
                    status__in=["complete", "split"]
                ).exists()
                else "complete"
            )
        except BudgetExceeded:
            run.status = "partial"
        except Exception as exc:
            run.status = "failed"
            raise CommandError(
                "Backfill stopped; last completed page preserved"
            ) from exc
        finally:
            run.requests = client.requests
            run.cache_hits = client.cache_hits
            run.finished_at = timezone.now()
            run.detail = "Date-partitioned HN submission history (stories with 20+ points). Coverage is query-defined; comments are separate. Lobsters not included."
            run.save()
            rerank()
        self.stdout.write(
            f"{run.status}: {run.records} records, {run.requests} network requests; pending={BackfillWindow.objects.filter(status='pending').count()}"
        )
