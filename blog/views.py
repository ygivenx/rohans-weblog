from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator

from .models import BlogPost, TIL, Bookmark, FeedItem
from .search import search_content
from .utils import render_markdown, POSTS_PER_PAGE, TILS_PER_PAGE, BOOKMARKS_PER_PAGE, FEED_PER_PAGE


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
    else:
        results = {
            "posts": BlogPost.objects.none(),
            "tils": TIL.objects.none(),
            "bookmarks": Bookmark.objects.none(),
            "feed_items": FeedItem.objects.none(),
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
    """List all feed items (paginated)."""
    items = FeedItem.objects.prefetch_related("tags").order_by("-created_date")

    paginator = Paginator(items, FEED_PER_PAGE)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    for item in page_obj:
        item.body_html = render_markdown(item.body)

    return render(
        request,
        "blog/feed_list.html",
        {
            "page_obj": page_obj,
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


def about(request):
    """Display the about page."""
    return render(request, "blog/about.html")
