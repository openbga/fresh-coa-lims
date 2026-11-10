from django.urls import path

from . import views

app_name = "sampling"
urlpatterns = [
    path("", views.lot_list, name="lots"),
    path("lots/<int:pk>/", views.lot_detail, name="lot"),
    path("lots/<int:pk>/requirements/", views.assign, name="assign"),
    path("lots/<int:pk>/sampling/new/", views.sampling_new, name="sampling_new"),
    path("records/<int:pk>/correct/", views.sampling_correct, name="sampling_correct"),
    path("records/<int:pk>/deviation/", views.deviation_assess, name="deviation_assess"),
    path("plans/", views.plan_list, name="plans"),
    path("plans/new/", views.plan_new, name="plan_new"),
    path("plans/<int:pk>/", views.plan_detail, name="plan"),
    path("plans/<int:pk>/versions/new/", views.plan_version_new, name="plan_version_new"),
    path("plan-versions/<int:pk>/approve/", views.plan_approve, name="plan_approve"),
    path("plan-versions/<int:pk>/withdraw/", views.plan_withdraw, name="plan_withdraw"),
]
