#!/usr/bin/env python3
"""
Load fiscal receipts from the Astral OFD API into PostgreSQL.

    python ofd_loader.py --init-schema      # create schema ofd (once)
    python ofd_loader.py                    # load everything
    python ofd_loader.py --from-page 120 --to-page 200
    python ofd_loader.py --resume           # skip pages already in ofd.load_log

Every write is idempotent, so re-running the same pages is safe and cheap.
All credentials live in .env; nothing sensitive is hard-coded here.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import socket
import sys
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp
import asyncpg
from dotenv import load_dotenv

log = logging.getLogger("ofd")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class Config:
    def __init__(self) -> None:
        load_dotenv()

        self.api_key: str = self._req("OFD_API_KEY")
        self.organization_id: str = self._req("OFD_ORGANIZATION_ID")
        self.db = self._db_config()

        self.base_url: str = os.getenv(
            "OFD_BASE_URL",
            "https://ofd.astralnalog.ru/api/v4.2/documents.tickets",
        )
        self.page_size: int = int(os.getenv("OFD_PAGE_SIZE", "1000"))
        self.first_page: int = int(os.getenv("OFD_FIRST_PAGE", "1"))
        self.concurrency: int = int(os.getenv("OFD_CONCURRENCY", "4"))
        self.request_timeout: int = int(os.getenv("OFD_REQUEST_TIMEOUT", "120"))
        self.max_retries: int = int(os.getenv("OFD_MAX_RETRIES", "5"))

        self.tz = ZoneInfo(os.getenv("OFD_TIMEZONE", "Europe/Saratov"))
        # Astral encodes local wall-clock time as a unix timestamp. Set this to
        # false only if you confirm the timestamps are genuine UTC instants.
        self.time_is_local: bool = _envbool("OFD_TIME_IS_LOCAL", True)

        self.log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()

    @staticmethod
    def _req(name: str) -> str:
        value = os.getenv(name)
        if not value:
            sys.exit(f"Missing required environment variable {name}. See .env.example")
        return value

    @staticmethod
    def _db_config() -> dict[str, Any]:
        """
        Build asyncpg connect kwargs.

        Discrete DB_* variables win over DATABASE_URL, because asyncpg splits a
        DSN at the FIRST '@'. A password containing '@' silently corrupts the
        hostname (postgres:p@ss@host -> host 'ss@host'), which surfaces much
        later as a confusing DNS failure. Discrete variables need no escaping.
        """
        host = os.getenv("DB_HOST")
        if host:
            return {
                "host": host,
                "port": int(os.getenv("DB_PORT", "5432")),
                "user": Config._req("DB_USER"),
                "password": os.getenv("DB_PASSWORD") or None,
                "database": Config._req("DB_NAME"),
                "ssl": os.getenv("DB_SSLMODE") or None,
            }

        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            sys.exit(
                "Set DB_HOST/DB_USER/DB_NAME (recommended) or DATABASE_URL. "
                "See .env.example"
            )
        return {"dsn": dsn}

    def db_target(self) -> str:
        """
        Describe the connection target for logs, without the password.

        For a DSN this deliberately splits at the FIRST '@', the way asyncpg
        does, so the logged host is the host asyncpg will really dial rather
        than the one urlparse would guess.
        """
        if "dsn" in self.db:
            rest = re.sub(r"^\w+://", "", self.db["dsn"])
            userinfo, _, hostpart = rest.partition("@")
            if not hostpart:                       # no credentials in the DSN
                userinfo, hostpart = "", rest
            user = userinfo.split(":", 1)[0] or "(default)"
            hostport, _, database = hostpart.partition("/")
            database = database.split("?", 1)[0]
            host, _, port = hostport.partition(":")
            return f"{user}@{host}:{port or 5432}/{database}"

        return (f"{self.db['user']}@{self.db['host']}:"
                f"{self.db['port']}/{self.db['database']}")

    def warn_on_dsn_password(self) -> None:
        """Flag a DSN whose password almost certainly breaks host parsing."""
        if "dsn" not in self.db:
            return
        rest = re.sub(r"^\w+://", "", self.db["dsn"])
        userinfo, _, hostpart = rest.partition("@")
        if "@" in hostpart and ":" in userinfo:
            log.warning(
                "DATABASE_URL contains more than one '@'. asyncpg splits at the "
                "first one, so part of your password is being read as the "
                "hostname. Use DB_HOST/DB_USER/DB_PASSWORD/DB_NAME, or "
                "percent-encode '@' as %40."
            )


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
    (r"рулет",                                   "cake",      "roll"),
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

class OfdClient:
    def __init__(self, cfg: Config, session: aiohttp.ClientSession) -> None:
        self.cfg = cfg
        self.session = session
        self._gate = asyncio.Semaphore(cfg.concurrency)

    async def fetch_page(self, page_number: int) -> tuple[int, list[dict[str, Any]]]:
        """Return (totalCount, documents) for one page, with retry/backoff."""
        params = {
            "api_key": self.cfg.api_key,
            "organizationId": self.cfg.organization_id,
            "pageNumber": page_number,
            "count": self.cfg.page_size,
        }

        delay = 2.0
        last_error: Exception | None = None

        for attempt in range(1, self.cfg.max_retries + 1):
            try:
                async with self._gate:
                    async with self.session.get(self.cfg.base_url, params=params) as resp:
                        if resp.status in (429, 500, 502, 503, 504):
                            raise aiohttp.ClientResponseError(
                                resp.request_info, resp.history,
                                status=resp.status, message=await resp.text(),
                            )
                        resp.raise_for_status()
                        payload = await resp.json()

                if not payload.get("ok", True):
                    raise RuntimeError(f"API returned ok=false: {payload}")

                result = payload.get("result") or {}
                return int(result.get("totalCount") or 0), list(result.get("documents") or [])

            except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as exc:
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

                await conn.execute(
                    """
                    INSERT INTO ofd.load_log
                        (organization_id, page_number, page_size,
                         documents_seen, receipts_new)
                    VALUES ($1,$2,$3,$4,$5)
                    ON CONFLICT (organization_id, page_number, page_size) DO UPDATE
                        SET documents_seen = EXCLUDED.documents_seen,
                            receipts_new   = ofd.load_log.receipts_new
                                             + EXCLUDED.receipts_new,
                            fetched_at     = now()
                    """,
                    self.cfg.organization_id, page_number,
                    self.cfg.page_size, len(docs), inserted,
                )

        return inserted


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

async def done_pages(pool: asyncpg.Pool, cfg: Config) -> set[int]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT page_number FROM ofd.load_log
            WHERE organization_id = $1 AND page_size = $2
            """,
            cfg.organization_id, cfg.page_size,
        )
    return {r["page_number"] for r in rows}


