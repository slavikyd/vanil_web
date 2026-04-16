from datetime import date, datetime
from typing import Any

from django.contrib import admin
from django.db.models import Prefetch
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import re_path
from django.utils import timezone
from django.utils.dateparse import parse_date

from .models import *
from openpyxl import Workbook

def _admin_or_redirect(request: HttpRequest, *, expects_json: bool) -> HttpResponse | None:
    """
    Mirror the spec behavior:
    - HTML: redirect to '/' if not admin
    - JSON: 403 {"error":"forbidden"} if not admin
    """
    if not request.user.is_authenticated:
        if expects_json:
            return JsonResponse({"error": "forbidden"}, status=403)
        return redirect("/")
    if not request.user.is_staff:
        if expects_json:
            return JsonResponse({"error": "forbidden"}, status=403)
        return redirect("/")
    return None


def _orders_payload(*, max_days: int | None, offset_days: int) -> dict[str, Any]:
    """
    Build payload compatible with LIVE_ADMIN_PAGE_SPEC.md.
    max_days:
      - live page: 5
      - archive: None (all), but offset_days=5 to skip newest 5
    """
    all_item_names = list(
        Items.objects.order_by("name").values_list("name", flat=True)
    )
    all_item_names = [n for n in all_item_names if n]  # drop null/empty

    orders_qs = (
        Orders.objects.select_related("cashier", "shop")
        .order_by("-order_for", "-created")
    )

    # Prefetch order items + item in one go.
    order_items = (
        OrdersItems.objects.select_related("item")
        .only("order_id", "item_id", "quantity", "item__name")
    )
    orders_qs = orders_qs.prefetch_related(Prefetch("ordersitems_set", queryset=order_items))

    # Group by day.
    grouped: dict[date, list[Orders]] = {}
    for o in orders_qs:
        grouped.setdefault(o.order_for, []).append(o)

    today = timezone.localdate()
    days_sorted = sorted(grouped.keys(), reverse=True)

    days_sorted = days_sorted[offset_days:]
    if max_days is not None:
        days_sorted = days_sorted[:max_days]

    days_payload: list[dict[str, Any]] = []
    for d in days_sorted:
        day_orders = sorted(
            grouped.get(d, []),
            key=lambda x: (x.created or datetime.min.replace(tzinfo=timezone.UTC)),
            reverse=True,
        )

        totals: dict[str, int] = {name: 0 for name in all_item_names}
        shops_map: dict[str, list[Orders]] = {}

        for o in day_orders:
            shop_key = (o.address or getattr(o, "shop_id", None) or "Unknown shop")
            shops_map.setdefault(shop_key, []).append(o)

            for oi in getattr(o, "ordersitems_set").all():
                item_name = getattr(oi.item, "name", None)
                if not item_name:
                    continue
                qty = oi.quantity or 0
                totals[item_name] = totals.get(item_name, 0) + int(qty)

        totals_list = [{"name": n, "quantity": totals.get(n, 0)} for n in sorted(totals.keys())]

        shops_payload = []
        for shop_key in sorted(shops_map.keys()):
            shop_orders = sorted(
                shops_map[shop_key],
                key=lambda x: (x.created or datetime.min.replace(tzinfo=timezone.UTC)),
                reverse=True,
            )
            orders_payload = []
            for o in shop_orders:
                created = o.created
                created_iso = created.isoformat() if created else None
                created_hhmm = created.strftime("%H:%M:%S") if created else ""

                items_payload = []
                for oi in getattr(o, "ordersitems_set").all():
                    item_name = getattr(oi.item, "name", None)
                    if not item_name:
                        continue
                    items_payload.append({"name": item_name, "quantity": int(oi.quantity or 0)})

                orders_payload.append(
                    {
                        "id": str(o.id),
                        "created": created_iso,
                        "created_hhmm": created_hhmm,
                        "address": o.address,
                        "cashier_name": getattr(o.cashier, "full_name", "") if o.cashier_id else "",
                        "shop_id": getattr(o, "shop_id", None),
                        "items": items_payload,
                    }
                )

            shops_payload.append({"shop": shop_key, "orders": orders_payload})

        days_payload.append(
            {
                "date": d.isoformat(),
                "is_today": d == today,
                "total_orders": len(day_orders),
                "totals": totals_list,
                "shops": shops_payload,
            }
        )

    return {
        "generated_at": timezone.now().astimezone(timezone.UTC).isoformat(),
        "days": days_payload,
    }


