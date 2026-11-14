from django.urls import path

from . import certificate_views, views

app_name = "quality"
urlpatterns = [
    path("", views.lot_list, name="lot_list"),
    path("lots/new/", views.lot_new, name="lot_new"),
    path("lots/<int:pk>/", views.lot_detail, name="lot_detail"),
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
    path("lots/<int:pk>/samples/new/", views.sample_new, name="sample_new"),
    path("samples/<int:pk>/results/new/", views.result_new, name="result_new"),
    path("results/<int:pk>/review/", views.sign, {"action": "review"}, name="review"),
    path("lots/<int:pk>/disposition/", views.sign, {"action": "disposition"}, name="disposition"),
]