async def open_pool(cfg: Config) -> asyncpg.Pool:
    """Connect, turning the usual failures into an actionable message."""
    cfg.warn_on_dsn_password()
    target = cfg.db_target()
    log.info("Connecting to postgres %s", target)
    try:
        return await asyncpg.create_pool(min_size=1, max_size=4, **cfg.db)
    except socket.gaierror as exc:
        host = target.split("@", 1)[1].split(":", 1)[0]
        sys.exit(
            f"Cannot resolve database host {host!r} ({exc}).\n"
            "  - If your password contains '@', asyncpg splits the DSN at the\n"
            "    FIRST '@' and treats the rest as the hostname. Use the\n"
            "    DB_HOST/DB_USER/DB_PASSWORD/DB_NAME variables instead of\n"
            "    DATABASE_URL, or percent-encode the password (@ -> %40).\n"
            f"  - If {host!r} is a Docker service name, run inside the same\n"
            "    compose network or point DB_HOST at the published address.\n"
            "  - Otherwise check DNS: getent hosts " + host
        )
    except OSError as exc:
        sys.exit(f"Cannot reach database at {target}: {exc}")
    except asyncpg.InvalidPasswordError:
        sys.exit(f"Password rejected for {target}")
    except asyncpg.InvalidCatalogNameError:
        sys.exit(f"Database does not exist: {target}")


async def run(args: argparse.Namespace, cfg: Config) -> None:
    pool = await open_pool(cfg)
    try:
        if args.init_schema:
            ddl = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
            async with pool.acquire() as conn:
                await conn.execute(ddl)
            log.info("Schema ofd created or already present")

        writer = Writer(pool, cfg)
        await writer.warm_cache()

        skip = await done_pages(pool, cfg) if args.resume else set()
        if skip:
            log.info("Resume: skipping %s pages already loaded", len(skip))

        timeout = aiohttp.ClientTimeout(total=cfg.request_timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            client = OfdClient(cfg, session)

            first = args.from_page or cfg.first_page
            total_count, docs = await client.fetch_page(first)
            log.info("API reports totalCount=%s", total_count)

            last_page = args.to_page
            if last_page is None and total_count:
                last_page = (
                    first + (total_count + cfg.page_size - 1) // cfg.page_size - 1
                )

            new_total = 0
            if first in skip:
                log.info("Page %s already loaded; skipping write", first)
            else:
                new_total += await writer.write_page(first, docs)
            seen = len(docs)
            seen_ids = {d.get("FnsID") for d in docs}

            page = first + 1
            batch = max(cfg.concurrency, 1)

            while last_page is None or page <= last_page:
                pages = [
                    p for p in range(page, min(page + batch, (last_page or page + batch) + 1))
                    if p not in skip
                ]
                if not pages:
                    page += batch
                    continue

                results = await asyncio.gather(
                    *(client.fetch_page(p) for p in pages),
                    return_exceptions=True,
                )

                stop = False
                for page_number, result in zip(pages, results):
                    if isinstance(result, Exception):
                        log.error("Page %s gave up: %s", page_number, result)
                        continue

                    _, page_docs = result
                    if not page_docs:
                        log.info("Page %s empty; end of data", page_number)
                        stop = True
                        break

                    ids = {d.get("FnsID") for d in page_docs}
                    if ids and ids <= seen_ids:
                        log.warning(
                            "Page %s repeats documents already seen; stopping. "
                            "Check that pageNumber is 1-based for this API.",
                            page_number,
                        )
                        stop = True
                        break
                    seen_ids |= ids

                    new_total += await writer.write_page(page_number, page_docs)
                    seen += len(page_docs)
                    log.info(
                        "Page %s: %s documents, %s receipts total new, %s seen",
                        page_number, len(page_docs), new_total, seen,
                    )

                    if len(page_docs) < cfg.page_size:
                        log.info("Short page %s; end of data", page_number)
                        stop = True
                        break

                if stop:
                    break
                page += batch

            log.info("Finished: %s documents seen, %s new receipts stored",
                     seen, new_total)
    finally:
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Astral OFD receipts into PostgreSQL")
    parser.add_argument("--init-schema", action="store_true",
                        help="apply schema.sql before loading")
    parser.add_argument("--from-page", type=int, default=None)
    parser.add_argument("--to-page", type=int, default=None)
    parser.add_argument("--resume", action="store_true",
                        help="skip pages recorded in ofd.load_log")
    args = parser.parse_args()

    cfg = Config()
    logging.basicConfig(
        level=cfg.log_level,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        asyncio.run(run(args, cfg))
    except KeyboardInterrupt:
        log.info("Interrupted; already-written pages are safe to resume from")


if __name__ == "__main__":
    main()