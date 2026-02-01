from django.urls import path
from . import views

app_name = "blog"

urlpatterns = [
    path("", views.index, name="index"),
    path("about/", views.about, name="about"),
    path("posts/<slug:slug>/", views.post_detail, name="post_detail"),
    path("til/", views.til_list, name="til_list"),
    path("til/<slug:slug>/", views.til_detail, name="til_detail"),
    path("bookmarks/", views.bookmarks_list, name="bookmarks_list"),
    path("search/", views.search, name="search"),
]
