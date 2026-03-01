from django.db import models
from django.utils.text import slugify
from django.urls import reverse


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
        return reverse("feed_detail", kwargs={"slug": self.slug})
