from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import include, path

from config import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("ready/", views.ready, name="ready"),
    path("accounts/login/", LoginView.as_view(), name="login"),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("admin/", admin.site.urls),
    path("page-docs/", include("pagedocs.urls")),
    path("", include("core.urls")),
    path("", include("quality.urls")),
    path("testing/", include("analytical.urls")),
    path("stability/", include("stability.urls")),
    path("sampling/", include("sampling.urls")),
    path("catalog/", include("catalog.urls")),
    path("laboratory/", include("laboratory.urls")),
    path("", include("reporting.urls")),
]
