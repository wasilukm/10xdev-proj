from django.conf import settings
from django.db import models


class Environment(models.Model):
    name = models.CharField(max_length=255, unique=True)
    version = models.CharField(max_length=100)
    purpose = models.CharField(max_length=255, db_index=True)
    project = models.CharField(max_length=255, db_index=True)
    use_case_tag = models.CharField(max_length=100, db_index=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_environments",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
