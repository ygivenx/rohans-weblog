import os
import uuid
import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import (
    HttpResponse,
    JsonResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
)
from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.utils.feedgenerator import Rss201rev2Feed
from django.utils.text import get_valid_filename
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .intake import IntakeError, authenticate_token, submit_digest
from .models import (
    BlogPost,
    TIL,
    Bookmark,
    FeedItem,
    Tag,
    ProductUpdate,
    DailyBriefing,
    Digest,
    Series,
)
from .product_updates import (
    verify_github_signature,
    upsert_github_release,
    sync_gumroad_products,
)
from .search import search_content
from .utils import render_markdown, POSTS_PER_PAGE, TILS_PER_PAGE, BOOKMARKS_PER_PAGE


def post_list(request):
    """List all published blog posts (paginated)."""
    posts = (
        BlogPost.objects.filter(is_published=True)
        .prefetch_related("tags")
        .order_by("-published_date", "-created_date")
    )

    paginator = Paginator(posts, POSTS_PER_PAGE)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "blog/index.html",
        {
            "page_obj": page_obj,
        },
    )


def post_detail(request, slug):
    """Display a single blog post."""
    post = get_object_or_404(BlogPost, slug=slug, is_published=True)
    post.content_html = render_markdown(post.content)

    return render(
        request,
        "blog/post_detail.html",
        {
            "post": post,
        },
    )


def til_list(request):
    """List all TIL entries (paginated)."""
    tils = TIL.objects.prefetch_related("tags").order_by("-created_date")

    paginator = Paginator(tils, TILS_PER_PAGE)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "blog/til_list.html",
        {
            "page_obj": page_obj,
        },
    )


def til_detail(request, slug):
    """Display a single TIL entry."""
    til = get_object_or_404(TIL, slug=slug)
    til.content_html = render_markdown(til.content)

    return render(
        request,
        "blog/til_detail.html",
        {
            "til": til,
        },
    )


def bookmarks_list(request):
    """List all bookmarks (paginated)."""
    bookmarks = Bookmark.objects.prefetch_related("tags").order_by("-created_date")

    paginator = Paginator(bookmarks, BOOKMARKS_PER_PAGE)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "blog/bookmarks_list.html",
        {
            "page_obj": page_obj,
        },
    )


def search(request):
    """Full-text search across all content types with optional tag filtering."""
    query = request.GET.get("q", "").strip()[:500]  # Limit query length
    tag_slug = request.GET.get("tag", "").strip()

    tag = None
    if tag_slug:
        try:
            from .models import Tag

            tag = Tag.objects.get(slug=tag_slug)
        except Tag.DoesNotExist:
            tag_slug = None

    if query or tag_slug:
        results = search_content(query, tag_slug=tag_slug if tag_slug else None)

        for post in results["posts"]:
            post.content_html = render_markdown(post.content)

        for til in results["tils"]:
            til.content_html = render_markdown(til.content)

        for item in results["feed_items"]:
            item.body_html = render_markdown(item.body)

        for briefing in results.get("briefings", []):
            briefing.summary_html = render_markdown(briefing.executive_summary_md)
    else:
        results = {
            "posts": BlogPost.objects.none(),
            "tils": TIL.objects.none(),
            "bookmarks": Bookmark.objects.none(),
            "feed_items": FeedItem.objects.none(),
            "briefings": DailyBriefing.objects.none(),
        }

    return render(
        request,
        "blog/search.html",
        {
            "query": query,
            "tag": tag,
            "tag_slug": tag_slug,
            "results": results,
            "has_results": any(results.values()),
        },
    )


def feed_list(request):
    """List all feed items grouped by month with timeline navigation."""
    from itertools import groupby

    items = list(FeedItem.objects.prefetch_related("tags").order_by("-created_date"))
    for item in items:
        item.body_html = render_markdown(item.body)

    grouped = []
    for key, group in groupby(items, key=lambda x: x.created_date.strftime("%Y-%m")):
        items_list = list(group)
        grouped.append(
            {
                "month_key": key,
                "month_label": items_list[0].created_date.strftime("%B %Y"),
                "items": items_list,
            }
        )

    return render(
        request,
        "blog/feed_list.html",
        {
            "grouped": grouped,
        },
    )


def feed_detail(request, slug):
    """Display a single feed item."""
    item = get_object_or_404(FeedItem, slug=slug)
    item.body_html = render_markdown(item.body)

    return render(
        request,
        "blog/feed_detail.html",
        {
            "item": item,
        },
    )


