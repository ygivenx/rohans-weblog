"""
URL configuration for rohans_weblog project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from blog.views import martor_local_uploader

urlpatterns = [
    path(
        "favicon.ico",
        RedirectView.as_view(url="/static/icons/favicon.png", permanent=False),
        name="favicon",
    ),
    path("admin/", admin.site.urls),
    path("martor/uploader/", martor_local_uploader, name="martor_uploader"),
    path("martor/", include("martor.urls")),
    path("", include("blog.urls")),
]
