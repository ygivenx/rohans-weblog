"""Versioned discovery vocabulary. Coverage describes these queries, not all semantics."""

from datetime import datetime, timezone as dt_timezone

from django.db import transaction

from .ingestion import QUERIES, ingest_story
from .models import BackfillWindow

# Verified against hn.algolia.com: results cap at 1000 hits per query, and without
# typoTolerance=false exhaustiveNbHits is almost always False (fuzzy matches), which
# made every window split. The points floor keeps a year under the cap for most terms.
MIN_POINTS = 20


def window_params(window):
    return dict(
        query=window.query,
        tags="story",
        numericFilters=f"created_at_i>={window.start},created_at_i<{window.end},points>={MIN_POINTS}",
        typoTolerance="false",
        hitsPerPage=100,
        page=window.page,
    )


HISTORICAL_QUERIES = QUERIES + [
    ("agents", "coding agent"),
    ("agents", "context engineering"),
    ("llms", "transformer"),
    ("llms", "neural network"),
    ("llms", "large language model"),
    ("rl", "RLHF"),
    ("rl", "policy gradient"),
    ("rl", "reward model"),
    ("data", "training data"),
    ("data", "synthetic data"),
    ("evals", "benchmark"),
    ("retrieval", "semantic search"),
    ("inference", "GPU"),
    ("inference", "quantization"),
    ("safety", "prompt injection"),
    ("safety", "AI safety"),
    ("multimodal", "robotics"),
    ("multimodal", "diffusion model"),
    ("engineering", "programming"),
    ("engineering", "software engineering"),
    ("engineering", "distributed systems"),
    ("engineering", "database"),
    ("engineering", "compiler"),
    ("engineering", "operating system"),
    ("production", "observability"),
    ("production", "machine learning"),
]


def initialize_windows(until):
    """Freeze yearly windows at initialization. Future refreshes extend coverage."""
    count = 0
    for category, query in HISTORICAL_QUERIES:
        last = BackfillWindow.objects.filter(query=query).order_by("-end").first()
        start = (
            last.end
            if last
            else int(datetime(2006, 1, 1, tzinfo=dt_timezone.utc).timestamp())
        )
        while start < until:
            year = datetime.fromtimestamp(start, tz=dt_timezone.utc).year
            end = min(
                until, int(datetime(year + 1, 1, 1, tzinfo=dt_timezone.utc).timestamp())
            )
            _, created = BackfillWindow.objects.get_or_create(
                query=query, start=start, end=end, defaults={"category": category}
            )
            count += created
            start = end
    return count


def process_window(window, data):
    total = data.get("nbHits")
    if not isinstance(total, int) or total < 0:
        raise ValueError("Missing or invalid hit count")
    exhaustive = data.get(
        "exhaustiveNbHits", data.get("exhaustive", {}).get("nbHits", True)
    )
    with transaction.atomic():
        window.expected_hits = total
        if total >= 900 or not exhaustive:
            if window.end - window.start <= 1:
                window.status = "blocked"
                window.note = "Source cap or inexact count within a one-second interval; cannot certify coverage"
            else:
                middle = (window.start + window.end) // 2
                for start, end in ((window.start, middle), (middle, window.end)):
                    BackfillWindow.objects.get_or_create(
                        query=window.query,
                        start=start,
                        end=end,
                        defaults={"category": window.category},
                    )
                window.status = "split"
            window.save()
            return 0
        records = 0
        skipped = 0
        for hit in data["hits"]:
            # Discussion-only posts still count toward scanned coverage; no external URL.
            if not hit.get("url"):
                continue
            try:
                ingest_story(hit, window.category)
                records += 1
            except (ValueError, TypeError, AttributeError):
                skipped += 1
        window.indexed_hits += len(data["hits"])
        window.page += 1
        if skipped:
            window.note = (
                "Malformed external-link records were skipped; review required"
            )
        if window.indexed_hits >= total:
            window.status = "review" if window.note else "complete"
        elif not data["hits"]:
            window.status = "blocked"
            window.note = "Source returned no records before its reported total"
        window.save()
        return records
