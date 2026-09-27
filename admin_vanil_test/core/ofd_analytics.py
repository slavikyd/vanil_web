"""Raw-SQL read access to the ofd schema for the admin summary panel.

ofd.* tables live in a separate schema owned by the receipts ingestor's
own migrations (see ../../migrations/), never introspected into this
app's ORM models — queried directly here instead of inventing a parallel
Django mapping for a schema this app doesn't own.

Every function takes a half-open [date_from, date_to) range over
ofd.receipts.date, the local-calendar-day column the ingestor already
computes at load time — filtering on it (rather than re-deriving day
boundaries from the timestamptz issued_at column here) avoids a second,
possibly drifting definition of "which day" a receipt belongs to.
"""

from dataclasses import dataclass
from datetime import date

from django.db import connection

_SUMMARY_SQL = """
    SELECT
        coalesce(sum(total_kop), 0) AS total_kop,
        coalesce(sum(cash_kop), 0) AS cash_kop,
        coalesce(sum(ecash_kop), 0) AS ecash_kop
    FROM ofd.receipts
    WHERE operation_type = 1
      AND date >= %s
      AND date < %s
"""

_DAILY_SQL = """
    SELECT
        date,
        coalesce(sum(cash_kop), 0) AS cash_kop,
        coalesce(sum(ecash_kop), 0) AS ecash_kop
    FROM ofd.receipts
    WHERE operation_type = 1
      AND date >= %s
      AND date < %s
    GROUP BY date
    ORDER BY date
"""


@dataclass(frozen=True)
class SummaryTotals:
    """Total revenue and its cash/card split for a date range."""

    revenue_rub: float
    cash_share_pct: float
    card_share_pct: float


@dataclass(frozen=True)
class DailyPoint:
    """One day's cash and card revenue, in rubles."""

    day: date
    cash_rub: float
    card_rub: float


def get_summary(date_from: date, date_to: date) -> SummaryTotals:
    """Revenue and cash/card share for receipt dates in [date_from, date_to)."""
    with connection.cursor() as cursor:
        cursor.execute(_SUMMARY_SQL, [date_from, date_to])
        total_kop, cash_kop, ecash_kop = cursor.fetchone()

    if not total_kop:
        return SummaryTotals(revenue_rub=0.0, cash_share_pct=0.0, card_share_pct=0.0)

    return SummaryTotals(
        revenue_rub=total_kop / 100,
        cash_share_pct=cash_kop * 100 / total_kop,
        card_share_pct=ecash_kop * 100 / total_kop,
    )


def get_daily_breakdown(date_from: date, date_to: date) -> list[DailyPoint]:
    """Per-day cash/card revenue for receipt dates in [date_from, date_to)."""
    with connection.cursor() as cursor:
        cursor.execute(_DAILY_SQL, [date_from, date_to])
        rows = cursor.fetchall()

    return [
        DailyPoint(day=day, cash_rub=cash_kop / 100, card_rub=ecash_kop / 100)
        for day, cash_kop, ecash_kop in rows
    ]