def tag_detail(request, slug):
    """Show all content with a given tag."""
    tag = get_object_or_404(Tag, slug=slug)

    posts = (
        BlogPost.objects.filter(is_published=True, tags=tag)
        .prefetch_related("tags")
        .order_by("-published_date", "-created_date")
    )
    tils = (
        TIL.objects.filter(tags=tag).prefetch_related("tags").order_by("-created_date")
    )
    feed_items = (
        FeedItem.objects.filter(tags=tag)
        .prefetch_related("tags")
        .order_by("-created_date")
    )

    for item in feed_items:
        item.body_html = render_markdown(item.body)

    briefings = (
        DailyBriefing.objects.filter(is_published=True, tags=tag)
        .prefetch_related("tags")
        .order_by("-briefing_date", "-created_date")
    )
    for briefing in briefings:
        briefing.summary_html = render_markdown(briefing.executive_summary_md)

    return render(
        request,
        "blog/tag_detail.html",
        {
            "tag": tag,
            "posts": posts,
            "tils": tils,
            "feed_items": feed_items,
            "briefings": briefings,
        },
    )


def about(request):
    """Display the about page."""
    return render(request, "blog/about.html")


def products_list(request):
    """Display product updates from GitHub releases and Gumroad products."""
    updates = ProductUpdate.objects.filter(is_visible=True).order_by(
        "-published_at", "-created_date"
    )
    github_updates = updates.filter(source="github")
    gumroad_updates = updates.filter(source="gumroad")

    return render(
        request,
        "blog/products_list.html",
        {
            "github_updates": github_updates,
            "gumroad_updates": gumroad_updates,
            "updates": updates,
        },
    )


def briefing_archive(request):
    """Display the Daily Intelligence Briefings archive list view."""
    briefings = list(
        DailyBriefing.objects.filter(is_published=True)
        .prefetch_related("tags")
        .order_by("-briefing_date", "-created_date")
    )
    for briefing in briefings:
        briefing.summary_html = render_markdown(briefing.executive_summary_md)

    latest_briefing = briefings[0] if briefings else None
    archive_briefings = briefings[1:] if len(briefings) > 1 else []

    return render(
        request,
        "blog/briefing_list.html",
        {
            "latest_briefing": latest_briefing,
            "archive_briefings": archive_briefings,
            "briefings": briefings,
        },
    )


def _render_briefing_response(request, briefing):
    """
    Render the Daily Intelligence Briefing inside an isolated sandboxed iframe
    (opaque origin, zero cookie/admin access) wrapped with the site navigation ribbon.
    """
    all_editions = list(
        DailyBriefing.objects.filter(is_published=True)
        .only("slug", "briefing_date", "signal_count")
        .order_by("-briefing_date", "-created_date")[:60]
    )
    return render(
        request,
        "blog/briefing_viewer.html",
        {
            "briefing": briefing,
            "all_editions": all_editions,
        },
    )


def briefing_list(request):
    """Render the latest full interactive briefing directly at /briefings/."""
    return briefing_latest(request)


def briefing_latest(request):
    """Always-on permanent route (/briefing/ and /briefings/) rendering the latest published briefing."""
    briefing = (
        DailyBriefing.objects.filter(is_published=True)
        .order_by("-briefing_date", "-created_date")
        .first()
    )
    if not briefing:
        return briefing_archive(request)
    return _render_briefing_response(request, briefing)


def briefing_detail(request, slug):
    """Render a specific Daily Intelligence Briefing by date slug."""
    briefing = get_object_or_404(DailyBriefing, slug=slug, is_published=True)
    return _render_briefing_response(request, briefing)


def briefing_rss(request):
    """RSS 2.0 feed of published Daily Intelligence Briefings."""
    feed = Rss201rev2Feed(
        title="Rohan Singh's Daily Intelligence Briefing",
        link=request.build_absolute_uri("/briefings/"),
        description="Autonomous daily synthesis of frontier AI, markets, systems, and global intelligence — Generated with ❤️ from Seattle, WA.",
        language="en-us",
    )
    briefings = DailyBriefing.objects.filter(is_published=True).order_by(
        "-briefing_date", "-created_date"
    )[:20]
    for b in briefings:
        item_url = request.build_absolute_uri(b.get_absolute_url())
        summary_html = render_markdown(b.executive_summary_md)
        feed.add_item(
            title=b.title,
            link=item_url,
            description=summary_html,
            unique_id=item_url,
            pubdate=b.created_date,
        )
    return HttpResponse(
        feed.writeString("utf-8"), content_type="application/rss+xml; charset=utf-8"
    )


@csrf_exempt
@require_POST
def github_webhook(request):
    """Ingest GitHub release webhooks."""
    secret = settings.GITHUB_WEBHOOK_SECRET
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_github_signature(request.body, signature, secret):
        return HttpResponseForbidden("Invalid signature")

    event = request.headers.get("X-GitHub-Event", "")
    if event != "release":
        return JsonResponse({"status": "ignored", "reason": "unsupported event"})

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON payload")

    if payload.get("action") != "published":
        return JsonResponse({"status": "ignored", "reason": "action not published"})

    owner = ((payload.get("repository") or {}).get("owner") or {}).get("login", "")
    expected_owner = settings.GITHUB_OWNER
    if expected_owner and owner.lower() != expected_owner.lower():
        return JsonResponse({"status": "ignored", "reason": "owner mismatch"})

    obj, created = upsert_github_release(payload)
    if not obj:
        return JsonResponse({"status": "ignored", "reason": "invalid release payload"})

    return JsonResponse(
        {
            "status": "ok",
            "created": created,
            "source": obj.source,
            "kind": obj.kind,
            "external_id": obj.external_id,
        }
    )


