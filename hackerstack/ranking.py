"""Explainable editorial heuristic, not a probability of correctness.

Votes are normalized within each source and logarithmically saturated. A repost
cannot add its votes to the same thread; mentions carry no invented votes.
"""

import math

from django.utils import timezone

from .models import Resource

HALF_LIVES = {
    "news": 30,
    "tool": 180,
    "documentation": 180,
    "article": 365,
    "website": 365,
    "paper": 730,
    "course": 1825,
}
SOURCE_SCALES = {"hn": 500, "lobsters": 100}


def components(resource, evidence, today=None):
    today = today or timezone.localdate()
    popularity = max(
        (
            math.log1p(max(0, e.points or 0))
            / (math.log1p(max(0, e.points or 0)) + math.log1p(SOURCE_SCALES[e.source]))
            for e in evidence
            if e.kind == "submission" and e.source in SOURCE_SCALES
        ),
        default=0.0,
    )
    threads = {(e.source, e.thread_id) for e in evidence}
    corroboration = 1 - math.exp(-len(threads) / 3)
    if resource.content_date:
        age = max(0, (today - resource.content_date).days)
        freshness = 2 ** (-age / max(1, resource.half_life_days))
    else:
        freshness = 0.5  # Unknown is not new, and recrawling cannot rejuvenate it.
        dates = [e.published_at.date() for e in evidence if e.published_at]
        if dates:
            # The oldest discussion establishes a minimum age, not a publication date.
            age = max(0, (today - min(dates)).days)
            freshness = min(freshness, 2 ** (-age / max(1, resource.half_life_days)))
    # R: Jev's probability that the link is on-topic; unreviewed links are neutral (0.5).
    relevance = 0.5 if resource.llm_score is None else resource.llm_score
    score = (
        100
        * (
            0.20
            + 0.40 * popularity
            + 0.20 * corroboration
            + 0.15 * resource.curated
            + 0.05 * relevance
        )
        * (0.20 + 0.80 * freshness)
    )
    return dict(
        score=round(score, 4),
        popularity=popularity,
        freshness=freshness,
        corroboration=corroboration,
        evidence_count=len(threads),
    )


def rerank():
    count = 0
    now = timezone.now()
    batch = []
    fields = [
        "score",
        "popularity",
        "freshness",
        "corroboration",
        "evidence_count",
        "ranked_at",
    ]
    # Updating scores while iterating a score-ordered cursor can revisit/skip rows.
    for r in (
        Resource.objects.order_by("pk")
        .prefetch_related("evidence")
        .iterator(chunk_size=250)
    ):
        values = components(r, list(r.evidence.all()))
        for key, value in values.items():
            setattr(r, key, value)
        r.ranked_at = now
        batch.append(r)
        if len(batch) == 250:
            Resource.objects.bulk_update(batch, fields, batch_size=100)
            batch = []
        count += 1
    if batch:
        Resource.objects.bulk_update(batch, fields, batch_size=100)
    return count
