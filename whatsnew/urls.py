from django.urls import path

from . import views

app_name = "whatsnew"
urlpatterns = [
    path("", views.index, name="index"),
]
