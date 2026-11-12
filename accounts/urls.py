from django.urls import path

from . import views

app_name = "accounts"
urlpatterns = [
    path("access/", views.access, name="access"),
    path("password/", views.password_change, name="password_change"),
    path("announcement/", views.announcement, name="announcement"),
    path("users/", views.user_list, name="user_list"),
    path("users/new/", views.user_create, name="user_create"),
    path("users/<int:pk>/", views.user_detail, name="user_detail"),
    path("users/<int:pk>/<str:action>/", views.user_action, name="user_action"),
]
