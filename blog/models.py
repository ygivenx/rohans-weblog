from django.db import models
from django.utils.text import slugify
from django.urls import reverse
from django.utils import timezone


class Tag(models.Model):
    """Reusable tag model for all content types."""

    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("tag_detail", kwargs={"slug": self.slug})


class BlogPost(models.Model):
    """Blog post model with markdown content."""

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    content = models.TextField(help_text="Markdown content")
    published_date = models.DateTimeField(null=True, blank=True)
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name="blog_posts")
    is_published = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["-published_date", "-created_date"]
        verbose_name = "Blog Post"
        verbose_name_plural = "Blog Posts"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("post_detail", kwargs={"slug": self.slug})


class TIL(models.Model):
    """Today I Learned entry model."""

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    content = models.TextField(help_text="Markdown content")
    created_date = models.DateTimeField(auto_now_add=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name="tils")

    class Meta:
        ordering = ["-created_date"]
        verbose_name = "TIL"
        verbose_name_plural = "TILs"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("til_detail", kwargs={"slug": self.slug})


class Bookmark(models.Model):
    """Bookmark model for saving interesting links."""

    url = models.URLField()
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_date = models.DateTimeField(auto_now_add=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name="bookmarks")
    via_url = models.URLField(
        blank=True, null=True, help_text="URL where this was found"
    )

    class Meta:
        ordering = ["-created_date"]
        verbose_name = "Bookmark"
        verbose_name_plural = "Bookmarks"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return self.url


class FeedItem(models.Model):
    """Feed item for microblog/tumblelog: links, notes, and code snippets."""

    CONTENT_TYPE_CHOICES = [
        ("link", "Link"),
        ("note", "Note"),
        ("code", "Code"),
    ]

    content_type = models.CharField(max_length=10, choices=CONTENT_TYPE_CHOICES)
    title = models.CharField(max_length=200, blank=True)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    url = models.URLField(blank=True, help_text="URL for link-type items")
    body = models.TextField(help_text="Markdown content")
    created_date = models.DateTimeField(auto_now_add=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name="feed_items")

    class Meta:
        ordering = ["-created_date"]
        verbose_name = "Feed Item"
        verbose_name_plural = "Feed Items"

    def __str__(self):
        return self.title or self.body[:50]

    def save(self, *args, **kwargs):
        if not self.slug:
            source = self.title or self.body[:50]
            base_slug = slugify(source)
            if not base_slug:
                base_slug = "feed-item"
            slug = base_slug
            n = 1
            while FeedItem.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("blog:feed_detail", kwargs={"slug": self.slug})


class ProductUpdate(models.Model):
    """Normalized store for external product updates (GitHub and Gumroad)."""

    SOURCE_CHOICES = [
        ("github", "GitHub"),
        ("gumroad", "Gumroad"),
    ]
    KIND_CHOICES = [
        ("release", "Release"),
        ("product", "Product"),
    ]

    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    external_id = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    summary = models.TextField(blank=True)
    url = models.URLField()
    owner = models.CharField(max_length=100, blank=True)
    repo = models.CharField(max_length=200, blank=True)
    version = models.CharField(max_length=100, blank=True)
    price = models.CharField(max_length=50, blank=True)
    currency = models.CharField(max_length=10, blank=True)
    product_slug = models.CharField(max_length=200, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    published_at = models.DateTimeField(default=timezone.now)
    is_visible = models.BooleanField(default=True, db_index=True)
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    mirrored_feed_item = models.OneToOneField(
        FeedItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="product_update",
    )

    class Meta:
        ordering = ["-published_at", "-created_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"], name="unique_source_external_id"
            )
        ]

    def __str__(self):
        return f"{self.get_source_display()}: {self.title}"

    @property
    def display_title(self):
        if self.source == "github":
            repo = (
                f"{self.owner}/{self.repo}" if self.owner and self.repo else self.repo
            )
            version = self.version or "release"
            if repo:
                return f"`{repo}` -> `{version}`"
            return f"GitHub release -> `{version}`"
        return self.title

    @property
    def display_summary(self):
        if self.source == "gumroad" and self.summary:
            return self.summary
        if self.source == "github" and self.summary:
            return self.summary
        return ""

    @property
    def display_meta(self):
        if self.source == "github":
            repo = (
                f"{self.owner}/{self.repo}" if self.owner and self.repo else self.repo
            )
            return f"github · {repo}" if repo else "github"
        if self.source == "gumroad":
            if self.price:
                return f"gumroad · {self.price}"
            return "gumroad"
        return self.source

    @property
    def display_cta_text(self):
        return "Buy now" if self.source == "gumroad" else "View release"
