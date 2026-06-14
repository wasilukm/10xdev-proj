from __future__ import annotations

from django.contrib.auth import login
from django.forms import BaseModelForm
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic.edit import CreateView

from .forms import SignUpForm


class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = "registration/signup.html"
    success_url = reverse_lazy("home")

    def form_valid(self, form: BaseModelForm) -> HttpResponse:
        response = super().form_valid(form)
        login(self.request, self.object)
        return response
