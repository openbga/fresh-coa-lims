from django.urls import include, path

from config.urls import urlpatterns as base

# The integrator registers reporting.urls in config.urls; add it here only until then.
registered = any(getattr(p, "app_name", None) == "reporting" for p in base)
urlpatterns = list(base) if registered else [*base, path("", include("reporting.urls"))]
