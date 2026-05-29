from django.contrib import admin

from .models import Environment


@admin.register(Environment)
class EnvironmentAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "project", "owner")
    list_filter = ("project", "purpose", "use_case_tag")
    search_fields = ("name",)
