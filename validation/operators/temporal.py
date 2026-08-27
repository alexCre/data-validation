from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta

from validation.registry import operator


def _as_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


@operator(
    "date_before",
    category="temporal",
    description="True if a is strictly before b.",
    input_types=["date", "date"],
    output_type="bool",
    examples=[{"args": ["2024-10-30", "2024-11-24"], "result": True}],
)
def date_before(a, b) -> bool | None:
    a, b = _as_date(a), _as_date(b)
    if a is None or b is None:
        return None
    return a < b


@operator(
    "date_after",
    category="temporal",
    description="True if a is strictly after b.",
    input_types=["date", "date"],
    output_type="bool",
    examples=[{"args": ["2024-11-24", "2024-10-30"], "result": True}],
)
def date_after(a, b) -> bool | None:
    a, b = _as_date(a), _as_date(b)
    if a is None or b is None:
        return None
    return a > b


@operator(
    "date_between",
    category="temporal",
    description="True if x falls within [start, end] inclusive.",
    input_types=["date", "date", "date"],
    output_type="bool",
)
def date_between(x, start, end) -> bool | None:
    x, start, end = _as_date(x), _as_date(start), _as_date(end)
    if x is None or start is None or end is None:
        return None
    return start <= x <= end


@operator(
    "add_days",
    category="temporal",
    description="Date shifted by a number of days (negative to shift earlier).",
    input_types=["date", "int"],
    output_type="date",
    examples=[{"args": ["2024-11-24", 120], "result": "2025-03-24"}],
)
def add_days(a, days: int):
    a = _as_date(a)
    if a is None:
        return None
    return a + timedelta(days=days)


@operator(
    "add_months",
    category="temporal",
    description="Date shifted by a number of calendar months (negative to shift earlier).",
    input_types=["date", "int"],
    output_type="date",
    examples=[{"args": ["2024-10-21", -1], "result": "2024-09-21"}],
)
def add_months(a, months: int):
    a = _as_date(a)
    if a is None:
        return None
    return a + relativedelta(months=months)


@operator(
    "days_between",
    category="temporal",
    description="Number of days between a and b (b - a).",
    input_types=["date", "date"],
    output_type="int",
)
def days_between(a, b) -> int | None:
    a, b = _as_date(a), _as_date(b)
    if a is None or b is None:
        return None
    return (b - a).days
