from django.urls import path
from . import views

app_name = "blog"

urlpatterns = [
    path("", views.feed_list, name="index"),
    path("digests/", views.digest_index, name="digest_index"),
    path("digests/<slug:series_slug>/", views.digest_series, name="digest_series"),
    path(
        "digests/<slug:series_slug>/<slug:slug>/",
        views.digest_detail,
        name="digest_detail",
    ),
    path("api/intake/", views.intake_api, name="intake_api"),
    path("briefing/", views.briefing_latest, name="briefing_latest"),
    path("briefings/", views.briefing_list, name="briefing_list"),
    path("briefings/archive/", views.briefing_archive, name="briefing_archive"),
    path("briefings/rss/", views.briefing_rss, name="briefing_rss"),
    path("briefings/<slug:slug>/", views.briefing_detail, name="briefing_detail"),
    path("products/", views.products_list, name="products_list"),
    path("posts/", views.post_list, name="post_list"),
    path("posts/<slug:slug>/", views.post_detail, name="post_detail"),
    path("til/", views.til_list, name="til_list"),
    path("til/<slug:slug>/", views.til_detail, name="til_detail"),
    path("feed/<slug:slug>/", views.feed_detail, name="feed_detail"),
    path("tags/<slug:slug>/", views.tag_detail, name="tag_detail"),
    path("search/", views.search, name="search"),
    path("about/", views.about, name="about"),
    path("webhooks/github/", views.github_webhook, name="github_webhook"),
    path("webhooks/gumroad/", views.gumroad_webhook, name="gumroad_webhook"),
]
