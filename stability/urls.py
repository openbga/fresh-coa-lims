from django.urls import path

from . import views

app_name = "stability"
urlpatterns = [
    path("", views.overview, name="overview"),
    path("protocols/", views.protocol_list, name="protocol_list"),
    path("protocols/new/", views.protocol_new, name="protocol_new"),
    path("protocols/<int:pk>/", views.protocol_detail, name="protocol_detail"),
    path("protocols/<int:pk>/conditions/new/", views.condition_new, name="condition_new"),
    path("protocols/<int:pk>/timepoints/new/", views.timepoint_new, name="timepoint_new"),
    path("protocols/<int:pk>/approve/", views.protocol_approve, name="protocol_approve"),
    path("studies/", views.study_list, name="study_list"),
    path("studies/new/", views.study_new, name="study_new"),
    path("studies/<int:pk>/", views.study_detail, name="study_detail"),
    path("studies/<int:pk>/close/", views.study_close, name="study_close"),
    path("pulls/", views.pull_list, name="pull_list"),
    path("pulls/<int:pk>/", views.pull_detail, name="pull_detail"),
    path("pulls/<int:pk>/record/", views.pull_record, name="pull_record"),
    path("pulls/<int:pk>/evidence/", views.pull_evidence, name="pull_evidence"),
    path("pulls/<int:pk>/missed/", views.pull_missed, name="pull_missed"),
    path("pulls/<int:pk>/accept/", views.pull_accept, name="pull_accept"),
    path("reserves/", views.reserve_list, name="reserve_list"),
    path("reserves/new/", views.reserve_new, name="reserve_new"),
    path("reserves/<int:pk>/", views.reserve_detail, name="reserve_detail"),
    path("retention/new/", views.obligation_new, name="obligation_new"),
    path("retention/<int:pk>/anchor/", views.anchor_set, name="anchor_set"),
    path("holds/", views.hold_list, name="hold_list"),
    path("holds/new/", views.hold_new, name="hold_new"),
    path("holds/<int:pk>/", views.hold_detail, name="hold_detail"),
    path("holds/<int:pk>/release/", views.hold_release, name="hold_release"),
]
