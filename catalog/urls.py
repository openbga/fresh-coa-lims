from django.urls import path

from . import views

app_name = "catalog"
urlpatterns = [
    path("", views.specification_list, name="specifications"),
    path("specifications/new/", views.specification_new, name="specification_new"),
    path("specifications/<int:pk>/", views.specification_detail, name="specification"),
    path(
        "specifications/<int:pk>/versions/new/",
        views.specification_version_new,
        name="specification_version_new",
    ),
    path(
        "specification-versions/<int:pk>/",
        views.specification_revision,
        name="specification_revision",
    ),
    path("specification-versions/<int:pk>/tests/new/", views.test_new, name="test_new"),
    path(
        "specification-versions/<int:pk>/tests/<int:line_pk>/remove/",
        views.test_remove,
        name="test_remove",
    ),
    path(
        "specification-versions/<int:pk>/approve/",
        views.specification_approve,
        name="specification_approve",
    ),
    path(
        "specification-versions/<int:pk>/withdraw/",
        views.specification_withdraw,
        name="specification_withdraw",
    ),
    path("methods/", views.method_list, name="methods"),
    path("methods/new/", views.method_new, name="method_new"),
    path("methods/<int:pk>/", views.method_detail, name="method"),
    path("methods/<int:pk>/versions/new/", views.method_version_new, name="method_version_new"),
    path("method-versions/<int:pk>/approve/", views.method_approve, name="method_approve"),
    path("method-versions/<int:pk>/qc-checks/new/", views.qc_check_new, name="qc_check_new"),
    path(
        "method-versions/<int:pk>/qc-checks/<int:check_pk>/remove/",
        views.qc_check_remove,
        name="qc_check_remove",
    ),
    path(
        "method-versions/<int:pk>/calculation/",
        views.calculation_set,
        name="calculation_set",
    ),
    path(
        "method-versions/<int:pk>/calculation/clear/",
        views.calculation_clear,
        name="calculation_clear",
    ),
    path(
        "method-versions/<int:pk>/calculation-inputs/new/",
        views.calculation_input_new,
        name="calculation_input_new",
    ),
    path(
        "method-versions/<int:pk>/calculation-inputs/<int:input_pk>/remove/",
        views.calculation_input_remove,
        name="calculation_input_remove",
    ),
    path("method-versions/<int:pk>/withdraw/", views.method_withdraw, name="method_withdraw"),
    path("materials/", views.material_list, name="materials"),
    path("materials/new/", views.material_new, name="material_new"),
]
