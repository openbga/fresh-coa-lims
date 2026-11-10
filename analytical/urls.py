from django.urls import path

from . import views

app_name = "analytical"
urlpatterns = [
    path("", views.test_list, name="test_list"),
    path("lot/<int:pk>/", views.lot_testing, name="lot_testing"),
    path("tests/<int:pk>/", views.test_detail, name="test_detail"),
    path("tests/<int:pk>/observations/new/", views.observation_new, name="observation_new"),
    path("observations/<int:pk>/correct/", views.observation_correct, name="observation_correct"),
    path("tests/<int:pk>/batch/", views.test_batch, name="test_batch"),
    path("tests/<int:pk>/return/", views.test_return, name="test_return"),
    path("tests/<int:pk>/review/", views.test_review, name="test_review"),
    path("batches/", views.batch_list, name="batch_list"),
    path("batches/new/", views.batch_new, name="batch_new"),
    path("batches/<int:pk>/", views.batch_detail, name="batch_detail"),
    path("batches/<int:pk>/qc/<slug:code>/", views.qc_record, name="qc_record"),
    path("qc/<int:pk>/correct/", views.qc_correct, name="qc_correct"),
    path("batches/<int:pk>/reject/", views.batch_reject, name="batch_reject"),
    path("investigations/", views.investigation_list, name="investigation_list"),
    path("investigations/<int:pk>/", views.investigation_detail, name="investigation_detail"),
    path("investigations/<int:pk>/entries/new/", views.entry_new, name="entry_new"),
    path("investigations/<int:pk>/escalate/", views.escalate, name="escalate"),
    path("investigations/<int:pk>/authorize/", views.authorize, name="authorize"),
    path("investigations/<int:pk>/conclude/", views.conclude, name="conclude"),
]
