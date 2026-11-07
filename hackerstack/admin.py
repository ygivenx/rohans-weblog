from django.contrib import admin
from .models import BackfillWindow, CollectionRun, Evidence, Resource
from .ranking import rerank


class EvidenceInline(admin.TabularInline):
    model = Evidence
    extra = 0


@admin.register(BackfillWindow)
class BackfillWindowAdmin(admin.ModelAdmin):
    list_display = (
        "query",
        "start",
        "end",
        "status",
        "page",
        "expected_hits",
        "indexed_hits",
    )
    list_filter = ("status", "category")
    readonly_fields = tuple(f.name for f in BackfillWindow._meta.fields)

    def has_add_permission(self, request):
        return False


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "kind",
        "curated",
        "score",
        "content_date",
        "is_active",
    )
    list_filter = ("category", "kind", "curated", "is_active")
    search_fields = ("title", "url", "description")
    readonly_fields = (
        "score",
        "popularity",
        "freshness",
        "corroboration",
        "evidence_count",
        "ranked_at",
        "search_text",
    )
    inlines = [EvidenceInline]

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        rerank()


@admin.register(CollectionRun)
class CollectionRunAdmin(admin.ModelAdmin):
    list_display = (
        "started_at",
        "source",
        "status",
        "requests",
        "cache_hits",
        "records",
    )
    readonly_fields = tuple(f.name for f in CollectionRun._meta.fields)

    def has_add_permission(self, request):
        return False
