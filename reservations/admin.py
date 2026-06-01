from django.contrib import admin
from django.utils import timezone

from .models import Reservation


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("environment", "owner", "during_local", "created_at")
    autocomplete_fields = ["environment", "owner"]

    @admin.display(description="During (local)")
    def during_local(self, obj):
        fmt = "%Y-%m-%d %H:%M %Z"
        lo = timezone.localtime(obj.during.lower).strftime(fmt)
        hi = timezone.localtime(obj.during.upper).strftime(fmt)
        return f"[{lo}, {hi})"
