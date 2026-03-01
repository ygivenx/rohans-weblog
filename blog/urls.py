from django.urls import path
from . import views

app_name = "blog"

urlpatterns = [
    path("", views.feed_list, name="index"),
    path("posts/", views.post_list, name="post_list"),
    path("posts/<slug:slug>/", views.post_detail, name="post_detail"),
    path("til/", views.til_list, name="til_list"),
    path("til/<slug:slug>/", views.til_detail, name="til_detail"),
    path("feed/<slug:slug>/", views.feed_detail, name="feed_detail"),
    path("tags/<slug:slug>/", views.tag_detail, name="tag_detail"),
    path("search/", views.search, name="search"),
    path("about/", views.about, name="about"),
]
