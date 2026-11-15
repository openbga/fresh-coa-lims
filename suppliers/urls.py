from django.urls import path

from . import qualification_views, views

app_name = "suppliers"
urlpatterns = [
    path("", views.supplier_list, name="list"),
    path("new/", views.supplier_new, name="new"),
    path("<int:pk>/", views.supplier_detail, name="detail"),
    path(
        "<int:pk>/qualifications/new/",
        qualification_views.qualification_new,
        name="qualification_new",
    ),
    path(
        "qualifications/<int:pk>/",
        qualification_views.qualification_detail,
        name="qualification_detail",
    ),
    path(
        "qualifications/<int:pk>/approve/",
        qualification_views.qualification_approve,
        name="qualification_approve",
    ),
    path(
        "qualifications/<int:pk>/revoke/",
        qualification_views.qualification_revoke,
        name="qualification_revoke",
    ),
]
