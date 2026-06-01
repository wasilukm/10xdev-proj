from django.urls import path

from . import views

app_name = "reservations"

urlpatterns = [
    path("create/", views.reservation_create, name="create"),
]