@csrf_exempt
@require_POST
def gumroad_webhook(request):
    """
    Receive Gumroad webhooks and trigger product catalog sync.

    Gumroad payloads vary by event type; for this app we refresh catalog
    via API so listed products remain source-of-truth.
    """
    expected_token = settings.GUMROAD_WEBHOOK_TOKEN
    provided = (
        request.POST.get("token")
        or request.POST.get("password")
        or request.headers.get("X-Gumroad-Token", "")
    )
    if expected_token and provided != expected_token:
        return HttpResponseForbidden("Invalid Gumroad token")

    stats = sync_gumroad_products()
    return JsonResponse({"status": "ok", **stats})


@login_required
@require_POST
def martor_local_uploader(request):
    """Upload markdown images to local MEDIA storage for admin users."""
    image = request.FILES.get("markdown-image-upload")
    if not image:
        return JsonResponse({"status": 400, "error": "No image uploaded."}, status=400)

    if not image.content_type.startswith("image/"):
        return JsonResponse({"status": 400, "error": "Invalid file type."}, status=400)

    max_size = 10 * 1024 * 1024
    if image.size > max_size:
        return JsonResponse(
            {"status": 400, "error": "Image exceeds 10MB limit."}, status=400
        )

    base_name = get_valid_filename(os.path.basename(image.name))
    upload_name = f"{uuid.uuid4().hex}_{base_name}"
    relative_path = os.path.join("uploads", "editor", upload_name)
    saved_path = default_storage.save(relative_path, image)
    public_url = settings.MEDIA_URL + saved_path

    return JsonResponse(
        {"status": 200, "link": public_url, "name": os.path.basename(saved_path)}
    )


# --- Digests & agent intake ---------------------------------------------------

INTAKE_MAX_REQUEST_BYTES = 512 * 1024


@csrf_exempt
@require_POST
def intake_api(request):
    """POST /api/intake/ - authenticated agents submit digests as drafts."""
    header = request.headers.get("Authorization", "")
    key = header[7:].strip() if header.lower().startswith("bearer ") else ""
    agent = authenticate_token(key)
    if not agent:
        return JsonResponse(
            {"ok": False, "error": "invalid or missing token"}, status=401
        )

    if len(request.body) > INTAKE_MAX_REQUEST_BYTES:
        return JsonResponse({"ok": False, "error": "request too large"}, status=413)
    try:
        payload = json.loads(request.body or b"{}")
        if not isinstance(payload, dict):
            raise ValueError
    except ValueError:
        return JsonResponse(
            {"ok": False, "error": "body must be a JSON object"}, status=400
        )

    try:
        digest, created = submit_digest(
            series=payload.get("series", ""),
            title=payload.get("title", ""),
            digest_date=payload.get("date", ""),
            body=payload.get("body", "") or "",
            items=payload.get("items"),
            external_id=str(payload.get("external_id", "") or ""),
            tags=payload.get("tags") or [],
            source_url=payload.get("source_url", "") or "",
            source="api",
            agent=agent,
        )
    except IntakeError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "id": digest.pk,
            "created": created,
            "status": digest.status,
            "series": digest.series.slug,
            "external_id": digest.external_id,
            "url": digest.get_absolute_url() if digest.status == "published" else None,
        },
        status=201 if created else 200,
    )


def digest_index(request):
    """Landing page for the Digests section: one card per series."""
    series_list = []
    for series in Series.objects.filter(is_active=True):
        latest = series.digests.filter(status=Digest.STATUS_PUBLISHED).first()
        if latest:
            series_list.append({"series": series, "latest": latest})
    latest_briefing = DailyBriefing.objects.filter(is_published=True).first()
    return render(
        request,
        "blog/digest_index.html",
        {"series_list": series_list, "latest_briefing": latest_briefing},
    )


def digest_series(request, series_slug):
    """List published digests in one series."""
    series = get_object_or_404(Series, slug=series_slug, is_active=True)
    digests = series.digests.filter(status=Digest.STATUS_PUBLISHED).prefetch_related(
        "tags"
    )
    page_obj = Paginator(digests, TILS_PER_PAGE).get_page(request.GET.get("page"))
    return render(
        request, "blog/digest_series.html", {"series": series, "page_obj": page_obj}
    )


def digest_detail(request, series_slug, slug):
    """Show one published digest, rendered in the site's own style."""
    digest = get_object_or_404(
        Digest.objects.select_related("series").prefetch_related("tags"),
        series__slug=series_slug,
        slug=slug,
        status=Digest.STATUS_PUBLISHED,
    )
    return render(
        request,
        "blog/digest_detail.html",
        {"digest": digest, "content_html": render_markdown(digest.body_md)},
    )
