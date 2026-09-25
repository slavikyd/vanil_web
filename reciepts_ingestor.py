#!/usr/bin/env python3
"""
Load fiscal receipts from the Astral OFD API into PostgreSQL.

    python reciepts_ingestor.py all                    # full backfill / reconciliation
    python reciepts_ingestor.py all --from-page 120 --to-page 200
    python reciepts_ingestor.py recent                  # only the newest unseen receipts
    python reciepts_ingestor.py serve                    # scheduler: `recent` every 30 min
                                                           # (window configurable), nightly `all`

Every write is idempotent (ON CONFLICT DO NOTHING keyed on the receipt's
fiscal identity), so re-running any mode for any page range is always safe.
All configuration lives in .env; nothing sensitive is hard-coded here.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

import asyncpg
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

load_dotenv()

from app.logging import setup_logging  # noqa: E402  (must follow load_dotenv)

log = logging.getLogger("ofd")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class Config:
    def __init__(self) -> None:
        self.api_key: str = self._req("OFD_API_KEY")
        self.organization_id: str = self._req("OFD_ORGANIZATION_ID")

        self.db_kwargs: dict[str, Any] = {
            "user": self._req("DB_USER"),
            "password": os.getenv("DB_PASS") or None,
            "database": self._req("DB_NAME"),
            "host": self._req("DB_HOST"),
            "port": int(os.getenv("DB_PORT", "5432")),
        }

        self.base_url: str = os.getenv(
            "OFD_BASE_URL",
            "https://ofd.astralnalog.ru/api/v4.2/documents.tickets",
        )
        self.page_size: int = int(os.getenv("OFD_PAGE_SIZE", "1000"))
        self.recent_page_size: int = int(os.getenv("OFD_RECENT_PAGE_SIZE", "200"))
        self.recent_stop_empty_pages: int = int(
            os.getenv("OFD_RECENT_STOP_EMPTY_PAGES", "2")
        )
        self.concurrency: int = int(os.getenv("OFD_CONCURRENCY", "4"))
        self.request_timeout: int = int(os.getenv("OFD_REQUEST_TIMEOUT", "120"))
        self.max_retries: int = int(os.getenv("OFD_MAX_RETRIES", "5"))

        self.tz = ZoneInfo(os.getenv("OFD_TIMEZONE", "Europe/Saratov"))
        # Astral encodes local wall-clock time as a unix timestamp. Set this to
        # false only if you confirm the timestamps are genuine UTC instants.
        self.time_is_local: bool = _envbool("OFD_TIME_IS_LOCAL", True)

        # `serve` schedule: `recent` runs every OFD_SCHEDULE_INTERVAL_MINUTES,
        # between OFD_SCHEDULE_HOUR_START and OFD_SCHEDULE_HOUR_END (inclusive).
        # `all` runs once nightly at OFD_NIGHTLY_RECONCILE_HOUR as a safety net
        # for anything `recent` missed.
        self.schedule_hour_start: int = int(os.getenv("OFD_SCHEDULE_HOUR_START", "7"))
        self.schedule_hour_end: int = int(os.getenv("OFD_SCHEDULE_HOUR_END", "23"))
        self.schedule_interval_minutes: int = int(
            os.getenv("OFD_SCHEDULE_INTERVAL_MINUTES", "30")
        )
        self.nightly_reconcile_hour: int = int(
            os.getenv("OFD_NIGHTLY_RECONCILE_HOUR", "3")
        )

        self.log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()

    @staticmethod
    def _req(name: str) -> str:
        value = os.getenv(name)
        if not value:
            sys.exit(f"Missing required environment variable {name}. See .env.example")
        return value


def _envbool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


# ---------------------------------------------------------------------------
# Item name parsing: turns free-text receipt lines into catalog attributes
# ---------------------------------------------------------------------------

# Ordered: the first pattern that matches wins.
CATEGORY_RULES: list[tuple[str, str, str]] = [
    (r"свеч",                                    "candles",   "candle"),
    (r"лимонад|кофе|чай|капучино|американо",     "drink",     "drink"),
    (r"пельмен|вареник",                         "frozen",    "frozen"),
    (r"зефир",                                   "confection", "marshmallow"),
    (r"печенье|гата|трубочк|орешки|ванильное яблоко|восточная сладость",
                                                 "cookie",    "cookie"),
    (r"торт",                                    "cake",      "cake"),
    (r"рулет",                                    "cake",      "roll"),
    (r"чизкейк",                                 "pastry",    "cheesecake"),
    (r"трайфл",                                  "pastry",    "trifle"),
    (r"корпусный десерт",                        "pastry",    "mousse_dessert"),
    (r"эклер",                                   "pastry",    "eclair"),
    (r"тарт",                                    "pastry",    "tart"),
    (r"кекс|штрудель",                           "pastry",    "bake"),
    (r"кейк-попс",                               "pastry",    "cake_pop"),
    (r"пирожное",                                "pastry",    "pastry"),
    (r"десерт",                                  "pastry",    "dessert"),
]

# "750г/шт", "90г", "0,5кг", "0,33л", "300 мл"
WEIGHT_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(кг|г|мл|л)\b", re.IGNORECASE
)
PIECE_RE = re.compile(r"/\s*шт|\bшт\b|\d+\s*шт", re.IGNORECASE)

# Only these categories are ever sold loose, by the kilogram.
WEIGHED_CATEGORIES = {"cake", "cookie"}


def parse_item(name_raw: str) -> dict[str, Any]:
    """Derive catalog attributes from a receipt line name."""
    low = name_raw.lower()

    category, subcategory = "other", None
    for pattern, cat, sub in CATEGORY_RULES:
        if re.search(pattern, low):
            category, subcategory = cat, sub
            break

    unit_weight_g: int | None = None
    match = WEIGHT_RE.search(name_raw)
    if match:
        value = Decimal(match.group(1).replace(",", "."))
        unit = match.group(2).lower()
        if unit == "кг":
            unit_weight_g = int(value * 1000)
        elif unit == "г":
            unit_weight_g = int(value)
        # мл / л are volumes; left as NULL so the column stays a clean weight.

    # A name carrying a unit size or an explicit "шт" is priced per piece.
    # A bare name is priced per kilogram, but only in the categories that are
    # actually sold loose: a candle with no stated size is still one candle.
    if PIECE_RE.search(name_raw) or match:
        sold_by = "piece"
    elif category in WEIGHED_CATEGORIES:
        sold_by = "kg"
    else:
        sold_by = "piece"

    # name_clean: drop the trailing size suffix and collapse quotes/whitespace.
    clean = WEIGHT_RE.sub("", name_raw)
    clean = PIECE_RE.sub("", clean)
    clean = clean.replace('"', "").replace("«", "").replace("»", "")
    clean = re.sub(r"\(\s*\)", "", clean)          # brackets emptied by the strips
    clean = re.sub(r"[\s,/]+", " ", clean).strip(" ,-/")

    return {
        "name_raw": name_raw,
        "name_clean": clean or name_raw,
        "category": category,
        "subcategory": subcategory,
        "sold_by": sold_by,
        "unit_weight_g": unit_weight_g,
    }


CASHIER_ROLES = ("Продавец-кассир", "Кассир", "Администратор")


def parse_cashier(name_raw: str) -> dict[str, Any]:
    """Split 'Продавец-кассир Иванова Мария' into role + normalized name."""
    role = None
    rest = name_raw.strip()
    for candidate in CASHIER_ROLES:
        if rest.lower().startswith(candidate.lower()):
            role = candidate
            rest = rest[len(candidate):].strip(" -")
            break

    parts = [p for p in re.split(r"\s+", rest) if p]
    clean = " ".join(p[:1].upper() + p[1:].lower() for p in parts)
    return {"name_raw": name_raw, "name_clean": clean or rest, "role": role}


# ---------------------------------------------------------------------------
# Document normalization
# ---------------------------------------------------------------------------

VAT_KEYS = (
    "ndsNo", "nds0", "nds5", "nds5105", "nds7", "nds7107", "nds10", "nds10110",
    "nds18", "nds18118", "nds20", "nds20120", "nds22", "nds22122",
)
ERROR_KEYS = (
    "FnsResponseErrCode", "FnsResponseErrTag", "FnsResponseErrMsg",
    "FnsResponseWrnCode", "FnsResponseWrnTag", "FnsResponseWrnMsg",
)


def to_instant(epoch: int, cfg: Config) -> datetime:
    """Convert the API timestamp into a real instant."""
    if cfg.time_is_local:
        naive = datetime.fromtimestamp(epoch, tz=timezone.utc).replace(tzinfo=None)
        return naive.replace(tzinfo=cfg.tz)
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


def line_amount_kop(quantity: Decimal, price_kop: int) -> int:
    return int((quantity * price_kop).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def normalize(doc: dict[str, Any], cfg: Config) -> dict[str, Any] | None:
    """Flatten one API document into row dicts. Returns None if unusable."""
    try:
        issued_at = to_instant(int(doc["issueDate"]), cfg)
        total_kop = int(doc["sum"])

        lines = []
        for line_no, raw_line in enumerate(doc.get("items") or [], start=1):
            quantity = Decimal(str(raw_line["count"]))
            price_kop = int(raw_line["price"])
            lines.append({
                "line_no": line_no,
                "name_raw": raw_line["name"].strip(),
                "quantity": quantity,
                "price_kop": price_kop,
                "amount_kop": line_amount_kop(quantity, price_kop),
            })

        if lines:
            lines_total = sum(line["amount_kop"] for line in lines)
            if lines_total != total_kop:
                log.warning(
                    "Line total %s != receipt sum %s (fns_id=%s); stored as-is",
                    lines_total, total_kop, doc.get("FnsID"),
                )

        vat = {key: int(doc[key]) for key in VAT_KEYS if doc.get(key)}
        errors = {key: doc[key] for key in ERROR_KEYS if doc.get(key)}

        return {
            "fns_id": doc.get("FnsID"),
            "kkt_reg_id": doc["kktRegId"],
            "fiscal_drive_number": doc["fiscalDriveNumber"],
            "shift_number": int(doc["shiftNumber"]),
            "check_number": int(doc["checkNumber"]),
            "fiscal_sign": int(doc["fiscalSign"]),
            "document_type": int(doc.get("documentType", 3)),
            "operation_type": int(doc.get("operationType", 1)),
            "issued_at": issued_at,
            "date": issued_at.astimezone(cfg.tz).date(),
            "cashier_raw": (doc.get("operator") or "").strip() or None,
            "taxation_type": doc.get("taxationType"),
            "is_marked": bool(doc.get("isMarked")),
            "total_kop": total_kop,
            "cash_kop": int(doc.get("cash") or 0),
            "ecash_kop": int(doc.get("ecash") or 0),
            "prepaid_kop": int(doc.get("prepaid") or 0),
            "credit_kop": int(doc.get("credit") or 0),
            "provision_kop": int(doc.get("provision") or 0),
            "vat": json.dumps(vat, ensure_ascii=False) if vat else None,
            "fns_code": doc.get("FnsCode"),
            "fns_errors": json.dumps(errors, ensure_ascii=False) if errors else None,
            "item_count": len(lines),
            "raw": json.dumps(doc, ensure_ascii=False),
            "lines": lines,
        }
    except (KeyError, TypeError, ValueError) as exc:
        log.error("Skipping malformed document %s: %s", doc.get("FnsID"), exc)
        return None


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class OfdClient:
    def __init__(self, cfg: Config, client: httpx.AsyncClient) -> None:
        self.cfg = cfg
        self.client = client
        self._gate = asyncio.Semaphore(cfg.concurrency)

    async def fetch_page(self, page_number: int, page_size: int) -> tuple[int, list[dict[str, Any]]]:
        """Return (totalCount, documents) for one page, with retry/backoff."""
        params = {
            "api_key": self.cfg.api_key,
            "organizationId": self.cfg.organization_id,
            "pageNumber": page_number,
            "count": page_size,
        }

        delay = 2.0
        last_error: Exception | None = None

        for attempt in range(1, self.cfg.max_retries + 1):
            try:
                async with self._gate:
                    resp = await self.client.get(self.cfg.base_url, params=params)

                if resp.status_code in RETRYABLE_STATUSES:
                    raise httpx.HTTPStatusError(
                        f"status {resp.status_code}: {resp.text}",
                        request=resp.request, response=resp,
                    )
                resp.raise_for_status()
                payload = resp.json()

                if not payload.get("ok", True):
                    raise RuntimeError(f"API returned ok=false: {payload}")

                result = payload.get("result") or {}
                return int(result.get("totalCount") or 0), list(result.get("documents") or [])

            except (httpx.HTTPError, RuntimeError) as exc:
                last_error = exc
                if attempt == self.cfg.max_retries:
                    break
                log.warning(
                    "Page %s attempt %s/%s failed (%s); retrying in %.0fs",
                    page_number, attempt, self.cfg.max_retries, exc, delay,
                )
                await asyncio.sleep(delay)
                delay *= 2

        raise RuntimeError(f"Page {page_number} failed after "
                           f"{self.cfg.max_retries} attempts: {last_error}")


# ---------------------------------------------------------------------------
# Database writer
# ---------------------------------------------------------------------------

class Writer:
    """Writes normalized documents, caching dimension lookups in memory."""

    def __init__(self, pool: asyncpg.Pool, cfg: Config) -> None:
        self.pool = pool
        self.cfg = cfg
        self._items: dict[str, int] = {}
        self._cashiers: dict[str, int] = {}
        self._registers: set[str] = set()

    async def warm_cache(self) -> None:
        async with self.pool.acquire() as conn:
            self._items = {
                r["name_raw"]: r["id"]
                for r in await conn.fetch("SELECT id, name_raw FROM ofd.items")
            }
            self._cashiers = {
                r["name_raw"]: r["id"]
                for r in await conn.fetch("SELECT id, name_raw FROM ofd.cashiers")
            }
            self._registers = {
                r["kkt_reg_id"]
                for r in await conn.fetch("SELECT kkt_reg_id FROM ofd.registers")
            }
        log.info(
            "Cache warm: %s items, %s cashiers, %s registers",
            len(self._items), len(self._cashiers), len(self._registers),
        )

    async def _register_id(self, conn: asyncpg.Connection, kkt: str, fn: str) -> None:
        if kkt in self._registers:
            return
        await conn.execute(
            """
            INSERT INTO ofd.registers (kkt_reg_id, fiscal_drive_number)
            VALUES ($1, $2)
            ON CONFLICT (kkt_reg_id) DO NOTHING
            """,
            kkt, fn,
        )
        self._registers.add(kkt)

    async def _item_id(self, conn: asyncpg.Connection, name_raw: str, marked: bool) -> int:
        cached = self._items.get(name_raw)
        if cached is not None:
            return cached

        attrs = parse_item(name_raw)
        item_id = await conn.fetchval(
            """
            INSERT INTO ofd.items
                (name_raw, name_clean, category, subcategory, sold_by,
                 unit_weight_g, is_marked)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (name_raw) DO UPDATE
                SET is_marked = ofd.items.is_marked OR EXCLUDED.is_marked
            RETURNING id
            """,
            attrs["name_raw"], attrs["name_clean"], attrs["category"],
            attrs["subcategory"], attrs["sold_by"], attrs["unit_weight_g"], marked,
        )
        self._items[name_raw] = item_id
        return item_id

    async def _cashier_id(self, conn: asyncpg.Connection, name_raw: str | None) -> int | None:
        if not name_raw:
            return None
        cached = self._cashiers.get(name_raw)
        if cached is not None:
            return cached

        attrs = parse_cashier(name_raw)
        cashier_id = await conn.fetchval(
            """
            INSERT INTO ofd.cashiers (name_raw, name_clean, role)
            VALUES ($1, $2, $3)
            ON CONFLICT (name_raw) DO UPDATE SET name_raw = EXCLUDED.name_raw
            RETURNING id
            """,
            attrs["name_raw"], attrs["name_clean"], attrs["role"],
        )
        self._cashiers[name_raw] = cashier_id
        return cashier_id

    async def write_page(self, page_number: int, docs: list[dict[str, Any]]) -> int:
        """Insert one page in a single transaction. Returns new receipt count."""
        rows = [r for r in (normalize(d, self.cfg) for d in docs) if r]
        inserted = 0

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for row in rows:
                    await self._register_id(
                        conn, row["kkt_reg_id"], row["fiscal_drive_number"]
                    )
                    cashier_id = await self._cashier_id(conn, row["cashier_raw"])

                    receipt_id = await conn.fetchval(
                        """
                        INSERT INTO ofd.receipts (
                            fns_id, kkt_reg_id, fiscal_drive_number, shift_number,
                            check_number, fiscal_sign, document_type, operation_type,
                            issued_at, date, cashier_id, taxation_type, is_marked,
                            total_kop, cash_kop, ecash_kop, prepaid_kop, credit_kop,
                            provision_kop, vat, fns_code, fns_errors, item_count, raw
                        ) VALUES (
                            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,
                            $14,$15,$16,$17,$18,$19,$20::jsonb,$21,$22::jsonb,$23,$24::jsonb
                        )
                        ON CONFLICT (fiscal_drive_number, shift_number, check_number)
                            DO NOTHING
                        RETURNING id
                        """,
                        row["fns_id"], row["kkt_reg_id"], row["fiscal_drive_number"],
                        row["shift_number"], row["check_number"], row["fiscal_sign"],
                        row["document_type"], row["operation_type"], row["issued_at"],
                        row["date"], cashier_id, row["taxation_type"], row["is_marked"],
                        row["total_kop"], row["cash_kop"], row["ecash_kop"],
                        row["prepaid_kop"], row["credit_kop"], row["provision_kop"],
                        row["vat"], row["fns_code"], row["fns_errors"],
                        row["item_count"], row["raw"],
                    )

                    if receipt_id is None:
                        continue  # already loaded on an earlier run
                    inserted += 1

                    if not row["lines"]:
                        continue

                    item_rows = []
                    for line in row["lines"]:
                        item_id = await self._item_id(
                            conn, line["name_raw"], row["is_marked"]
                        )
                        item_rows.append((
                            receipt_id, line["line_no"], item_id,
                            line["quantity"], line["price_kop"], line["amount_kop"],
                        ))

                    await conn.executemany(
                        """
                        INSERT INTO ofd.receipt_items
                            (receipt_id, line_no, item_id, quantity, price_kop, amount_kop)
                        VALUES ($1,$2,$3,$4,$5,$6)
                        ON CONFLICT (receipt_id, line_no) DO NOTHING
                        """,
                        item_rows,
                    )

        return inserted


# ---------------------------------------------------------------------------
# Ingestion runs (observability only — never used to skip work)
# ---------------------------------------------------------------------------

@dataclass
class RunStats:
    pages_walked: int = 0
    documents_seen: int = 0
    receipts_new: int = 0


async def record_run(
    pool: asyncpg.Pool, mode: str, started_at: datetime, stats: RunStats,
    error: str | None = None,
) -> None:
    await pool.execute(
        """
        INSERT INTO ofd.ingest_runs
            (mode, started_at, finished_at, pages_walked, documents_seen, receipts_new, error)
        VALUES ($1, $2, now(), $3, $4, $5, $6)
        """,
        mode, started_at, stats.pages_walked, stats.documents_seen,
        stats.receipts_new, error,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

async def run_all(
    cfg: Config, writer: Writer, client: OfdClient,
    from_page: int | None = None, to_page: int | None = None,
) -> RunStats:
    """Full backfill/reconciliation: walk every page once, oldest-bound by
    totalCount. Idempotent inserts mean this doubles as a full reconciliation
    pass — safe, and cheap in DB terms, to re-run at any time."""
    stats = RunStats()

    first = from_page or 1
    total_count, docs = await client.fetch_page(first, cfg.page_size)
    log.info("all: totalCount=%s", total_count)

    last_page = to_page
    if last_page is None and total_count:
        last_page = first + (total_count + cfg.page_size - 1) // cfg.page_size - 1

    stats.pages_walked += 1
    if not docs:
        log.info("all: page %s empty; nothing to load", first)
        return stats

    stats.receipts_new += await writer.write_page(first, docs)
    stats.documents_seen += len(docs)

    page = first + 1
    batch = max(cfg.concurrency, 1)

    while last_page is None or page <= last_page:
        pages = list(range(page, min(page + batch, (last_page or page + batch) + 1)))
        if not pages:
            break

        results = await asyncio.gather(
            *(client.fetch_page(p, cfg.page_size) for p in pages),
            return_exceptions=True,
        )

        stop = False
        for page_number, result in zip(pages, results):
            if isinstance(result, Exception):
                log.error("all: page %s gave up: %s", page_number, result)
                continue

            _, page_docs = result
            stats.pages_walked += 1
            if not page_docs:
                log.info("all: page %s empty; end of data", page_number)
                stop = True
                break

            stats.receipts_new += await writer.write_page(page_number, page_docs)
            stats.documents_seen += len(page_docs)
            log.info(
                "all: page %s documents=%s new_total=%s seen_total=%s",
                page_number, len(page_docs), stats.receipts_new, stats.documents_seen,
            )

        if stop:
            break
        page += batch

    log.info(
        "all: finished pages=%s documents=%s new=%s",
        stats.pages_walked, stats.documents_seen, stats.receipts_new,
    )
    return stats


async def run_recent(cfg: Config, writer: Writer, client: OfdClient) -> RunStats:
    """Delta fetch: walk forward from page 1 (newest first) until enough
    consecutive pages contain nothing new. Cheap enough to run every 30 min.

    On a fresh/empty database this will walk the entire history, which is
    correct (there's nothing to consider "already seen" yet) but slow — run
    `all` once first to backfill before turning on the schedule."""
    stats = RunStats()
    consecutive_empty_new = 0
    page = 1

    while consecutive_empty_new < cfg.recent_stop_empty_pages:
        _, docs = await client.fetch_page(page, cfg.recent_page_size)
        stats.pages_walked += 1

        if not docs:
            log.info("recent: page %s empty; end of data", page)
            break

        new_inserted = await writer.write_page(page, docs)
        stats.documents_seen += len(docs)
        stats.receipts_new += new_inserted

        consecutive_empty_new = 0 if new_inserted else consecutive_empty_new + 1
        log.info(
            "recent: page %s documents=%s new=%s consecutive_empty=%s",
            page, len(docs), new_inserted, consecutive_empty_new,
        )
        page += 1

    log.info(
        "recent: finished pages=%s documents=%s new=%s",
        stats.pages_walked, stats.documents_seen, stats.receipts_new,
    )
    return stats


async def open_pool(cfg: Config) -> asyncpg.Pool:
    """Connect, turning the usual failures into an actionable message.

    Raises a plain RuntimeError (never sys.exit) so a transient outage stays
    catchable by `execute()` / the `serve` job wrappers instead of killing a
    long-running scheduler process."""
    log.info(
        "Connecting to postgres %s@%s:%s/%s",
        cfg.db_kwargs["user"], cfg.db_kwargs["host"],
        cfg.db_kwargs["port"], cfg.db_kwargs["database"],
    )
    try:
        return await asyncpg.create_pool(min_size=1, max_size=4, **cfg.db_kwargs)
    except OSError as exc:
        raise RuntimeError(f"Cannot reach database at {cfg.db_kwargs['host']}: {exc}") from exc
    except asyncpg.InvalidPasswordError as exc:
        raise RuntimeError(
            f"Password rejected for {cfg.db_kwargs['user']}@{cfg.db_kwargs['host']}"
        ) from exc
    except asyncpg.InvalidCatalogNameError as exc:
        raise RuntimeError(f"Database does not exist: {cfg.db_kwargs['database']}") from exc


RunFn = Callable[[Writer, OfdClient], Awaitable[RunStats]]


async def execute(cfg: Config, mode: str, run_fn: RunFn) -> RunStats:
    """Open a pool + HTTP client for one run, execute it, and always record
    the outcome to ofd.ingest_runs (success or failure) before closing.

    `pool` starts as None and open_pool() runs inside the try block so a
    connection failure is logged here (not silently dropped by a caller's
    bare except) and skips the record_run/pool.close() calls it can't do
    without a pool."""
    started_at = datetime.now(timezone.utc)
    pool: asyncpg.Pool | None = None
    try:
        pool = await open_pool(cfg)
        timeout = httpx.Timeout(cfg.request_timeout)
        async with httpx.AsyncClient(timeout=timeout) as http_client:
            ofd_client = OfdClient(cfg, http_client)
            writer = Writer(pool, cfg)
            await writer.warm_cache()
            stats = await run_fn(writer, ofd_client)

        await record_run(pool, mode, started_at, stats)
        return stats
    except Exception as exc:
        log.exception("%s: run failed", mode)
        if pool is not None:
            try:
                await record_run(pool, mode, started_at, RunStats(), error=str(exc)[:500])
            except Exception:
                log.exception("%s: failed to record the failed run", mode)
        raise
    finally:
        if pool is not None:
            await pool.close()


# ---------------------------------------------------------------------------
# Scheduler (Docker `serve` service)
# ---------------------------------------------------------------------------

def _cron_minutes(interval_minutes: int) -> str:
    return ",".join(str(m) for m in range(0, 60, interval_minutes))


def build_scheduler(cfg: Config) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    minute = _cron_minutes(cfg.schedule_interval_minutes)
    hour = f"{cfg.schedule_hour_start}-{cfg.schedule_hour_end}"

    async def recent_job() -> None:
        try:
            await execute(cfg, "recent", lambda w, c: run_recent(cfg, w, c))
        except Exception:
            pass  # already logged and recorded; keep the scheduler alive

    async def nightly_job() -> None:
        try:
            await execute(cfg, "all", lambda w, c: run_all(cfg, w, c))
        except Exception:
            pass

    scheduler.add_job(
        recent_job, trigger=CronTrigger(minute=minute, hour=hour),
        id="recent", replace_existing=True,
    )
    scheduler.add_job(
        nightly_job,
        trigger=CronTrigger(hour=cfg.nightly_reconcile_hour, minute=0),
        id="nightly_reconcile", replace_existing=True,
    )
    return scheduler


async def serve(cfg: Config) -> None:
    scheduler = build_scheduler(cfg)
    scheduler.start()
    log.info(
        "serve: scheduler started jobs=%s",
        [j.id for j in scheduler.get_jobs()],
    )
    try:
        await asyncio.Event().wait()  # run forever
    finally:
        scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Load Astral OFD receipts into PostgreSQL")
    sub = parser.add_subparsers(dest="command", required=True)

    p_all = sub.add_parser("all", help="full backfill / reconciliation (walks every page once)")
    p_all.add_argument("--from-page", type=int, default=None)
    p_all.add_argument("--to-page", type=int, default=None)

    sub.add_parser("recent", help="fetch only the newest not-yet-loaded receipts")
    sub.add_parser("serve", help="run the scheduler: `recent` on a schedule, nightly `all`")

    args = parser.parse_args()
    cfg = Config()

    setup_logging()
    logging.getLogger().setLevel(cfg.log_level)

    if args.command == "all":
        asyncio.run(execute(
            cfg, "all",
            lambda w, c: run_all(cfg, w, c, args.from_page, args.to_page),
        ))
    elif args.command == "recent":
        asyncio.run(execute(cfg, "recent", lambda w, c: run_recent(cfg, w, c)))
    elif args.command == "serve":
        try:
            asyncio.run(serve(cfg))
        except KeyboardInterrupt:
            log.info("serve: interrupted, shutting down")


if __name__ == "__main__":
    main()
