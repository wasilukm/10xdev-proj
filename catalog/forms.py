from __future__ import annotations

from django import forms

from accounts.models import User

from .models import Environment


class EnvironmentForm(forms.ModelForm):
    """Create/edit form for catalog environments (staff-only manage UI)."""

    owner = forms.ModelChoiceField(queryset=User.objects.all())

    class Meta:
        model = Environment
        fields = ["name", "version", "purpose", "project", "use_case_tag", "owner"]
