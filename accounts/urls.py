from django.urls import path

from . import views

app_name = "accounts"
urlpatterns = [
    path("access/", views.access, name="access"),
    path("password/", views.password, name="password"),
    path("password/change/", views.password_change, name="password_change"),
    path("two-factor/", views.two_factor_page, name="two_factor"),
    path("two-factor/setup/", views.two_factor_setup, name="two_factor_setup"),
    path("two-factor/security-key/", views.security_key_add, name="security_key_add"),
    path("single-sign-on/", views.single_sign_on_page, name="single_sign_on"),
    path("announcement/", views.announcement, name="announcement"),
    path("announcement/change/", views.announcement_change, name="announcement_change"),
    path("users/", views.user_list, name="user_list"),
    path("users/new/", views.user_create, name="user_create"),
    path("users/<int:pk>/", views.user_detail, name="user_detail"),
    path("users/<int:pk>/<str:action>/", views.user_action, name="user_action"),
]
