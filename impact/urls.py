from django.urls import path

from . import views

app_name = "impact"
urlpatterns = [
    path("", views.assessment_list, name="list"),
    path("new/", views.assessment_new, name="new"),
    path("<int:pk>/", views.assessment_detail, name="detail"),
    path("<int:pk>/find/", views.assessment_find, name="find"),
    path("<int:pk>/records/new/", views.record_add, name="add"),
    path("<int:pk>/conclude/", views.assessment_conclude, name="conclude"),
    path("<int:pk>/withdraw/", views.assessment_withdraw, name="withdraw"),
    path("records/<int:pk>/decide/", views.record_decide, name="decide"),
    path("records/<int:pk>/hold/", views.record_hold, name="hold"),
]
