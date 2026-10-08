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

The per-period queries bucket receipt dates by a `Granularity` (day, week,
month or year) so a long range can be viewed at a readable resolution.
Buckets are clipped to the requested range: a range starting mid-month
yields a first "month" holding only the days from the range start.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from django.db import connection

MONTHS_IN_YEAR = 12


@dataclass(frozen=True)
class Granularity:
    """One way of bucketing receipt dates for the charts and the pivot table."""

    key: str  # doubles as the `date_trunc` unit and the `?group=` value
    menu: str  # dropdown entry
    by_phrase: str  # completes "Выручка по ..."
    columns_phrase: str  # completes "магазины × ..."


GRANULARITIES = (
    Granularity("day", "По дням", "дням", "дни"),
    Granularity("week", "По неделям", "неделям", "недели"),
    Granularity("month", "По месяцам", "месяцам", "месяцы"),
    Granularity("year", "По годам", "годам", "годы"),
)
GRANULARITY_BY_KEY = {granularity.key: granularity for granularity in GRANULARITIES}

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

# total_kop includes amounts already collected as an advance on an earlier
# receipt (prepaid_kop) — counting it again here double-counts that advance
# against the receipt where it was first collected. paid_kop = total_kop -
# prepaid_kop is the amount actually paid *on this receipt*. A fully-prepaid
# receipt (paid_kop = 0) is still a real sale and must still be counted —
# the zero filter below only drops genuinely empty documents (raw
# total_kop = 0: shift-open/close reports), never anything based on the
# post-subtraction amount.
#
# Refunds (operation_type 2) are netted into revenue, not dropped. OFD stores
# them with a *negative* total_kop but *positive* cash/ecash/prepaid (checked
# on prod data: |total| = cash + ecash + prepaid for both sales and refunds),
# so a refund's paid amount is total + prepaid (= -(cash + ecash)) and its
# cash/card parts must be negated before summing with the sales.
_OPERATION_FILTER = "r.operation_type IN (1, 2)"
_PAID_EXPR = "(CASE r.operation_type WHEN 2 THEN r.total_kop + r.prepaid_kop ELSE r.total_kop - r.prepaid_kop END)"
_CASH_EXPR = "(CASE r.operation_type WHEN 2 THEN -r.cash_kop ELSE r.cash_kop END)"
_ECASH_EXPR = "(CASE r.operation_type WHEN 2 THEN -r.ecash_kop ELSE r.ecash_kop END)"
_ZERO_RECEIPT_FILTER = "AND r.total_kop <> 0"

_SUMMARY_SQL = f"""
    SELECT
        coalesce(sum({_PAID_EXPR}), 0) AS paid_kop,
        coalesce(sum({_CASH_EXPR}), 0) AS cash_kop,
        coalesce(sum({_ECASH_EXPR}), 0) AS ecash_kop
    FROM ofd.receipts r
    {_SHOP_JOIN}
    WHERE {_OPERATION_FILTER}
      {_ZERO_RECEIPT_FILTER}
      AND r.date >= %s
      AND r.date < %s
      {{shop_filter}}
"""

_PERIOD_SQL = f"""
    SELECT
        {{bucket}} AS period_start,
        coalesce(sum({_CASH_EXPR}), 0) AS cash_kop,
        coalesce(sum({_ECASH_EXPR}), 0) AS ecash_kop
    FROM ofd.receipts r
    {_SHOP_JOIN}
    WHERE {_OPERATION_FILTER}
      {_ZERO_RECEIPT_FILTER}
      AND r.date >= %s
      AND r.date < %s
      {{shop_filter}}
    GROUP BY 1
    ORDER BY 1
"""

_SHOP_PERIOD_MATRIX_SQL = f"""
    SELECT
        {{bucket}} AS period_start,
        {_SHOP_EXPR} AS shop,
        coalesce(sum({_PAID_EXPR}), 0) AS paid_kop,
        coalesce(sum({_CASH_EXPR}), 0) AS cash_kop,
        coalesce(sum({_ECASH_EXPR}), 0) AS ecash_kop
    FROM ofd.receipts r
    {_SHOP_JOIN}
    WHERE {_OPERATION_FILTER}
      {_ZERO_RECEIPT_FILTER}
      AND r.date >= %s
      AND r.date < %s
      {{shop_filter}}
    GROUP BY 1, 2
    ORDER BY 1, 2
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
class PeriodPoint:
    """One period's cash and card revenue, in rubles."""

    start: date
    cash_rub: float
    card_rub: float


@dataclass(frozen=True)
class PeriodCell:
    """One shop's total/cash/card revenue in one period."""

    total_rub: float
    cash_rub: float
    card_rub: float


@dataclass(frozen=True)
class ShopPeriodMatrixRow:
    """One shop's revenue for each period in the matrix, aligned with periods."""

    shop: str
    cells: list[PeriodCell]
    total_rub: float
    total_cash_rub: float
    total_card_rub: float


@dataclass(frozen=True)
class ShopPeriodMatrix:
    """Revenue pivoted: shops as rows, periods (period start dates) as columns."""

    periods: list[date]
    rows: list[ShopPeriodMatrixRow]


def period_start(day: date, granularity: Granularity) -> date:
    """First day of the bucket `day` falls in (weeks start Monday, like Postgres)."""
    if granularity.key == "week":
        return day - timedelta(days=day.weekday())
    if granularity.key == "month":
        return day.replace(day=1)
    if granularity.key == "year":
        return day.replace(month=1, day=1)
    return day


