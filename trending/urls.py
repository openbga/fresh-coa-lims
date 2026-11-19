from django.urls import path

from . import views

app_name = "trending"

urlpatterns = [
    path("", views.chart_list, name="chart_list"),
    path("new/", views.chart_new, name="chart_new"),
    path("<int:pk>/", views.chart_detail, name="chart_detail"),
    path("<int:pk>/limits/new/", views.limits_new, name="limits_new"),
    path("limits/<int:pk>/", views.limits_detail, name="limits_detail"),
    path("limits/<int:pk>/change/", views.limits_edit, name="limits_edit"),
    path("limits/<int:pk>/approve/", views.limits_approve, name="limits_approve"),
    path("evaluations/", views.evaluation_list, name="evaluation_list"),
    path("<int:pk>/evaluations/new/", views.evaluation_new, name="evaluation_new"),
    path("evaluations/<int:pk>/", views.evaluation_detail, name="evaluation_detail"),
    path("evaluations/<int:pk>/alerts/", views.evaluation_alerts, name="evaluation_alerts"),
    path("evaluations/<int:pk>/findings/", views.evaluation_findings, name="evaluation_findings"),
    path("evaluations/<int:pk>/conclude/", views.evaluation_conclude, name="evaluation_conclude"),
]
