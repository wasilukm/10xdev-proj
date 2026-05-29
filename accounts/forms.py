from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import AllowedEmailDomain, User


class SignUpForm(UserCreationForm):
    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name")

    def clean_email(self):
        email = self.cleaned_data["email"]
        domain = email.split("@")[-1].lower()
        if AllowedEmailDomain.objects.exists():
            if not AllowedEmailDomain.objects.filter(domain=domain).exists():
                raise forms.ValidationError(
                    "Sign-up is restricted to approved email domains."
                )
        return email
