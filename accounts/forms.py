from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import AllowedEmailDomain, User


class SignUpForm(UserCreationForm):
    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name")

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].lower()
        domain = email.split("@")[-1]
        if (
            AllowedEmailDomain.objects.exists()
            and not AllowedEmailDomain.objects.filter(domain=domain).exists()
        ):
            raise forms.ValidationError(
                "Sign-up is restricted to approved email domains."
            )
        return email


class EmailAuthenticationForm(AuthenticationForm):
    def clean_username(self) -> str:
        return self.cleaned_data["username"].lower()
