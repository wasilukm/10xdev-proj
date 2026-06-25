from django.contrib import admin  # noqa: F401

# Environment is intentionally not registered in the Django admin. Its catalog
# CRUD lives in the staff-gated /manage/environments/ UI (S-05), which is the
# single guarded write path. See context/changes/admin-env-catalog/.
