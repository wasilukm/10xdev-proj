from datetime import datetime, timezone

from psycopg.types.range import Range

_FIXED_NOW = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)


def _dt(h, m=0, d=1):
    """Aware UTC datetime on 2024-01-01 at the given hour/minute."""
    return datetime(2024, 1, d, h, m, tzinfo=timezone.utc)


def _range(sh, eh):
    return Range(lower=_dt(sh), upper=_dt(eh), bounds="[)")
