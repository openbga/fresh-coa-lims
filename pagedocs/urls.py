from django.urls import path

from . import views

app_name = "pagedocs"
urlpatterns = [
    path("", views.page_doc, name="doc"),
]
