from django.urls import path

from . import views

urlpatterns = [
    path("", views.environment_list, name="home"),
    path("manage/environments/", views.environment_manage, name="env_manage"),
    path("manage/environments/new/", views.environment_create, name="env_create"),
]