def earliest_period_start(last_day: date, granularity: Granularity, periods: int) -> date:
    """Start of the bucket `periods - 1` buckets before the one holding `last_day`."""
    steps_back = periods - 1
    current = period_start(last_day, granularity)
    if granularity.key == "week":
        return current - timedelta(weeks=steps_back)
    if granularity.key == "month":
        months_total = current.year * MONTHS_IN_YEAR + current.month - 1 - steps_back
        year, month_index = divmod(months_total, MONTHS_IN_YEAR)
        return date(year, month_index + 1, 1)
    if granularity.key == "year":
        return date(current.year - steps_back, 1, 1)
    return current - timedelta(days=steps_back)


def _bucket_sql(granularity: Granularity) -> str:
    """SQL expression for the bucket start date. The unit is interpolated, not
    bound, so it must be one of ours — never anything caller-supplied."""
    if GRANULARITY_BY_KEY.get(granularity.key) != granularity:
        raise ValueError(f"Unsupported granularity: {granularity!r}")
    return f"date_trunc('{granularity.key}', r.date::timestamp)::date"


def _fill_template(
    sql_template: str,
    shops: list[str] | None,
    params: list[Any],
    bucket: str = "",
) -> str:
    """Fills the {shop_filter} and {bucket} placeholders, appending `shops` to
    params if set."""
    if not shops:
        return sql_template.format(shop_filter="", bucket=bucket)
    params.append(shops)
    return sql_template.format(shop_filter=_SHOP_FILTER_CLAUSE, bucket=bucket)


def get_shop_list() -> list[str]:
    """Every distinct shop label, for populating the shop filter dropdown."""
    with connection.cursor() as cursor:
        cursor.execute(_SHOP_LIST_SQL)
        return [row[0] for row in cursor.fetchall()]


def get_summary(date_from: date, date_to: date, shops: list[str] | None = None) -> SummaryTotals:
    """Revenue and cash/card share for receipt dates in [date_from, date_to)."""
    params: list[Any] = [date_from, date_to]
    sql = _fill_template(_SUMMARY_SQL, shops, params)

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        paid_kop, cash_kop, ecash_kop = cursor.fetchone()

    # sum() over a bigint column comes back as numeric, which psycopg2 maps
    # to Decimal — cast to float so this matches the declared field types
    # and can be mixed freely with plain floats elsewhere.
    paid_kop, cash_kop, ecash_kop = float(paid_kop), float(cash_kop), float(ecash_kop)

    if not paid_kop:
        return SummaryTotals(
            revenue_rub=0.0, cash_rub=0.0, cash_share_pct=0.0, card_rub=0.0, card_share_pct=0.0,
        )

    return SummaryTotals(
        revenue_rub=paid_kop / 100,
        cash_rub=cash_kop / 100,
        cash_share_pct=cash_kop * 100 / paid_kop,
        card_rub=ecash_kop / 100,
        card_share_pct=ecash_kop * 100 / paid_kop,
    )


def get_period_breakdown(
    date_from: date,
    date_to: date,
    granularity: Granularity,
    shops: list[str] | None = None,
) -> list[PeriodPoint]:
    """Per-period cash/card revenue for receipt dates in [date_from, date_to)."""
    params: list[Any] = [date_from, date_to]
    sql = _fill_template(_PERIOD_SQL, shops, params, bucket=_bucket_sql(granularity))

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    return [
        PeriodPoint(start=start, cash_rub=float(cash_kop) / 100, card_rub=float(ecash_kop) / 100)
        for start, cash_kop, ecash_kop in rows
    ]


def get_shop_period_matrix(
    date_from: date,
    date_to: date,
    granularity: Granularity,
    shops: list[str] | None = None,
) -> ShopPeriodMatrix:
    """Revenue per shop per period for [date_from, date_to), pivoted for display."""
    params: list[Any] = [date_from, date_to]
    sql = _fill_template(_SHOP_PERIOD_MATRIX_SQL, shops, params, bucket=_bucket_sql(granularity))

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    periods = sorted({start for start, _shop, _paid, _cash, _ecash in rows})
    period_index = {start: position for position, start in enumerate(periods)}
    empty_cell = PeriodCell(total_rub=0.0, cash_rub=0.0, card_rub=0.0)

    cells_by_shop: dict[str, list[PeriodCell]] = {}
    for start, shop_name, paid_kop, cash_kop, ecash_kop in rows:
        cell = PeriodCell(
            total_rub=float(paid_kop) / 100,
            cash_rub=float(cash_kop) / 100,
            card_rub=float(ecash_kop) / 100,
        )
        cells_by_shop.setdefault(shop_name, [empty_cell] * len(periods))[period_index[start]] = cell

    matrix_rows = [
        ShopPeriodMatrixRow(
            shop=shop_name,
            cells=cells,
            total_rub=sum(cell.total_rub for cell in cells),
            total_cash_rub=sum(cell.cash_rub for cell in cells),
            total_card_rub=sum(cell.card_rub for cell in cells),
        )
        for shop_name, cells in sorted(cells_by_shop.items())
    ]
    return ShopPeriodMatrix(periods=periods, rows=matrix_rows)
