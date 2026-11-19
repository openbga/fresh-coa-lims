from django.urls import path

from . import views

app_name = "planning"
urlpatterns = [
    path("", views.work_list, name="work_list"),
    path("plan/", views.plan, name="plan"),
    path("tests/<int:pk>/take/", views.take, name="take"),
    path("workload/", views.workload, name="workload"),
    path("reminders/", views.reminders, name="reminders"),
    path("figures/", views.figures, name="figures"),
    path("figures/tests/", views.reviewed, name="reviewed"),
    path("targets/", views.targets, name="targets"),
    path("targets/change/", views.targets_change, name="targets_change"),
]
