from django.contrib import admin

from .models import Reservation


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("environment", "owner", "during", "created_at")
    autocomplete_fields = ["environment", "owner"]
