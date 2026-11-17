from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.urls import include, path

from accounts.views import SignIn, login_passkey, login_sso, login_sso_callback, login_verify
from config import views

handler403 = "accounts.views.permission_denied"

urlpatterns = [
    path("health/", views.health, name="health"),
    path("ready/", views.ready, name="ready"),
    path("accounts/login/", SignIn.as_view(), name="login"),
    path("accounts/login/verify/", login_verify, name="login_verify"),
    path("accounts/login/passkey/", login_passkey, name="login_passkey"),
    path("accounts/login/sso/", login_sso, name="login_sso"),
    path("accounts/login/sso/callback/", login_sso_callback, name="login_sso_callback"),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("accounts/", include("accounts.urls")),
    path("admin/", admin.site.urls),
    path("page-docs/", include("pagedocs.urls")),
    path("", include("core.urls")),
    path("", include("quality.urls")),
    path("testing/", include("analytical.urls")),
    path("stability/", include("stability.urls")),
    path("sampling/", include("sampling.urls")),
    path("catalog/", include("catalog.urls")),
    path("suppliers/", include("suppliers.urls")),
    path("laboratory/", include("laboratory.urls")),
    path("validation/", include("validation.urls")),
    path("", include("reporting.urls")),
]
