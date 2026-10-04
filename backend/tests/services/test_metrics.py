import uuid
from datetime import date

from app.services.metrics import MetricsQuery


def test_previous_has_the_same_length_and_ends_the_day_before() -> None:
    query = MetricsQuery(uuid.uuid4(), None, date(2026, 3, 1), date(2026, 3, 10))

    previous = query.previous()

    assert query.days == 10
    assert (previous.date_from, previous.date_to) == (
        date(2026, 2, 19),
        date(2026, 2, 28),
    )
    assert previous.workspace_id == query.workspace_id
