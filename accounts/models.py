from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def create_user(
        self, email: str, password: str | None = None, **extra_fields: Any
    ) -> User:
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email).lower()
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self, email: str, password: str | None = None, **extra_fields: Any
    ) -> User:
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None  # type: ignore[assignment]
    email = models.EmailField(unique=True)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()  # type: ignore[misc, assignment]

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="user_email_ci_uniq"),
        ]


class AllowedEmailDomain(models.Model):
    domain = models.CharField(max_length=255, unique=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.domain = self.domain.lower()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.domain
