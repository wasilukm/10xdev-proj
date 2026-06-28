from django.urls import path

from . import views

urlpatterns = [
    path("", views.environment_list, name="home"),
    path("manage/environments/", views.environment_manage, name="env_manage"),
    path("manage/environments/new/", views.environment_create, name="env_create"),
    path(
        "manage/environments/<int:pk>/edit/",
        views.environment_edit,
        name="env_edit",
    ),
    path(
        "manage/environments/<int:pk>/delete/",
        views.environment_delete,
        name="env_delete",
    ),
]
