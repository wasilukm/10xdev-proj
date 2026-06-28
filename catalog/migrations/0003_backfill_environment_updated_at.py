from django.db import migrations
from django.db.models import Min


def anchor_updated_at(apps, schema_editor):
    """Stamp existing envs' updated_at to their earliest reservation's created_at.

    0002 added updated_at(auto_now), filling existing rows with the migration-run
    time. The change-badge is derived as updated_at > reservation.created_at, so
    that fill would spuriously badge every reservation predating the deploy. Anchor
    each env's updated_at to its earliest reservation so the badge only fires on a
    genuine post-deploy edit. .update() bypasses auto_now (env.save() would reset it).
    """
    Environment = apps.get_model("catalog", "Environment")
    for env_pk, earliest in (
        Environment.objects.annotate(earliest=Min("reservations__created_at"))
        .filter(earliest__isnull=False)
        .values_list("pk", "earliest")
    ):
        Environment.objects.filter(pk=env_pk).update(updated_at=earliest)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0002_environment_updated_at"),
        # Reads the cross-app reverse relation `reservations__created_at`, so the
        # Reservation FK must exist in the historical state before this runs.
        # Without this dependency a fresh-DB migrate can order 0003 first → FieldError.
        ("reservations", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(anchor_updated_at, migrations.RunPython.noop),
    ]
