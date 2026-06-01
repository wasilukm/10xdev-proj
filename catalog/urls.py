from django.urls import path

from . import views

urlpatterns = [
    path("", views.environment_list, name="home"),
]
