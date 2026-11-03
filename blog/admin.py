from django.contrib import admin, messages
from django import forms
from martor.widgets import AdminMartorWidget
from .briefings import (
    extract_briefing_metadata,
    sanitize_briefing_html,
    mirror_briefing_to_feed,
)
from .intake import (
    create_agent_token,
    publish_digest,
    unpublish_digest,
)
from .models import (
    AgentToken,
    BlogPost,
    TIL,
    Bookmark,
    Tag,
    FeedItem,
    ProductUpdate,
    DailyBriefing,
    Digest,
    Series,
)


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


@admin.register(ProductUpdate)
class ProductUpdateAdmin(admin.ModelAdmin):
    """Admin interface for product updates ingested from external sources."""

    list_display = [
        "title",
        "source",
        "kind",
        "owner",
        "repo",
        "price",
        "published_at",
        "is_visible",
    ]
    list_filter = ["source", "kind", "is_visible", "published_at"]
    search_fields = ["title", "external_id", "owner", "repo", "product_slug", "url"]
    ordering = ["-published_at", "-created_date"]
    readonly_fields = [
        "external_id",
        "raw_payload",
        "created_date",
        "updated_date",
        "mirrored_feed_item",
    ]


class DailyBriefingAdminForm(forms.ModelForm):
    """Admin form allowing 1-click upload of a Gemini HTML briefing artifact."""

    html_file = forms.FileField(
        required=False,
        help_text="Upload a daily_intelligence_briefing_*.html file to automatically extract metadata, strip emails/Gmail links, and populate all fields.",
    )

    class Meta:
        model = DailyBriefing
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].required = False
        self.fields["briefing_date"].required = False
        self.fields["sanitized_html"].required = False

    def clean(self):
        cleaned_data = super().clean()
        uploaded = cleaned_data.get("html_file")
        raw_html = cleaned_data.get("sanitized_html") or ""
        filename = ""

        if uploaded:
            filename = uploaded.name
            raw_html = uploaded.read().decode("utf-8", errors="replace")

        if raw_html:
            meta = extract_briefing_metadata(
                raw_html,
                briefing_date=cleaned_data.get("briefing_date"),
                filename=filename,
            )
            cleaned_data["sanitized_html"] = sanitize_briefing_html(raw_html)
            if not cleaned_data.get("title"):
                cleaned_data["title"] = meta["title"]
            if not cleaned_data.get("briefing_date"):
                cleaned_data["briefing_date"] = meta["briefing_date"]
            if not cleaned_data.get("edition_meta"):
                cleaned_data["edition_meta"] = meta["edition_meta"]
            if not cleaned_data.get("signal_count"):
                cleaned_data["signal_count"] = meta["signal_count"]
            if not cleaned_data.get("executive_summary_md"):
                cleaned_data["executive_summary_md"] = meta["executive_summary_md"]
            if not cleaned_data.get("metrics_json"):
                cleaned_data["metrics_json"] = meta["metrics_json"]
            if not cleaned_data.get("slug") and cleaned_data.get("briefing_date"):
                cleaned_data["slug"] = cleaned_data["briefing_date"].isoformat()

        if not cleaned_data.get("sanitized_html"):
            raise forms.ValidationError(
                "Please either upload an HTML file or paste HTML into Sanitized HTML."
            )
        if not cleaned_data.get("briefing_date"):
            raise forms.ValidationError("Briefing date is required.")
        if not cleaned_data.get("title"):
            cleaned_data["title"] = (
                f"Daily Intelligence Briefing • {cleaned_data['briefing_date'].strftime('%B %d, %Y')}"
            )
        return cleaned_data


