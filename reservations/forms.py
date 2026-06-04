from datetime import timedelta

from django import forms
from django.utils import timezone
from psycopg.types.range import Range

from catalog.models import Environment
from . import services


DURATION_CHOICES = [
    ("1h", "1 hour"),
    ("2h", "2 hours"),
    ("4h", "4 hours"),
    ("custom", "Custom (hours)"),
    ("until_next", "Until next reservation (max 4 h)"),
]


class ReservationForm(forms.Form):
    environment = forms.ModelChoiceField(
        queryset=Environment.objects.all(),
        widget=forms.HiddenInput,
    )
    start = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        label="Start",
    )
    duration = forms.ChoiceField(choices=DURATION_CHOICES, label="Duration")
    custom_hours = forms.DecimalField(
        min_value=0.25,
        max_digits=5,
        decimal_places=2,
        required=False,
        label="Custom hours",
    )

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start")
        duration = cleaned_data.get("duration")
        env = cleaned_data.get("environment")
        custom_hours = cleaned_data.get("custom_hours")

        if not (start and duration and env):
            return cleaned_data

        if duration == "custom" and not custom_hours:
            self.add_error("custom_hours", "Enter the number of hours for a custom duration.")
            return cleaned_data

        if timezone.is_naive(start):
            start = timezone.make_aware(start, timezone.get_current_timezone())
            cleaned_data["start"] = start

        if start < timezone.now():
            raise forms.ValidationError("Start time must be in the future.")

        end = services.compute_end(env, start, duration, custom_hours=custom_hours)

        if end <= start:
            raise forms.ValidationError("Computed end time is not after start — choose a longer duration.")

        cleaned_data["during"] = Range(start, end, "[)")
        return cleaned_data


class ReservationEditForm(forms.Form):
    hours = forms.DecimalField(
        min_value=0.25,
        max_digits=5,
        decimal_places=2,
        required=True,
        label="Duration (hours)",
    )

    def __init__(self, *args, start, **kwargs):
        super().__init__(*args, **kwargs)
        self._start = start

    def clean(self):
        cleaned_data = super().clean()
        hours = cleaned_data.get("hours")
        if hours is None:
            return cleaned_data

        end = self._start + timedelta(hours=float(hours))

        if end <= self._start:
            raise forms.ValidationError("Computed end time is not after start — choose a longer duration.")

        if end <= timezone.now():
            raise forms.ValidationError(
                "New end must be in the future — increase the hours or cancel instead."
            )

        cleaned_data["during"] = Range(self._start, end, "[)")
        return cleaned_data
