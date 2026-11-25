from collections import Counter

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count

from .models import BlogPost, DailyBriefing, FeedItem, TIL, Tag

ALL_TAGS_CACHE_KEY = "blog:all_tags"
ALL_TAGS_CACHE_TTL = 300


def invalidate_all_tags_cache(**kwargs):
    """Clear the cached header tag list when tagged content changes."""
    cache.delete(ALL_TAGS_CACHE_KEY)


def _compute_all_tags():
    """Compute tag counts via independent aggregations instead of a 4-way M2M join."""
    totals = Counter()
    queries = (
        BlogPost.objects.filter(is_published=True, tags__isnull=False),
        TIL.objects.filter(tags__isnull=False),
        FeedItem.objects.filter(daily_briefing__isnull=True, tags__isnull=False),
        DailyBriefing.objects.filter(is_published=True, tags__isnull=False),
    )
    for qs in queries:
        for row in qs.values("tags").annotate(c=Count("id", distinct=True)):
            totals[row["tags"]] += row["c"]

    if not totals:
        return []

    tags = list(Tag.objects.filter(pk__in=totals.keys()).order_by("name"))
    for tag in tags:
        tag.total_count = totals[tag.pk]
    return tags


def all_tags(request):
    """Inject cached tags with total content counts into every template."""
    tags = cache.get(ALL_TAGS_CACHE_KEY)
    if tags is None:
        tags = _compute_all_tags()
        cache.set(ALL_TAGS_CACHE_KEY, tags, ALL_TAGS_CACHE_TTL)

    return {
        "all_tags": tags,
        "debug_mode": settings.DEBUG,
    }
