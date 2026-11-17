from django.urls import path

from reporting import views as reporting_views

from . import acceptance_views, certificate_views, rejection_views, views

app_name = "quality"
urlpatterns = [
    path("", views.lot_list, name="lot_list"),
    path("lots/new/", views.lot_new, name="lot_new"),
    path("lots/<int:pk>/", views.lot_detail, name="lot_detail"),
    # The export reads every app's records, so it lives in reporting; it is part of the lot.
    path("lots/<int:pk>/record/", reporting_views.lot_record_export, name="lot_record"),
    path("lots/<int:pk>/receipt/new/", views.receipt_new, name="receipt_new"),
    path("lots/<int:pk>/receipt/correct/", views.receipt_correct, name="receipt_correct"),
    path(
        "lots/<int:pk>/supplier-certificates/new/",
        certificate_views.certificate_new,
        name="certificate_new",
    ),
    path(
        "supplier-certificates/<int:pk>/",
        certificate_views.certificate_detail,
        name="certificate_detail",
    ),
    path(
        "supplier-certificates/<int:pk>/correct/",
        certificate_views.certificate_correct,
        name="certificate_correct",
    ),
    path(
        "supplier-certificates/<int:pk>/withdraw/",
        certificate_views.certificate_withdraw,
        name="certificate_withdraw",
    ),
    path(
        "supplier-results/<int:pk>/propose/",
        acceptance_views.acceptance_new,
        name="acceptance_new",
    ),
    path(
        "supplier-result-acceptances/<int:pk>/",
        acceptance_views.acceptance_detail,
        name="acceptance_detail",
    ),
    path(
        "supplier-result-acceptances/<int:pk>/accept/",
        acceptance_views.acceptance_accept,
        name="acceptance_accept",
    ),
    path(
        "supplier-result-acceptances/<int:pk>/withdraw/",
        acceptance_views.acceptance_withdraw,
        name="acceptance_withdraw",
    ),
    path("lots/<int:pk>/samples/new/", views.sample_new, name="sample_new"),
    path("samples/<int:pk>/results/new/", views.result_new, name="result_new"),
    path("results/<int:pk>/review/", views.sign, {"action": "review"}, name="review"),
    path("lots/<int:pk>/disposition/", views.sign, {"action": "disposition"}, name="disposition"),
    path("lots/<int:pk>/reject/", rejection_views.lot_reject, name="lot_reject"),
    path("lots/<int:pk>/cancel/", rejection_views.lot_cancel, name="lot_cancel"),
]
