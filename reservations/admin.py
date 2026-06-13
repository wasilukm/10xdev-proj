from __future__ import annotations

from datetime import datetime
from typing import cast

from django.contrib import admin
from django.utils import timezone

from .models import Reservation


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("environment", "owner", "during_local", "created_at")
    autocomplete_fields = ["environment", "owner"]

    @admin.display(description="During (local)")
    def during_local(self, obj: Reservation) -> str:
        # during is non-empty and bounded (reservation_during_bounded
        # CheckConstraint), so lower/upper are never None.
        fmt = "%Y-%m-%d %H:%M %Z"
        lo = timezone.localtime(cast(datetime, obj.during.lower)).strftime(fmt)
        hi = timezone.localtime(cast(datetime, obj.during.upper)).strftime(fmt)
        return f"[{lo}, {hi})"
