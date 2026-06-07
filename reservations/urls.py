from django.urls import path

from . import views

app_name = "reservations"

urlpatterns = [
    path("create/", views.reservation_create, name="create"),
    path("mine/", views.my_reservations, name="mine"),
    path("<int:pk>/edit/", views.reservation_edit, name="edit"),
    path("<int:pk>/cancel/", views.reservation_cancel, name="cancel"),
]
