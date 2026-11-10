from django.urls import path

from . import views

app_name = "laboratory"
urlpatterns = [
    path("", views.overview, name="overview"),
    path("equipment/", views.equipment_list, name="equipment_list"),
    path("equipment/new/", views.equipment_new, name="equipment_new"),
    path("equipment/<int:pk>/", views.equipment_detail, name="equipment_detail"),
    path("equipment/<int:pk>/calibrations/new/", views.calibration_new, name="calibration_new"),
    path(
        "equipment/<int:pk>/out-of-service/",
        views.equipment_out_of_service,
        name="equipment_out_of_service",
    ),
    path("equipment/<int:pk>/return-to-service/", views.equipment_return, name="equipment_return"),
    path(
        "equipment/<int:equipment_pk>/qualifications/new/",
        views.qualification_new,
        name="equipment_qualification_new",
    ),
    path("calibrations/", views.calibration_list, name="calibration_list"),
    path("calibrations/<int:pk>/accept/", views.calibration_accept, name="calibration_accept"),
    path("qualifications/", views.qualification_list, name="qualification_list"),
    path("qualifications/new/", views.qualification_new, name="qualification_new"),
    path("qualifications/<int:pk>/", views.qualification_detail, name="qualification_detail"),
    path(
        "qualifications/<int:pk>/approve/",
        views.qualification_approve,
        name="qualification_approve",
    ),
    path(
        "qualifications/<int:pk>/revoke/", views.qualification_revoke, name="qualification_revoke"
    ),
    path("reagents/", views.reagent_list, name="reagent_list"),
    path("reagents/new/", views.reagent_new, name="reagent_new"),
    path("reagents/<int:pk>/", views.reagent_detail, name="reagent_detail"),
    path("reagents/<int:pk>/release/", views.reagent_release, name="reagent_release"),
    path("reagents/<int:pk>/reject/", views.reagent_reject, name="reagent_reject"),
    path("uses/", views.use_list, name="use_list"),
    path("uses/new/", views.use_new, name="use_new"),
]
