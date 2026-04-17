from datetime import date, datetime
from io import BytesIO
from typing import Any

from django.contrib import admin
from django.db.models import Prefetch, Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.response import TemplateResponse
from django.urls import path, re_path
from django.utils import timezone
from django.utils.dateparse import parse_date

from .models import *
from openpyxl import Workbook



def _orders_payload(*, max_days: int | None, offset_days: int) -> dict[str, Any]:
    today = timezone.localdate()

    # Step 1: fetch only the distinct dates we care about — tiny query, just dates
    dates_qs = (
        Orders.objects
        .values_list("order_for", flat=True)
        .distinct()
        .order_by("-order_for")
    )
    # Queryset slicing = LIMIT/OFFSET in SQL, no Python filtering
    if max_days is not None:
        dates_qs = dates_qs[offset_days:offset_days + max_days]
    else:
        dates_qs = dates_qs[offset_days:]

    date_range = list(dates_qs)
    if not date_range:
        return {"generated_at": timezone.now().isoformat(), "days": []}

    # Step 2: fetch only order items within those dates, DB does the aggregation
    rows = (
        OrdersItems.objects
        .filter(order__order_for__in=date_range)
        .select_related("item", "order", "order__cashier", "order__shop")
        .values(
            "order__order_for",
            "order__id",
            "order__address",
            "order__created",
            "order__cashier__full_name",
            "order__shop_id",
            "item__name",
        )
        .annotate(total_qty=Sum("quantity"))
        .order_by("order__order_for", "order__id")
    )

    # Step 3: group results in Python — but only the rows we actually fetched
    grouped: dict[date, dict] = {}
    for row in rows:
        d = row["order__order_for"]
        order_id = row["order__id"]

        if d not in grouped:
            grouped[d] = {"totals": {}, "orders": {}}

        # Accumulate totals per item for this day
        name = row["item__name"]
        if name:
            grouped[d]["totals"][name] = grouped[d]["totals"].get(name, 0) + row["total_qty"]

        # Accumulate per-order item list for the shops breakdown
        if order_id not in grouped[d]["orders"]:
            grouped[d]["orders"][order_id] = {
                "id": str(order_id),
                "address": row["order__address"],
                "created": row["order__created"],
                "cashier_name": row["order__cashier__full_name"] or "",
                "shop_id": row["order__shop_id"],
                "items": [],
            }
        if name:
            grouped[d]["orders"][order_id]["items"].append({
                "name": name,
                "quantity": row["total_qty"],
            })

    # Step 4: shape into the final payload your frontend expects
    days_payload = []
    for d in sorted(grouped.keys(), reverse=True):
        day = grouped[d]

        totals_list = [
            {"name": n, "quantity": q}
            for n, q in sorted(day["totals"].items())
        ]

        # Group orders by shop/address for the "По магазинам" tab
        shops_map: dict[str, list] = {}
        for order in day["orders"].values():
            shop_key = order["address"] or order["shop_id"] or "Unknown shop"
            shops_map.setdefault(shop_key, []).append(order)

        shops_payload = [
            {"shop": shop_key, "orders": orders}
            for shop_key, orders in sorted(shops_map.items())
        ]

        days_payload.append({
            "date": d.isoformat(),
            "is_today": d == today,
            "total_orders": len(day["orders"]),
            "totals": totals_list,
            "shops": shops_payload,
        })

    return {
        "generated_at": timezone.now().isoformat(),
        "days": days_payload,
    }


@admin.register(Orders)
class OrdersAdmin(admin.ModelAdmin):
    # Replaces the default changelist with your live orders page
    change_list_template = "admin/orders/live.html"

    def get_urls(self):
        """
        Proper way to add custom URLs — no monkey-patching.
        self.admin_site.admin_view() wraps each view with:
          - login_required
          - staff_required
          - CSRF protection
        So you don't need _admin_or_redirect anymore.
        """
        urls = super().get_urls()
        custom = [
            path("live-data/",
                 self.admin_site.admin_view(self.live_data_view),
                 name="orders_live_data"),

            path("archive/",
                 self.admin_site.admin_view(self.archive_view),
                 name="orders_archive"),

            path("archive/data/",
                 self.admin_site.admin_view(self.archive_data_view),
                 name="orders_archive_data"),

            path("export/totals/",
                 self.admin_site.admin_view(self.export_totals_view),
                 name="orders_export_totals"),
        ]
        # custom must come BEFORE urls — Django matches first URL that fits
        return custom + urls

    def changelist_view(self, request, extra_context=None):
        """
        This IS the Orders list page in admin (/admin/core/orders/).
        We override it to render your live orders template instead
        of the default table of Order rows.
        """
        ctx = {
            **self.admin_site.each_context(request),  # user, site_title, etc.
            "title": "Живые заявки",
            # URLs are now proper named reverses — no hardcoded strings
            "data_url": "live-data/",
            "archive_url": "archive/",
            "export_url": "export/totals/",
            "opts": self.model._meta,  # needed for breadcrumbs to work
            **(extra_context or {}),
        }
        return TemplateResponse(request, "admin/orders/live.html", ctx)

    def live_data_view(self, request: HttpRequest) -> JsonResponse:
        """Returns JSON for the live page (newest 5 days)."""
        payload = _orders_payload(max_days=5, offset_days=0)
        return JsonResponse(payload)

    def archive_view(self, request: HttpRequest) -> HttpResponse:
        """Renders the archive HTML page (orders older than 5 days)."""
        ctx = {
            **self.admin_site.each_context(request),
            "title": "Архив заявок",
            "data_url": "data/",
            "live_url": "../",  # back to changelist
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/orders/archive.html", ctx)

    def archive_data_view(self, request: HttpRequest) -> JsonResponse:
        """Returns JSON for the archive page (everything older than 5 days)."""
        payload = _orders_payload(max_days=None, offset_days=5)
        return JsonResponse(payload)

    def export_totals_view(self, request: HttpRequest) -> HttpResponse:
        """
        Returns an .xlsx file for a given date.
        Expects ?order_for=YYYY-MM-DD in the query string.
        """
        order_for = parse_date(request.GET.get("order_for") or "")
        if not order_for:
            return HttpResponse("Missing ?order_for=YYYY-MM-DD", status=400)

        all_item_names = list(
            Items.objects.order_by("name").values_list("name", flat=True)
        )
        totals: dict[str, int] = {n: 0 for n in all_item_names if n}

        for oi in (OrdersItems.objects
                   .select_related("item")
                   .filter(order__order_for=order_for)
                   .only("quantity", "item__name")):
            name = getattr(oi.item, "name", None)
            if name:
                totals[name] = totals.get(name, 0) + int(oi.quantity or 0)

        wb = Workbook()
        ws = wb.active
        ws.title = f"Totals {order_for}"
        ws.append(["Item", "Ordered quantity"])
        for name in sorted(totals):
            ws.append([name, totals[name]])

        buf = BytesIO()
        wb.save(buf)

        resp = HttpResponse(
            buf.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = f'attachment; filename="totals_{order_for}.xlsx"'
        return resp



@admin.register(Cashiers)
class CashiersAdmin(admin.ModelAdmin):
    list_display = [f.name for f in Cashiers._meta.fields]

@admin.register(Categories)
class CategoriesAdmin(admin.ModelAdmin):
    list_display = [f.name for f in Categories._meta.fields]

@admin.register(Items)
class ItemsAdmin(admin.ModelAdmin):
    list_display = ["name", "active", "category"]
    list_editable = ["active", "category"]

@admin.register(Shops)
class ShopsAdmin(admin.ModelAdmin):
    pass