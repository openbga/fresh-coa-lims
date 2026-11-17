from django.urls import path

from . import lookups, preferences, views

app_name = "core"
urlpatterns = [
    path("signature-pin/", views.pin_status, name="pin_status"),
    path("signature-pin/change/", views.pin, name="pin"),
    path("rules/", views.rules, name="rules"),
    path("rules/<int:pk>/approve/", views.rule_approve, name="rule_approve"),
    path("audit/", views.audit, name="audit"),
    path("lookups/<slug:name>/", lookups.lookup, name="lookup"),
    path("preferences/", preferences.preference, name="preference"),
]
