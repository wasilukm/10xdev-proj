from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.db import models
from django.db.models import Q


class Reservation(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reservations",
    )
    environment = models.ForeignKey(
        "catalog.Environment",
        on_delete=models.PROTECT,
        related_name="reservations",
    )
    during = DateTimeRangeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            ExclusionConstraint(
                name="reservation_no_overlap",
                expressions=[
                    ("environment", RangeOperators.EQUAL),
                    ("during", RangeOperators.OVERLAPS),
                ],
                index_type="GIST",
            ),
            models.CheckConstraint(
                name="reservation_during_bounded",
                condition=Q(
                    during__isempty=False,
                    during__lower_inf=False,
                    during__upper_inf=False,
                ),
            ),
        ]

    def __str__(self):
        return f"{self.environment} / {self.owner} / {self.during}"