def admin_orders_live(request: HttpRequest) -> HttpResponse:
    denied = _admin_or_redirect(request, expects_json=False)
    if denied:
        return denied
    ctx = {
        **admin.site.each_context(request),
        "title": "Админ - Живые заявки",
        "data_url": "/admin/orders/data",
        "archive_url": "/admin/orders/archive",
        "normal_orders_url": "/admin/core/orders/",
        "home_url": "/",
        "page_heading": "Живые заявки",
        "archive_heading": "Архив (старше 5 дней)",
        "show_archive_link": True,
        "show_live_link": False,
    }
    return render(request, "admin/orders/live.html", ctx)


def admin_orders_live_data(request: HttpRequest) -> JsonResponse:
    denied = _admin_or_redirect(request, expects_json=True)
    if denied:
        return denied  # type: ignore[return-value]
    payload = _orders_payload(max_days=5, offset_days=0)
    return JsonResponse(payload)


def admin_orders_live_archive(request: HttpRequest) -> HttpResponse:
    denied = _admin_or_redirect(request, expects_json=False)
    if denied:
        return denied
    ctx = {
        **admin.site.each_context(request),
        "title": "Админ - Живые заявки (архив)",
        "data_url": "/admin/orders/archive/data",
        "archive_url": "/admin/orders/archive",
        "live_url": "/admin/orders",
        "normal_orders_url": "/admin/core/orders/",
        "home_url": "/",
        "page_heading": "Архив (старше 5 дней)",
        "show_archive_link": False,
        "show_live_link": True,
    }
    return render(request, "admin/orders/archive.html", ctx)


def admin_orders_live_archive_data(request: HttpRequest) -> JsonResponse:
    denied = _admin_or_redirect(request, expects_json=True)
    if denied:
        return denied  # type: ignore[return-value]
    payload = _orders_payload(max_days=None, offset_days=5)
    return JsonResponse(payload)


def admin_orders_live_export_totals(request: HttpRequest) -> HttpResponse:
    denied = _admin_or_redirect(request, expects_json=False)
    if denied:
        return denied

    order_for = parse_date(request.GET.get("order_for") or "")
    if not order_for:
        return HttpResponse("Missing or invalid 'order_for' (expected YYYY-MM-DD).", status=400)



    all_item_names = list(Items.objects.order_by("name").values_list("name", flat=True))
    all_item_names = [n for n in all_item_names if n]

    totals: dict[str, int] = {name: 0 for name in all_item_names}
    order_items_qs = (
        OrdersItems.objects.select_related("item", "order")
        .filter(order__order_for=order_for)
        .only("order_id", "item_id", "quantity", "item__name")
    )
    for oi in order_items_qs:
        name = getattr(oi.item, "name", None)
        if not name:
            continue
        totals[name] = totals.get(name, 0) + int(oi.quantity or 0)

    wb = Workbook()
    ws = wb.active
    ws.title = f"Totals {order_for.isoformat()}"
    ws.append(["Item", "Ordered quantity"])
    for name in sorted(totals.keys()):
        ws.append([name, totals.get(name, 0)])

    from io import BytesIO

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"live_totals_{order_for.isoformat()}.xlsx"
    resp = HttpResponse(
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


def _install_admin_urls() -> None:
    get_urls = admin.site.get_urls

    def custom_get_urls():
        urls = get_urls()
        custom = [
            # Accept both with and without trailing slash.
            re_path(r"^orders/?$", admin_orders_live),
            re_path(r"^orders/data/?$", admin_orders_live_data),
            re_path(r"^orders/archive/?$", admin_orders_live_archive),
            re_path(r"^orders/archive/data/?$", admin_orders_live_archive_data),
            re_path(r"^orders/export/totals/?$", admin_orders_live_export_totals),
        ]
        return custom + urls

    admin.site.get_urls = custom_get_urls  # type: ignore[method-assign]


_install_admin_urls()


# Register your models here.
@admin.register(Cashiers)
class CashiersAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Cashiers._meta.fields]


@admin.register(Categories)
class CategoriesAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Categories._meta.fields]


@admin.register(Items)
class ItemsAdmin(admin.ModelAdmin):
    list_display = ["name", "active", "category"]
    list_editable = ["active", "category"]


@admin.register(Orders)
class OrdersAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Orders._meta.fields]

# OrdersItems uses a composite primary key; Django admin does not support that yet.

@admin.register(Shops)
class ShopsAdmin(admin.ModelAdmin):
    pass

