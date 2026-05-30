from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from .forms import EmailAuthenticationForm
from .views import SignUpView

urlpatterns = [
    path(
        "login/",
        LoginView.as_view(authentication_form=EmailAuthenticationForm),
        name="login",
    ),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("signup/", SignUpView.as_view(), name="signup"),
]
