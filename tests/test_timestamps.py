from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

from Backends.backend import models
from Backends.backend.routes.audit import _entered_datetime


def test_every_model_timestamp_keeps_its_time_zone():
    # A naive column on PostgreSQL stores aware values in the session's local time (#16).
    naive = [
        f"{table.name}.{column.name}"
        for table in models.Base.metadata.sorted_tables
        for column in table.columns
        if isinstance(column.type, sa.DateTime) and not column.type.timezone
    ]
    assert naive == []


def test_dates_typed_into_audit_filters_are_lgu_local_time():
    assert _entered_datetime("2026-10-21") == datetime(2026, 10, 20, 16, 0, tzinfo=timezone.utc)
    assert _entered_datetime("2026-10-21T09:30:00") == datetime(2026, 10, 21, 1, 30, tzinfo=timezone.utc)
    assert _entered_datetime("2026-10-21T09:30:00+00:00").utcoffset() == timedelta(0)


def test_frontend_reads_naive_api_times_as_utc():
    import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
    from frontend.admin.tracking_ui import local_time

    assert local_time("2026-10-21T05:00:00") == datetime(2026, 10, 21, 5, 0, tzinfo=timezone.utc)
    assert local_time("2026-10-21T13:00:00+08:00") == datetime(2026, 10, 21, 5, 0, tzinfo=timezone.utc)
    assert local_time("not a time") is None
