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

An optional `shops` list narrows every query to just those shops (matched
the same way the Grafana dashboards do: the shop's address, or "ККТ
<register id>" for a register with no shop linked yet) — `None`/empty
means all shops.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from django.db import connection

_SHOP_EXPR = "coalesce(sh.address, 'ККТ ' || reg.kkt_reg_id)"
_SHOP_JOIN = """
    JOIN ofd.registers reg ON reg.kkt_reg_id = r.kkt_reg_id
    LEFT JOIN ofd.shops sh ON sh.id = reg.shop_id
"""
_SHOP_FILTER_CLAUSE = f"AND {_SHOP_EXPR} = ANY(%s)"

_SHOP_LIST_SQL = f"""
    SELECT DISTINCT {_SHOP_EXPR}
    FROM ofd.registers reg
    LEFT JOIN ofd.shops sh ON sh.id = reg.shop_id
    ORDER BY 1
"""

_SUMMARY_SQL = f"""
    SELECT
        coalesce(sum(r.total_kop), 0) AS total_kop,
        coalesce(sum(r.cash_kop), 0) AS cash_kop,
        coalesce(sum(r.ecash_kop), 0) AS ecash_kop
    FROM ofd.receipts r
    {_SHOP_JOIN}
    WHERE r.operation_type = 1
      AND r.date >= %s
      AND r.date < %s
      {{shop_filter}}
"""

_DAILY_SQL = f"""
    SELECT
        r.date,
        coalesce(sum(r.cash_kop), 0) AS cash_kop,
        coalesce(sum(r.ecash_kop), 0) AS ecash_kop
    FROM ofd.receipts r
    {_SHOP_JOIN}
    WHERE r.operation_type = 1
      AND r.date >= %s
      AND r.date < %s
      {{shop_filter}}
    GROUP BY r.date
    ORDER BY r.date
"""

_SHOP_DAY_MATRIX_SQL = f"""
    SELECT
        r.date,
        {_SHOP_EXPR} AS shop,
        coalesce(sum(r.total_kop), 0) AS total_kop,
        coalesce(sum(r.cash_kop), 0) AS cash_kop,
        coalesce(sum(r.ecash_kop), 0) AS ecash_kop
    FROM ofd.receipts r
    {_SHOP_JOIN}
    WHERE r.operation_type = 1
      AND r.date >= %s
      AND r.date < %s
      {{shop_filter}}
    GROUP BY r.date, shop
    ORDER BY r.date, shop
"""


@dataclass(frozen=True)
class SummaryTotals:
    """Total revenue and its cash/card split for a date range."""

    revenue_rub: float
    cash_rub: float
    cash_share_pct: float
    card_rub: float
    card_share_pct: float


@dataclass(frozen=True)
class DailyPoint:
    """One day's cash and card revenue, in rubles."""

    day: date
    cash_rub: float
    card_rub: float


@dataclass(frozen=True)
class DayCell:
    """One shop's total/cash/card revenue on one day."""

    total_rub: float
    cash_rub: float
    card_rub: float


@dataclass(frozen=True)
class ShopDayMatrixRow:
    """One shop's revenue for each day in the matrix, aligned with days."""

    shop: str
    cells: list[DayCell]
    total_rub: float
    total_cash_rub: float
    total_card_rub: float


@dataclass(frozen=True)
class ShopDayMatrix:
    """Revenue pivoted: shops as rows, days as columns."""

    days: list[date]
    rows: list[ShopDayMatrixRow]


def _with_shop_filter(sql_template: str, shops: list[str] | None, params: list[Any]) -> str:
    """Fills in the {shop_filter} placeholder, appending `shops` to params if set."""
    if not shops:
        return sql_template.format(shop_filter="")
    params.append(shops)
    return sql_template.format(shop_filter=_SHOP_FILTER_CLAUSE)


def get_shop_list() -> list[str]:
    """Every distinct shop label, for populating the shop filter dropdown."""
    with connection.cursor() as cursor:
        cursor.execute(_SHOP_LIST_SQL)
        return [row[0] for row in cursor.fetchall()]


def get_summary(date_from: date, date_to: date, shops: list[str] | None = None) -> SummaryTotals:
    """Revenue and cash/card share for receipt dates in [date_from, date_to)."""
    params: list[Any] = [date_from, date_to]
    sql = _with_shop_filter(_SUMMARY_SQL, shops, params)

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        total_kop, cash_kop, ecash_kop = cursor.fetchone()

    # sum() over a bigint column comes back as numeric, which psycopg2 maps
    # to Decimal — cast to float so this matches the declared field types
    # and can be mixed freely with plain floats elsewhere.
    total_kop, cash_kop, ecash_kop = float(total_kop), float(cash_kop), float(ecash_kop)

    if not total_kop:
        return SummaryTotals(
            revenue_rub=0.0, cash_rub=0.0, cash_share_pct=0.0, card_rub=0.0, card_share_pct=0.0,
        )

    return SummaryTotals(
        revenue_rub=total_kop / 100,
        cash_rub=cash_kop / 100,
        cash_share_pct=cash_kop * 100 / total_kop,
        card_rub=ecash_kop / 100,
        card_share_pct=ecash_kop * 100 / total_kop,
    )


def get_daily_breakdown(date_from: date, date_to: date, shops: list[str] | None = None) -> list[DailyPoint]:
    """Per-day cash/card revenue for receipt dates in [date_from, date_to)."""
    params: list[Any] = [date_from, date_to]
    sql = _with_shop_filter(_DAILY_SQL, shops, params)

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    return [
        DailyPoint(day=day, cash_rub=float(cash_kop) / 100, card_rub=float(ecash_kop) / 100)
        for day, cash_kop, ecash_kop in rows
    ]


def get_shop_day_matrix(date_from: date, date_to: date, shops: list[str] | None = None) -> ShopDayMatrix:
    """Revenue per shop per day for [date_from, date_to), pivoted for display."""
    params: list[Any] = [date_from, date_to]
    sql = _with_shop_filter(_SHOP_DAY_MATRIX_SQL, shops, params)

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    days = sorted({day for day, _shop, _total, _cash, _ecash in rows})
    day_index = {day: position for position, day in enumerate(days)}
    empty_cell = DayCell(total_rub=0.0, cash_rub=0.0, card_rub=0.0)

    cells_by_shop: dict[str, list[DayCell]] = {}
    for day, shop_name, total_kop, cash_kop, ecash_kop in rows:
        cell = DayCell(
            total_rub=float(total_kop) / 100,
            cash_rub=float(cash_kop) / 100,
            card_rub=float(ecash_kop) / 100,
        )
        cells_by_shop.setdefault(shop_name, [empty_cell] * len(days))[day_index[day]] = cell

    matrix_rows = [
        ShopDayMatrixRow(
            shop=shop_name,
            cells=cells,
            total_rub=sum(cell.total_rub for cell in cells),
            total_cash_rub=sum(cell.cash_rub for cell in cells),
            total_card_rub=sum(cell.card_rub for cell in cells),
        )
        for shop_name, cells in sorted(cells_by_shop.items())
    ]
    return ShopDayMatrix(days=days, rows=matrix_rows)
