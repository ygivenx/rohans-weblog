import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from hackerstack.ingestion import (
    BudgetExceeded,
    CachedHNClient,
    QUERIES,
    ingest_story,
    ingest_comment,
)
from hackerstack.models import CATEGORIES, CollectionCursor, CollectionRun
from hackerstack.ranking import rerank


class Command(BaseCommand):
    help = "Collect HN links with a request budget, or import a local Lobsters story export. Never crawls Lobsters."

    def add_arguments(self, parser):
        parser.add_argument("--max-requests", type=int, default=24)
        parser.add_argument("--mode", choices=["popular", "recent"], default="popular")
        parser.add_argument("--lobsters-file", type=Path)
        parser.add_argument(
            "--thread-id",
            help="Index external links in an HN discussion, with resumable comment pagination",
        )
        parser.add_argument(
            "--category", choices=list(dict(CATEGORIES)), default="research"
        )

    def handle(self, *args, **options):
        if not 1 <= options["max_requests"] <= 100:
            raise CommandError("--max-requests must be between 1 and 100")
        if options["thread_id"] and (
            not options["thread_id"].isdigit() or options["lobsters_file"]
        ):
            raise CommandError(
                "--thread-id must be numeric and cannot be combined with --lobsters-file"
            )
        run = CollectionRun.objects.create(
            source="lobsters-import" if options["lobsters_file"] else "hn"
        )
        client = CachedHNClient(budget=options["max_requests"])
        errors = []
        try:
            if options["thread_id"]:
                thread_id = options["thread_id"]
                cursor, _ = CollectionCursor.objects.get_or_create(
                    key=f"hn:comments:{thread_id}"
                )
                # Bound even cache-only runs. A subsequent call continues at the next page.
                for _ in range(options["max_requests"]):
                    data = client.get(
                        "search_by_date",
                        dict(
                            tags=f"comment,story_{thread_id}",
                            hitsPerPage=100,
                            page=cursor.page,
                        ),
                    )
                    with transaction.atomic():
                        for hit in data["hits"]:
                            try:
                                run.records += ingest_comment(
                                    hit, options["category"], thread_id
                                )
                            except (ValueError, TypeError, AttributeError):
                                errors.append("Skipped malformed comment")
                        pages = min(int(data.get("nbPages", 1)), 10)
                        cursor.page += 1
                        done = cursor.page >= pages
                        if done:
                            cursor.page = 0
                            cursor.cycle += 1
                        cursor.save()
                    if done:
                        break
                run.detail = f"Comment links from HN thread {thread_id}; API result cap applies. Mentions are not endorsements."
                if not done:
                    errors.append("More comment pages remain")
            elif options["lobsters_file"]:
                path = options["lobsters_file"]
                if path.stat().st_size > 10_000_000:
                    raise ValueError("Import exceeds 10 MB")
                stories = json.loads(path.read_text())
                if not isinstance(stories, list) or len(stories) > 10000:
                    raise ValueError(
                        "Expected an array of at most 10,000 Lobsters stories"
                    )
                with transaction.atomic():
                    for hit in stories:
                        ingest_story(hit, options["category"], "lobsters")
                run.records = len(stories)
            else:
                # Least recently serviced query first prevents a small budget starving later topics.
                jobs = []
                for category, query in QUERIES:
                    cursor, _ = CollectionCursor.objects.get_or_create(
                        key=f"hn:{options['mode']}:{query}"
                    )
                    jobs.append((cursor, category, query))
                jobs.sort(key=lambda job: job[0].updated_at)
                for cursor, category, query in jobs:
                    endpoint = (
                        "search" if options["mode"] == "popular" else "search_by_date"
                    )
                    page = cursor.page if options["mode"] == "popular" else 0
                    data = client.get(
                        endpoint,
                        dict(query=query, tags="story", hitsPerPage=50, page=page),
                    )
                    with transaction.atomic():
                        for hit in data["hits"]:
                            if not hit.get("url"):
                                continue
                            try:
                                ingest_story(hit, category)
                                run.records += 1
                            except (ValueError, TypeError, AttributeError):
                                errors.append("Skipped malformed record")
                        pages = min(int(data.get("nbPages", 1)), 20)
                        cursor.page = page + 1 if page + 1 < pages else 0
                        if cursor.page == 0:
                            cursor.cycle += 1
                        cursor.save()
                run.detail = "One page per topic; 50 results/page. Search API result cap applies. Recent mode refreshes the newest page; popular mode resumes pagination. Comment threads are indexed separately. Not exhaustive."
            run.status = "partial" if errors else "complete"
        except BudgetExceeded as exc:
            run.status = "partial"
            run.detail = str(exc)
        except Exception as exc:
            run.status = "failed"
            run.detail = (
                f"{type(exc).__name__}: Collection stopped; completed pages preserved."
            )
            raise CommandError(run.detail) from exc
        finally:
            run.requests = client.requests
            run.cache_hits = client.cache_hits
            run.finished_at = timezone.now()
            run.detail += f" Skipped records: {len(errors)}."
            run.save()
            rerank()
        self.stdout.write(
            f"{run.status}: {run.records} records, {run.requests} network requests, {run.cache_hits} cached responses"
        )
