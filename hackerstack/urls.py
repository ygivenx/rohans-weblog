from django.urls import path
from . import views

app_name = "hackerstack"
urlpatterns = [
    path("", views.index, name="index"),
    path("weekly/", views.weekly, name="weekly"),
    path("weekly/rss/", views.weekly_rss, name="weekly_rss"),
    path("weekly/<str:week>/", views.weekly, name="weekly_issue"),
]
