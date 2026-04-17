from datetime import date, datetime
from io import BytesIO
from typing import Any

from django.contrib import admin
from django.db.models import Prefetch
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.response import TemplateResponse
from django.urls import path, re_path
from django.utils import timezone
from django.utils.dateparse import parse_date

from .models import *
from openpyxl import Workbook



def _orders_payload(*, max_days: int | None, offset_days: int) -> dict[str, Any]:
    """
    Builds the full data payload for both live and archive views.

    max_days=5, offset_days=0  → newest 5 days  (live page)
    max_days=None, offset_days=5 → everything older (archive)
    """
    all_item_names = list(
        Items.objects.order_by("name").values_list("name", flat=True)
    )
    all_item_names = [n for n in all_item_names if n]

    # Single DB round-trip: orders + their items + shop + cashier
    order_items_prefetch = (
        OrdersItems.objects
        .select_related("item")
        .only("order_id", "item_id", "quantity", "item__name")
    )
    orders_qs = (
        Orders.objects
        .select_related("cashier", "shop")
        .order_by("-order_for", "-created")
        .prefetch_related(Prefetch("ordersitems_set", queryset=order_items_prefetch))
    )

    # Group orders by their delivery date
    grouped: dict[date, list] = {}
    for o in orders_qs:
        grouped.setdefault(o.order_for, []).append(o)

    today = timezone.localdate()
    days_sorted = sorted(grouped.keys(), reverse=True)[offset_days:]
    if max_days is not None:
        days_sorted = days_sorted[:max_days]

    days_payload = []
    for d in days_sorted:
        day_orders = sorted(
            grouped.get(d, []),
            key=lambda x: (x.created or datetime.min.replace(tzinfo=timezone.UTC)),
            reverse=True,
        )

        # Sum quantities per item across all orders for this day
        totals: dict[str, int] = {name: 0 for name in all_item_names}
        shops_map: dict[str, list] = {}

        for o in day_orders:
            shop_key = o.address or getattr(o, "shop_id", None) or "Unknown shop"
            shops_map.setdefault(shop_key, []).append(o)

            for oi in o.ordersitems_set.all():
                name = getattr(oi.item, "name", None)
                if name:
                    totals[name] = totals.get(name, 0) + int(oi.quantity or 0)

        totals_list = [
            {"name": n, "quantity": totals.get(n, 0)}
            for n in sorted(totals.keys())
        ]

        shops_payload = []
        for shop_key in sorted(shops_map.keys()):
            shop_orders = sorted(
                shops_map[shop_key],
                key=lambda x: (x.created or datetime.min.replace(tzinfo=timezone.UTC)),
                reverse=True,
            )
            orders_payload = []
            for o in shop_orders:
                items_payload = [
                    {"name": oi.item.name, "quantity": int(oi.quantity or 0)}
                    for oi in o.ordersitems_set.all()
                    if getattr(oi.item, "name", None)
                ]
                orders_payload.append({
                    "id": str(o.id),
                    "created": o.created.isoformat() if o.created else None,
                    "created_hhmm": o.created.strftime("%H:%M:%S") if o.created else "",
                    "address": o.address,
                    "cashier_name": getattr(o.cashier, "full_name", "") if o.cashier_id else "",
                    "shop_id": getattr(o, "shop_id", None),
                    "items": items_payload,
                })
            shops_payload.append({"shop": shop_key, "orders": orders_payload})

        days_payload.append({
            "date": d.isoformat(),
            "is_today": d == today,
            "total_orders": len(day_orders),
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