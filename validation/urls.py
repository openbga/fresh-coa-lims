from django.urls import path

from . import views

app_name = "validation"
urlpatterns = [
    path("", views.use_list, name="use_list"),
    path("intended-use/new/", views.use_new, name="use_new"),
    path("intended-use/<int:pk>/", views.use_detail, name="use_detail"),
    path("intended-use/<int:pk>/accept/", views.use_accept, name="use_accept"),
    path("intended-use/<int:pk>/withdraw/", views.use_withdraw, name="use_withdraw"),
    path("rehearsals/", views.rehearsal_list, name="rehearsal_list"),
    path("rehearsals/new/", views.rehearsal_new, name="rehearsal_new"),
    path("rehearsals/<int:pk>/", views.rehearsal_detail, name="rehearsal_detail"),
    path("rehearsals/<int:pk>/files/new/", views.rehearsal_file_new, name="rehearsal_file_new"),
    path("rehearsals/files/<int:pk>/", views.rehearsal_file, name="rehearsal_file"),
    path("rehearsals/<int:pk>/accept/", views.rehearsal_accept, name="rehearsal_accept"),
    path("rehearsals/<int:pk>/withdraw/", views.rehearsal_withdraw, name="rehearsal_withdraw"),
]
