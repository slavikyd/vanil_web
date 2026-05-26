from prometheus_client import Counter, Histogram

orders_created = Counter(
    'orders_created_total',
    'Total number of orders created',
    ['cashier_id', 'shop_id'],
)

orders_failed = Counter(
    'orders_failed_total',
    'Total number of failed order attempts',
    ['reason'],
)

cart_items_added = Counter(
    'cart_items_added_total',
    'Total number of items added to cart',
)

cart_cleared = Counter(
    'cart_cleared_total',
    'Total number of cart clears',
)

order_size = Histogram(
    'order_size_items',
    'Number of items per order',
    buckets=[1, 2, 3, 5, 10, 15, 20, 30, 50],
)