@admin.register(DailyBriefing)
class DailyBriefingAdmin(admin.ModelAdmin):
    """Admin interface for Daily Intelligence Briefings."""

    form = DailyBriefingAdminForm
    list_display = [
        "briefing_date",
        "title",
        "signal_count",
        "edition_meta",
        "is_published",
        "created_date",
    ]
    list_filter = ["is_published", "briefing_date", "tags"]
    search_fields = ["title", "slug", "executive_summary_md", "edition_meta"]
    filter_horizontal = ["tags"]
    date_hierarchy = "briefing_date"
    ordering = ["-briefing_date", "-created_date"]
    readonly_fields = ["created_date", "updated_date", "mirrored_feed_item"]

    fieldsets = (
        (
            "Quick Upload (Gemini HTML Artifact)",
            {"fields": ("html_file", "is_published")},
        ),
        (
            "Briefing Metadata (Auto-filled from HTML if blank)",
            {
                "fields": (
                    "title",
                    "slug",
                    "briefing_date",
                    "edition_meta",
                    "signal_count",
                    "executive_summary_md",
                    "metrics_json",
                )
            },
        ),
        (
            "Sanitized Interactive HTML",
            {
                "fields": ("sanitized_html",),
                "classes": ("collapse",),
            },
        ),
        (
            "System & Feed Mirror",
            {
                "fields": (
                    "tags",
                    "mirrored_feed_item",
                    "created_date",
                    "updated_date",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        mirror_briefing_to_feed(obj)


@admin.register(Series)
class SeriesAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "auto_publish", "is_active"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(AgentToken)
class AgentTokenAdmin(admin.ModelAdmin):
    """Create a token here; the key is displayed exactly once, then only a hash is kept."""

    list_display = ["name", "prefix", "is_active", "last_used_at", "created_date"]
    list_filter = ["is_active"]
    fields = ["name", "is_active", "prefix", "last_used_at", "created_date"]
    readonly_fields = ["prefix", "last_used_at", "created_date"]

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
            return
        token, key = create_agent_token(obj.name)
        obj.pk, obj.prefix = token.pk, token.prefix
        obj._state.adding = False
        messages.warning(
            request,
            f"Key for {token.name} (copy it now, it will not be shown again): {key}",
        )


@admin.action(description="Publish selected digests")
def publish_selected(modeladmin, request, queryset):
    for digest in queryset:
        publish_digest(digest)
    modeladmin.message_user(request, f"Published {queryset.count()} digest(s).")


@admin.action(description="Unpublish selected digests (back to draft)")
def unpublish_selected(modeladmin, request, queryset):
    for digest in queryset:
        unpublish_digest(digest)
    modeladmin.message_user(request, f"Moved {queryset.count()} digest(s) to draft.")


@admin.register(Digest)
class DigestAdmin(admin.ModelAdmin):
    """Editorial desk: agent submissions land here as drafts."""

    list_display = ["title", "series", "digest_date", "status", "source", "agent"]
    list_filter = ["status", "series", "source", "agent"]
    search_fields = ["title", "body_md", "external_id"]
    filter_horizontal = ["tags"]
    date_hierarchy = "digest_date"
    actions = [publish_selected, unpublish_selected]
    readonly_fields = [
        "source",
        "agent",
        "published_at",
        "mirrored_feed_item",
        "created_date",
        "updated_date",
    ]
    fields = [
        "series",
        "title",
        "digest_date",
        "external_id",
        "slug",
        "body_md",
        "source_url",
        "tags",
        "status",
        "source",
        "agent",
        "published_at",
        "mirrored_feed_item",
        "created_date",
        "updated_date",
    ]

    def save_model(self, request, obj, form, change):
        requested = form.cleaned_data["status"]
        prior = Digest.objects.get(pk=obj.pk).status if change else None
        if not change:
            obj.source = "admin"
        # Save as the prior status, then let the pipeline apply the transition
        # so the Feed card is created/updated/removed consistently.
        obj.status = prior or Digest.STATUS_DRAFT
        super().save_model(request, obj, form, change)
        if requested == Digest.STATUS_PUBLISHED:
            publish_digest(obj)
        elif prior == Digest.STATUS_PUBLISHED:
            unpublish_digest(obj)
