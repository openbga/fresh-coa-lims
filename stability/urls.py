from django.urls import path

from . import shelf_life_views, views

app_name = "stability"
urlpatterns = [
    path("", views.overview, name="overview"),
    path("protocols/", views.protocol_list, name="protocol_list"),
    path("protocols/new/", views.protocol_new, name="protocol_new"),
    path("protocols/<int:pk>/", views.protocol_detail, name="protocol_detail"),
    path("protocols/<int:pk>/conditions/new/", views.condition_new, name="condition_new"),
    path("protocols/<int:pk>/timepoints/new/", views.timepoint_new, name="timepoint_new"),
    path("protocols/<int:pk>/approve/", views.protocol_approve, name="protocol_approve"),
    path("protocols/<int:pk>/withdraw/", views.protocol_withdraw, name="protocol_withdraw"),
    path("studies/", views.study_list, name="study_list"),
    path("studies/new/", views.study_new, name="study_new"),
    path("studies/<int:pk>/", views.study_detail, name="study_detail"),
    path("studies/<int:pk>/close/", views.study_close, name="study_close"),
    path("pulls/", views.pull_list, name="pull_list"),
    path("pulls/<int:pk>/", views.pull_detail, name="pull_detail"),
    path("pulls/<int:pk>/record/", views.pull_record, name="pull_record"),
    path("pulls/<int:pk>/tests/", views.pull_tests, name="pull_tests"),
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
    path("shelf-life/", shelf_life_views.shelf_life_list, name="shelf_life_list"),
    path("shelf-life/new/", shelf_life_views.shelf_life_new, name="shelf_life_new"),
    path("shelf-life/<int:pk>/", shelf_life_views.shelf_life_detail, name="shelf_life_detail"),
    path(
        "shelf-life/<int:pk>/change/",
        shelf_life_views.shelf_life_change,
        name="shelf_life_change",
    ),
    path(
        "shelf-life/<int:pk>/withdraw/",
        shelf_life_views.shelf_life_withdraw,
        name="shelf_life_withdraw",
    ),
    path(
        "shelf-life/<int:pk>/conclude/",
        shelf_life_views.shelf_life_conclude,
        name="shelf_life_conclude",
    ),
]
