from collections import Counter
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
import re

from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Case, CharField, F, Max, Q, When
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.feedgenerator import Rss201rev2Feed
from django.utils.html import escape

from blog.models import Sponsor

from .models import CATEGORIES, Evidence, KINDS, Resource
from .search import search

WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")
HS_META_CACHE_KEY = "hackerstack:index_meta"
HS_META_CACHE_TTL = 300


def invalidate_hs_meta_cache(**kwargs):
    cache.delete(HS_META_CACHE_KEY)


def _index_meta():
    meta = cache.get(HS_META_CACHE_KEY)
    if meta is None:
        active = Resource.objects.filter(is_active=True)
        meta = {
            "has_filtered": active.filter(llm_relevant=False).exists(),
            "ranked_at": Resource.objects.aggregate(value=Max("ranked_at"))["value"],
        }
        cache.set(HS_META_CACHE_KEY, meta, HS_META_CACHE_TTL)
    return meta


def _format_week(year, week_num):
    return f"{year}-W{week_num:02d}"


def _week_bounds(year, week_num):
    start_date = date.fromisocalendar(year, week_num, 1)
    start_dt = datetime.combine(start_date, time.min, tzinfo=dt_timezone.utc)
    return start_dt, start_dt + timedelta(days=7)


def _parse_week(value):
    match = WEEK_RE.match(value or "")
    if not match:
        raise Http404("Invalid week format")
    year, week_num = int(match.group(1)), int(match.group(2))
    try:
        date.fromisocalendar(year, week_num, 1)
    except ValueError as exc:
        raise Http404("Invalid ISO week") from exc
    return year, week_num


def _qualifying_hn_evidence():
    return Evidence.objects.filter(
        source="hn",
        kind="submission",
        published_at__isnull=False,
        resource__is_active=True,
    ).exclude(resource__llm_relevant=False)


def _latest_hn_week():
    latest = _qualifying_hn_evidence().aggregate(value=Max("published_at"))["value"]
    anchor = (latest or timezone.now()).astimezone(dt_timezone.utc).date()
    iso = anchor.isocalendar()
    return iso.year, iso.week


def _weekly_entries(week_start, week_end, category=""):
    qs = (
        _qualifying_hn_evidence()
        .filter(published_at__gte=week_start, published_at__lt=week_end)
        .select_related("resource")
        .order_by(F("points").desc(nulls_last=True), "-comments", "-published_at", "id")
    )
    deduped = []
    seen = set()
    for ev in qs:
        if ev.resource_id in seen:
            continue
        seen.add(ev.resource_id)
        deduped.append({"resource": ev.resource, "evidence": ev})
    counts = Counter(entry["resource"].topic for entry in deduped)
    topic_counts = [
        (key, label, counts[key]) for key, label in CATEGORIES if counts.get(key)
    ]
    if category in dict(CATEGORIES):
        filtered = [e for e in deduped if e["resource"].topic == category]
    else:
        filtered = deduped
    return filtered, len(deduped), topic_counts


def weekly(request, week=None):
    year, week_num = _parse_week(week) if week else _latest_hn_week()
    week_start, week_end = _week_bounds(year, week_num)
    week_end_date = (week_end - timedelta(days=1)).date()
    category = request.GET.get("category", "")
    if category not in dict(CATEGORIES):
        category = ""

    entries, total_count, topic_counts = _weekly_entries(
        week_start, week_end, category=category
    )
    page = Paginator(entries, 25).get_page(request.GET.get("page"))

    prev_iso = (week_start.date() - timedelta(days=7)).isocalendar()
    next_iso = week_end.date().isocalendar()
    has_prev = _qualifying_hn_evidence().filter(published_at__lt=week_start).exists()
    has_next = _qualifying_hn_evidence().filter(published_at__gte=week_end).exists()

    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "hackerstack/weekly.html",
        dict(
            page=page,
            week_code=_format_week(year, week_num),
            week_start=week_start.date(),
            week_end=week_end_date,
            prev_week=_format_week(prev_iso.year, prev_iso.week) if has_prev else "",
            next_week=_format_week(next_iso.year, next_iso.week) if has_next else "",
            is_latest=not has_next,
            total_count=total_count,
            category=category,
            topic_counts=topic_counts,
            querystring=params.urlencode(),
            sponsor=Sponsor.active_for(Sponsor.PLACEMENT_HACKERSTACK),
        ),
    )


def weekly_rss(request):
    year, week_num = _latest_hn_week()
    week_start, week_end = _week_bounds(year, week_num)
    week_code = _format_week(year, week_num)
    entries, _, _ = _weekly_entries(week_start, week_end)
    feed = Rss201rev2Feed(
        title=f"HackerStack Weekly HN ({week_code})",
        link=request.build_absolute_uri(reverse("hackerstack:weekly")),
        description="Top weekly AI and software engineering stories from Hacker News, curated via HackerStack.",
        language="en-us",
    )
    for entry in entries[:30]:
        resource = entry["resource"]
        ev = entry["evidence"]
        pts = f"{ev.points} points" if ev.points is not None else "HN submission"
        desc = (
            f"<p>{escape(resource.description)}</p>"
            f"<p>{pts} · {ev.comments} comments · "
            f'<a href="{escape(ev.discussion_url)}">HN discussion</a></p>'
        )
        feed.add_item(
            title=resource.title,
            link=resource.url,
            description=desc,
            unique_id=f"{week_code}:{ev.source_id}",
            pubdate=ev.published_at,
        )
    response = HttpResponse(
        feed.writeString("utf-8"), content_type="application/rss+xml; charset=utf-8"
    )
    response["Cache-Control"] = "public, max-age=300"
    return response


def index(request):
    q = request.GET.get("q", "").strip()[:200]
    category = request.GET.get("category", "")
    kind = request.GET.get("kind", "")
    source = request.GET.get("source", "")
    sort = request.GET.get("sort", "rank")
    show = "filtered" if request.GET.get("show") == "filtered" else ""
    # Topic = the page review's category when it judged the link relevant, else the keyword match.
    everything = Resource.objects.filter(is_active=True).annotate(
        topic_key=Case(
            When(Q(llm_relevant=True) & ~Q(llm_category=""), then=F("llm_category")),
            default=F("category"),
            output_field=CharField(),
        )
    )
    meta = _index_meta()
    has_filtered = meta["has_filtered"]
    # Links the page review judged off-topic are hidden unless asked for.
    resources = (
        everything.filter(llm_relevant=False)
        if show
        else everything.exclude(llm_relevant=False)
    )
    if category in dict(CATEGORIES):
        resources = resources.filter(topic_key=category)
    if kind in dict(KINDS):
        resources = resources.filter(kind=kind)
    if source in ("hn", "lobsters"):
        resources = resources.filter(evidence__source=source).distinct()
    elif source == "curated":
        resources = resources.filter(curated=True)
    if q:
        resources = search(resources, q)
    ordering = {
        "rank": ["-score"],
        "popular": ["-popularity", "-score"],
        "fresh": ["-freshness", "-score"],
    }.get(sort, ["-score"])
    if q and sort == "rank" and "title_match" in resources.query.annotations:
        ordering = ["-title_match"] + ordering
    page = Paginator(
        resources.order_by(*ordering, "id").prefetch_related("evidence"), 24
    ).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "hackerstack/index.html",
        dict(
            page=page,
            q=q,
            category=category,
            kind=kind,
            source=source,
            sort=sort,
            show=show,
            has_filtered=has_filtered,
            categories=list(CATEGORIES),
            kinds=KINDS,
            querystring=params.urlencode(),
            ranked_at=meta["ranked_at"],
        ),
    )
