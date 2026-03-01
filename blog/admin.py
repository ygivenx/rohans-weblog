from django.contrib import admin
from django import forms
from martor.widgets import AdminMartorWidget
from .models import BlogPost, TIL, Bookmark, Tag, FeedItem


class BlogPostAdminForm(forms.ModelForm):
    """Custom form for BlogPost with Martor markdown editor."""

    class Meta:
        model = BlogPost
        fields = "__all__"
        widgets = {
            "content": AdminMartorWidget(),
        }


class TILAdminForm(forms.ModelForm):
    """Custom form for TIL with Martor markdown editor."""

    class Meta:
        model = TIL
        fields = "__all__"
        widgets = {
            "content": AdminMartorWidget(),
        }


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    """Admin interface for Tag model."""

    list_display = ["name", "slug"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}
    ordering = ["name"]


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    """Admin interface for BlogPost model."""

    form = BlogPostAdminForm
    list_display = [
        "title",
        "slug",
        "is_published",
        "published_date",
        "created_date",
        "updated_date",
    ]
    list_filter = ["is_published", "published_date", "created_date", "tags"]
    search_fields = ["title", "content", "slug"]
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ["tags"]
    date_hierarchy = "published_date"
    ordering = ["-published_date", "-created_date"]

    fieldsets = (
        ("Content", {"fields": ("title", "slug", "content")}),
        ("Publishing", {"fields": ("is_published", "published_date")}),
        (
            "Metadata",
            {
                "fields": ("tags", "created_date", "updated_date"),
                "classes": ("collapse",),
            },
        ),
    )

    readonly_fields = ["created_date", "updated_date"]


@admin.register(TIL)
class TILAdmin(admin.ModelAdmin):
    """Admin interface for TIL model."""

    form = TILAdminForm
    list_display = ["title", "slug", "created_date"]
    list_filter = ["created_date", "tags"]
    search_fields = ["title", "content", "slug"]
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ["tags"]
    date_hierarchy = "created_date"
    ordering = ["-created_date"]

    fieldsets = (
        ("Content", {"fields": ("title", "slug", "content")}),
        ("Metadata", {"fields": ("tags", "created_date"), "classes": ("collapse",)}),
    )

    readonly_fields = ["created_date"]


@admin.register(Bookmark)
class BookmarkAdmin(admin.ModelAdmin):
    """Admin interface for Bookmark model."""

    list_display = ["title", "url", "created_date", "via_url"]
    list_filter = ["created_date", "tags"]
    search_fields = ["title", "url", "description", "via_url"]
    filter_horizontal = ["tags"]
    date_hierarchy = "created_date"
    ordering = ["-created_date"]

    fieldsets = (
        (
            "Bookmark Information",
            {"fields": ("title", "url", "description", "via_url")},
        ),
        ("Metadata", {"fields": ("tags", "created_date"), "classes": ("collapse",)}),
    )

    readonly_fields = ["created_date"]


class FeedItemAdminForm(forms.ModelForm):
    """Custom form for FeedItem with Martor markdown editor."""

    class Meta:
        model = FeedItem
        fields = "__all__"
        widgets = {
            "body": AdminMartorWidget(),
        }


@admin.register(FeedItem)
class FeedItemAdmin(admin.ModelAdmin):
    """Admin interface for FeedItem model."""

    form = FeedItemAdminForm
    list_display = ["__str__", "content_type", "slug", "created_date"]
    list_filter = ["content_type", "created_date", "tags"]
    search_fields = ["title", "body", "url", "slug"]
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ["tags"]
    date_hierarchy = "created_date"
    ordering = ["-created_date"]

    fieldsets = (
        ("Content", {"fields": ("content_type", "title", "slug", "url", "body")}),
        ("Metadata", {"fields": ("tags", "created_date")}),
    )

    readonly_fields = ["created_date"]
