from django.core.paginator import Paginator
from django.db.models import Case, CharField, Count, F, Max, Q, When
from django.shortcuts import render

from .models import CATEGORIES, KINDS, BackfillWindow, CollectionRun, Resource
from .search import search


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
    filtered_count = everything.filter(llm_relevant=False).count()
    # Links the page review judged off-topic are hidden unless asked for.
    resources = (
        everything.filter(llm_relevant=False)
        if show
        else everything.exclude(llm_relevant=False)
    )
    total = resources.count()
    counts = dict(resources.values_list("topic_key").annotate(n=Count("id")))
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
            filtered_count=filtered_count,
            categories=[(key, label, counts.get(key, 0)) for key, label in CATEGORIES],
            kinds=KINDS,
            total=total,
            coverage=dict(
                BackfillWindow.objects.values_list("status").annotate(n=Count("id"))
            ),
            coverage_queries=BackfillWindow.objects.values("query").distinct().count(),
            lobsters_count=Resource.objects.filter(evidence__source="lobsters")
            .distinct()
            .count(),
            querystring=params.urlencode(),
            last_run=CollectionRun.objects.order_by("-started_at").first(),
            ranked_at=Resource.objects.aggregate(value=Max("ranked_at"))["value"],
        ),
    )
