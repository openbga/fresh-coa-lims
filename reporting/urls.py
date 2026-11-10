from django.urls import path

from . import views

app_name = "reporting"
urlpatterns = [
    path("reports/", views.report_list, name="list"),
    path("reports/new/", views.report_new, name="new"),
    path("reports/issue/<int:lot_pk>/", views.issue_preview, name="issue_preview"),
    path("reports/issue/<int:lot_pk>/sign/", views.issue_sign, name="issue_sign"),
    path("reports/<int:pk>/", views.report_detail, name="detail"),
    path("reports/<int:pk>/amend/", views.amend_preview, name="amend_preview"),
    path("reports/<int:pk>/amend/sign/", views.amend_sign, name="amend_sign"),
    path("reports/<int:pk>/versions/<int:number>/", views.version_detail, name="version"),
    path("reports/<int:pk>/versions/<int:number>/pdf/", views.version_pdf, name="pdf"),
]
