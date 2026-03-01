from django.db.models import Count, Q
from .models import Tag


def all_tags(request):
    """Inject all tags with total content counts into every template."""
    tags = Tag.objects.annotate(
        post_count=Count("blog_posts", filter=Q(blog_posts__is_published=True), distinct=True),
        til_count=Count("tils", distinct=True),
        feed_count=Count("feed_items", distinct=True),
    ).order_by("name")

    for tag in tags:
        tag.total_count = tag.post_count + tag.til_count + tag.feed_count

    return {"all_tags": [t for t in tags if t.total_count > 0]}
