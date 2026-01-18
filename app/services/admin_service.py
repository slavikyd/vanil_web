import io
import uuid
from collections import defaultdict
from datetime import date, datetime
from io import BytesIO

import openpyxl
from openpyxl import Workbook

from app.infrastructure.uow import AsyncpgUnitOfWork


class AdminService:
    @staticmethod
    async def create_item(
        *, uow: AsyncpgUnitOfWork, name: str, price: float, ttl: int
    ) -> None:
        assert uow.items is not None
        await uow.items.create(name=name, price=price, ttl=ttl)

    @staticmethod
    async def delete_item(*, uow: AsyncpgUnitOfWork, item_id: uuid.UUID) -> None:
        assert uow.items is not None
        await uow.items.delete(item_id=item_id)

    @staticmethod
    async def list_items(*, uow: AsyncpgUnitOfWork) -> list[dict]:
        assert uow.items is not None
        return await uow.items.list_for_admin()

    @staticmethod
    async def toggle_items(
        *, uow: AsyncpgUnitOfWork, active_map: dict[uuid.UUID, bool]
    ) -> None:
        assert uow.items is not None
        for item_id, is_active in active_map.items():
            await uow.items.set_active(item_id=item_id, active=is_active)

    @staticmethod
    async def get_orders(
        *, uow: AsyncpgUnitOfWork, order_for: str | None, address: str | None
    ) -> dict:
        assert uow.orders is not None

        order_for_date: date | None = None
        if order_for:
            try:
                order_for_date = datetime.strptime(order_for, "%Y-%m-%d").date()
            except ValueError:
                order_for_date = None

        rows = await uow.orders.admin_rows(order_for=order_for_date, address=address)

        grouped: dict = {}
        for r in rows:
            d = r["order_for"]
            oid = r["order_id"]
            grouped.setdefault(d, {}).setdefault(
                oid,
                {
                    "id": oid,
                    "created": r["created"],
                    "address": r["address"],
                    "cashier_name": r["cashier_name"],
                    "items": [],
                },
            )["items"].append({"name": r["item_name"], "quantity": r["quantity"]})

        return grouped

    @staticmethod
    async def delete_order(*, uow: AsyncpgUnitOfWork, order_id: uuid.UUID) -> bool:
        assert uow.orders is not None
        return await uow.orders.delete_order(order_id=order_id)

    @staticmethod
    async def export_orders(
        *, uow: AsyncpgUnitOfWork, address: str | None
    ) -> io.BytesIO:
        assert uow.orders is not None

        orders = await uow.orders.export_orders_list(address=address)

        wb = Workbook()
        wb.remove(wb.active)

        sheets = {}
        for o in orders:
            addr = o["address"] or "Unknown"
            name = addr[:31]
            ws = sheets.setdefault(name, wb.create_sheet(title=name))
            if ws.max_row == 1:
                ws.append(
                    [
                        "Order ID",
                        "Created",
                        "Address",
                        "Cashier",
                        "Item",
                        "Qty",
                        "Price",
                    ]
                )

            items = await uow.orders.export_order_items(order_id=uuid.UUID(o["id"]))
            for it in items:
                ws.append(
                    [
                        o["id"],
                        o["created"].strftime("%Y-%m-%d %H:%M:%S"),
                        o["address"],
                        o["cashier_name"],
                        it["name"],
                        it["quantity"],
                        float(it["price"]),
                    ]
                )

        stream = io.BytesIO()
        wb.save(stream)
        stream.seek(0)
        return stream

    @staticmethod
    async def export_by_address(*, uow: AsyncpgUnitOfWork, order_for: date) -> BytesIO:
        assert uow.orders is not None

        rows = await uow.orders.export_by_address_rows(order_for=order_for)

        wb = openpyxl.Workbook()
        wb.remove(wb.active)

        grouped = defaultdict(list)
        for r in rows:
            grouped[r["address"]].append((r["name"], r["quantity"]))

        for addr, items in grouped.items():
            ws = wb.create_sheet(title=(addr or "Unknown")[:31])
            ws.append(["Item", "Quantity"])
            for n, q in items:
                ws.append([n, q])

        output = BytesIO()
        wb.save(output)
        output.seek(0)
        return output
