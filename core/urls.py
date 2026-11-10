from django.urls import path

from . import views

app_name = "core"
urlpatterns = [
    path("signature-pin/", views.pin, name="pin"),
    path("rules/", views.rules, name="rules"),
    path("rules/<int:pk>/approve/", views.rule_approve, name="rule_approve"),
    path("audit/", views.audit, name="audit"),
]
